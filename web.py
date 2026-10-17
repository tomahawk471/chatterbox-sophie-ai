import os
import time
import re
import json
import random
import secrets
import asyncio
import queue
import threading
import concurrent.futures

import numpy as np
import torch
import torchaudio as ta
from openai import OpenAI
from fastapi import (
    FastAPI, Depends, HTTPException, status, Request,
    WebSocket, WebSocketDisconnect,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import uvicorn

# Per-process token proving a browser already passed Basic Auth — used by
# the websocket instead of relying on Safari re-sending Basic Auth headers
# on a WS handshake. See check_ws_auth().
SESSION_TOKEN = secrets.token_urlsafe(24)

import config
from config import API_BASE, MODEL, API_KEY

if not os.path.exists(config.VOICE_SAMPLE):
    raise SystemExit(
        f"No voice sample at {config.VOICE_SAMPLE}.\n"
        "Run  python scripts/download_default_voice.py  for the default voice,\n"
        "or put your own 5-20 second clip there (see README.md)."
    )
if config.HOST not in ("127.0.0.1", "localhost", "::1") and not config.PASSWORD:
    raise SystemExit(
        f"Refusing to listen on {config.HOST} without a password -- anyone on the\n"
        "network could use it. Set SOPHIE_PASSWORD, or leave SOPHIE_HOST at 127.0.0.1."
    )

from chatterbox.tts_turbo import ChatterboxTurboTTS
from prompt import BASE_PROMPT
import topic_starters
import idle as idle_source
import extraction
import mood
import vad
import stt
from memory import (
    load_history, save_history, load_seed_memory, load_learned_profile,
    get_recent_history, build_system_prompt, get_time_context, add_timestamp
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONVO_LOG = config.CONVO_LOG

app = FastAPI()
# Login is only enforced when SOPHIE_PASSWORD is set (see config.py).
security = HTTPBasic(auto_error=bool(config.PASSWORD))
client = OpenAI(base_url=API_BASE, api_key=API_KEY)
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))

# Serve archival audio copies (not used for live playback — that goes over
# the websocket, sentence-by-sentence, as it's generated — but kept around
# for history/debugging).
os.makedirs(config.AUDIO_DIR, exist_ok=True)
app.mount("/audio", StaticFiles(directory=config.AUDIO_DIR), name="audio")

print("Loading Chatterbox Turbo...")
tts_model = ChatterboxTurboTTS.from_pretrained(device="cuda")
REF_AUDIO = config.VOICE_SAMPLE

# Compute voice conditioning ONCE at startup instead of on every generate()
# call — see tts_turbo.py's prepare_conditionals()/generate(); passing
# audio_prompt_path every call re-runs it from scratch each time.
tts_model.prepare_conditionals(REF_AUDIO)
print("TTS ready.")

vad.load()
stt.load()

# All TTS generation is routed through one persistent worker thread rather
# than a fresh thread per request. Chatterbox doesn't use torch.compile (no
# CUDA-graph thread-locality issue like CSM had), but this still keeps GPU
# calls serialized and off the asyncio event loop with a single mechanism.
tts_executor = concurrent.futures.ThreadPoolExecutor(max_workers=1, thread_name_prefix="tts-gen")

# In-memory idle/proactive-topic state (single-process local app, no need
# to persist across restarts). Server-wide rather than per-connection since
# this is a single-user app — one active conversation at a time in practice.
idle_state = {
    "last_interaction": time.time(),
    "pending_topic": None,
    "pending_sent": None,
}


def check_auth(credentials: HTTPBasicCredentials = Depends(security)):
    if not config.PASSWORD:
        return "local"
    # Username compared case-insensitively — some mobile keyboards
    # autocapitalize the first letter of a Basic Auth username field, and
    # the username isn't the actual security boundary here, the password is.
    user_ok = secrets.compare_digest(credentials.username.lower(), config.USERNAME.lower())
    pass_ok = secrets.compare_digest(credentials.password, config.PASSWORD)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


