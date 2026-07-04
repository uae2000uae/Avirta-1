"""
AI Question Generator Module for Question Management

This module provides functionality for generating questions using AI services.
It supports generating multiple types of questions (multiple choice, true/false, text)
with customizable options.
"""

import json
import uuid
import os
import re
import threading
from datetime import datetime
import requests
from questionmanagement.question_bank import question_bank


# ------------------------- Generation progress tracking -------------------------
# Thread-safe progress slot the AI Generator UI polls while questions are being
# generated. Mirrors the polling pattern used by git_push_helper.py. This is a
# single-admin tool, so a single module-level slot is sufficient.
_gen_progress_lock = threading.Lock()
_gen_progress = {
    "status": "idle",     # idle | running | success | failed
    "percent": 0,
    "message": "",
    "generated": 0,
    "total": 0,
    "batch_id": None,
    "error": None,
}


def reset_generation_progress(total: int = 0):
    """Reset the progress slot to a fresh running state."""
    with _gen_progress_lock:
        _gen_progress.update({
            "status": "running",
            "percent": 0,
            "message": "Starting…",
            "generated": 0,
            "total": int(total or 0),
            "batch_id": None,
            "error": None,
        })


def _set_generation_progress(**kwargs):
    """Update the progress slot in a thread-safe manner."""
    with _gen_progress_lock:
        _gen_progress.update(kwargs)


def get_generation_progress() -> dict:
    """Return a copy of the current generation progress."""
    with _gen_progress_lock:
        return dict(_gen_progress)


def _normalize_question_text(text: str) -> str:
    """Normalize question text for robust duplicate detection.

    - Lowercase
    - Strip leading/trailing whitespace
    - Collapse internal whitespace to single spaces
    - Remove Arabic diacritics/harakat and tatweel
    - Remove common punctuation (including Arabic punctuation)
    - Normalize various dash/quote characters
    """
    try:
        if text is None:
            return ""
        s = str(text)
        # Lowercase
        s = s.lower()
        # Remove Arabic diacritics and tatweel
        # Ranges: \u0610-\u061A, \u064B-\u065F, \u0670, \u06D6-\u06ED, tatweel \u0640
        s = re.sub(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED\u0640]", "", s)
        # Normalize various alef forms to bare alef
        s = s.replace("\u0622", "\u0627").replace("\u0623", "\u0627").replace("\u0625", "\u0627").replace("\u0671", "\u0627")
        # Normalize yaa alif maqsura to yaa
        s = s.replace("\u0649", "\u064a")
        # Unify quotes and dashes
        for ch in ["\u2018", "\u2019", "\u201C", "\u201D", "\u00AB", "\u00BB", "\u2032", "\u2033", "'", '"']:
            s = s.replace(ch, " ")
        for ch in ["\u2013", "\u2014", "-", "–", "—"]:
            s = s.replace(ch, " ")
        # Remove punctuation including Arabic question/comma marks
        s = re.sub(r"[\.,!?؛،:؛\(\)\[\]\{\}<>/~`@#$%^&*_+=|\\]", " ", s)
        # Collapse whitespace to single spaces
        s = re.sub(r"\s+", " ", s).strip()
        return s
    except Exception:
        try:
            return str(text).strip().lower()
        except Exception:
            return ""


def _post_with_retries(url: str, headers: dict, json_data: dict, timeout: float, max_retries: int = 2, backoff: float = 1.5):
    """POST with limited retries for transient network errors/timeouts.

    Retries on:
    - requests.exceptions.Timeout / RequestException with timeout in message
    - HTTP 502/503/504 from server

    Increases timeout each retry up to 300s and applies exponential backoff between attempts.
    Returns the final requests.Response on success; raises RequestException on failure.
    """
    import time as _time
    last_err = None
    t = float(timeout or 60)
    attempts = max(1, int(max_retries) + 1)
    for attempt in range(1, attempts + 1):
        try:
            resp = requests.post(url, headers=headers, json=json_data, timeout=t)
            # Retry on transient 5xx
            if resp.status_code in (502, 503, 504):
                last_err = requests.exceptions.RequestException(
                    f"Transient server error {resp.status_code}: {resp.text[:200]}"
                )
                print(f"OpenAI request attempt {attempt}/{attempts} got {resp.status_code}; retrying...")
            else:
                return resp
        except requests.exceptions.Timeout as e:
            last_err = e
            print(f"OpenAI request timed out after {t}s on attempt {attempt}/{attempts}; retrying...")
        except requests.exceptions.RequestException as e:
            # Network hiccup: retry; otherwise break if last attempt
            last_err = e
            msg = str(e).lower()
            if "timeout" in msg or "temporarily" in msg or "connection aborted" in msg:
                print(f"OpenAI request network error on attempt {attempt}/{attempts}; retrying...")
            else:
                # Non-retriable client-side error; raise immediately
                raise
        # If we will retry
        if attempt < attempts:
            _time.sleep(min(2.0 * (backoff ** (attempt - 1)), 8.0))
            t = min(300.0, t * backoff)
        else:
            break
    # Exhausted retries
    hint = " Consider increasing the Openai Request Timeout in Admin settings and try again."
    raise requests.exceptions.RequestException(f"OpenAI request failed after retries: {last_err}{hint}")


# ------------------------- RAG / difficulty / validation helpers -------------------------
# These implement the source-grounded, points-based-difficulty, AI-validated flow
# described in questionmanagement/AI_generator.txt. They are kept additive: the
# generated/saved JSON structure consumed by the app is unchanged.

# 5-level difficulty system. Points double as the difficulty signal: higher points
# means a harder / less common question.
DIFFICULTY_LEVELS = {
    100: "Very easy: direct recall of a basic, well-known fact. No reasoning required.",
    200: "Easy: simple recognition or a one-step factual question; slightly less obvious than 100.",
    300: "Medium: requires connecting two facts or understanding context.",
    400: "Hard: requires comparison, chronology, classification, or cause/effect reasoning.",
    500: "Very hard: requires deeper reasoning, multi-step deduction, or less obvious facts.",
}

# Baseline shape used to spread a "mixed" batch evenly across the five levels.
DEFAULT_DISTRIBUTION = {100: 2, 200: 2, 300: 2, 400: 2, 500: 2}

# Map the admin difficulty labels to point values (shared by generation + validation).
DIFFICULTY_TO_POINTS = {"easiest": 100, "easy": 200, "medium": 300, "hard": 400, "hardest": 500}

# Grounding mode. When False (default), retrieved facts are treated as OPTIONAL
# supporting context: the model may also use reliable general knowledge to stay
# on-topic and reach the requested count. When True, generation is hard-limited
# to the retrieved facts (one question per fact, source fields required) - which
# produces off-topic/too-few questions whenever retrieval is weak, so it is off.
ENFORCE_STRICT_GROUNDING = False


def fetch_wikipedia_summary(topic: str, lang: str = "en") -> dict:
    """Fetch a short encyclopedic summary from Wikipedia (best-effort).

    Returns an empty dict on any failure (missing page, network error, timeout)
    so callers can degrade gracefully to ungrounded generation.
    """
    try:
        topic = (topic or "").strip()
        if not topic:
            return {}
        lang = (lang or "en").strip().lower() or "en"
        safe_topic = topic.replace(" ", "_")
        url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{safe_topic}"
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "AvirtaTriviaQuestionGenerator/1.0"},
        )
        if response.status_code != 200:
            return {}
        data = response.json()
        extract = data.get("extract", "")
        if not extract:
            return {}
        return {
            "source_name": "Wikipedia",
            "source_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
            "title": data.get("title", topic),
            "extract": extract,
        }
    except Exception as e:
        print(f"Wikipedia summary fetch failed for '{topic}' ({lang}): {e}")
        return {}


def search_wikipedia_pages(topic: str, lang: str = "en", limit: int = 10) -> list:
    """Return titles of pages related to ``topic`` via the MediaWiki search API.

    Best-effort: returns an empty list on any failure so callers can degrade to
    a single-page lookup or to ungrounded generation.
    """
    try:
        topic = (topic or "").strip()
        if not topic:
            return []
        lang = (lang or "en").strip().lower() or "en"
        url = f"https://{lang}.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": topic,
            "format": "json",
            "srlimit": max(1, int(limit or 10)),
        }
        response = requests.get(
            url,
            params=params,
            timeout=20,
            headers={"User-Agent": "AvirtaTriviaQuestionGenerator/1.0"},
        )
        if response.status_code != 200:
            return []
        data = response.json()
        return [item.get("title", "") for item in data.get("query", {}).get("search", []) if item.get("title")]
    except Exception as e:
        print(f"Wikipedia page search failed for '{topic}' ({lang}): {e}")
        return []


