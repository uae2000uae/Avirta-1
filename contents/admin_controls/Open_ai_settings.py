import os
import json
from openai import OpenAI

settings = {
    # API key (or set OPENAI_API_KEY in your environment or Secret Manager)
    'openai_api_key': os.getenv('OPENAI_API_KEY', ''),

    # Models
    'generator_model': 'gpt-4o-mini',  # fastest good-quality multilingual generator
    'validator_model': 'o4-mini',      # stronger reasoning for fact-check/fix; or use 'gpt-4o'

    # Tunables
    'temperature_generate': 0.5,   # 0.4–0.6 gives variety with reasonable accuracy
    'temperature_validate': 0.1,   # low for stricter factuality
    'top_p': 1.0,
    'frequency_penalty': 0.0,
    'presence_penalty': 0.0,
    'max_tokens': 800,             # adjust based on how long your Q/A is
    'seed': 0,
}

client = OpenAI(api_key=settings['openai_api_key'])

def chat(model, messages, temperature, max_tokens):
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        top_p=settings['top_p'],
        frequency_penalty=settings['frequency_penalty'],
        presence_penalty=settings['presence_penalty'],
        max_tokens=max_tokens,
        seed=settings['seed'],
    )
    return resp.choices[0].message.content

def generate_qa(category="General Knowledge", difficulty="medium"):
    system = (
        "You are a bilingual (Arabic and English) trivia writer. "
        "Create a single high-quality, unambiguous question with one correct answer. "
        "Return ONLY JSON with keys: "
        "{'category','difficulty','question_ar','answer_ar','question_en','answer_en','source'}."
        "Keep it concise and culturally neutral. If facts are time-sensitive, include a brief source."
    )
    user = f"Category: {category}\nDifficulty: {difficulty}\nConstraints: factual, clear, concise."

    raw = chat(
        model=settings['generator_model'],
        messages=[{"role":"system","content":system}, {"role":"user","content":user}],
        temperature=settings['temperature_generate'],
        max_tokens=settings['max_tokens'],
    )

    # Best-effort parse
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # If the model added extra text, try to extract JSON
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start:end+1])
        else:
            raise ValueError(f"Model did not return JSON: {raw}")
    return data

def validate_qa(item):
    """
    Validate and, if needed, correct the QA. Returns a JSON with the same keys plus {'status'}.
    status ∈ {'ok','fixed','reject'}.
    """
    system = (
        "You are a strict fact-checker for bilingual trivia (Arabic/English). "
        "Verify accuracy, clarity, and ambiguity. If anything is wrong or unclear, fix it. "
        "Return ONLY JSON with the same fields and an extra 'status' key: 'ok', 'fixed', or 'reject'. "
        "If rejecting, explain why in 'source' briefly."
    )
    user = "Validate this item:\n" + json.dumps(item, ensure_ascii=False)

    raw = chat(
        model=settings['validator_model'],
        messages=[{"role":"system","content":system}, {"role":"user","content":user}],
        temperature=settings['temperature_validate'],
        max_tokens=settings['max_tokens'],
    )
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            data = json.loads(raw[start:end+1])
        else:
            raise ValueError(f"Validator did not return JSON: {raw}")
    return data

if __name__ == "__main__":
    item = generate_qa(category="Science", difficulty="easy")
    print("Generated:", json.dumps(item, ensure_ascii=False, indent=2))

    checked = validate_qa(item)
    print("Validated:", json.dumps(checked, ensure_ascii=False, indent=2))