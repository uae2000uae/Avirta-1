"""
Anthropic (Claude) AI question generator for Avirta.

A clean, self-contained implementation of the source-grounded generation
pipeline described in ``AI_generator.txt`` (the rules document), built on the
Anthropic Messages API:

    topic/prompt
        -> retrieve source facts (Wikipedia RAG)
        -> generate questions from facts only  (Claude, strict JSON)
        -> AI validation pass                  (Claude, strict JSON)
        -> deterministic (code) validation
        -> remove duplicates (within batch + against recent batches)
        -> save batch (same format/folder as the OpenAI generator)

It deliberately REUSES the shared helpers already proven in
``ai_question_generator`` (fact retrieval, difficulty distribution, duplicate
detection, code validation, progress reporting and batch persistence) so the
rest of the app - history, preview, saving to the bank - works unchanged
regardless of which provider produced a batch.

The API key is read from the ``ANTHROPIC_API_KEY`` secret (Google Secret
Manager / env) via the centralized settings loader; callers pass it in through
``options['api_key']``.
"""
from __future__ import annotations

import json
import re
import uuid
import threading
from datetime import datetime

# Reuse the battle-tested helpers + shared state from the OpenAI generator so
# both providers behave identically everywhere except the actual model call.
from questionmanagement.ai_question_generator import (
    ai_question_generator,            # singleton: _save_batch / get_batch / temp_storage_path
    build_source_facts,
    build_difficulty_distribution,
    calculate_distribution,
    extract_approved_questions,
    filter_duplicates,
    collect_existing_questions_from_bank,
    code_filter_valid_questions,
    _normalize_question_type,
    _post_with_retries,
    DIFFICULTY_TO_POINTS,
    # Shared progress slot so the existing /api/ai/generation_progress endpoint
    # and the generator page's progress bar work for Anthropic too.
    reset_generation_progress,
    _set_generation_progress,
    get_generation_progress,
)
from contents.admin_controls.anthropic_models import (
    is_known_model,
    get_max_output_tokens,
    sampling_is_deprecated,
    DEFAULT_MODEL,
)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"

# The five-level points system from the rules document.
POINT_LEVELS = (100, 200, 300, 400, 500)


# --------------------------------------------------------------------------- #
# Low-level Claude call
# --------------------------------------------------------------------------- #
def _redact(text: str) -> str:
    """Mask Anthropic-style keys in any message we might surface to the UI."""
    try:
        return re.sub(r"sk-ant-[A-Za-z0-9_\-]{5,}", "sk-ant-***REDACTED***", str(text))
    except Exception:
        return str(text)


def _extract_json(text: str):
    """Best-effort parse of a JSON object/array from a model reply.

    Claude is instructed to return raw JSON, but we still tolerate stray prose or
    ```json fences by stripping fences and slicing to the outermost braces/brackets.
    """
    if not text:
        raise ValueError("Empty response from Claude.")
    s = text.strip()
    # Strip ```json ... ``` / ``` ... ``` fences if present.
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
        s = re.sub(r"\s*```$", "", s).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    # Fall back to the outermost JSON span.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = s.find(opener)
        end = s.rfind(closer)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(s[start:end + 1])
            except Exception:
                continue
    raise ValueError("Could not parse JSON from Claude response.")


