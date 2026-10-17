"""Download the default voice: ~20s of the public-domain LJSpeech dataset
(a single American female speaker reading non-fiction, recorded 2016-2017
for LibriVox) — written to voice_ref/sample.wav.

    python scripts/download_default_voice.py

Uses the Hugging Face datasets-server API, so no dataset download is needed.
"""
import io
import json
import os
import sys
import urllib.request

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import config  # noqa: E402

TARGET_SECONDS = 20
OUT_SR = 24000
API = "https://datasets-server.huggingface.co/rows?dataset=MikhailT/lj-speech&config=default&split=full&offset={}&length=20"
# A run of clips from one chapter, so the delivery stays consistent.
OFFSET = 200


def main():
    wav_path = config.VOICE_SAMPLE
    os.makedirs(os.path.dirname(wav_path), exist_ok=True)
    if os.path.exists(wav_path) and "--force" not in sys.argv:
        print(f"{wav_path} already exists — pass --force to replace it.")
        return

    print("Fetching LJSpeech clips...")
    rows = json.load(urllib.request.urlopen(API.format(OFFSET), timeout=60))["rows"]

    import librosa  # deferred: only needed for resampling/trimming

    parts, total = [], 0.0
    gap = np.zeros(int(0.3 * OUT_SR), np.float32)
    for r in rows:
        row = r["row"]
        data = urllib.request.urlopen(row["audio"][0]["src"], timeout=60).read()
        audio, sr = sf.read(io.BytesIO(data), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        audio = librosa.resample(audio, orig_sr=sr, target_sr=OUT_SR)
        audio, _ = librosa.effects.trim(audio, top_db=35)
        parts += [audio, gap]
        total += len(audio) / OUT_SR
        if total >= TARGET_SECONDS:
            break

    audio = np.concatenate(parts[:-1])
    audio = audio / np.abs(audio).max() * 0.9
    sf.write(wav_path, audio, OUT_SR)
    print(f"Saved {total:.1f}s of audio to {wav_path}")


if __name__ == "__main__":
    main()
