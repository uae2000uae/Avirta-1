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
# generated. Mirrors the polling pattern used by github_integration.py. This is a
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


def build_source_facts(topic: str, lang: str = "en") -> dict:
    """Build a best-effort source-facts package for grounding generation.

    An empty ``facts`` list is allowed; generation then falls back to general
    knowledge. Can be extended later with Wikidata/DBpedia/Open Trivia DB.
    """
    facts = []
    wiki = fetch_wikipedia_summary(topic, lang=lang)
    if wiki.get("extract"):
        facts.append({
            "source": wiki["source_name"],
            "title": wiki["title"],
            "url": wiki["source_url"],
            "text": wiki["extract"],
        })
    return {
        "topic": topic,
        "language": lang,
        "retrieved_at": datetime.now().isoformat(),
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


def _normalize_question_type(qtype: str) -> str:
    """Map model-emitted types onto the app's canonical set.

    The enhanced spec uses ``short_answer``; the app uses ``text``. Keep the
    output JSON consumers happy by collapsing aliases to canonical values.
    """
    t = str(qtype or "").strip().lower()
    if t in ("short_answer", "short", "open", "open_ended", "fill_in_the_blank", "fill_in"):
        return "text"
    if t in ("multiple_choice", "mcq", "multiple-choice"):
        return "multiple_choice"
    if t in ("true_false", "true/false", "boolean", "tf"):
        return "true_false"
    return t or "text"


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
            # Token-aware, chunked generation to reliably reach requested count
            total_questions = []
            batch_sizes = []
            # Build a set of normalized texts already existing in selected reference categories (to avoid repeats)
            existing_normalized = set()
            try:
                if reference_categories:
                    question_bank.load_questions()
                    for category_id in reference_categories:
                        if category_id in question_bank.categories:
                            for qid in question_bank.categories.get(category_id, []):
                                q = question_bank.questions.get(qid)
                                if not q:
                                    continue
                                qtext = _normalize_question_text(q.get('question', ''))
                                if qtext:
                                    existing_normalized.add(qtext)
            except Exception:
                # Best effort; continue without blocking generation
                existing_normalized = set()

            # Track normalized texts we add in this session to prevent duplicates within generated set
            seen_texts = set(existing_normalized)

            # Best-effort RAG: retrieve source facts once for grounding. Never
            # blocks generation — an empty package falls back to general knowledge.
            source_facts = None
            if use_source_grounding:
                try:
                    wiki_lang = 'ar' if str(language).lower() == 'arabic' else 'en'
                    _set_generation_progress(message="Retrieving source facts…")
                    source_facts = build_source_facts(prompt, lang=wiki_lang)
                    if source_facts.get("facts"):
                        print(f"Grounding generation on {len(source_facts['facts'])} retrieved source fact(s).")
                    else:
                        print("No source facts retrieved; generating from general knowledge.")
                except Exception as e:
                    print(f"Source-fact retrieval failed (continuing ungrounded): {e}")
                    source_facts = None

            # Preserve original start index and adjust per batch to conceptually skip earlier candidates
            original_start = int(getattr(self, 'start_index', 0) or 0)

            # Heuristic per-call size: Arabic tends to be longer; keep smaller batch
            default_chunk = 10 if str(language).lower() == 'english' else 7
            remaining = int(num_questions)
            max_batches = max(10, (remaining + default_chunk - 1) // default_chunk + 4)
            batches_done = 0

            while remaining > 0 and batches_done < max_batches:
                per_call = min(default_chunk, remaining)
                # Nudge per_call up if admin configured very high max tokens
                try:
                    if self.max_output_tokens >= 8000 and per_call < 15 and str(language).lower() == 'english':
                        per_call = min(15, remaining)
                except Exception:
                    pass

                # Adjust start_index for this batch to avoid earlier candidates
                setattr(self, 'start_index', original_start + len(total_questions))

                # Soft difficulty target for this chunk (spread across 100–500 when mixed).
                chunk_distribution = build_difficulty_distribution(per_call, difficulty)

                batch = self._generate_questions_with_openai(
                    prompt,
                    question_type,
                    difficulty,
                    per_call,
                    include_explanations,
                    language,
                    reference_categories,
                    source_facts=source_facts,
                    distribution=chunk_distribution
                ) or []

                # De-duplicate by normalized question text
                added = 0
                for q in batch:
                    try:
                        qtext = _normalize_question_text(q.get('question', ''))
                    except Exception:
                        qtext = ''
                    if not qtext or qtext in seen_texts:
                        continue
                    seen_texts.add(qtext)
                    total_questions.append(q)
                    added += 1
                    if len(total_questions) >= num_questions:
                        break

                batch_sizes.append({'requested': per_call, 'received': len(batch), 'added_unique': added})
                remaining = max(0, num_questions - len(total_questions))
                batches_done += 1

                # Report real progress: scale the generation phase (10%–95%) by
                # how many unique questions we've accumulated so far.
                pct = 10 + int(85 * min(1.0, len(total_questions) / max(1, num_questions)))
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

            # Optional second AI pass: strict quality-control review. Best-effort —
            # on failure it returns the generated questions unchanged.
            review_summary = {}
            validated = False
            if questions and use_validation:
                _set_generation_progress(percent=95, message="Validating questions…")
                reviewed, review_summary = self._validate_questions_with_openai(
                    questions, source_facts=source_facts, language=language
                )
                if reviewed:
                    validated = reviewed is not questions
                    questions = reviewed

            # If successful, return the questions
            if questions:
                print(f"Successfully generated {len(questions)} questions with OpenAI API (requested {num_questions}).")
                # Generate a unique batch ID
                batch_id = str(uuid.uuid4())

                # Store the batch
                self.question_batches[batch_id] = questions

                # Create metadata
                metadata = {
                    'prompt': prompt,
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
                    'generation_version': 'v3_rag_points_difficulty',
                    'source_grounded': bool(source_facts and source_facts.get('facts')),
                    'validated': validated,
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
                "temperature": min(max(self.temperature, 0.0), 2.0),
                "top_p": self.top_p,
                "max_tokens": test_max_tokens,
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

        # Create a system prompt that instructs the AI how to format the response.
        # This is the enhanced, source-grounded designer prompt (see
        # questionmanagement/AI_generator.txt). The OUTPUT schema is intentionally
        # pinned to the fields the rest of the app consumes (type/question/options/
        # correct_answer/explanation/points), with optional enrichment fields.
        system_prompt = """
        You are an expert trivia question designer for a high-quality educational trivia game.
        Generate clear, factually accurate questions based on the user's prompt.

        DIFFICULTY POINT SYSTEM (the "points" field doubles as the difficulty signal —
        higher points means a harder or less commonly known question):
        100 = Very easy: direct recall of a well-known, clearly stated fact. No reasoning required.
        200 = Easy: simple recognition or a one-step factual question; slightly less obvious than 100.
        300 = Medium: requires connecting two facts or understanding context; not answerable by only
              recognizing a famous name.
        400 = Hard: requires comparison, chronology, classification, or cause/effect reasoning;
              distractors should be highly plausible.
        500 = Very hard: requires deeper reasoning, multi-step deduction, less obvious facts, or careful
              distinction between similar concepts. Must still be fair and fully answerable.

        QUESTION REQUIREMENTS:
        1. Each question must have exactly one correct answer.
        2. Do not invent facts; do not produce trick questions.
        3. Avoid ambiguous wording.
        4. Avoid duplicate or near-duplicate questions, and avoid asking the same kind of fact repeatedly.
        5. Mix question styles and phrasing.
        6. Do not mention "source", "passage", "context", or "provided facts" inside the question text.

        MULTIPLE CHOICE RULES:
        - Provide exactly 4 options.
        - Exactly one option is correct; "correct_answer" must match one option verbatim.
        - Distractors must be plausible but clearly incorrect.
        - Do not use "All of the above" or "None of the above"; vary the position of the correct option.

        TRUE/FALSE RULES:
        - Avoid trivially obvious statements; false statements must be realistically false.

        TEXT (SHORT ANSWER) RULES:
        - The answer must be short and specific.

        OUTPUT FORMAT:
        Return ONLY valid JSON: a JSON array of question objects (no markdown, no commentary).
        Use exactly these object shapes.

        For multiple-choice questions:
        {
            "type": "multiple_choice",
            "question": "The question text",
            "options": ["Option A", "Option B", "Option C", "Option D"],
            "correct_answer": "The correct option (exactly matching one of the options)",
            "explanation": "Explanation of why this is the correct answer",
            "points": 100|200|300|400|500
        }

        For true/false questions:
        {
            "type": "true_false",
            "question": "The question text",
            "correct_answer": "True|False",
            "explanation": "Explanation of why this is correct",
            "points": 100|200|300|400|500
        }

        For text questions:
        {
            "type": "text",
            "question": "The question text",
            "correct_answer": "The correct answer",
            "explanation": "Explanation of why this is correct",
            "points": 100|200|300|400|500
        }
        """

        # Source-grounded (RAG) block: if we retrieved verified facts, require the
        # model to generate strictly from them; otherwise rely on general knowledge
        # but still demand factual accuracy.
        grounding_facts = []
        try:
            if isinstance(source_facts, dict):
                grounding_facts = source_facts.get("facts", []) or []
        except Exception:
            grounding_facts = []

        if grounding_facts:
            system_prompt += f"""

        SOURCE FACTS (verified). Generate questions using ONLY the information below.
        Do not introduce facts that are not supported by these sources:
        {json.dumps(source_facts, ensure_ascii=False, indent=2)}
            """
        else:
            system_prompt += (
                "\nThere are no retrieved source facts; rely on widely-accepted general knowledge "
                "and only state facts you are confident are correct."
            )

        # Add existing questions to the system prompt if available
        if existing_questions:
            existing_questions_text = "\n".join([f"- {q}" for q in existing_questions[:50]])  # Limit to 50 questions to avoid token limits
            system_prompt += f"""

            IMPORTANT: Avoid generating questions that are similar to the following existing questions:
            {existing_questions_text}

            If there are more than 50 existing questions, I've only shown you a subset. Please try to generate questions that are substantially different from these and would explore new aspects of the topic.
            """

        # Add specific instructions based on options. question_type may be a
        # single type, a comma-separated subset of types, or 'mixed' (all types).
        if question_type and question_type != 'mixed':
            selected_types = [t.strip() for t in str(question_type).split(',') if t.strip()]
            if len(selected_types) == 1:
                system_prompt += f"\nOnly generate {selected_types[0]} questions."
            elif selected_types:
                system_prompt += (
                    f"\nOnly generate questions of these types: {', '.join(selected_types)}. "
                    "Distribute the questions roughly evenly across these types."
                )

        if difficulty != 'mixed':
            # Map difficulty to points
            points_value = DIFFICULTY_TO_POINTS.get(difficulty, 0)  # Get the correct point value
            system_prompt += f"\nAll questions should have {points_value} points."
        else:
            system_prompt += "\nGenerate questions across all difficulty levels."
            # Provide a soft target distribution across the five point levels.
            if isinstance(distribution, dict) and any(distribution.values()):
                system_prompt += (
                    "\nAim for approximately this distribution of point values "
                    f"(points: count): {json.dumps(distribution)}."
                )

        if not include_explanations:
            system_prompt += "\nDo not include explanations."

        # Add language-specific instructions
        if language.lower() == 'arabic':
            system_prompt += "\nGenerate all questions and answers in Arabic language. Use proper Arabic grammar and vocabulary."
        else:
            system_prompt += "\nGenerate all questions and answers in English language."

        # Create the user prompt
        user_prompt = f"Generate {num_questions} questions about: {prompt}"
        # If start_index > 0, instruct the model to conceptually skip earlier results
        if isinstance(self.start_index, int) and self.start_index > 0:
            system_prompt += f"\nWhen listing or selecting candidate questions, start at index {self.start_index} (skip the first {self.start_index} possible results)."
            user_prompt += f" Also, skip the first {self.start_index} possible results when selecting which questions to output."

        # If JSON response_format is requested, explicitly instruct JSON output in both messages
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
            system_prompt += "\nReturn only JSON. Respond with a single valid JSON object or array adhering to the expected schema. Do not include any non-JSON text."
            user_prompt = (
                f"Produce JSON only. Generate {num_questions} questions about: {prompt}. "
                "Respond strictly in JSON."
            )

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
            "temperature": min(max(self.temperature, 0.0), 2.0),
            "top_p": self.top_p,
            "frequency_penalty": self.frequency_penalty,
            "presence_penalty": self.presence_penalty,
            "max_tokens": self.max_output_tokens,
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
{json.dumps(facts_payload, ensure_ascii=False, indent=2)}

GENERATED QUESTIONS:
{json.dumps(questions, ensure_ascii=False, indent=2)}

Review each question for:
1. Factual accuracy (and, when source facts are provided, support by those facts).
2. Exactly one correct answer.
3. Clear, unambiguous wording.
4. For multiple_choice: plausible-but-incorrect distractors and a correct_answer matching one option.
5. Whether the points value (100/200/300/400/500) matches the actual difficulty.
6. No duplicate or near-duplicate questions.
7. A correct explanation.

For each question return a status of "approved", "needs_revision", or "rejected".
For "approved" and "needs_revision", include the final corrected question under
"approved_question", preserving the SAME field schema as the input
(type/question/options/correct_answer/explanation/points). Use type values from
{{"multiple_choice","true_false","text"}} only. {lang_note}

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
        "points": 100
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
                # Low temperature for consistent, conservative review.
                "temperature": min(max(0.2, 0.0), 2.0),
                "top_p": self.top_p,
                "max_tokens": self.max_output_tokens,
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