def retrieve_multiple_wikipedia_sources(topic: str, lang: str = "en", limit: int = 10) -> list:
    """Retrieve several related Wikipedia page summaries to build a fact pool.

    A single short summary rarely yields enough diverse facts for many questions,
    so we search for related pages and fetch a summary for each. Returns a list of
    source dicts: ``{source, title, url, text, retrieved_at}``. Best-effort and
    de-duplicated by title; may be empty (then generation falls back to general
    knowledge).
    """
    now = datetime.now().isoformat()
    sources = []
    seen_titles = set()

    # Candidate titles: the topic itself first, then related search hits.
    titles = [topic] + search_wikipedia_pages(topic, lang=lang, limit=limit)

    for title in titles:
        key = (title or "").strip().lower()
        if not key or key in seen_titles:
            continue
        seen_titles.add(key)

        wiki = fetch_wikipedia_summary(title, lang=lang)
        if wiki.get("extract"):
            sources.append({
                "source": wiki.get("source_name", "Wikipedia"),
                "title": wiki.get("title", title),
                "url": wiki.get("source_url", ""),
                "text": wiki.get("extract", ""),
                "retrieved_at": now,
            })
        # Stop once we have enough distinct sources.
        if len(sources) >= max(1, int(limit or 10)):
            break

    return sources


def split_sources_into_facts(sources: list) -> list:
    """Split source extracts into individual sentence-level facts with IDs.

    Each fact carries a unique ``fact_id`` so the generator can cite it and the
    backend can reject repeated facts across a batch and across batches. Very
    short fragments (< 50 chars) are dropped as unlikely to be self-contained.
    """
    facts = []
    for source in sources or []:
        text = source.get("extract") or source.get("text") or ""
        if not text:
            continue
        for sentence in re.split(r"(?<=[.!?])\s+", text):
            sentence = (sentence or "").strip()
            if len(sentence) < 50:
                continue
            facts.append({
                "fact_id": str(uuid.uuid4()),
                "fact": sentence,
                "source_title": source.get("title", ""),
                "source_url": source.get("url", "") or source.get("source_url", ""),
                "retrieved_at": source.get("retrieved_at", datetime.now().isoformat()),
            })
    return facts


def build_source_facts(topic: str, lang: str = "en", limit: int = 10) -> dict:
    """Build a best-effort, multi-source fact pool for grounding generation.

    Retrieves several related Wikipedia pages, splits them into sentence-level
    facts (each with a ``fact_id``), and returns both the raw ``sources`` and the
    ``facts`` pool. An empty ``facts`` list is allowed; generation then falls back
    to general knowledge. Can be extended later with Wikidata/DBpedia/Open Trivia DB.
    """
    sources = retrieve_multiple_wikipedia_sources(topic, lang=lang, limit=limit)
    facts = split_sources_into_facts(sources)
    return {
        "topic": topic,
        "language": lang,
        "retrieved_at": datetime.now().isoformat(),
        "sources": sources,
        "facts": facts,
    }


def build_difficulty_distribution(num_questions: int, difficulty: str = "mixed") -> dict:
    """Return a target points distribution for a batch of ``num_questions``.

    - For a specific difficulty, all questions land on the mapped point value.
    - For ``mixed``, spread as evenly as possible across the five levels,
      distributing any remainder from the easiest level upward.
    """
    levels = [100, 200, 300, 400, 500]
    dist = {str(p): 0 for p in levels}
    try:
        n = max(0, int(num_questions))
    except (TypeError, ValueError):
        n = 0

    if difficulty and difficulty != "mixed":
        points = DIFFICULTY_TO_POINTS.get(difficulty, 300)
        dist[str(points)] = n
        return dist

    base, remainder = divmod(n, len(levels))
    for i, p in enumerate(levels):
        dist[str(p)] = base + (1 if i < remainder else 0)
    return dist


def calculate_distribution(questions) -> dict:
    """Count how many questions fall on each point value."""
    dist = {str(p): 0 for p in (100, 200, 300, 400, 500)}
    for q in questions or []:
        points = str(q.get("points")) if isinstance(q, dict) else None
        if points in dist:
            dist[points] += 1
    return dist


def extract_approved_questions(validation_result) -> list:
    """Pull the approved (and revised) questions out of a validation result."""
    approved = []
    if not isinstance(validation_result, dict):
        return approved
    for item in validation_result.get("questions", []):
        if not isinstance(item, dict):
            continue
        if item.get("status") in ("approved", "needs_revision") and item.get("approved_question"):
            approved.append(item["approved_question"])
    return approved


# The one canonical question-type set enforced everywhere (UI, save, validation).
ALLOWED_TYPES = {"multiple_choice", "true_false", "text"}


def _normalize_question_type(qtype: str) -> str:
    """Map model-emitted types onto the app's single canonical set.

    Earlier prompts/specs used ``short_answer``; the app uses ``text``. Collapse
    every alias to one of ALLOWED_TYPES so the output JSON consumers stay happy.
    Unknown values default to ``text`` (the most permissive type — it needs no
    options, so it never fails the multiple-choice structural checks).
    """
    t = str(qtype or "").strip().lower()
    mapping = {
        "mcq": "multiple_choice",
        "multiple choice": "multiple_choice",
        "multiple-choice": "multiple_choice",
        "multiple_choice": "multiple_choice",
        "true false": "true_false",
        "true/false": "true_false",
        "true-false": "true_false",
        "true_false": "true_false",
        "boolean": "true_false",
        "tf": "true_false",
        "short_answer": "text",
        "short answer": "text",
        "short": "text",
        "open": "text",
        "open_ended": "text",
        "fill_in_the_blank": "text",
        "fill_in": "text",
        "text": "text",
    }
    return mapping.get(t, "text")


def is_duplicate_question(new_q: dict, existing_questions: list) -> bool:
    """Backend duplicate test that goes beyond exact question wording.

    Two questions are duplicates when they share a ``fact_id``, or the same
    normalized source fact, or identical normalized question text, or the same
    answer drawn from the same source fact. This catches paraphrases that ask
    about the same underlying fact.
    """
    new_text = _normalize_question_text(new_q.get("question", ""))
    new_answer = _normalize_question_text(new_q.get("correct_answer", ""))
    new_fact_id = new_q.get("fact_id")
    new_source_fact = _normalize_question_text(new_q.get("source_fact_used", ""))

    for old_q in existing_questions or []:
        old_text = _normalize_question_text(old_q.get("question", ""))
        old_answer = _normalize_question_text(old_q.get("correct_answer", ""))
        old_fact_id = old_q.get("fact_id")
        old_source_fact = _normalize_question_text(old_q.get("source_fact_used", ""))

        if new_fact_id and old_fact_id and new_fact_id == old_fact_id:
            return True
        if new_source_fact and old_source_fact and new_source_fact == old_source_fact:
            return True
        if new_text and old_text and new_text == old_text:
            return True
        if new_answer and old_answer and new_answer == old_answer and new_source_fact and new_source_fact == old_source_fact:
            return True

    return False


def filter_duplicates(generated_questions: list, existing_questions: list):
    """Split generated questions into unique vs duplicate against a running memory.

    The memory starts from ``existing_questions`` and grows as each unique question
    is accepted, so duplicates within the generated set are also caught.
    """
    approved, rejected = [], []
    memory = list(existing_questions or [])
    for q in generated_questions or []:
        if is_duplicate_question(q, memory):
            rejected.append(q)
            continue
        approved.append(q)
        memory.append(q)
    return approved, rejected


# How many of the most recent AI batches to scan for cross-batch duplicate memory.
_MEMORY_BATCH_WINDOW = 50


def collect_existing_questions_from_bank() -> list:
    """Gather questions from recent AI-generated batches for duplicate memory.

    ``get_all_batches()`` returns newest-first; ``get_batch()`` returns a LIST of
    question dicts in this module. Capped to the most recent ``_MEMORY_BATCH_WINDOW``
    batches to bound cost. Best-effort — never raises.
    """
    existing = []
    try:
        batches = get_all_batches() or []
        if len(batches) > _MEMORY_BATCH_WINDOW:
            print(f"Duplicate memory: scanning {_MEMORY_BATCH_WINDOW} of {len(batches)} batches (older ones skipped).")
            batches = batches[:_MEMORY_BATCH_WINDOW]
        for batch_meta in batches:
            batch_id = batch_meta.get("batch_id") or batch_meta.get("id")
            if not batch_id:
                continue
            questions = get_batch(batch_id)
            if isinstance(questions, list):
                existing.extend(q for q in questions if isinstance(q, dict))
    except Exception as e:
        print(f"collect_existing_questions_from_bank failed (continuing without memory): {e}")
    return existing


def collect_used_fact_ids(existing_questions: list) -> set:
    """Return the set of non-empty fact_ids already used by existing questions."""
    return {q.get("fact_id") for q in (existing_questions or []) if isinstance(q, dict) and q.get("fact_id")}