def _call_claude(api_key, model, system_prompt, user_prompt, max_tokens,
                 temperature=0.7, top_p=1.0, timeout=60.0):
    """Send a single Messages API request and return the parsed JSON payload.

    Raises ValueError with a redacted message on any HTTP/parse failure.
    """
    headers = {
        "x-api-key": (api_key or "").strip(),
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    body = {
        "model": model,
        "max_tokens": int(max_tokens),
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    }
    # Opus 4.7+ retired temperature/top_p/top_k and returns HTTP 400 if they are
    # sent. Only include sampling params for models that still accept them.
    if not sampling_is_deprecated(model):
        body["temperature"] = max(0.0, min(float(temperature), 1.0))
        body["top_p"] = max(0.0, min(float(top_p), 1.0))

    resp = _post_with_retries(
        ANTHROPIC_API_URL, headers, body,
        timeout=timeout or 60, max_retries=2, backoff=1.5,
    )
    if resp.status_code != 200:
        raise ValueError(_redact(f"Anthropic API error {resp.status_code}: {resp.text[:500]}"))

    data = resp.json()
    # Messages API returns content as a list of blocks; concatenate text blocks.
    parts = [b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"]
    text = "".join(parts).strip()
    if not text:
        raise ValueError("Claude returned no text content.")
    return _extract_json(text)


# --------------------------------------------------------------------------- #
# Prompt building (from the rules document, adapted for Claude)
# --------------------------------------------------------------------------- #
_DIFFICULTY_SPEC = (
    "DIFFICULTY POINT SYSTEM (each question uses exactly one of these point values):\n"
    "- 100 = Very easy: direct recall of a well-known fact; no reasoning.\n"
    "- 200 = Easy: simple recognition or a one-step factual question.\n"
    "- 300 = Medium: requires connecting two facts or understanding context.\n"
    "- 400 = Hard: requires comparison, chronology, classification or cause/effect.\n"
    "- 500 = Very hard: requires deeper reasoning, multi-step deduction, or fine distinctions - still fair.\n"
)


def _type_instruction(question_type):
    """Translate the app's question_type option into a prompt instruction."""
    if not question_type or question_type == "mixed":
        return "Use a natural mix of the allowed question types."
    selected = [t.strip() for t in str(question_type).split(",") if t.strip()]
    if len(selected) == 1:
        return f"Only generate '{selected[0]}' questions."
    return f"Only generate questions of these types: {', '.join(selected)} (roughly evenly)."


def build_generation_prompt(topic, category, source_facts, question_count,
                            distribution, question_type="mixed",
                            language="arabic", include_explanations=True):
    """Return (system_prompt, user_prompt) for the generation call."""
    facts = (source_facts or {}).get("facts") or []
    grounded = bool(facts)
    lang_line = (
        "Write every question, option, answer and explanation in Arabic, using correct Arabic grammar."
        if str(language).lower() == "arabic"
        else "Write every question, option, answer and explanation in English."
    )

    system_prompt = (
        "You are an expert trivia question designer for a high-quality trivia game. "
        "You always return strict, valid JSON only - no markdown, no commentary."
    )

    sections = [
        f"TOPIC: {topic}",
        f"CATEGORY: {category}",
        f"Generate exactly {question_count} trivia questions.",
        _DIFFICULTY_SPEC,
        "TARGET DIFFICULTY DISTRIBUTION (points: count): "
        + json.dumps(distribution, separators=(",", ":")),
    ]

    if grounded:
        facts_json = json.dumps(facts, ensure_ascii=False, separators=(",", ":"))
        sections.append(
            'SOURCE FACTS (verified) - each has "fact_id", "fact", "source_title", "source_url".\n'
            "Build questions using ONLY these facts. Do not invent facts. Use each fact for at most one question.\n"
            f"FACT POOL: {facts_json}\n"
            'For EVERY question, copy from the single fact you used: "fact_id", '
            '"source_fact_used" (that fact\'s exact text), "source_title", "source_url".'
        )
    else:
        sections.append(
            "There are no retrieved source facts; rely on widely-accepted general knowledge "
            "and only state facts you are confident are correct."
        )

    rules = [
        "Each question has exactly one correct answer.",
        "Avoid ambiguous wording and near-duplicate questions.",
        "Mix question styles; do not repeatedly ask the same kind of fact.",
        'Never mention "source", "passage" or "provided facts" in a question.',
        _type_instruction(question_type),
        "multiple_choice: exactly 4 plausible options, only one correct, no 'All/None of the above', randomize the correct position.",
        "true_false: avoid trivially obvious statements; false statements must be realistically false.",
        "text: the answer is short and specific; include acceptable alternatives if relevant.",
    ]
    if include_explanations:
        rules.append("Include a short, correct 'explanation' for each question.")
    else:
        rules.append("Do not include explanations (use an empty string).")
    rules.append(lang_line)
    sections.append("RULES:\n" + "\n".join(f"- {r}" for r in rules))

    sections.append(
        "OUTPUT FORMAT - return ONLY this JSON object (no markdown):\n"
        "{\n"
        '  "questions": [\n'
        "    {\n"
        '      "type": "multiple_choice | true_false | text",\n'
        '      "question": "",\n'
        '      "options": ["", "", "", ""],\n'
        '      "correct_answer": "",\n'
        '      "acceptable_answers": [],\n'
        '      "explanation": "",\n'
        '      "points": 100,\n'
        '      "fact_id": "",\n'
        '      "source_fact_used": "",\n'
        '      "source_title": "",\n'
        '      "source_url": ""\n'
        "    }\n"
        "  ]\n"
        "}\n"
        "For true_false and text questions use an empty options array []. "
        "For true_false, correct_answer must be exactly \"True\" or \"False\"."
    )

    user_prompt = (
        f"Generate {question_count} questions about: {topic}. "
        "Respond strictly with the JSON object described above and nothing else."
    )
    return system_prompt, "\n\n".join(sections) + "\n\n" + user_prompt


def build_validation_prompt(source_facts, generated_questions):
    """Return (system_prompt, user_prompt) for the validation/review call."""
    facts = (source_facts or {}).get("facts") or []
    system_prompt = (
        "You are a strict trivia quality-control reviewer. "
        "You always return strict, valid JSON only - no markdown, no commentary."
    )
    user_prompt = (
        "Review the generated trivia questions" + (" against the source facts" if facts else "") + ".\n\n"
        + ("SOURCE FACTS: " + json.dumps(facts, ensure_ascii=False, separators=(",", ":")) + "\n\n" if facts else "")
        + "GENERATED QUESTIONS: "
        + json.dumps(generated_questions, ensure_ascii=False, separators=(",", ":"))
        + "\n\nFor each question check: factual accuracy; the answer is fully supported"
        + (" by the source facts" if facts else "")
        + "; exactly one correct answer; clear and unambiguous; distractors plausible but wrong; "
        "the points value fits the 100/200/300/400/500 scale; not a duplicate; explanation correct.\n\n"
        "Fix minor issues in place and mark such questions 'needs_revision'. Approve good ones. "
        "Reject questions that are wrong or unfixable.\n\n"
        "Return ONLY this JSON object:\n"
        "{\n"
        '  "review_summary": {"total_questions": 0, "approved": 0, "rejected": 0, "needs_revision": 0},\n'
        '  "questions": [\n'
        "    {\n"
        '      "status": "approved | needs_revision | rejected",\n'
        '      "issues": [],\n'
        '      "approved_question": {\n'
        '        "type": "", "question": "", "options": [], "correct_answer": "",\n'
        '        "acceptable_answers": [], "explanation": "", "points": 100,\n'
        '        "fact_id": "", "source_fact_used": "", "source_title": "", "source_url": ""\n'
        "      }\n"
        "    }\n"
        "  ]\n"
        "}\n"
        "For rejected questions set approved_question to null."
    )
    return system_prompt, user_prompt


# --------------------------------------------------------------------------- #
# Question normalization
# --------------------------------------------------------------------------- #
def _coerce_points(value):
    """Snap any model-emitted points value onto the nearest allowed level."""
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return 300
    if n in POINT_LEVELS:
        return n
    return min(POINT_LEVELS, key=lambda lvl: abs(lvl - n))


def _normalize_questions(raw_questions, default_points=300):
    """Coerce raw model output into the app's canonical question shape.

    Keeps the source-tracing fields (fact_id/source_*) so both duplicate
    detection and code validation can use them; the fields are harmless to the
    downstream save/preview flow.
    """
    normalized = []
    for q in raw_questions or []:
        if not isinstance(q, dict):
            continue
        qtype = _normalize_question_type(q.get("type"))
        options = q.get("options") or []
        if qtype != "multiple_choice":
            options = []  # only MCQs carry options
        item = {
            "type": qtype,
            "question": (q.get("question") or "").strip(),
            "options": [str(o).strip() for o in options],
            "correct_answer": str(q.get("correct_answer", "")).strip(),
            "explanation": (q.get("explanation") or "").strip(),
            "points": _coerce_points(q.get("points", default_points)),
        }
        # Carry through optional metadata when present.
        for key in ("acceptable_answers", "fact_id", "source_fact_used", "source_title", "source_url"):
            if q.get(key):
                item[key] = q[key]
        if item["question"] and item["correct_answer"]:
            normalized.append(item)
    return normalized


# --------------------------------------------------------------------------- #
# Generator
# --------------------------------------------------------------------------- #
class AnthropicQuestionGenerator:
    """Generates trivia questions with Claude following the rules-doc pipeline."""

    def __init__(self):
        self.api_key = None
        self.model = DEFAULT_MODEL
        self.temperature = 0.7
        self.top_p = 1.0
        self.max_output_tokens = 8192
        self.request_timeout = 60.0

    def _apply_options(self, options):
        api_key = (options.get("api_key") or self.api_key or "").strip()
        if api_key.lower().startswith("bearer "):
            api_key = api_key[7:].strip()
        self.api_key = api_key
        model = options.get("model") or self.model
        self.model = model if is_known_model(model) else DEFAULT_MODEL
        self.temperature = float(options.get("temperature", self.temperature))
        self.top_p = float(options.get("top_p", self.top_p))
        cap = get_max_output_tokens(self.model)
        try:
            self.max_output_tokens = max(1, min(int(options.get("max_output_tokens", self.max_output_tokens)), cap))
        except (TypeError, ValueError):
            self.max_output_tokens = min(8192, cap)
        try:
            self.request_timeout = float(options.get("request_timeout", self.request_timeout) or 60)
        except (TypeError, ValueError):
            self.request_timeout = 60.0

    def verify_api_connection(self):
        """Cheap round-trip to confirm the key/model work. Returns (ok, message)."""
        if not self.api_key:
            return False, "No Anthropic API key provided."
        try:
            headers = {
                "x-api-key": self.api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "content-type": "application/json",
            }
            body = {
                "model": self.model,
                "max_tokens": 16,
                "messages": [{"role": "user", "content": "Reply with the single word: OK"}],
            }
            resp = _post_with_retries(ANTHROPIC_API_URL, headers, body, timeout=20, max_retries=1)
            if resp.status_code == 200:
                return True, f"Connected to Anthropic ({self.model})."
            return False, _redact(f"HTTP {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            return False, _redact(str(e))

    def generate_questions(self, prompt, options=None):
        """Run the full pipeline and return (batch_id, questions)."""
        options = options or {}
        self._apply_options(options)
        if not self.api_key:
            raise ValueError("No Anthropic API key configured. Set the ANTHROPIC_API_KEY secret.")

        topic = (prompt or "").strip()
        if not topic:
            raise ValueError("A topic/prompt is required.")
        category = (options.get("category") or topic).strip()
        num_questions = int(options.get("num_questions", 20) or 20)
        question_type = options.get("question_type", "mixed")
        difficulty = options.get("difficulty", "mixed")
        language = options.get("language", "arabic")
        include_explanations = bool(options.get("include_explanations", True))
        use_source_grounding = bool(options.get("use_source_grounding", True))
        use_validation = bool(options.get("use_validation", True))

        distribution = build_difficulty_distribution(num_questions, difficulty)

        # 1) Retrieve source facts (RAG). Optional / best-effort.
        _set_generation_progress(percent=10, message="Retrieving source facts…")
        source_facts = {"topic": topic, "facts": []}
        if use_source_grounding:
            try:
                lang_code = "ar" if str(language).lower() == "arabic" else "en"
                source_facts = build_source_facts(topic, lang=lang_code)
            except Exception as e:
                print(f"[anthropic] source fact retrieval failed, continuing ungrounded: {e}")
        grounded = bool(source_facts.get("facts"))

        # 2) Generate.
        _set_generation_progress(percent=35, message="Generating questions with Claude…")
        gen_system, gen_user = build_generation_prompt(
            topic, category, source_facts, num_questions, distribution,
            question_type=question_type, language=language,
            include_explanations=include_explanations,
        )
        gen_data = _call_claude(
            self.api_key, self.model, gen_system, gen_user,
            self.max_output_tokens, self.temperature, self.top_p, self.request_timeout,
        )
        raw_questions = gen_data.get("questions", gen_data) if isinstance(gen_data, dict) else gen_data
        questions = _normalize_questions(raw_questions)

        # Deterministic structural validation (source required only when grounded).
        questions, _rejected = code_filter_valid_questions(questions, require_source=grounded)

        # 3) AI validation pass.
        if use_validation and questions:
            _set_generation_progress(percent=65, message="Validating questions with Claude…")
            try:
                val_system, val_user = build_validation_prompt(source_facts, questions)
                val_data = _call_claude(
                    self.api_key, self.model, val_system, val_user,
                    self.max_output_tokens, 0.2, 1.0, self.request_timeout,
                )
                approved = extract_approved_questions(val_data)
                approved = _normalize_questions(approved)
                approved, _ = code_filter_valid_questions(approved, require_source=False)
                if approved:
                    questions = approved
            except Exception as e:
                print(f"[anthropic] validation pass failed, keeping generated set: {e}")

        # 4) Remove duplicates (within batch + against recent batches).
        _set_generation_progress(percent=85, message="Removing duplicates…")
        try:
            existing = collect_existing_questions_from_bank()
        except Exception:
            existing = []
        questions, _dupes = filter_duplicates(questions, existing)

        if not questions:
            raise ValueError("No valid questions were produced. Try a broader topic or fewer constraints.")

        # 5) Save batch (same folder/format as the OpenAI generator).
        batch_id = str(uuid.uuid4())
        metadata = {
            "prompt": topic,
            "question_type": question_type if question_type else "mixed",
            "difficulty": difficulty,
            "num_questions": len(questions),
            "include_explanations": include_explanations,
            "language": language,
            "timestamp": datetime.now().isoformat(),
            "provider": "anthropic",
            "model": self.model,
            "difficulty_distribution": calculate_distribution(questions),
            "grounded": grounded,
        }
        ai_question_generator._save_batch(batch_id, questions, metadata)
        # Mirror into the singleton's in-memory cache so get_batch() finds it immediately.
        ai_question_generator.question_batches[batch_id] = questions
        return batch_id, questions


# Module-level singleton + thin functional wrappers (mirrors ai_question_generator's API).
anthropic_question_generator = AnthropicQuestionGenerator()


def generate_questions(prompt, options=None):
    """Standalone generation entry point using the Anthropic generator."""
    return anthropic_question_generator.generate_questions(prompt, options)


def start_generation_async(prompt, options=None):
    """Run Anthropic generation in a background thread, reporting shared progress.

    Uses the same progress slot as the OpenAI generator so the existing polling
    endpoint / progress bar work unchanged. Returns False if a run is active.
    """
    if get_generation_progress().get("status") == "running":
        return False
    try:
        total = int((options or {}).get("num_questions", 20))
    except (TypeError, ValueError):
        total = 0
    reset_generation_progress(total=total)

    def _run():
        try:
            batch_id, questions = anthropic_question_generator.generate_questions(prompt, options)
            _set_generation_progress(
                status="success", percent=100, generated=len(questions),
                batch_id=batch_id, message=f"Generated {len(questions)} questions.",
            )
        except Exception as e:
            _set_generation_progress(status="failed", message="Generation failed.", error=_redact(str(e)))

    threading.Thread(target=_run, daemon=True).start()
    return True


def verify_api_connection(api_key, model=DEFAULT_MODEL, request_timeout=20.0):
    """Standalone connection check for the admin 'test key' flow."""
    gen = AnthropicQuestionGenerator()
    gen.api_key = (api_key or "").strip()
    gen.model = model if is_known_model(model) else DEFAULT_MODEL
    gen.request_timeout = request_timeout
    return gen.verify_api_connection()
