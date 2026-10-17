# Chatterbox Sophie AI

A local, real-time voice-to-voice companion. You talk, Sophie listens, thinks with a local LLM, and answers out loud in a cloned voice using [Chatterbox TTS](https://github.com/resemble-ai/chatterbox). It's hands-free and full-duplex: you can interrupt her mid-sentence like a real conversation.

Everything runs on your own machine. No audio or text leaves it (apart from optional random Wikipedia topics, see below).

## Features

- **Hands-free voice:** continuous mic capture with Silero VAD turn detection. No push-to-talk.
- **Barge-in:** say "stop", "wait", "hold on" (or start talking about something else) and she stops. Small acknowledgements like "yeah", "mhm" or "okay" don't interrupt her.
- **Streaming speech:** the reply is spoken sentence by sentence as it's generated, so she starts talking almost immediately.
- **Memory:** after each exchange, a background pass picks out facts you mention about yourself and remembers them (`learned_profile.json`). You can also pre-load facts in `seed_memory.json`.
- **Mood:** a second background pass judges how the conversation is going (are you driving it, quiet, joking, stressed?) and shifts Sophie's stance for the next turn: leading, following, playful or supportive.
- **Idle topics:** if it's quiet for a while, she brings something up on her own, either one of your own lines from `topic_starters.py` or a random Wikipedia fact.
- **Text input** too, for when you can't talk.

## Requirements

| | |
|---|---|
| OS | Linux (tested on Ubuntu 24.04) |
| GPU | NVIDIA. About 4 GB VRAM for Chatterbox, plus whatever your LLM needs (an 8B model at Q4 is about 6 GB) |
| Python | **3.12**. Newer versions (3.13+) can't install Chatterbox's pinned dependencies |
| Browser | Chrome or Chromium |
| LLM | Any OpenAI-compatible chat server. Recommended: llama.cpp + Dolphin 3.0 Llama 3.1 8B (see [LLM_SETUP.md](LLM_SETUP.md)) |

## Install

```bash
git clone https://github.com/tomahawk471/chatterbox-sophie-ai.git
cd chatterbox-sophie-ai
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

This downloads a few GB (PyTorch with CUDA, among others).

### Get a voice

```bash
python scripts/download_default_voice.py
```

This fetches about 20 seconds of the public-domain LJSpeech voice into `voice_ref/sample.wav`. To use your own voice instead, replace that file with 5-20 seconds of one person speaking clearly (no music, background noise or other voices).

> **Consent:** only clone a voice you have the right to use, with the speaker's permission. Don't use clips of celebrities or anyone who hasn't agreed.

### Start an LLM server

Sophie needs a local LLM server for her thinking. **See [LLM_SETUP.md](LLM_SETUP.md)** for full step-by-step instructions. The short version, with the recommended model ([Dolphin 3.0 Llama 3.1 8B abliterated](https://huggingface.co/mradermacher/Dolphin3.0-Llama3.1-8B-abliterated-GGUF), Q4_K_M: fast, and great at casual conversation):

```bash
# once: build llama.cpp with CUDA (see LLM_SETUP.md) and download the model
mkdir -p ~/models
wget -O ~/models/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf \
  "https://huggingface.co/mradermacher/Dolphin3.0-Llama3.1-8B-abliterated-GGUF/resolve/main/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf"

# every time, in its own terminal:
~/llama.cpp/build/bin/llama-server -m ~/models/Dolphin3.0-Llama3.1-8B-abliterated.Q4_K_M.gguf \
  --port 8080 -c 8192 -ngl 99 --jinja --reasoning off
```

Ollama and LM Studio work too (also covered in LLM_SETUP.md).

## Run

```bash
source venv/bin/activate
python web.py
```

The first start downloads Chatterbox, Whisper and Silero VAD. When you see `Uvicorn running`, open **<http://localhost:7862>** in Chrome, click the orb, allow the microphone and start talking.

- Use `localhost` exactly: browsers only allow the microphone on `localhost` or HTTPS pages.
- **Use headphones.** Through speakers, Sophie hears herself and interrupts her own replies.
- If the page stops responding after a restart, hard-refresh (`Ctrl+Shift+R`).

Press `Ctrl+C` to stop.

## Make it yours

**See [CUSTOMIZING.md](CUSTOMIZING.md)** for a step-by-step guide: changing her personality, how much she leads vs. follows, what she knows about you, and resetting her memory.

| File | What to change |
|---|---|
| `prompt.py` | Sophie's personality, background and way of talking |
| `mood.py` | The mood states, what each one tells her to do, and when the classifier picks them |
| `topic_starters.py` | Lines she brings up when it's quiet, and what she says if you ignore her |
| `seed_memory.json` | Facts she already "knows" about you. Copy `seed_memory.example.json` to start |
| `config.py` | Interrupt and acknowledgement words, turn-taking timings, idle timings |

## Configuration

All settings are environment variables.

| Variable | Default | What it does |
|---|---|---|
| `SOPHIE_LLM_URL` | `http://localhost:8080/v1` | OpenAI-compatible LLM endpoint |
| `SOPHIE_LLM_MODEL` | `local-model` | Model name (llama.cpp ignores it) |
| `SOPHIE_LLM_API_KEY` | `not-needed` | For servers that need a key |
| `SOPHIE_PORT` | `7862` | Web port |
| `SOPHIE_HOST` | `127.0.0.1` | Bind address. Anything else requires `SOPHIE_PASSWORD` |
| `SOPHIE_USERNAME` / `SOPHIE_PASSWORD` | `user` / *(none)* | Browser login, enabled when a password is set |
| `SOPHIE_VOICE` | `voice_ref/sample.wav` | Voice sample to clone |
| `SOPHIE_AUDIO_DIR` | `audio_history/` | Where copies of her replies are saved |

To use it from a phone on your network, set `SOPHIE_HOST=0.0.0.0` and a `SOPHIE_PASSWORD`. Phones need HTTPS for the microphone, so put it behind an HTTPS reverse proxy or tunnel.

## Files it creates

`history.json`, `learned_profile.json`, `mood_state.json`, `conversation_log.txt` and `audio_history/`: your conversations and what Sophie remembers about you. They're all local and git-ignored. Delete them any time to reset her memory.

`chat.py` is a terminal text-only test bench that uses the same personality and memory.

## Licence

Apache 2.0, see [LICENSE](LICENSE) and [NOTICE](NOTICE).
