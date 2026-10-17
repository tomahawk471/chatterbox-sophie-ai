# mood.py
#
# Dynamic mood state: shifts Sophie's conversational stance based
# on how the conversation is trending, the way a real person's tone shifts
# with the conversation instead of staying fixed. Runs one turn behind the
# live conversation -- update_mood() is called after a reply has already
# been sent (see _update_mood_async in web.py), reading the exchange that
# just finished and updating state for the *next* reply. Same non-blocking
# fire-and-forget pattern as extraction.py's fact extraction, so it never
# adds latency to the live voice loop.
#
# Everything tunable lives in this one file -- the state machine, the
# classifier prompt, and the phrasing injected into the system prompt -- so
# this is the one place to come back and adjust it.

import json
import re

from openai import OpenAI
from config import API_BASE, MODEL, API_KEY, MOOD_STATE_FILE

client = OpenAI(base_url=API_BASE, api_key=API_KEY)

# ---- editable state machine --------------------------------------------
# Valid "dynamic" values and the instruction injected into the system
# prompt for each. Edit the wording here (or add your own states) to change
# how each mood actually plays out -- this is the main dial you'll want to
# come back and tune. Any new state also needs describing in
# MOOD_CLASSIFY_PROMPT below so the classifier knows when to pick it.
DYNAMIC_INSTRUCTIONS = {
    "leading": (
        "Right now you're taking the lead. The user is giving short answers or waiting "
        "for you, so carry the conversation: bring up something of your own, tell a quick "
        "story, or take the topic somewhere new."
    ),
    "following": (
        "Right now the user is leading. They have something they want to talk about, so "
        "follow their thread, react to what they're actually saying, and don't change the subject."
    ),
    "playful": (
        "You're in a light, playful mood. Tease a little, joke around, keep it quick and fun."
    ),
    "supportive": (
        "The user seems stressed, down or tired. Be calm and warm, slow down, listen more "
        "than you talk, and don't try to fix everything or force cheerfulness."
    ),
    "neutral": "",
}

DEFAULT_STATE = {"dynamic": "neutral", "energy": 0.5}

# ---- editable classifier prompt ----------------------------------------
MOOD_CLASSIFY_PROMPT = """You are a silent conversational-mood tracker reading a live voice conversation between Sophie and the user. Your only job is to judge how Sophie's conversational stance should shift.

Current state (JSON): {state}

Recent conversation (most recent last):
{transcript}

Judge two things and respond with ONLY a JSON object:

1. "energy": a float from 0.0 to 1.0 for the user's current energy
   - 0.0-0.3 = low: tired, flat, sad or stressed
   - 0.4-0.6 = normal, relaxed conversation
   - 0.7-1.0 = high: excited, joking, animated

2. "dynamic": one of "leading", "following", "playful", "supportive", "neutral"

Rules for choosing dynamic:

- "leading" when the user is passive, giving short replies, or invites Sophie to pick
  the topic ("I don't know, you pick", "tell me something", "what's new with you").
- "following" when the user is clearly driving: telling a story, explaining something,
  or asking Sophie about a specific topic.
- "playful" when the user is joking, teasing or the conversation is light and quick.
- "supportive" when the user sounds stressed, upset, tired or is talking about
  something difficult.
- "neutral" is the default when nothing particular is happening.

- Prefer keeping the current dynamic unless the recent conversation clearly supports a
  change. Do not flip on a single ambiguous or short line.

Respond with ONLY valid JSON in this exact form:
{{"energy": <float>, "dynamic": "<one of the five states>"}}
No commentary, no markdown, no extra text."""


def load_mood_state():
    try:
        with open(MOOD_STATE_FILE, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return dict(DEFAULT_STATE)


def save_mood_state(state):
    with open(MOOD_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _parse_json_object(raw):
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


def update_mood(recent_history, user_message, sophie_reply):
    """Look at the exchange that just finished and update mood_state.json
    for the *next* turn. Call this after a reply has already been sent --
    it never blocks or adds latency to the live conversation."""
    try:
        state = load_mood_state()

        transcript_lines = []
        for msg in recent_history[-6:]:
            speaker = "User" if msg["role"] == "user" else "Sophie"
            transcript_lines.append(f"{speaker}: {msg['content']}")
        transcript_lines.append(f"User: {user_message}")
        transcript_lines.append(f"Sophie: {sophie_reply}")

        prompt = MOOD_CLASSIFY_PROMPT.format(
            state=json.dumps(state),
            transcript="\n".join(transcript_lines),
        )
        response = client.chat.completions.create(
            model=MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=60,
        )
        raw = response.choices[0].message.content.strip()
        result = _parse_json_object(raw)

        new_dynamic = result.get("dynamic")
        new_energy = result.get("energy")

        if new_dynamic in DYNAMIC_INSTRUCTIONS:
            state["dynamic"] = new_dynamic
        if isinstance(new_energy, (int, float)):
            state["energy"] = max(0.0, min(1.0, float(new_energy)))

        save_mood_state(state)
        print(f"[mood] -> {state}")
    except Exception as e:
        # Never let a failed mood pass affect the live conversation -- just
        # keep whatever state was already on disk.
        print(f"[mood] skipped: {e}")


def get_mood_prompt_fragment(state=None):
    """Text block to append to the system prompt for the *next* reply,
    reflecting the current mood state. Returns "" for neutral so it's a
    no-op on the base personality until the conversation actually earns it."""
    if state is None:
        state = load_mood_state()
    instruction = DYNAMIC_INSTRUCTIONS.get(state.get("dynamic", "neutral"), "")
    return f"\n\n{instruction}" if instruction else ""
