"""Character voice with Qwen3-TTS on a CUDA GPU. Runs in its own environment (see the notebook).

  design: a few takes of one neutral line, in a voice built from a written description; pick one.
  speak:  clone the picked take for every sentence of a script, so the whole voice-over is one voice.
          Writes voice.wav and sentences.json ([{text, from, to}] in seconds).

  python tts.py design --spec spec.txt --line "..." --takes 4 --out takes/
  python tts.py speak --script script.txt --ref voice_ref.wav --ref-text ref_text.txt --out out/
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

sys.path.insert(0, str(Path(__file__).parent))
from text import LEAD_IN, split_script  # noqa: E402

DESIGN_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
CLONE_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"
DTYPES = {"float32": torch.float32, "float16": torch.float16, "bfloat16": torch.bfloat16}


def load(name, dtype):
    # T4/P100 have no fast bf16 and no FlashAttention 2, so default to plain attention.
    return Qwen3TTSModel.from_pretrained(name, device_map="cuda:0", dtype=DTYPES[dtype], attn_implementation="sdpa")


def design(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = load(DESIGN_MODEL, args.dtype)
    spec = Path(args.spec).read_text().strip()
    for i in range(1, args.takes + 1):
        print(f"Making take {i} of {args.takes}...", flush=True)
        torch.manual_seed(100 + i)
        wavs, sr = model.generate_voice_design(text=args.line, language=args.lang, instruct=spec)
        sf.write(out / f"take_{i}.wav", np.asarray(wavs[0], dtype=np.float32), sr)
        print(f"Take {i} of {args.takes} ready.", flush=True)


def speak(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    model = load(CLONE_MODEL, args.dtype)
    prompt = model.create_voice_clone_prompt(ref_audio=args.ref, ref_text=Path(args.ref_text).read_text().strip())

    chunks, sentences, sr = [], [], None
    t = LEAD_IN
    for text, pause in split_script(Path(args.script).read_text()):
        print(f"Speaking: {text}", flush=True)
        torch.manual_seed(7)
        wavs, sr = model.generate_voice_clone(text=text, language=args.lang, voice_clone_prompt=prompt)
        audio = np.asarray(wavs[0], dtype=np.float32)
        if not chunks:
            chunks.append(np.zeros(int(LEAD_IN * sr), dtype=np.float32))
        dur = len(audio) / sr
        sentences.append({"text": text, "from": round(t, 2), "to": round(t + dur, 2)})
        chunks += [audio, np.zeros(int(pause * sr), dtype=np.float32)]
        t += dur + pause
        print(f"  {dur:4.1f}s  {text}")

    chunks.append(np.zeros(int(0.5 * sr), dtype=np.float32))  # tail room
    audio = np.concatenate(chunks)
    audio = audio / max(1e-6, np.abs(audio).max()) * 0.89
    sf.write(out / "voice.wav", audio, sr)
    (out / "sentences.json").write_text(json.dumps(sentences, indent=2))
    print(f"voice: {len(audio) / sr:.1f}s, {len(sentences)} sentences")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", default="English")
    ap.add_argument("--dtype", default="float32", choices=DTYPES)
    sub = ap.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("design")
    d.add_argument("--spec", required=True)
    d.add_argument("--line", required=True)
    d.add_argument("--takes", type=int, default=4)
    d.add_argument("--out", required=True)
    s = sub.add_parser("speak")
    s.add_argument("--script", required=True)
    s.add_argument("--ref", required=True)
    s.add_argument("--ref-text", required=True)
    s.add_argument("--out", required=True)
    args = ap.parse_args()
    design(args) if args.cmd == "design" else speak(args)


if __name__ == "__main__":
    main()