def code_validate_question(q: dict, require_source: bool = True):
    """Deterministic (non-AI) validation of a single question.

    AI review can pass a structurally-broken question; this enforces hard rules:
    a question/answer must exist, points must be one of the five levels, multiple
    choice needs exactly 4 distinct options containing the correct answer, and
    true/false answers must be true/false. ``fact_id``/``source_url`` are required
    ONLY when ``require_source`` is True (i.e. when the batch is grounded on facts);
    ungrounded fallback generation is exempt so it never returns empty.

    Returns ``(is_valid, issues)`` and normalizes ``q['type']`` in place.
    """
    issues = []
    if not isinstance(q, dict):
        return False, ["not_an_object"]

    qtype = _normalize_question_type(q.get("type"))
    q["type"] = qtype

    if not q.get("question"):
        issues.append("missing_question")
    if q.get("points") not in (100, 200, 300, 400, 500):
        issues.append("invalid_points")
    if not q.get("correct_answer"):
        issues.append("missing_correct_answer")

    if qtype == "multiple_choice":
        options = q.get("options") or []
        if len(options) != 4:
            issues.append("multiple_choice_must_have_4_options")
        normalized_options = [_normalize_question_text(o) for o in options]
        normalized_answer = _normalize_question_text(q.get("correct_answer", ""))
        if normalized_answer and normalized_answer not in normalized_options:
            issues.append("correct_answer_not_in_options")
        if len(set(normalized_options)) != len(normalized_options):
            issues.append("duplicate_options")

    if qtype == "true_false":
        if _normalize_question_text(q.get("correct_answer", "")) not in ("true", "false"):
            issues.append("true_false_answer_must_be_true_or_false")

    if require_source:
        if not q.get("fact_id"):
            issues.append("missing_fact_id")
        if not q.get("source_url"):
            issues.append("missing_source_url")

    return len(issues) == 0, issues


def code_filter_valid_questions(questions: list, require_source: bool = True):
    """Apply code_validate_question to a list; return (valid, rejected_with_issues)."""
    valid, rejected = [], []
    for q in questions or []:
        ok, issues = code_validate_question(q, require_source=require_source)
        if ok:
            valid.append(q)
        else:
            rejected.append({"question": q, "issues": issues})
    return valid, rejected