def check_ws_auth(websocket: WebSocket) -> bool:
    """Not Basic Auth over the WS handshake — Safari (iOS in particular)
    doesn't reliably re-send cached HTTP Basic Auth credentials on a
    WebSocket upgrade the way it does for a normal page load, a known
    cross-browser inconsistency that can make a WS connection silently fail
    to authenticate on iPhone specifically. Sidestepped entirely: the page
    can only ever render SESSION_TOKEN if it already passed check_auth's
    Basic Auth to load in the first place (see home()), so a valid token in
    the WS URL's query string proves the same thing, via a mechanism every
    browser handles identically for WebSocket URLs."""
    token = websocket.query_params.get("token", "")
    return secrets.compare_digest(token, SESSION_TOKEN)


def get_reply(user_input, history, seed_memory, learned_profile):
    time_context = get_time_context(history)
    system_prompt = build_system_prompt(BASE_PROMPT, seed_memory, learned_profile, time_context)
    # Reflects mood.py's mood_state.json as of the *previous* exchange --
    # see _update_mood_async, which updates it one turn behind so this
    # never adds latency to the live reply.
    system_prompt += mood.get_mood_prompt_fragment()
    messages = [{"role": "system", "content": system_prompt}]
    for msg in get_recent_history(history):
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_input})
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
        temperature=0.75,
        max_tokens=config.REPLY_MAX_TOKENS,
    )
    return response.choices[0].message.content.strip()


def speak_streaming(text, on_chunk, should_stop=None):
    """Generate speech sentence by sentence, calling on_chunk(audio_np) as
    soon as each sentence is ready. Chatterbox has no true frame-level
    streaming API (generate() is always a monolithic blocking call per
    invocation) — this is sentence-level pseudo-streaming: still one
    blocking generate() per sentence, but each result is handed off the
    moment it's done instead of waiting for the whole reply.

    should_stop, if given, is checked before starting each new sentence so a
    barge-in can free up the TTS worker thread quickly instead of finishing
    every remaining sentence of an abandoned reply — it can't cancel a
    generate() call already in flight, but it stops queuing more of them."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        sentences = [text]

    for i, sentence in enumerate(sentences):
        if should_stop and should_stop():
            print("TTS generation stopped early (interrupted).")
            break
        print(f"Speaking ({i+1}/{len(sentences)}): {sentence[:60]}...")
        start = time.time()
        wav = tts_model.generate(sentence)  # no audio_prompt_path -> reuses cached conditioning
        print(f" TTS took {time.time()-start:.2f}s")
        audio_np = wav.squeeze(0).detach().cpu().numpy().astype("float32")
        on_chunk(audio_np)


async def stream_reply_audio(websocket, text, loop, state):
    """Runs speak_streaming on the dedicated tts_executor thread and relays
    each sentence's audio to the websocket as soon as it's ready. Bails out
    early (without sending further chunks) if state.interrupted gets set by
    the receiver loop mid-stream — see ConnState / handle_audio_chunk."""
    chunk_queue = queue.Queue()
    all_chunks = []

    def run_generation():
        try:
            speak_streaming(
                text,
                on_chunk=lambda audio: chunk_queue.put(("chunk", audio)),
                should_stop=lambda: state.interrupted,
            )
        except Exception as e:
            print(f"TTS error: {e}")
        finally:
            chunk_queue.put(("done", None))

    tts_executor.submit(run_generation)

    await websocket.send_json({"type": "stream_start", "sample_rate": tts_model.sr})

    while True:
        kind, audio = await loop.run_in_executor(None, chunk_queue.get)
        if kind == "done":
            break
        if state.interrupted:
            continue  # drain without sending further audio
        all_chunks.append(audio)
        await websocket.send_bytes(audio.tobytes())

    await websocket.send_json({"type": "stream_end"})

    if all_chunks and not state.interrupted:
        full = np.concatenate(all_chunks)
        filename = f"reply_{int(time.time())}.wav"
        path = os.path.join(config.AUDIO_DIR, filename)
        ta.save(path, torch.from_numpy(full).unsqueeze(0), tts_model.sr)


def _log_turn(user_text, sophie_text):
    with open(CONVO_LOG, "a", encoding="utf-8") as f:
        if user_text is not None:
            f.write(f"USER: {user_text}\n")
        f.write(f"SOPHIE: {sophie_text}\n")
        f.write("-" * 50 + "\n")


def _extract_async(user_message):
    """Fire-and-forget background fact extraction."""
    threading.Thread(target=extraction.extract_and_merge, args=(user_message,), daemon=True).start()


def _update_mood_async(recent_history, user_message, sophie_reply):
    """Fire-and-forget background mood update -- see mood.py."""
    threading.Thread(
        target=mood.update_mood,
        args=(recent_history, user_message, sophie_reply),
        daemon=True,
    ).start()


def _pick_topic():
    if random.random() < config.INTERNET_TOPIC_CHANCE:
        fact = idle_source.get_internet_topic()
        if fact:
            title, extract = fact
            return _phrase_internet_fact(title, extract)
    return random.choice(topic_starters.TOPIC_STARTERS)


def _phrase_internet_fact(title, extract):
    try:
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": BASE_PROMPT},
                {"role": "user", "content": (
                    "Randomly bring up this fact you just came across, like it "
                    "crossed your mind out of nowhere. 1-2 short casual sentences, "
                    "not a lecture, no 'did you know' cliche:\n\n"
                    f"Topic: {title}\n{extract}"
                )},
            ],
            temperature=0.8,
            max_tokens=80,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        print(f"[idle] phrasing failed: {e}")
        return random.choice(topic_starters.TOPIC_STARTERS)


def _classify_barge_in(text):
    """Decide what a candidate interruption during SPEAKING actually means.
    See config.py's BACKCHANNEL_PHRASES / TRIGGER_WORDS for the tuning."""
    if not text:
        return "ignore"
    normalized = text.strip().lower().strip(".,!?")
    if any(trigger in normalized for trigger in config.TRIGGER_WORDS):
        return "trigger"
    if normalized in config.BACKCHANNEL_PHRASES:
        return "backchannel"
    return "substantive"


