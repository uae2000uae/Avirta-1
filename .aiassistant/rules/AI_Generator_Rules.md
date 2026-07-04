---
apply: always
---

Below is a **full end-to-end upgraded version** of your AI trivia generation flow, redesigned around:

* **RAG / source-grounded generation**
* **Wikipedia/Wikidata/Open Trivia DB style retrieval**
* **strict JSON output**
* **AI validation**
* **duplicate checking**
* **5-level difficulty system using points: 100, 200, 300, 400, 500**
* **batch saving and progress tracking**, aligned with the structure already present in your uploaded module, which includes progress tracking, async generation, retries, batch retrieval, metadata handling, duplicate normalization, and API connection verification. [\[dbpedia.org\]](https://www.dbpedia.org/resources/sparql/)

***

# Recommended End-to-End Flow

```text
Admin enters topic/category
        ↓
Retrieve source facts
        ↓
Generate questions from facts only
        ↓
Validate questions
        ↓
Score difficulty as 100 / 200 / 300 / 400 / 500
        ↓
Remove duplicates
        ↓
Save approved batch
        ↓
Return batch ID + generated questions
```

***

# Difficulty System: 5 Levels

Use points instead of “easy / medium / hard”.

```python
DIFFICULTY_LEVELS = {
    100: "Very easy: direct recall of a basic fact.",
    200: "Easy: simple recognition or one-step factual question.",
    300: "Medium: requires connecting two facts or understanding context.",
    400: "Hard: requires comparison, chronology, or classification.",
    500: "Very hard: requires deeper reasoning, less obvious facts, or multi-step deduction."
}
```

Example distribution for 25 questions:

```python
DEFAULT_DISTRIBUTION = {
    100: 6,
    200: 6,
    300: 5,
    400: 4,
    500: 4
}
```

***

# Production Prompt: Question Generation

Use this as your **main generation prompt**.

```text
You are an expert trivia question designer for a high-quality trivia game.

Your task is to generate trivia questions using ONLY the verified source facts provided below.

SOURCE FACTS:
{{source_facts}}

TOPIC:
{{topic}}

CATEGORY:
{{category}}

Generate exactly {{question_count}} questions.

DIFFICULTY POINT SYSTEM:
Each question must have one of these point values:

100 = Very easy:
- Direct recall of a well-known or clearly stated fact.
- No reasoning required.

200 = Easy:
- Simple recognition.
- One-step factual question.
- Slightly less obvious than 100.

300 = Medium:
- Requires connecting two facts.
- Requires understanding context.
- Not answerable by only recognizing a famous name.

400 = Hard:
- Requires comparison, chronology, classification, or cause/effect reasoning.
- Distractors should be highly plausible.

500 = Very hard:
- Requires deeper reasoning, multi-step deduction, less obvious facts, or careful distinction between similar concepts.
- Should still be fair and fully supported by the source facts.

QUESTION REQUIREMENTS:
1. Use only the source facts.
2. Do not invent facts.
3. Each question must have exactly one correct answer.
4. Avoid ambiguous wording.
5. Avoid duplicate or near-duplicate questions.
6. Mix question styles.
7. Avoid asking the same type of fact repeatedly.
8. Do not mention “source”, “passage”, or “provided facts” in the question.

QUESTION TYPES:
Use a mix of:
- multiple_choice
- true_false
- short_answer

MULTIPLE CHOICE RULES:
- Provide exactly 4 options.
- Only one option may be correct.
- Distractors must be plausible but incorrect.
- Do not use “All of the above” or “None of the above”.
- Randomize the correct answer position.

TRUE/FALSE RULES:
- Avoid obvious true/false statements.
- False statements must be realistically false.

SHORT ANSWER RULES:
- Answer should be short and specific.
- Include acceptable alternative answers if relevant.

OUTPUT FORMAT:
Return ONLY valid JSON.
Do not include markdown.
Do not include commentary.

Use this exact structure:

{
  "batch_metadata": {
    "topic": "{{topic}}",
    "category": "{{category}}",
    "question_count": {{question_count}},
    "difficulty_distribution": {
      "100": 0,
      "200": 0,
      "300": 0,
      "400": 0,
      "500": 0
    },
    "generation_version": "v3_rag_points_difficulty"
  },
  "questions": [
    {
      "id": "",
      "question": "",
      "type": "multiple_choice",
      "points": 100,
      "category": "",
      "subcategory": "",
      "options": ["", "", "", ""],
      "correct_answer": "",
      "acceptable_answers": [],
      "explanation": "",
      "source_fact_used": "",
      "confidence": "high",
      "quality_tags": ["factual", "clear", "non_duplicate"]
    }
  ]
}
```

***

# Validation Prompt

Use this as the **second AI call**.

```text
You are a strict trivia quality-control reviewer.

Review the generated trivia questions against the source facts.

SOURCE FACTS:
{{source_facts}}

GENERATED QUESTIONS:
{{generated_questions_json}}

Review each question for:
1. Factual accuracy.
2. Whether the answer is fully supported by the source facts.
3. Whether there is exactly one correct answer.
4. Whether the question is clear and not ambiguous.
5. Whether distractors are plausible but incorrect.
6. Whether the points value is appropriate:
   - 100 = very easy
   - 200 = easy
   - 300 = medium
   - 400 = hard
   - 500 = very hard
7. Whether the question is duplicated or too similar to another question.
8. Whether the explanation is correct.

Return ONLY valid JSON.

Use this exact structure:

{
  "review_summary": {
    "total_questions": 0,
    "approved": 0,
    "rejected": 0,
    "needs_revision": 0
  },
  "questions": [
    {
      "id": "",
      "status": "approved",
      "issues": [],
      "recommended_fix": "",
      "approved_question": {
        "id": "",
        "question": "",
        "type": "",
        "points": 100,
        "category": "",
        "subcategory": "",
        "options": [],
        "correct_answer": "",
        "acceptable_answers": [],
        "explanation": "",
        "source_fact_used": "",
        "confidence": ""
      }
    }
  ]
}
```

***

# Full End-to-End Python Structure

This is a clean version you can merge into your existing `AIQuestionGenerator` module.

```python
import json
import uuid
import re
import requests
from datetime import datetime


DIFFICULTY_LEVELS = {
    100: "Very easy: direct recall of a basic fact.",
    200: "Easy: simple recognition or one-step factual question.",
    300: "Medium: requires connecting two facts or understanding context.",
    400: "Hard: requires comparison, chronology, or classification.",
    500: "Very hard: requires deeper reasoning or multi-step deduction."
}


DEFAULT_DISTRIBUTION = {
    100: 2,
    200: 2,
    300: 2,
    400: 2,
    500: 2
}


def normalize_question_text(text: str) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text


def fetch_wikipedia_summary(topic: str) -> dict:
    """
    Fetch a short encyclopedic summary from Wikipedia.
    """
    safe_topic = topic.replace(" ", "_")
    url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_topic}"

    response = requests.get(
        url,
        timeout=20,
        headers={
            "User-Agent": "TriviaQuestionGenerator/1.0"
        }
    )

    if response.status_code != 200:
        return {}

    data = response.json()

    return {
        "source_name": "Wikipedia",
        "source_url": data.get("content_urls", {}).get("desktop", {}).get("page", ""),
        "title": data.get("title", topic),
        "extract": data.get("extract", "")
    }


def build_source_facts(topic: str) -> dict:
    """
    Builds a source-facts package for the AI.
    You can later extend this with Wikidata, DBpedia, Open Trivia DB, or your own database.
    """
    wikipedia_data = fetch_wikipedia_summary(topic)

    facts = []

    if wikipedia_data.get("extract"):
        facts.append({
            "source": wikipedia_data["source_name"],
            "title": wikipedia_data["title"],
            "url": wikipedia_data["source_url"],
            "text": wikipedia_data["extract"]
        })

    return {
        "topic": topic,
        "retrieved_at": datetime.utcnow().isoformat(),
        "facts": facts
    }


def build_generation_prompt(topic, category, source_facts, question_count, distribution):
    return f"""
You are an expert trivia question designer for a high-quality trivia game.

Your task is to generate trivia questions using ONLY the verified source facts provided below.

SOURCE FACTS:
{json.dumps(source_facts, ensure_ascii=False, indent=2)}

TOPIC:
{topic}

CATEGORY:
{category}

Generate exactly {question_count} questions.

DIFFICULTY POINT SYSTEM:
Each question must have one of these point values:

100 = Very easy:
- Direct recall of a well-known or clearly stated fact.
- No reasoning required.

200 = Easy:
- Simple recognition.
- One-step factual question.
- Slightly less obvious than 100.

300 = Medium:
- Requires connecting two facts.
- Requires understanding context.
- Not answerable by only recognizing a famous name.

400 = Hard:
- Requires comparison, chronology, classification, or cause/effect reasoning.
- Distractors should be highly plausible.

500 = Very hard:
- Requires deeper reasoning, multi-step deduction, less obvious facts, or careful distinction between similar concepts.
- Should still be fair and fully supported by the source facts.

TARGET DIFFICULTY DISTRIBUTION:
{json.dumps(distribution, indent=2)}

QUESTION REQUIREMENTS:
1. Use only the source facts.
2. Do not invent facts.
3. Each question must have exactly one correct answer.
4. Avoid ambiguous wording.
5. Avoid duplicate or near-duplicate questions.
6. Mix question styles.
7. Avoid asking the same type of fact repeatedly.
8. Do not mention “source”, “passage”, or “provided facts” in the question.

QUESTION TYPES:
Use a mix of:
- multiple_choice
- true_false
- short_answer

MULTIPLE CHOICE RULES:
- Provide exactly 4 options.
- Only one option may be correct.
- Distractors must be plausible but incorrect.
- Do not use “All of the above” or “None of the above”.
- Randomize the correct answer position.

TRUE/FALSE RULES:
- Avoid obvious true/false statements.
- False statements must be realistically false.

SHORT ANSWER RULES:
- Answer should be short and specific.
- Include acceptable alternative answers if relevant.

OUTPUT FORMAT:
Return ONLY valid JSON.
Do not include markdown.
Do not include commentary.

Use this exact structure:

{{
  "batch_metadata": {{
    "topic": "{topic}",
    "category": "{category}",
    "question_count": {question_count},
    "difficulty_distribution": {{
      "100": 0,
      "200": 0,
      "300": 0,
      "400": 0,
      "500": 0
    }},
    "generation_version": "v3_rag_points_difficulty"
  }},
  "questions": [
    {{
      "id": "",
      "question": "",
      "type": "multiple_choice",
      "points": 100,
      "category": "",
      "subcategory": "",
      "options": ["", "", "", ""],
      "correct_answer": "",
      "acceptable_answers": [],
      "explanation": "",
      "source_fact_used": "",
      "confidence": "high",
      "quality_tags": ["factual", "clear", "non_duplicate"]
    }}
  ]
}}
"""


def build_validation_prompt(source_facts, generated_questions):
    return f"""
You are a strict trivia quality-control reviewer.

Review the generated trivia questions against the source facts.

SOURCE FACTS:
{json.dumps(source_facts, ensure_ascii=False, indent=2)}

GENERATED QUESTIONS:
{json.dumps(generated_questions, ensure_ascii=False, indent=2)}

Review each question for:
1. Factual accuracy.
2. Whether the answer is fully supported by the source facts.
3. Whether there is exactly one correct answer.
4. Whether the question is clear and not ambiguous.
5. Whether distractors are plausible but incorrect.
6. Whether the points value is appropriate:
   - 100 = very easy
   - 200 = easy
   - 300 = medium
   - 400 = hard
   - 500 = very hard
7. Whether the question is duplicated or too similar to another question.
8. Whether the explanation is correct.

Return ONLY valid JSON.

Use this exact structure:

{{
  "review_summary": {{
    "total_questions": 0,
    "approved": 0,
    "rejected": 0,
    "needs_revision": 0
  }},
  "questions": [
    {{
      "id": "",
      "status": "approved",
      "issues": [],
      "recommended_fix": "",
      "approved_question": {{
        "id": "",
        "question": "",
        "type": "",
        "points": 100,
        "category": "",
        "subcategory": "",
        "options": [],
        "correct_answer": "",
        "acceptable_answers": [],
        "explanation": "",
        "source_fact_used": "",
        "confidence": ""
      }}
    }}
  ]
}}
"""


def assign_ids(generated_data):
    for q in generated_data.get("questions", []):
        if not q.get("id"):
            q["id"] = str(uuid.uuid4())
    return generated_data


def remove_duplicates(questions):
    seen = set()
    unique_questions = []

    for q in questions:
        normalized = normalize_question_text(q.get("question", ""))
        source_fact = normalize_question_text(q.get("source_fact_used", ""))

        duplicate_key = f"{normalized}|{source_fact}"

        if duplicate_key in seen:
            continue

        seen.add(duplicate_key)
        unique_questions.append(q)

    return unique_questions


def calculate_distribution(questions):
    distribution = {
        "100": 0,
        "200": 0,
        "300": 0,
        "400": 0,
        "500": 0
    }

    for q in questions:
        points = str(q.get("points"))
        if points in distribution:
            distribution[points] += 1

    return distribution


def extract_approved_questions(validation_result):
    approved = []

    for item in validation_result.get("questions", []):
        if item.get("status") == "approved" and item.get("approved_question"):
            approved.append(item["approved_question"])

    return approved


def save_question_batch(batch_id, topic, category, questions, source_facts):
    """
    Replace this with your actual question_bank save method.
    """
    batch = {
        "batch_id": batch_id,
        "topic": topic,
        "category": category,
        "created_at": datetime.utcnow().isoformat(),
        "question_count": len(questions),
        "difficulty_distribution": calculate_distribution(questions),
        "questions": questions,
        "source_facts": source_facts
    }

    filename = f"question_batch_{batch_id}.json"

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(batch, f, ensure_ascii=False, indent=2)

    return batch
```

***

# Main Generator Function

This is the full orchestration function.

```python
def generate_trivia_batch(
    client,
    model,
    topic,
    category="General Knowledge",
    question_count=10,
    distribution=None
):
    if distribution is None:
        distribution = DEFAULT_DISTRIBUTION

    batch_id = str(uuid.uuid4())

    # 1. Retrieve facts
    source_facts = build_source_facts(topic)

    if not source_facts.get("facts"):
        raise ValueError(f"No source facts found for topic: {topic}")

    # 2. Build generation prompt
    generation_prompt = build_generation_prompt(
        topic=topic,
        category=category,
        source_facts=source_facts,
        question_count=question_count,
        distribution=distribution
    )

    # 3. Generate questions
    generation_response = client.chat.completions.create(
        model=model,
        temperature=0.65,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You generate high-quality trivia questions in strict JSON only."
            },
            {
                "role": "user",
                "content": generation_prompt
            }
        ]
    )

    generated_data = json.loads(
        generation_response.choices[0].message.content
    )

    generated_data = assign_ids(generated_data)

    # 4. Validate questions
    validation_prompt = build_validation_prompt(
        source_facts=source_facts,
        generated_questions=generated_data
    )

    validation_response = client.chat.completions.create(
        model=model,
        temperature=0.2,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": "You are a strict trivia quality-control reviewer. Return JSON only."
            },
            {
                "role": "user",
                "content": validation_prompt
            }
        ]
    )

    validation_result = json.loads(
        validation_response.choices[0].message.content
    )

    # 5. Extract approved questions
    approved_questions = extract_approved_questions(validation_result)

    # 6. Remove duplicates
    approved_questions = remove_duplicates(approved_questions)

    # 7. Save batch
    saved_batch = save_question_batch(
        batch_id=batch_id,
        topic=topic,
        category=category,
        questions=approved_questions,
        source_facts=source_facts
    )

    return {
        "batch_id": batch_id,
        "topic": topic,
        "category": category,
        "requested_question_count": question_count,
        "approved_question_count": len(approved_questions),
        "difficulty_distribution": calculate_distribution(approved_questions),
        "validation_summary": validation_result.get("review_summary", {}),
        "questions": approved_questions,
        "saved_batch": saved_batch
    }
```

***

# How to Connect This to Your Existing Module

Your file already has a pattern for:

* `start_generation_async(prompt, options=None)`
* `generate_questions(prompt, options=None)`
* `get_batch(batch_id)`
* `get_batch_metadata(batch_id)`
* `get_all_batches()`
* `verify_api_connection(...)`
* generation progress state management. [\[dbpedia.org\]](https://www.dbpedia.org/resources/sparql/)

So I would **not replace everything**. I would refactor your module like this:

```text
start_generation_async()
    ↓
generate_trivia_batch()
    ↓
build_source_facts()
    ↓
generate questions
    ↓
validate questions
    ↓
remove duplicates
    ↓
save batch
```

Your existing async/progress system can remain. The engine above should become the **new internal generation flow**.

***

# Recommended Options Object

Instead of passing only a free-text prompt, pass structured options:

```python
options = {
    "topic": "Ancient Egypt",
    "category": "History",
    "question_count": 10,
    "difficulty_distribution": {
        100: 2,
        200: 2,
        300: 2,
        400: 2,
        500: 2
    },
    "question_types": [
        "multiple_choice",
        "true_false",
        "short_answer"
    ],
    "model": "gpt-4o-mini"
}
```

***

# Example Output Shape

```json
{
  "batch_id": "c42a7f0e-91a7-4d2a-b7d7-3e7acbcf3c3f",
  "topic": "Ancient Egypt",
  "category": "History",
  "approved_question_count": 10,
  "difficulty_distribution": {
    "100": 2,
    "200": 2,
    "300": 2,
    "400": 2,
    "500": 2
  },
  "questions": [
    {
      "id": "b9d5f4c8-7c21-44bb-b327-24f6c63a2b52",
      "question": "Which river was central to the development of ancient Egyptian civilization?",
      "type": "multiple_choice",
      "points": 100,
      "category": "History",
      "subcategory": "Ancient Civilizations",
      "options": ["Nile", "Amazon", "Danube", "Tigris"],
      "correct_answer": "Nile",
      "acceptable_answers": [],
      "explanation": "The Nile River was central to ancient Egyptian civilization.",
      "source_fact_used": "Ancient Egypt developed along the Nile River.",
      "confidence": "high"
    }
  ]
}
```

***

# Important Improvement: If Approved Questions Are Too Few

Sometimes validation may reject questions. Add this logic later:

```text
If requested 10 questions but only 7 pass validation:
    regenerate 3 replacement questions
    validate again
    merge
    deduplicate
```

This will make your system much stronger.

***

# My Recommendation

Start by implementing this in stages:

1. **Stage 1:** Add the 100–500 difficulty prompt.
2. **Stage 2:** Add Wikipedia source retrieval.
3. **Stage 3:** Add validation pass.
4. **Stage 4:** Add duplicate removal.
5. **Stage 5:** Add automatic replacement when questions are rejected.

The biggest quality jump will come from **source-grounded generation + validation**, not simply changing the model.