class AIQuestionGenerator:
    """
    A class to generate questions using AI services.

    This class provides methods for generating questions based on prompts,
    with customizable options for question type, difficulty, etc.
    """

    @staticmethod
    def _redact_secrets(text: str) -> str:
        """Redact API key-like substrings in error messages to avoid leaking secrets."""
        try:
            import re as _re
            if not isinstance(text, str):
                return text
            # Mask common patterns like sk-... and ghp_...
            text = _re.sub(r"sk-[A-Za-z0-9_\-]{5,}", "sk-***REDACTED***", text)
            text = _re.sub(r"ghp_[A-Za-z0-9]{5,}", "ghp_***REDACTED***", text)
            return text
        except Exception:
            return text

    def __init__(self, temp_storage_path=None):
        """
        Initialize a new AI question generator.

        Args:
            temp_storage_path (str, optional): Path to store temporarily generated questions.
                If None, defaults to "questionmanagement/ai_generated_questions".
        """
        # Set default path if none provided
        if temp_storage_path is None:
            temp_storage_path = os.path.join("questionmanagement", "ai_generated_questions")
        # Convert to absolute path if it's a relative path
        if not os.path.isabs(temp_storage_path):
            # Get the absolute path relative to the current script location
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            self.temp_storage_path = os.path.join(base_dir, temp_storage_path)
        else:
            self.temp_storage_path = temp_storage_path

        # Create storage directory if it doesn't exist
        os.makedirs(self.temp_storage_path, exist_ok=True)

        # Dictionary to store generated question batches
        self.question_batches = {}

        # OpenAI API settings (will be set by the web app)
        self.api_key = None
        self.model = "gpt-4o-mini"
        self.temperature = 0.55
        self.top_p = 1.0
        self.frequency_penalty = 0.0
        self.presence_penalty = 0.0
        self.reasoning_effort = 'medium'  # used only by reasoning-family models (e.g. GPT-5.x)
        self.verbosity = 'medium'  # used only by reasoning-family models (e.g. GPT-5.x)
        self.max_output_tokens = 2000
        self.seed = 0
        self.stop = None
        self.response_format = None  # e.g., {"type": "json_object"}
        self.request_timeout = 60.0
        self.base_url = "https://api.openai.com/v1"
        self.organization = None
        self.user = None
        # Generation controls
        self.start_index = 0  # Offset to skip earlier candidate results

        # API connection status
        self.api_connected = False

    def _get_model_max_completion_tokens(self, model_name: str) -> int:
        """Return max supported completion tokens for known models; safe fallback otherwise."""
        from contents.admin_controls.openai_models import is_known_model, get_max_output_tokens
        if is_known_model(model_name):
            return get_max_output_tokens(model_name)

        caps = {
            'gpt-4o': 16384,
            'gpt-4o-mini': 16384,
            'o4-mini': 16384,
            'gpt-4.1': 16384,
            'gpt-4.1-mini': 16384,
        }
        for key, val in caps.items():
            if str(model_name or '').startswith(key):
                return val
        return 4096

    def _is_reasoning_model(self) -> bool:
        """Whether self.model is a reasoning-family model (e.g. GPT-5.x) rather
        than a standard chat-completions model (e.g. GPT-4o). Reasoning models
        don't accept temperature/top_p/frequency_penalty/presence_penalty and
        use max_completion_tokens + reasoning_effort/verbosity instead."""
        try:
            from contents.admin_controls.openai_models import is_known_model, get_model_config
            if is_known_model(self.model):
                return get_model_config(self.model).get('family') == 'reasoning'
        except Exception:
            pass
        return False

    def _generation_params(self, max_tokens_value, temperature_override=None):
        """Build the model-appropriate sampling/reasoning + token-limit params
        for a Chat Completions payload. Centralizes the standard-vs-reasoning
        split so the three call sites below stay in sync."""
        if self._is_reasoning_model():
            params = {"max_completion_tokens": max_tokens_value}
            if getattr(self, 'reasoning_effort', None):
                params["reasoning_effort"] = self.reasoning_effort
            if getattr(self, 'verbosity', None):
                params["verbosity"] = self.verbosity
            return params

        temperature = self.temperature if temperature_override is None else temperature_override
        return {
            "temperature": min(max(temperature, 0.0), 2.0),
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": max_tokens_value,
        }

    def generate_questions(self, prompt, options=None):
        """
        Generate questions based on a prompt and options.

        Args:
            prompt (str): The prompt to generate questions from
            options (dict, optional): Options for generation. Defaults to None.
                Possible options:
                - question_type: Type of questions to generate (mixed, multiple_choice, true_false, text)
                - difficulty: Difficulty level (mixed, easy, medium, hard)
                - num_questions: Number of questions to generate
                - include_explanations: Whether to include explanations for correct answers
                - language: Language for questions (english, arabic)
                - reference_categories: List of category IDs to read and avoid repeating questions from
                - api_key: OpenAI API key
                - model: OpenAI model to use
                - temperature: Temperature for generation
                - max_output_tokens: Maximum output tokens for generation

        Returns:
            tuple: (batch_id, questions) where batch_id is a unique identifier for this batch
                and questions is a list of generated question dictionaries

        Raises:
            ValueError: If no valid API key is provided or API connection fails
        """
        if options is None:
            options = {}

        # Set default options
        question_type = options.get('question_type', 'mixed')
        difficulty = options.get('difficulty', 'mixed')
        num_questions = int(options.get('num_questions', 20))
        include_explanations = options.get('include_explanations', True)
        language = options.get('language', 'arabic')
        reference_categories = options.get('reference_categories', [])
        # Dedicated retrieval/framing topic, separate from free-text instructions
        # in `prompt`. Falls back to the prompt when no explicit topic is given.
        instructions = (prompt or '').strip()
        search_topic = (options.get('topic') or '').strip() or instructions
        # Effective generation prompt: anchor firmly on the topic, then append
        # any free-text focus/style so the model stays on-subject.
        if instructions and instructions != search_topic:
            gen_prompt = f"{search_topic}. {instructions}"
        else:
            gen_prompt = search_topic
        # Enhanced flow toggles (default on; degrade gracefully when disabled/failed)
        use_source_grounding = bool(options.get('use_source_grounding', True))
        use_validation = bool(options.get('use_validation', True))

        # Get API settings from options if provided (centralized loader feeds these)
        self.api_key = options.get('api_key', self.api_key)
        # Normalize API key: strip whitespace and remove accidental 'Bearer ' prefix
        if self.api_key:
            self.api_key = str(self.api_key).strip()
            if self.api_key.lower().startswith('bearer '):
                self.api_key = self.api_key[7:].strip()
        self.model = options.get('model', self.model)
        # Bound temperature to provider-allowed range [0.0, 2.0]
        self.temperature = float(options.get('temperature', self.temperature))
        if self.temperature < 0.0:
            self.temperature = 0.0
        elif self.temperature > 2.0:
            self.temperature = 2.0
        # Top-p and penalties
        self.top_p = float(options.get('top_p', self.top_p))
        self.frequency_penalty = float(options.get('frequency_penalty', self.frequency_penalty))
        self.presence_penalty = float(options.get('presence_penalty', self.presence_penalty))
        # Reasoning-model-only controls (ignored for standard chat models)
        self.reasoning_effort = options.get('reasoning_effort', self.reasoning_effort)
        self.verbosity = options.get('verbosity', self.verbosity)
        # Tokens / seed / stops
        self.max_output_tokens = int(options.get('max_output_tokens', self.max_output_tokens))
        self.seed = int(options.get('seed', self.seed) or 0)
        self.stop = options.get('stop', self.stop)
        # Response formatting: accept dict, string name, or legacy boolean flags
        self.response_format = options.get('response_format', self.response_format)
        # If response_format is provided as a string 'json_object', normalize to dict
        if isinstance(self.response_format, str) and self.response_format.lower() == 'json_object':
            self.response_format = {"type": "json_object"}
        # Support legacy json mode flags from callers/admin
        legacy_json_mode = options.get('json_mode') or options.get('openai_json_mode')
        if legacy_json_mode and not self.response_format:
            self.response_format = {"type": "json_object"}
        # Generation controls
        try:
            self.start_index = max(0, int(options.get('start_index', self.start_index) or 0))
        except Exception:
            self.start_index = 0
        # Timeouts and routing
        self.request_timeout = float(options.get('request_timeout', self.request_timeout) or 60)
        self.base_url = options.get('base_url', self.base_url) or self.base_url
        self.organization = options.get('organization', self.organization)
        self.user = options.get('user', self.user)

        # Clamp max tokens based on model capability
        try:
            cap = self._get_model_max_completion_tokens(self.model)
            self.max_output_tokens = max(1, min(int(self.max_output_tokens), cap))
        except Exception:
            # Fallback safe bound
            self.max_output_tokens = max(1, min(int(self.max_output_tokens), 4096))

        # Check if API key is provided and not empty
        if not self.api_key or not self.api_key.strip():
            raise ValueError("OpenAI API key is required to generate questions. Please provide a valid API key.")

        print(f"API key is provided (length: {len(self.api_key.strip())}). Verifying OpenAI API connection...")

        _set_generation_progress(percent=5, total=num_questions, message="Validating API key…")

        # Verify the API connection first
        connection_success, connection_message = self.verify_api_connection()

        if not connection_success:
            raise ValueError(f"OpenAI API connection failed: {connection_message}")

        print(f"OpenAI API connection successful. Attempting to generate questions.")
        _set_generation_progress(percent=10, message="Connected. Generating questions…")
        try:
            # Token-aware, chunked generation to reliably reach requested count.
            # Each round runs the enforced pipeline:
            #   generate (over unused facts) -> AI validate -> code validate ->
            #   backend duplicate rejection -> top up until the target is met.
            total_questions = []
            batch_sizes = []

            # --- Duplicate memory (dicts) ----------------------------------------
            # 1) Questions in the admin-selected reference categories.
            ref_existing = []
            try:
                if reference_categories:
                    question_bank.load_questions()
                    for category_id in reference_categories:
                        if category_id in question_bank.categories:
                            for qid in question_bank.categories.get(category_id, []):
                                q = question_bank.questions.get(qid)
                                if isinstance(q, dict) and q.get('question'):
                                    ref_existing.append(q)
            except Exception:
                ref_existing = []

            # 2) Cross-batch memory: questions (and their fact_ids) from recent AI batches.
            bank_existing = collect_existing_questions_from_bank()
            existing_questions = ref_existing + bank_existing
            print(f"Duplicate memory loaded: {len(ref_existing)} reference + {len(bank_existing)} prior-batch questions.")

            # --- Best-effort RAG: multi-source fact pool -------------------------
            # Never blocks generation — an empty pool falls back to general knowledge.
            source_facts = None
            if use_source_grounding:
                try:
                    wiki_lang = 'ar' if str(language).lower() == 'arabic' else 'en'
                    _set_generation_progress(percent=12, message="Retrieving online sources…")
                    source_facts = build_source_facts(search_topic, lang=wiki_lang)
                    n_src = len(source_facts.get("sources", []))
                    n_facts = len(source_facts.get("facts", []))
                    if n_facts:
                        print(f"Grounding on {n_facts} facts from {n_src} source(s).")
                        _set_generation_progress(percent=20, message=f"Built {n_facts} source facts from {n_src} pages…")
                    else:
                        print("No source facts retrieved; generating from general knowledge.")
                except Exception as e:
                    print(f"Source-fact retrieval failed (continuing ungrounded): {e}")
                    source_facts = None

            # We may have a fact pool to offer as context. Whether we HARD-enforce
            # it (one question per fact, source fields required) is controlled by
            # ENFORCE_STRICT_GROUNDING - off by default so facts are optional
            # context and the model stays on-topic / reaches the requested count.
            grounded = bool(source_facts and source_facts.get('facts'))
            enforce_grounding = grounded and ENFORCE_STRICT_GROUNDING
            fact_pool = list(source_facts.get('facts', [])) if grounded else []

            # Preserve original start index and adjust per batch to conceptually skip earlier candidates
            original_start = int(getattr(self, 'start_index', 0) or 0)

            # Heuristic per-call size: Arabic tends to be longer; keep smaller batch
            default_chunk = 10 if str(language).lower() == 'english' else 7
            remaining = int(num_questions)
            max_batches = max(10, (remaining + default_chunk - 1) // default_chunk + 4)
            batches_done = 0
            code_rejected_total = 0
            dup_rejected_total = 0
            validated = False
            review_summary = {}

            while remaining > 0 and batches_done < max_batches:
                per_call = min(default_chunk, remaining)
                # Nudge per_call up if admin configured very high max tokens
                try:
                    if self.max_output_tokens >= 8000 and per_call < 15 and str(language).lower() == 'english':
                        per_call = min(15, remaining)
                except Exception:
                    pass

                # Strict-grounding only: restrict to unused facts and cap the batch
                # by how many remain (one question per fact). In soft mode we pass
                # all facts as optional context and never cap by fact count.
                chunk_source_facts = source_facts
                if enforce_grounding:
                    used_ids = collect_used_fact_ids(existing_questions + total_questions)
                    unused_facts = [f for f in fact_pool if f.get('fact_id') not in used_ids]
                    if not unused_facts:
                        print("No unused source facts remain; stopping generation early.")
                        break
                    per_call = min(per_call, len(unused_facts))
                    chunk_source_facts = {**source_facts, 'facts': unused_facts}

                # Adjust start_index for this batch to avoid earlier candidates
                setattr(self, 'start_index', original_start + len(total_questions))

                # Soft difficulty target for this chunk (spread across 100–500 when mixed).
                chunk_distribution = build_difficulty_distribution(per_call, difficulty)

                batch = self._generate_questions_with_openai(
                    gen_prompt,
                    question_type,
                    difficulty,
                    per_call,
                    include_explanations,
                    language,
                    reference_categories,
                    source_facts=chunk_source_facts,
                    distribution=chunk_distribution
                ) or []

                # Per-round AI validation (best-effort; returns input on failure).
                if batch and use_validation:
                    _set_generation_progress(message="Validating questions…")
                    batch, round_summary = self._validate_questions_with_openai(
                        batch, source_facts=chunk_source_facts, language=language
                    )
                    validated = True
                    if isinstance(round_summary, dict) and round_summary:
                        review_summary = round_summary

                # Code-level (deterministic) validation. Source fields are required
                # only under strict grounding; in soft mode questions may come from
                # general knowledge, so we don't require citations.
                code_valid, code_rej = code_filter_valid_questions(batch, require_source=enforce_grounding)
                code_rejected_total += len(code_rej)

                # Backend duplicate rejection against memory + everything accepted so far.
                unique, dups = filter_duplicates(code_valid, existing_questions + total_questions)
                dup_rejected_total += len(dups)

                added = 0
                for q in unique:
                    total_questions.append(q)
                    added += 1
                    if len(total_questions) >= num_questions:
                        break

                batch_sizes.append({
                    'requested': per_call,
                    'received': len(batch),
                    'code_valid': len(code_valid),
                    'rejected_by_code': len(code_rej),
                    'rejected_as_duplicate': len(dups),
                    'added_unique': added,
                })
                remaining = max(0, num_questions - len(total_questions))
                batches_done += 1

                # Report real progress: scale the generation phase (20%–95%) by
                # how many unique questions we've accumulated so far.
                pct = 20 + int(75 * min(1.0, len(total_questions) / max(1, num_questions)))
                _set_generation_progress(
                    percent=pct,
                    generated=len(total_questions),
                    message=f"Generated {len(total_questions)} of {num_questions} questions…",
                )

                # If provider keeps returning too few (e.g., 4-5), try one more slightly smaller batch
                if remaining > 0 and added == 0 and per_call > 1:
                    default_chunk = max(1, default_chunk - 1)

            questions = total_questions

            # Restore original start index
            setattr(self, 'start_index', original_start)

            # If successful, return the questions
            if questions:
                print(f"Successfully generated {len(questions)} questions with OpenAI API (requested {num_questions}).")
                # Generate a unique batch ID
                batch_id = str(uuid.uuid4())

                # Store the batch
                self.question_batches[batch_id] = questions

                # Create metadata
                metadata = {
                    'prompt': gen_prompt,
                    'topic': search_topic,
                    'question_type': question_type,
                    'difficulty': difficulty,
                    'num_questions': len(questions),
                    'num_requested': num_questions,
                    'num_returned': len(questions),
                    'include_explanations': include_explanations,
                    'language': language,
                    'start_index': original_start,
                    'batches': batch_sizes,
                    'timestamp': datetime.now().isoformat(),
                    'model': self.model,
                    'temperature': self.temperature,
                    'top_p': self.top_p,
                    'reference_categories': reference_categories,
                    # Enhanced (RAG + points-difficulty + validation) flow metadata
                    'generation_version': 'v4_rag_factpool_enforced',
                    'source_grounded': grounded,
                    'used_fact_grounding': grounded,
                    'sources_count': len(source_facts.get('sources', [])) if source_facts else 0,
                    'facts_count': len(source_facts.get('facts', [])) if source_facts else 0,
                    'validated': validated,
                    'rejected_by_code': code_rejected_total,
                    'rejected_as_duplicate': dup_rejected_total,
                    'difficulty_distribution': calculate_distribution(questions),
                    'validation_summary': review_summary,
                }

                # Save to temporary storage with metadata
                self._save_batch(batch_id, questions, metadata)

                return batch_id, questions
            else:
                raise ValueError("OpenAI API returned no questions. Please try again with a different prompt or settings.")
        except Exception as e:
            print(f"Error generating questions with OpenAI: {str(e)}")
            raise ValueError(f"Failed to generate questions with OpenAI: {str(e)}")

    def get_batch(self, batch_id):
        """
        Get a batch of generated questions by ID.

        Args:
            batch_id (str): The batch ID

        Returns:
            list: The list of questions in the batch, or None if not found
        """
        # Try to get from memory first
        if batch_id in self.question_batches:
            return self.question_batches[batch_id]

        # If not in memory, try to load from storage
        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        if os.path.exists(batch_path):
            try:
                with open(batch_path, 'r', encoding="utf-8") as f:
                    batch_data = json.load(f)

                # Handle both old and new format
                if isinstance(batch_data, list):
                    # Old format: just a list of questions
                    questions = batch_data
                elif isinstance(batch_data, dict) and 'questions' in batch_data:
                    # New format: dict with 'metadata' and 'questions'
                    questions = batch_data['questions']
                else:
                    # Unknown format
                    print(f"Unknown batch data format for batch {batch_id}")
                    return None

                # Cache in memory
                self.question_batches[batch_id] = questions
                return questions
            except json.JSONDecodeError as e:
                print(f"Error decoding JSON for batch {batch_id}: {str(e)}")
                return None
            except Exception as e:
                print(f"Unexpected error loading batch {batch_id}: {str(e)}")
                return None

        return None

    def get_batch_metadata(self, batch_id):
        """
        Get metadata for a batch of generated questions by ID.

        Args:
            batch_id (str): The batch ID

        Returns:
            dict: The metadata for the batch, or None if not found or no metadata exists
        """
        # Try to load from storage
        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        if os.path.exists(batch_path):
            try:
                with open(batch_path, 'r', encoding="utf-8") as f:
                    batch_data = json.load(f)

                # Handle both old and new format
                if isinstance(batch_data, dict) and 'metadata' in batch_data:
                    # New format: dict with 'metadata' and 'questions'
                    meta = batch_data['metadata']
                    # Ensure backward compatibility and fallback for missing 'num_questions'
                    if 'num_questions' not in meta:
                        if 'num_returned' in meta:
                            meta['num_questions'] = meta['num_returned']
                        elif 'questions' in batch_data:
                            meta['num_questions'] = len(batch_data['questions'])
                        else:
                            meta['num_questions'] = 'unknown'
                    return meta
                elif isinstance(batch_data, list):
                    # Old format: just a list of questions, no metadata
                    # Create basic metadata with file creation time and estimated question count
                    return {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                        'num_questions': len(batch_data),
                        'prompt': 'Unknown (Legacy Format)',
                        'question_type': 'mixed',
                        'difficulty': 'mixed',
                        'language': 'unknown'
                    }
                else:
                    # Unknown format but still a valid JSON, create minimal metadata
                    return {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                        'prompt': 'Unknown Format',
                        'question_type': 'unknown',
                        'difficulty': 'unknown',
                        'language': 'unknown'
                    }
            except json.JSONDecodeError:
                # If JSON is invalid, still return minimal metadata so it shows in the list
                return {
                    'timestamp': datetime.fromtimestamp(os.path.getctime(batch_path)).isoformat(),
                    'prompt': 'Invalid JSON Format',
                    'question_type': 'unknown',
                    'difficulty': 'unknown',
                    'language': 'unknown'
                }

        return None

    def _save_batch(self, batch_id, questions, metadata=None):
        """
        Save a batch of questions to temporary storage.

        Args:
            batch_id (str): The batch ID
            questions (list): The list of questions to save
            metadata (dict, optional): Additional metadata about the batch. Defaults to None.
        """
        # If no metadata is provided, create an empty dict
        if metadata is None:
            metadata = {}

        # Add timestamp if not present
        if 'timestamp' not in metadata:
            metadata['timestamp'] = datetime.now().isoformat()

        # Create a structure that includes both metadata and questions
        batch_data = {
            'metadata': metadata,
            'questions': questions
        }

        batch_path = os.path.join(self.temp_storage_path, f"{batch_id}.json")
        with open(batch_path, 'w', encoding="utf-8") as f:
            json.dump(batch_data, f, indent=2, ensure_ascii=False)

    def verify_api_connection(self):
        """
        Verify the connection to the OpenAI API.

        Returns:
            tuple: (success, message) where success is a boolean indicating if the connection was successful
                and message is a string with details about the connection status
        """
        if not self.api_key or not self.api_key.strip():
            self.api_connected = False
            print(f"API key validation failed. API key: '{self.api_key}'")
            return False, "OpenAI API key is missing or empty"

        try:
            # Prepare a simple API request to test the connection
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key.strip()}"  # Ensure no whitespace in the API key
            }
            if self.organization:
                headers["OpenAI-Organization"] = str(self.organization)

            # Build minimal messages; if json_object is requested, explicitly mention JSON per provider rules
            wants_json = False
            try:
                rf = self.response_format
                if isinstance(rf, dict) and rf.get("type") == "json_object":
                    wants_json = True
                elif isinstance(rf, str) and rf.lower() == "json_object":
                    wants_json = True
            except Exception:
                wants_json = False

            if wants_json:
                messages = [
                    {"role": "system", "content": "You are a connectivity tester. Reply only with a small valid JSON object and nothing else."},
                    {"role": "user", "content": "Please respond with a JSON object: {\"ok\": true}"}
                ]
                test_max_tokens = 20
            else:
                messages = [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Hello, are you connected?"}
                ]
                test_max_tokens = 50

            data = {
                "model": self.model,
                "messages": messages,
                **self._generation_params(test_max_tokens),
            }
            if self.response_format:
                data["response_format"] = self.response_format
            if self.user:
                data["user"] = self.user
            if self.seed:
                # Only include if non-zero for determinism, some models support it
                try:
                    if int(self.seed) > 0:
                        data["seed"] = int(self.seed)
                except Exception:
                    pass

            # Build endpoint from base_url
            base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
            url = f"{base}/chat/completions"

            print(f"Verifying OpenAI API connection with key: '{self.api_key[:5]}...'")
            response = _post_with_retries(
                url,
                headers,
                data,
                timeout=self.request_timeout or 60,
                max_retries=2,
                backoff=1.5
            )

            if response.status_code == 200:
                self.api_connected = True
                print("OpenAI API connection successful")
                return True, "OpenAI API connection successful"
            else:
                self.api_connected = False
                raw_error = f"OpenAI API error: {response.status_code} - {response.text}"
                error_message = self._redact_secrets(raw_error)
                print(error_message)
                return False, error_message

        except requests.exceptions.RequestException as e:
            self.api_connected = False
            error_message = f"Failed to connect to OpenAI API: {str(e)}"
            print(error_message)
            return False, error_message
        except Exception as e:
            self.api_connected = False
            error_message = f"Unexpected error during API connection verification: {str(e)}"
            print(error_message)
            return False, error_message

    def _generate_questions_with_openai(self, prompt, question_type, difficulty, num_questions, include_explanations, language='english', reference_categories=None, source_facts=None, distribution=None):
        """
        Generate questions using the OpenAI API.

        Args:
            prompt (str): The prompt to generate questions from
            question_type (str): Type of questions to generate
            difficulty (str): Difficulty level
            num_questions (int): Number of questions to generate
            include_explanations (bool): Whether to include explanations
            language (str, optional): Language for questions (english, arabic). Defaults to 'english'.
            reference_categories (list, optional): List of category IDs to read and avoid repeating questions from.
            source_facts (dict, optional): Best-effort RAG grounding package from
                build_source_facts(). When it contains facts, the model is told to
                generate ONLY from them; when empty/None, generation falls back to
                general knowledge.
            distribution (dict, optional): Target points distribution for this chunk
                (e.g. {"100": 2, "200": 2, ...}) used as a soft difficulty target.

        Returns:
            list: A list of generated question dictionaries
        """
        # Ensure API key is valid
        if not self.api_key or not self.api_key.strip():
            print(f"OpenAI API key is missing or empty: '{self.api_key}'")
            raise ValueError("OpenAI API key is required")

        # Use the stripped API key to avoid any whitespace issues
        api_key = self.api_key.strip()

        print(f"Preparing to call OpenAI API with model: {self.model}, temperature: {self.temperature}")
        print(f"Generating {num_questions} {question_type} questions with difficulty: {difficulty}")
        print(f"Using API key: '{api_key[:5]}...'")

        # Get existing questions from reference categories if provided
        existing_questions = []
        if reference_categories and len(reference_categories) > 0:
            print(f"Reading questions from {len(reference_categories)} reference categories")
            # Ensure question_bank has the latest data
            question_bank.load_questions()

            # Collect questions from each selected category
            for category_id in reference_categories:
                if category_id in question_bank.categories:
                    category_questions = []
                    for question_id in question_bank.categories[category_id]:
                        if question_id in question_bank.questions:
                            question = question_bank.questions[question_id]
                            # Add only the question text to avoid making the prompt too long
                            question_text = question.get('question', '')
                            if question_text:
                                category_questions.append(question_text)

                    if category_questions:
                        print(f"Found {len(category_questions)} questions in category {category_id}")
                        existing_questions.extend(category_questions)
                else:
                    print(f"Category {category_id} not found in question bank")

        # Build the system prompt as flush-left sections joined at the end, so
        # nothing carries stray leading whitespace into the token stream and no
        # earlier instruction gets silently dropped by a later reassignment
        # (the previous version overwrote user_prompt in the JSON-mode branch,
        # discarding the start_index instruction - fixed below). Loosely based
        # on questionmanagement/AI_generator.txt. The OUTPUT schema is pinned to
        # the fields the rest of the app consumes (type/question/options/
        # correct_answer/explanation/points), with optional enrichment fields.
        sections = ['''You are an expert trivia question designer for a high-quality educational trivia game.
Generate clear, factually accurate questions based on the user's prompt.

DIFFICULTY POINTS ("points" is the difficulty signal):
100 Very easy - direct recall of a well-known fact, no reasoning needed
200 Easy - simple recognition or a one-step fact, slightly less obvious than 100
300 Medium - connects two facts or needs context; not answerable from a name alone
400 Hard - comparison, chronology, classification, or cause/effect; distractors highly plausible
500 Very hard - multi-step deduction or fine distinctions between similar concepts; still fair and answerable

QUESTION REQUIREMENTS:
1. Exactly one correct answer per question.
2. Do not invent facts or write trick questions.
3. Avoid ambiguous wording.
4. No duplicate/near-duplicate questions or repeating the same kind of fact.
5. Mix question styles and phrasing.
6. Never mention "source", "passage", "context", or "provided facts" in the question text.

MULTIPLE CHOICE: exactly 4 options; exactly one correct, matching "correct_answer" verbatim; distractors plausible but clearly wrong; no "All/None of the above"; vary the correct option's position.
TRUE/FALSE: avoid trivially obvious statements; false statements must be realistically false.
TEXT: the answer must be short and specific.

OUTPUT FORMAT: return ONLY a JSON array of question objects (no markdown, no commentary), using exactly these shapes:
{"type": "multiple_choice", "question": "...", "options": ["...", "...", "...", "..."], "correct_answer": "...", "explanation": "...", "points": 100}
{"type": "true_false", "question": "...", "correct_answer": "True|False", "explanation": "...", "points": 100}
{"type": "text", "question": "...", "correct_answer": "...", "explanation": "...", "points": 100}''']

        # Source-grounded (RAG) block: if we retrieved verified facts, require the
        # model to generate strictly from them; otherwise rely on general knowledge
        # but still demand factual accuracy.
        grounding_facts = []
        try:
            if isinstance(source_facts, dict):
                grounding_facts = source_facts.get("facts", []) or []
        except Exception:
            grounding_facts = []

        if grounding_facts and ENFORCE_STRICT_GROUNDING:
            # Strict-grounding mode: each fact has a fact_id / source_title /
            # source_url. Require every question to cite exactly the fact it was
            # built from so the backend can enforce one-question-per-fact.
            facts_json = json.dumps(grounding_facts, ensure_ascii=False, separators=(',', ':'))
            sections.append(
                'SOURCE FACTS (verified) - each has "fact_id", "fact", "source_title", "source_url".\n'
                "Build questions using ONLY these facts; do not introduce unsupported facts. "
                "Use each fact for at most one question.\n"
                f"FACT POOL: {facts_json}\n\n"
                "For EVERY question, also copy these fields from the single fact you used: "
                '"fact_id", "source_fact_used" (that fact\'s exact text), "source_title", "source_url", '
                'and "confidence" (one of "high"|"medium"|"low").\n'
                'Grounded example: {"type":"multiple_choice","question":"...","options":["...","...","...","..."],'
                '"correct_answer":"...","explanation":"...","points":100,"fact_id":"<id>",'
                '"source_fact_used":"<fact text>","source_title":"<title>","source_url":"<url>","confidence":"high"}'
            )
        elif grounding_facts:
            # Soft-grounding mode: facts are OPTIONAL context. The model may also
            # use its own reliable knowledge to stay on-topic and reach the count.
            facts_json = json.dumps(grounding_facts, ensure_ascii=False, separators=(',', ':'))
            sections.append(
                "SUPPORTING FACTS (optional context retrieved from reference sources). "
                "Use them when relevant and correct, but you are NOT limited to them - draw on your own "
                "reliable general knowledge to cover the requested topic fully and reach the requested count. "
                "IGNORE any supporting fact that is not about the requested topic; never let these facts pull "
                "questions off-topic.\n"
                f"FACTS: {facts_json}\n"
                'If a question happens to be based on one of these facts, you may include its "fact_id" and "source_url".'
            )
        else:
            sections.append(
                "Rely on your own reliable, widely-accepted general knowledge about the requested topic; "
                "only state facts you are confident are correct."
            )

        # Avoid re-asking questions that already exist in the referenced categories.
        if existing_questions:
            shown = existing_questions[:50]
            coverage = f"showing 50 of {len(existing_questions)}" if len(existing_questions) > 50 else f"all {len(existing_questions)}"
            sections.append(
                f"AVOID DUPLICATES ({coverage}) - do not repeat or closely resemble any of these existing questions:\n"
                + "\n".join(f"- {q}" for q in shown)
            )

        # Consolidate all per-request generation settings into one block instead
        # of scattering single-line appends throughout the function.
        settings_lines = []
        if question_type and question_type != 'mixed':
            # question_type may be a single type or a comma-separated subset.
            selected_types = [t.strip() for t in str(question_type).split(',') if t.strip()]
            if len(selected_types) == 1:
                settings_lines.append(f"Only generate {selected_types[0]} questions.")
            elif selected_types:
                settings_lines.append(
                    f"Only generate questions of these types: {', '.join(selected_types)}, distributed roughly evenly."
                )

        if difficulty != 'mixed':
            points_value = DIFFICULTY_TO_POINTS.get(difficulty, 0)
            settings_lines.append(f"All questions must have {points_value} points.")
        else:
            settings_lines.append("Generate questions across all difficulty levels.")
            if isinstance(distribution, dict) and any(distribution.values()):
                settings_lines.append(
                    "Aim for this distribution of point values (points: count): "
                    f"{json.dumps(distribution, separators=(',', ':'))}."
                )

        if not include_explanations:
            settings_lines.append("Do not include explanations.")

        settings_lines.append(
            "Generate all questions and answers in Arabic, using proper Arabic grammar and vocabulary."
            if language.lower() == 'arabic'
            else "Generate all questions and answers in English."
        )

        if isinstance(self.start_index, int) and self.start_index > 0:
            settings_lines.append(
                f"Start at candidate index {self.start_index} (skip the first {self.start_index} possible results)."
            )

        sections.append("GENERATION SETTINGS:\n" + "\n".join(f"- {line}" for line in settings_lines))

        system_prompt = "\n\n".join(sections)

        # Build the user prompt incrementally (never reassigned wholesale) so
        # every addition - including the start_index skip - survives into the
        # final request regardless of whether JSON mode is on.
        user_prompt = f"Generate {num_questions} questions about: {prompt}"
        if isinstance(self.start_index, int) and self.start_index > 0:
            user_prompt += f" Skip the first {self.start_index} possible results when selecting which questions to output."

        # If JSON response_format is requested, reinforce JSON-only output in both messages.
        wants_json = False
        try:
            rf = self.response_format
            if isinstance(rf, dict) and rf.get("type") == "json_object":
                wants_json = True
            elif isinstance(rf, str) and rf.lower() == "json_object":
                wants_json = True
        except Exception:
            wants_json = False

        if wants_json:
            system_prompt += "\n\nReturn only JSON: a single valid JSON array/object matching the schema above, with no other text."
            user_prompt += " Respond strictly in JSON."

        # Prepare the API request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"  # Use the stripped API key
        }
        if self.organization:
            headers["OpenAI-Organization"] = str(self.organization)

        data = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            **self._generation_params(self.max_output_tokens),
        }
        if self.stop:
            data["stop"] = self.stop
        if self.response_format:
            data["response_format"] = self.response_format
        if self.user:
            data["user"] = self.user
        if self.seed:
            try:
                if int(self.seed) > 0:
                    data["seed"] = int(self.seed)
            except Exception:
                pass

        # Build endpoint from base_url
        base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        url = f"{base}/chat/completions"

        print("Making API request to OpenAI...")
        try:
            # Make the API request
            response = _post_with_retries(
                url,
                headers,
                data,
                timeout=self.request_timeout or 60,
                max_retries=2,
                backoff=1.5
            )

            # Check for errors; handle provider constraint on json_object requiring 'json' in messages
            if response.status_code != 200:
                txt = response.text
                # Specific fallback for: messages must contain the word 'json'
                if response.status_code == 400 and "must contain the word 'json'" in txt.lower():
                    print("OpenAI 400 due to json_object constraint; retrying without response_format (text-mode fallback) ...")
                    data_no_rf = dict(data)
                    if "response_format" in data_no_rf:
                        del data_no_rf["response_format"]
                    response = _post_with_retries(
                        url,
                        headers,
                        data_no_rf,
                        timeout=self.request_timeout or 60,
                        max_retries=2,
                        backoff=1.5
                    )
                # If still not OK, raise
                if response.status_code != 200:
                    raw_error = f"OpenAI API error: {response.status_code} - {response.text}"
                    error_message = self._redact_secrets(raw_error)
                    print(error_message)
                    raise Exception(error_message)

            print("Received successful response from OpenAI API")
            # Parse the response
            response_data = response.json()
            content = response_data['choices'][0]['message']['content']
            print(f"Response content length: {len(content)} characters")

            # Try to extract JSON from the response
            try:
                # First, try direct JSON parse
                try:
                    parsed = json.loads(content)
                except Exception:
                    # Fallback: extract JSON array/object substring
                    json_match = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
                    if json_match:
                        content = json_match.group(0)
                        parsed = json.loads(content)
                        print("Extracted JSON segment from response")
                    else:
                        raise

                # Normalize parsed JSON into a list of question dicts
                questions = None
                if isinstance(parsed, list):
                    questions = parsed
                elif isinstance(parsed, dict):
                    # Common patterns: {"questions": [...]} or a single question object
                    if isinstance(parsed.get('questions'), list):
                        questions = parsed['questions']
                    else:
                        # Search for the first list of dicts within the object
                        list_candidate = None
                        for v in parsed.values():
                            if isinstance(v, list) and v and isinstance(v[0], dict):
                                list_candidate = v
                                break
                        if list_candidate is not None:
                            questions = list_candidate
                        else:
                            # Treat entire object as a single question if it looks like one
                            keyset = set(k.lower() for k in parsed.keys())
                            required_keys = {'type', 'question', 'correct_answer'}
                            if required_keys.issubset(keyset):
                                questions = [parsed]
                            else:
                                questions = []
                else:
                    questions = []

                print(f"Successfully parsed JSON; normalized to list with {len(questions)} items")

                # Validate the questions
                validated_questions = []
                for i, question in enumerate(questions):
                    print(f"Validating question {i+1}...")
                    if not isinstance(question, dict):
                        print(f"Item {i+1} is not an object, skipping")
                        continue
                    # Ensure required fields are present
                    if 'type' not in question or 'question' not in question or 'correct_answer' not in question:
                        print(f"Question {i+1} missing required fields, skipping")
                        continue

                    # Collapse the enhanced spec's type aliases (e.g. short_answer)
                    # onto the canonical set the app consumes (text/multiple_choice/
                    # true_false) so the output JSON structure stays unchanged.
                    question['type'] = _normalize_question_type(question.get('type'))

                    # Ensure multiple choice questions have options
                    if question['type'] == 'multiple_choice' and ('options' not in question or not question['options']):
                        print(f"Multiple choice question {i+1} missing options, skipping")
                        continue

                    # Always set points based on difficulty if not mixed
                    if difficulty != 'mixed':
                        question['points'] = DIFFICULTY_TO_POINTS.get(difficulty, 300)
                        print(f"Set points to {question['points']} for question {i+1} based on difficulty: {difficulty}")
                    else:
                        # For mixed difficulty, keep the model's points if valid,
                        # otherwise default to 300.
                        try:
                            pts = int(question.get('points'))
                        except (TypeError, ValueError):
                            pts = None
                        if pts not in (100, 200, 300, 400, 500):
                            question['points'] = 300
                            print(f"Normalized points to default (300) for question {i+1} (mixed difficulty)")
                        else:
                            question['points'] = pts

                    # Remove difficulty field if present (as per PRJ-002 rule)
                    if 'difficulty' in question:
                        del question['difficulty']
                        print(f"Removed difficulty field from question {i+1} as per PRJ-002 rule")

                    validated_questions.append(question)
                    print(f"Question {i+1} validated successfully")

                print(f"Validation complete. {len(validated_questions)} of {len(questions)} questions are valid.")
                return validated_questions

            except json.JSONDecodeError as e:
                print(f"JSON parsing error: {str(e)}")
                print(f"Content that failed to parse: {content[:500]}...")  # Print first 500 chars
                return None
            except Exception as e:
                print(f"Error validating questions: {str(e)}")
                print(f"Response content: {content[:500]}...")  # Print first 500 chars
                return None

        except requests.exceptions.RequestException as e:
            print(f"Request error: {str(e)}")
            raise Exception(f"Failed to connect to OpenAI API: {str(e)}")
        except Exception as e:
            print(f"Unexpected error during API call: {str(e)}")
            raise

    def _validate_questions_with_openai(self, questions, source_facts=None, language='english'):
        """Second AI pass: a strict quality-control review of generated questions.

        Implements the validation stage from AI_generator.txt. Best-effort by
        design: on ANY failure (network, parse, empty result) it returns the
        input ``questions`` unchanged so generation never ends up empty.

        Returns:
            tuple(list, dict): (approved_questions, review_summary)
        """
        review_summary = {}
        if not questions:
            return questions, review_summary
        if not self.api_key or not self.api_key.strip():
            return questions, review_summary

        api_key = self.api_key.strip()

        try:
            facts_payload = source_facts if isinstance(source_facts, dict) else {"facts": []}
            lang_note = (
                "Keep all reviewed/approved question text in Arabic."
                if str(language).lower() == 'arabic'
                else "Keep all reviewed/approved question text in English."
            )

            review_prompt = f"""
You are a strict trivia quality-control reviewer.

Review the generated trivia questions against the source facts (when provided).

SOURCE FACTS:
{json.dumps(facts_payload, ensure_ascii=False, separators=(',', ':'))}

GENERATED QUESTIONS:
{json.dumps(questions, ensure_ascii=False, separators=(',', ':'))}

Review each question for:
1. Factual accuracy and staying on the requested topic. Source facts (when provided) are OPTIONAL supporting context - do NOT reject a correct, on-topic question merely because it is not covered by them; reject only off-topic or factually wrong questions.
2. Exactly one correct answer.
3. Clear, unambiguous wording.
4. For multiple_choice: plausible-but-incorrect distractors and a correct_answer matching one option.
5. Whether the points value (100/200/300/400/500) matches the actual difficulty.
6. No duplicate or near-duplicate questions.
7. A correct explanation.

For each question return a status of "approved", "needs_revision", or "rejected".
For "approved" and "needs_revision", include the final corrected question under
"approved_question", preserving the SAME field schema as the input. Use type values
from {{"multiple_choice","true_false","text"}} only. {lang_note}

CRITICAL: you MUST carry through the source-traceability fields UNCHANGED from the
input question — do NOT drop or alter them: "fact_id", "source_fact_used",
"source_title", "source_url", "confidence". These power backend duplicate
detection; losing them corrupts the pipeline.

Return ONLY valid JSON with this exact structure:

{{
  "review_summary": {{ "total_questions": 0, "approved": 0, "rejected": 0, "needs_revision": 0 }},
  "questions": [
    {{
      "status": "approved",
      "issues": [],
      "recommended_fix": "",
      "approved_question": {{
        "type": "multiple_choice",
        "question": "",
        "options": [],
        "correct_answer": "",
        "explanation": "",
        "points": 100,
        "fact_id": "",
        "source_fact_used": "",
        "source_title": "",
        "source_url": "",
        "confidence": "high"
      }}
    }}
  ]
}}
"""

            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            }
            if self.organization:
                headers["OpenAI-Organization"] = str(self.organization)

            data = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": "You are a strict trivia quality-control reviewer. Return JSON only."},
                    {"role": "user", "content": review_prompt},
                ],
                # Low temperature for consistent, conservative review (ignored for reasoning models).
                **self._generation_params(self.max_output_tokens, temperature_override=0.2),
            }
            if self.response_format:
                data["response_format"] = self.response_format
            if self.user:
                data["user"] = self.user

            base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
            url = f"{base}/chat/completions"

            print(f"Running AI validation pass on {len(questions)} questions...")
            response = _post_with_retries(
                url, headers, data,
                timeout=self.request_timeout or 60,
                max_retries=2, backoff=1.5,
            )

            # Handle the json_object "must contain the word 'json'" constraint.
            if response.status_code == 400 and "must contain the word 'json'" in response.text.lower():
                data_no_rf = dict(data)
                data_no_rf.pop("response_format", None)
                response = _post_with_retries(
                    url, headers, data_no_rf,
                    timeout=self.request_timeout or 60,
                    max_retries=2, backoff=1.5,
                )

            if response.status_code != 200:
                print(self._redact_secrets(f"Validation pass failed: {response.status_code} - {response.text[:200]}"))
                return questions, review_summary

            content = response.json()['choices'][0]['message']['content']
            try:
                validation_result = json.loads(content)
            except Exception:
                m = re.search(r'(\{.*\}|\[.*\])', content, re.DOTALL)
                if not m:
                    return questions, review_summary
                validation_result = json.loads(m.group(0))

            review_summary = validation_result.get("review_summary", {}) if isinstance(validation_result, dict) else {}
            approved = extract_approved_questions(validation_result)

            # Re-normalize approved questions to the canonical app schema.
            cleaned = []
            for q in approved:
                if not isinstance(q, dict) or not q.get("question") or "correct_answer" not in q:
                    continue
                q["type"] = _normalize_question_type(q.get("type"))
                if q["type"] == "multiple_choice" and not q.get("options"):
                    continue
                try:
                    pts = int(q.get("points"))
                except (TypeError, ValueError):
                    pts = 300
                q["points"] = pts if pts in (100, 200, 300, 400, 500) else 300
                cleaned.append(q)

            # Only adopt the validated set if it kept a reasonable amount of
            # content; otherwise fall back to the original generated questions.
            if cleaned:
                print(f"Validation kept {len(cleaned)} of {len(questions)} questions.")
                return cleaned, review_summary

            print("Validation produced no usable questions; keeping originals.")
            return questions, review_summary

        except Exception as e:
            print(f"Validation pass error (keeping originals): {self._redact_secrets(str(e))}")
            return questions, review_summary