def _resample_linear(x, orig_sr, target_sr):
    """Cheap linear-interpolation resample — good enough for VAD/ASR input
    (not hi-fi audio), avoids pulling torchaudio/librosa into the hot path
    for every small incoming mic chunk."""
    if orig_sr == target_sr or x.size == 0:
        return x.astype("float32")
    duration = len(x) / orig_sr
    target_len = max(1, int(round(duration * target_sr)))
    orig_idx = np.linspace(0, len(x) - 1, num=len(x))
    target_idx = np.linspace(0, len(x) - 1, num=target_len)
    return np.interp(target_idx, orig_idx, x).astype("float32")


PREROLL_SAMPLES = int(config.MIC_SAMPLE_RATE * config.VAD_SPEECH_PAD_MS / 1000)


class ConnState:
    """Per-websocket-connection state for the full-duplex voice loop. mode
    is the single source of truth for how incoming audio gets treated:
    "listening" -> normal turn-taking (accumulate an utterance, transcribe
    it on VAD end-of-speech); "speaking" -> barge-in candidate detection
    while Sophie's reply is streaming out."""

    def __init__(self):
        self.mode = "listening"
        self.native_sample_rate = 48000  # updated by the client's mic_start message
        self.vad_carry = np.array([], dtype=np.float32)
        self.preroll = np.array([], dtype=np.float32)
        self.vad_iter = vad.new_iterator(config.VAD_THRESHOLD, config.VAD_MIN_SILENCE_MS, config.VAD_SPEECH_PAD_MS)
        self.in_speech = False
        self.utterance_buf = []
        self.candidate_buf = []
        self.interrupted = False
        self.utterance_queue = asyncio.Queue()

    def reset_vad(self, min_silence_ms):
        self.vad_iter = vad.new_iterator(config.VAD_THRESHOLD, min_silence_ms, config.VAD_SPEECH_PAD_MS)
        self.in_speech = False
        self.utterance_buf = []
        self.candidate_buf = []

    def set_mode(self, mode, min_silence_ms):
        print(f"[state] mode -> {mode}")
        self.mode = mode
        self.reset_vad(min_silence_ms)


