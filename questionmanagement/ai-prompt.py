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
``