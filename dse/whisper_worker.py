"""Runs INSIDE the speech environment (faster-whisper), not the toolkit's own Python: python whisper_worker.py <audio.wav> <model> <out.json>

Writes {"words": [{"w": "hello", "start": 0.12, "end": 0.48}, ...], "seconds": 12.3}. It imports nothing from the toolkit so it runs in the separate environment.
"""
import json
import sys


def main(argv: list[str]) -> int:
    wav, model, out = argv[0], argv[1], argv[2]
    import wave

    import numpy as np
    from faster_whisper import WhisperModel
    # the toolkit already made a 16 kHz mono wav with ffmpeg, so read it here and hand the samples over (this skips faster-whisper's own decoder, which needs the av package)
    with wave.open(wav, "rb") as w:
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768.0
    m = WhisperModel(model, device="cpu", compute_type="int8")
    segs, info = m.transcribe(audio, word_timestamps=True, vad_filter=True, beam_size=1, condition_on_previous_text=False)
    words = []
    for s in segs:
        for w in (s.words or []):
            t = (w.word or "").strip()
            if t:
                words.append({"w": t, "start": round(float(w.start), 3), "end": round(float(w.end), 3)})
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"words": words, "seconds": round(float(info.duration), 3)}, f)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