# Create a singleton instance
ai_question_generator = AIQuestionGenerator()


def start_generation_async(prompt, options=None):
    """Run question generation in a background thread, reporting progress.

    Progress is exposed via get_generation_progress() for the UI to poll. On
    success the progress slot carries the resulting batch_id; on failure it
    carries a redacted error message.

    Returns:
        bool: True if a new generation was started, False if one is already running.
    """
    with _gen_progress_lock:
        if _gen_progress.get("status") == "running":
            return False

    try:
        total = int((options or {}).get('num_questions', 20))
    except (TypeError, ValueError):
        total = 0
    reset_generation_progress(total=total)

    def _run():
        try:
            batch_id, questions = ai_question_generator.generate_questions(prompt, options)
            _set_generation_progress(
                status="success",
                percent=100,
                generated=len(questions),
                batch_id=batch_id,
                message=f"Generated {len(questions)} questions.",
            )
        except Exception as e:
            _set_generation_progress(
                status="failed",
                message="Generation failed.",
                error=AIQuestionGenerator._redact_secrets(str(e)),
            )

    threading.Thread(target=_run, daemon=True).start()
    return True


def generate_questions(prompt, options=None):
    """
    Generate questions based on a prompt and options.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        prompt (str): The prompt to generate questions from
        options (dict, optional): Options for generation. Defaults to None.
            Possible options:
            - question_type: Type of questions to generate (mixed, multiple_choice, true_false, text)
            - difficulty: Difficulty level (mixed, easy, medium, hard)
            - num_questions: Number of questions to generate
            - include_explanations: Whether to include explanations for correct answers
            - language: Language for questions (english, arabic)
            - api_key: OpenAI API key
            - model: OpenAI model to use
            - temperature: Temperature for generation
            - max_output_tokens: Maximum output tokens for generation

    Returns:
        tuple: (batch_id, questions) where batch_id is a unique identifier for this batch
            and questions is a list of generated question dictionaries
    """
    return ai_question_generator.generate_questions(prompt, options)