async def handle_audio_chunk(state, raw_bytes, websocket, loop):
    chunk = np.frombuffer(raw_bytes, dtype=np.float32)
    chunk = _resample_linear(chunk, state.native_sample_rate, config.MIC_SAMPLE_RATE)
    if chunk.size == 0:
        return

    # Rolling pre-roll buffer, always kept up to date regardless of mode, so
    # a detected speech-start can be backfilled instead of clipping the
    # first syllable (VADIterator's speech_pad_ms accounts for this in its
    # reported timestamp, but we still need the actual samples on hand).
    state.preroll = np.concatenate([state.preroll, chunk])[-PREROLL_SAMPLES:]

    buf = np.concatenate([state.vad_carry, chunk])
    n_windows = len(buf) // vad.CHUNK_SAMPLES
    usable = n_windows * vad.CHUNK_SAMPLES
    state.vad_carry = buf[usable:]

    for i in range(n_windows):
        window = buf[i * vad.CHUNK_SAMPLES:(i + 1) * vad.CHUNK_SAMPLES]
        event = state.vad_iter(torch.from_numpy(window))

        if state.mode == "listening":
            if event and "start" in event:
                state.in_speech = True
                state.utterance_buf = [state.preroll.copy()]
            elif state.in_speech:
                state.utterance_buf.append(window)
            if event and "end" in event:
                state.in_speech = False
                audio = np.concatenate(state.utterance_buf) if state.utterance_buf else np.array([], dtype=np.float32)
                state.utterance_buf = []
                await state.utterance_queue.put(("audio", audio))

        elif state.mode == "speaking":
            if event and "start" in event:
                print("[barge-in] candidate speech started")
                state.in_speech = True
                state.candidate_buf = [state.preroll.copy()]
            elif state.in_speech:
                state.candidate_buf.append(window)
            if event and "end" in event:
                state.in_speech = False
                candidate = np.concatenate(state.candidate_buf) if state.candidate_buf else np.array([], dtype=np.float32)
                state.candidate_buf = []
                duration_ms = len(candidate) / config.MIC_SAMPLE_RATE * 1000
                if duration_ms < config.BARGE_IN_MIN_SPEECH_MS:
                    continue  # too short to be a real word — noise/blip, ignore

                text = await loop.run_in_executor(None, stt.transcribe_array, candidate)
                decision = _classify_barge_in(text)
                print(f"[barge-in] heard {duration_ms:.0f}ms -> '{text}' -> {decision}")

                if decision in ("trigger", "substantive"):
                    state.interrupted = True
                    await websocket.send_json({"type": "interrupt"})
                    state.set_mode("listening", config.VAD_MIN_SILENCE_MS)
                    if text:
                        # Already transcribed it — feed it straight in as the
                        # new message instead of making the user repeat
                        # themselves.
                        idle_state["pending_topic"] = None
                        idle_state["pending_sent"] = None
                        idle_state["last_interaction"] = time.time()
                        await state.utterance_queue.put(("text", text))
                # "backchannel" -> do nothing, stay in speaking mode


async def _handle_user_utterance(websocket, loop, text):
    """Shared reply-generation path for both typed and voice-transcribed
    input: get a reply, persist history, kick off background extraction."""
    history = load_history()
    seed_memory = load_seed_memory()
    learned_profile = load_learned_profile()

    reply = await loop.run_in_executor(
        None, get_reply, text, history, seed_memory, learned_profile
    )
    await websocket.send_json({"type": "reply_text", "role": "assistant", "text": reply})

    recent_before = get_recent_history(history)

    history.append(add_timestamp({"role": "user", "content": text}))
    history.append(add_timestamp({"role": "assistant", "content": reply}))
    save_history(history)
    _log_turn(text, reply)

    _extract_async(text)
    _update_mood_async(recent_before, text, reply)
    return reply


