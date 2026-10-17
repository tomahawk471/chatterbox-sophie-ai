# extraction.py
#
# Background fact extraction: after every exchange, asks the LLM to pull out
# any new/updated personal facts about the user and merges them into
# learned_profile.json. Runs as a FastAPI background task *after* the reply
# has already been sent and spoken, so it never adds latency to the
# conversation — this is what makes memory.py's profile dynamic instead of
# static.

import json
import re

from openai import OpenAI
from config import API_BASE, MODEL, API_KEY
from memory import load_learned_profile, save_learned_profile

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

EXTRACTION_PROMPT = """You are a silent fact-extraction pass reading a live conversation. Your only job is to notice when the USER reveals a new or updated personal fact about themselves, and record it as data.

Facts already known about the user (JSON):
{profile}

The user just said, word for word:
"{user}"

Rules:
- Only extract facts the user is actually revealing about THEMSELVES in that line (e.g. their location, job, hobbies, relationships, plans, opinions, pets, life events).
- Ignore greetings, filler, and short reactions that don't contain new information.
- Requests, instructions, and questions are NOT facts about the user. "Tell me a story about a dog who learns to surf" does not mean the user surfs — it's a request, extract nothing from it. Only extract when the user is actually stating something true about their own life.
- Never invent a fact, and never extract anything from someone else's words — only the user's line above.
- Use short lowercase snake_case keys (e.g. "hobby", "job", "holiday_2026") and short natural-language values.

If there's a new or updated fact, respond with ONLY a JSON object of the new/changed key-value pairs. If there's nothing worth remembering, respond with ONLY {{}}. No commentary, no markdown — just the JSON object."""


def _parse_json_object(raw):
    """Pull a JSON object out of the model's raw output, tolerating markdown
    code fences or stray text around it."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip(), flags=re.MULTILINE)
    match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
    if not match:
        return {}
    try:
        obj = json.loads(match.group(0))
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def extract_and_merge(user_message):
    try:
        current = load_learned_profile()
        prompt = EXTRACTION_PROMPT.format(
            profile=json.dumps(current),
            user=user_message,
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=200,
        )
        raw = response.choices[0].message.content.strip()
        facts = _parse_json_object(raw)
        if facts:
            current.update(facts)
            save_learned_profile(current)
            print(f"[extraction] learned: {facts}")
    except Exception as e:
        # Never let a failed extraction pass affect the live conversation.
        print(f"[extraction] skipped: {e}")