def get_batch(batch_id):
    """
    Get a batch of generated questions by ID.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        batch_id (str): The batch ID

    Returns:
        list: The list of questions in the batch, or None if not found
    """
    return ai_question_generator.get_batch(batch_id)

def get_batch_metadata(batch_id):
    """
    Get metadata for a batch of generated questions by ID.

    This is a standalone function that uses the AIQuestionGenerator class.

    Args:
        batch_id (str): The batch ID

    Returns:
        dict: The metadata for the batch, or None if not found or no metadata exists
    """
    return ai_question_generator.get_batch_metadata(batch_id)

def get_all_batches():
    """
    Get a list of all available question batches.

    This is a standalone function that uses the AIQuestionGenerator class.

    Returns:
        list: A list of dictionaries containing batch_id and metadata for each batch,
              sorted by timestamp (newest first)
    """
    batches = []

    # Get the path to the AI generated questions folder
    folder_path = ai_question_generator.temp_storage_path

    # List all JSON files in the folder
    if os.path.exists(folder_path):
        for filename in os.listdir(folder_path):
            if filename.endswith('.json'):
                batch_id = filename[:-5]  # Remove .json extension
                metadata = get_batch_metadata(batch_id)

                # If metadata is None, create a minimal metadata object with file creation time
                if not metadata:
                    file_path = os.path.join(folder_path, filename)
                    metadata = {
                        'timestamp': datetime.fromtimestamp(os.path.getctime(file_path)).isoformat(),
                        'prompt': 'Unknown (File format not recognized)',
                        'question_type': 'unknown',
                        'difficulty': 'unknown',
                        'language': 'unknown',
                        'num_questions': 'unknown'
                    }

                # Always add the batch to the list
                batches.append({
                    'batch_id': batch_id,
                    'metadata': metadata
                })

    # Sort batches by timestamp (newest first)
    batches.sort(key=lambda x: x['metadata'].get('timestamp', ''), reverse=True)

    return batches