async def turn_loop(websocket, state, loop):
    while True:
        item = await state.utterance_queue.get()
        if item is None:
            return
        kind, payload = item

        if kind == "audio":
            text = await loop.run_in_executor(None, stt.transcribe_array, payload)
            if not text:
                continue
            idle_state["pending_topic"] = None
            idle_state["pending_sent"] = None
            idle_state["last_interaction"] = time.time()
            await websocket.send_json({"type": "reply_text", "role": "user", "text": text})
            reply = await _handle_user_utterance(websocket, loop, text)

        elif kind == "text":
            reply = await _handle_user_utterance(websocket, loop, payload)

        elif kind == "proactive":
            reply = payload
            history = load_history()
            history.append(add_timestamp({"role": "assistant", "content": reply}))
            save_history(history)
            _log_turn(None, f"{reply}  [proactive]")
            await websocket.send_json({"type": "reply_text", "role": "assistant", "text": reply})

        else:
            continue

        # --- speak it, with barge-in candidate detection active while she talks ---
        state.interrupted = False
        state.set_mode("speaking", config.BARGE_IN_MIN_SILENCE_MS)

        await stream_reply_audio(websocket, reply, loop, state)

        if not state.interrupted:
            state.set_mode("listening", config.VAD_MIN_SILENCE_MS)
        # else: handle_audio_chunk already switched us back to listening
        # mode (possibly with a new utterance already queued) — don't touch it.


async def receiver_loop(websocket, state, loop):
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break

            if message.get("bytes") is not None:
                await handle_audio_chunk(state, message["bytes"], websocket, loop)

            elif message.get("text") is not None:
                data = json.loads(message["text"])
                mtype = data.get("type")

                if mtype == "mic_start":
                    state.native_sample_rate = data.get("sample_rate", 48000)

                elif mtype == "message":
                    text = data.get("text", "").strip()
                    if text:
                        idle_state["pending_topic"] = None
                        idle_state["pending_sent"] = None
                        idle_state["last_interaction"] = time.time()
                        await state.utterance_queue.put(("text", text))

                elif mtype == "idle_checkin":
                    now = time.time()
                    if idle_state["pending_topic"]:
                        if now - idle_state["pending_sent"] > config.RESPONSE_TIMEOUT_SECONDS:
                            text = random.choice(topic_starters.GIVE_UP_LINES)
                            idle_state["last_interaction"] = now
                            idle_state["pending_topic"] = None
                            idle_state["pending_sent"] = None
                            await state.utterance_queue.put(("proactive", text))
                        else:
                            await websocket.send_json({"type": "no_checkin"})
                    elif now - idle_state["last_interaction"] > config.IDLE_THRESHOLD_SECONDS:
                        text = await loop.run_in_executor(None, _pick_topic)
                        idle_state["pending_topic"] = text
                        idle_state["pending_sent"] = now
                        await state.utterance_queue.put(("proactive", text))
                    else:
                        await websocket.send_json({"type": "no_checkin"})

    except WebSocketDisconnect:
        pass
    finally:
        await state.utterance_queue.put(None)


@app.get("/", response_class=HTMLResponse)
def home(request: Request, user: str = Depends(check_auth)):
    # No chat transcript in this UI — history.json is still the source of
    # truth for LLM context/memory, just not rendered on screen.
    return templates.TemplateResponse(request, "index.html", {"ws_token": SESSION_TOKEN})


@app.websocket("/ws/chat")
async def ws_chat(websocket: WebSocket):
    if not check_ws_auth(websocket):
        await websocket.close(code=1008)  # policy violation
        return

    await websocket.accept()
    loop = asyncio.get_event_loop()
    state = ConnState()

    receiver = asyncio.create_task(receiver_loop(websocket, state, loop))
    turn = asyncio.create_task(turn_loop(websocket, state, loop))

    done, pending = await asyncio.wait(
        [receiver, turn], return_when=asyncio.FIRST_COMPLETED
    )
    for task in pending:
        task.cancel()


if __name__ == "__main__":
    print(f"Open http://localhost:{config.PORT} in Chrome.")
    uvicorn.run(app, host=config.HOST, port=config.PORT)
