# config.py
#
# Every setting can be overridden with an environment variable (shown next to
# it), so nothing here needs editing for a normal install.

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# --- LLM: any OpenAI-compatible chat server (llama.cpp, Ollama, LM Studio, vLLM...) ---
API_BASE = os.environ.get("SOPHIE_LLM_URL", "http://localhost:8080/v1")
MODEL = os.environ.get("SOPHIE_LLM_MODEL", "local-model")  # llama.cpp ignores this; Ollama/LM Studio need the real name
API_KEY = os.environ.get("SOPHIE_LLM_API_KEY", "not-needed")

MAX_HISTORY = 12          # how many recent messages to keep in LLM context
REPLY_MAX_TOKENS = 180    # per-reply token cap sent to the LLM -- raised from 120 because replies were getting cut off mid-sentence

# Local data files, created on first run (all git-ignored).
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
SEED_MEMORY_FILE = os.path.join(BASE_DIR, "seed_memory.json")    # manually implanted facts — never auto-edited (see seed_memory.example.json)
PROFILE_FILE = os.path.join(BASE_DIR, "learned_profile.json")    # starts empty, grows via extraction.py
MOOD_STATE_FILE = os.path.join(BASE_DIR, "mood_state.json")      # dynamic mood state, updated after each exchange by mood.py
CONVO_LOG = os.path.join(BASE_DIR, "conversation_log.txt")

# --- web server ---
HOST = os.environ.get("SOPHIE_HOST", "127.0.0.1")
PORT = int(os.environ.get("SOPHIE_PORT", "7862"))
# Login is only required when a password is set. Leaving it unset is fine for
# localhost, but web.py refuses to listen on a network address without one.
USERNAME = os.environ.get("SOPHIE_USERNAME", "user")
PASSWORD = os.environ.get("SOPHIE_PASSWORD", "")
AUDIO_DIR = os.environ.get("SOPHIE_AUDIO_DIR", os.path.join(BASE_DIR, "audio_history"))

# --- voice ---
# Chatterbox clones the voice from this clip (5-20 s of one person speaking).
# scripts/download_default_voice.py fetches a public-domain default.
VOICE_SAMPLE = os.environ.get("SOPHIE_VOICE", os.path.join(BASE_DIR, "voice_ref", "sample.wav"))

# --- idle / proactive topic behavior ---
IDLE_THRESHOLD_SECONDS = 5 * 20     # how long with no messages before Sophie brings something up
RESPONSE_TIMEOUT_SECONDS = 90       # how long to wait for a reply before giving up on it
POLL_INTERVAL_SECONDS = 15          # how often the browser checks in (must match templates/index.html)
INTERNET_TOPIC_CHANCE = 0.3         # odds of a random internet fact vs. a topic_starters.py line

# --- speech-to-text (faster-whisper) ---
WHISPER_MODEL_SIZE = "small"        # already cached locally, proven config from earlier testing
WHISPER_DEVICE = "cpu"
WHISPER_COMPUTE_TYPE = "int8"

# --- voice activity detection (Silero VAD) ---
MIC_SAMPLE_RATE = 16000             # everything gets resampled to this for VAD/STT
VAD_THRESHOLD = 0.5                 # speech-probability threshold
VAD_SPEECH_PAD_MS = 150             # padding kept around detected speech so words aren't clipped

# Normal turn-taking: can afford to wait a bit longer before deciding the
# user has actually finished talking (don't cut off a mid-sentence pause).
VAD_MIN_SILENCE_MS = 500

# Barge-in candidate detection while Sophie is speaking: react faster, and
# ignore anything shorter than a real word (coughs, clicks, background noise).
BARGE_IN_MIN_SILENCE_MS = 250
BARGE_IN_MIN_SPEECH_MS = 200

# Said while listening, not meant to take the floor — Sophie keeps talking.
# Matched as an exact (whole-utterance) match, not a substring, so "yeah but
# actually..." still counts as a real interruption.
BACKCHANNEL_PHRASES = {
    "yeah", "yep", "yup", "mhm", "mm-hmm", "uh-huh", "right", "okay", "ok",
    "sure", "i see", "got it", "totally", "true", "fair enough", "makes sense",
    "cool", "nice", "wow",
}

# Said anywhere in the utterance -> immediate hard interrupt, no other checks.
# The guaranteed override even if the backchannel/substantive classification
# above is ever wrong.
TRIGGER_WORDS = {
    "stop", "wait", "hold on", "hang on", "actually", "no", "never mind",
}