def verify_api_connection(api_key: str,
                          model: str = "gpt-4o-mini",
                          temperature: float = 0.55,
                          top_p: float = 1.0,
                          frequency_penalty: float = 0.0,
                          presence_penalty: float = 0.0,
                          response_format=None,
                          base_url: str = "https://api.openai.com/v1",
                          organization: str = None,
                          user: str = None,
                          request_timeout: float = 60.0,
                          seed: int = 0):
    """Standalone helper to verify OpenAI connectivity with the provided key.

    Returns:
        tuple(bool, str): success flag and diagnostic message.
    """
    try:
        gen = AIQuestionGenerator()
        gen.api_key = (api_key or "").strip()
        # Clean potential accidental prefix
        if gen.api_key.lower().startswith("bearer "):
            gen.api_key = gen.api_key[7:].strip()
        gen.model = model or gen.model
        gen.temperature = float(temperature)
        gen.top_p = float(top_p)
        gen.frequency_penalty = float(frequency_penalty)
        gen.presence_penalty = float(presence_penalty)
        gen.response_format = response_format
        gen.base_url = base_url or gen.base_url
        gen.organization = organization
        gen.user = user
        gen.request_timeout = float(request_timeout or 60)
        try:
            gen.seed = int(seed or 0)
        except Exception:
            gen.seed = 0
        return gen.verify_api_connection()
    except Exception as e:
        # Use the class redactor to avoid leaking keys
        try:
            msg = AIQuestionGenerator._redact_secrets(str(e))
        except Exception:
            msg = str(e)
        return False, msg
