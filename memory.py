# memory.py

import json
import os
from datetime import datetime, timedelta
from config import HISTORY_FILE, SEED_MEMORY_FILE, PROFILE_FILE, MAX_HISTORY

def load_json(path, default):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

def load_history():
    return load_json(HISTORY_FILE, [])

def save_history(history):
    if len(history) > 40:
        history = history[-40:]
    save_json(HISTORY_FILE, history)

def load_seed_memory():
    """Facts you manually implant about a specific person before they ever
    say a word to Sophie. Edit seed_memory.json directly — nothing here is
    ever auto-modified, so it's a safe place to pre-load "already knows you"
    facts for someone trying this out (see seed_memory.example.json)."""
    return load_json(SEED_MEMORY_FILE, {})

def load_learned_profile():
    """Facts Sophie has picked up on her own during conversation. Starts
    empty and grows via extraction.py after each exchange. Fine to hand-edit
    or wipe (delete learned_profile.json) if you want her to forget."""
    return load_json(PROFILE_FILE, {})

def save_learned_profile(profile):
    save_json(PROFILE_FILE, profile)

def get_recent_history(history):
    return history[-MAX_HISTORY:]

def build_system_prompt(base_prompt, seed_memory, learned_profile, time_context=""):
    prompt = base_prompt

    # Seed facts first, learned facts layered on top (a learned update can
    # refresh a seeded fact, e.g. seed says "unemployed", conversation later
    # reveals they started a new job).
    combined = {**seed_memory, **learned_profile}
    if combined:
        prompt += "\n\nThings you know about the user:"
        for key, value in combined.items():
            prompt += f"\n- {key}: {value}"

    if time_context:
        prompt += f"\n\n{time_context}"

    return prompt

def get_time_context(history):
    """Return a short note about how long since the last conversation."""
    if not history:
        return "This is the first time you're talking to the user."

    last_time = None
    for msg in reversed(history):
        if "timestamp" in msg:
            last_time = msg["timestamp"]
            break

    if not last_time:
        return ""

    try:
        last_dt = datetime.fromisoformat(last_time)
        now = datetime.now()
        diff = now - last_dt

        minutes = diff.total_seconds() / 60

        if minutes < 45:
            return "You spoke to the user very recently (less than an hour ago). Keep it casual and continuous, like the conversation just paused."
        elif minutes < 180:
            return "You spoke a couple of hours ago. A light 'hey again' style is fine."
        elif minutes < 1440:
            return "You last spoke earlier today or yesterday. A normal friendly greeting is fine."
        else:
            return "It's been a while since you last spoke. A normal 'hey, how have you been?' style is appropriate."
    except:
        return ""

def add_timestamp(message):
    """Add current timestamp to a message."""
    message["timestamp"] = datetime.now().isoformat()
    return message
