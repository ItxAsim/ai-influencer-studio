"""Build influencer_studio.ipynb from the files in this repo.

The notebook is self-contained: studio/ and remotion/ are embedded in its first code cell, so it runs on
Kaggle without cloning anything. Edit those files, then run:

    python build_notebook.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).parent
EMBED = sorted(
    [p for p in (ROOT / "studio").glob("*") if p.suffix in (".py", ".md")]
    + [p for p in (ROOT / "remotion").rglob("*")
       if p.is_file() and p.suffix in (".ts", ".tsx", ".mjs", ".json")
       and not {"node_modules", "public", "out"} & set(p.parts) and p.name not in ("props.json", "package-lock.json")]
)

cells = []


def md(s):
    cells.append({"cell_type": "markdown", "metadata": {}, "source": s.strip("\n").splitlines(True)})


def code(s):
    cells.append({"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [], "source": s.strip("\n").splitlines(True)})


# ================================================================ intro + guide
md(r"""
# AI Influencer Studio — a free web app for AI-influencer videos

Turn a character, one photo and a script into a finished vertical talking video, in a point-and-click web app
that runs on Kaggle's free GPU, with open models and no API keys:
**character → idea → script → voice → moving video → lip-sync → subtitles and sound**.

| Step | Model | What it does |
|---|---|---|
| Ideas & script | Qwen3-4B-Instruct | Writes video ideas and a script in your character's voice (or paste your own) |
| Voice | Qwen3-TTS VoiceDesign + Base | Builds a voice from a written description once, then reuses it for every script |
| Movement | Wan 2.2 TI2V-5B | Turns your start photo into short clips of the character breathing, blinking, moving |
| Lip-sync | LatentSync 1.5 | Redraws the mouth to match the voice |
| Finishing | Remotion (ffmpeg fallback) | Hook title, word-by-word subtitles, ambient sound, camera drift, loudness |

## How to start
1. Right panel → **Session options → Accelerator: GPU T4 x2** and **Internet: On** (needs phone verification).
2. Set a password in the last cell, then **Run all** (about 5 minutes).
3. Open the **public link** the last cell prints (`https://….gradio.live`), log in as `studio` with your password.
4. Keep this Kaggle tab open while you work: the app runs inside this notebook session and stops with it.

A 35–50 s video takes about 1.5–2 hours on a T4 the first time (mostly video generation and lip-sync).
Kaggle gives about 30 GPU hours a week. Everything you make is saved under `/kaggle/working/studio`
(the Output panel); download your **character pack** so you can reuse the same voice in a new session.
""")
md((ROOT / "studio" / "guide.md").read_text())

# ================================================================ setup
md("## Setup")
files = {str(p.relative_to(ROOT)): p.read_text() for p in EMBED}
code(
    "# The studio's code, embedded so this notebook needs nothing else. Unpacked to /tmp/studio.\n"
    f"FILES = {json.dumps(files, indent=0, ensure_ascii=False)}\n"
    + r'''
import os, sys
from pathlib import Path
for rel, text in FILES.items():
    p = Path("/tmp/studio") / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
sys.path.insert(0, "/tmp/studio/studio")
print("unpacked", len(FILES), "files")
'''
)
code(r'''
!nvidia-smi --query-gpu=name,memory.total --format=csv
# Keep Kaggle's own torch: pin it so no package below can swap it out of the running kernel
# (that breaks it with "module 'torch' has no attribute '_utils'").
!python -c "import importlib.metadata as m; [print(f'{p}=={m.version(p)}') for p in ('torch','torchvision','torchaudio') if any(d.metadata['Name'].lower()==p for d in m.distributions())]" > /tmp/torch-pin.txt
!pip -q install -U -c /tmp/torch-pin.txt "gradio>=6,<7" "diffusers>=0.35" "transformers>=4.51" accelerate gguf bitsandbytes ftfy imageio imageio-ffmpeg sentencepiece uv
!python -c "import torch; print('torch OK', torch.__version__, torch.cuda.is_available())"
''')
md("""
If a cell fails with `torch has no attribute '_utils'`: **Run → Restart & clear cell outputs**, then run all again.

## Launch the studio
""")
code(r'''
PASSWORD = "change-me"   # the public link is open to anyone who has it, so protect your GPU with a password

assert PASSWORD != "change-me", "Set your own PASSWORD first."
from app import launch
demo = launch(share=True, password=PASSWORD)
''')

nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python"},
        "kaggle": {"accelerator": "gpu", "isInternetEnabled": True},
    },
    "nbformat": 4,
    "nbformat_minor": 4,
}
# Self-check: the embedded files must come back byte-identical when the cell runs (a literal that escapes
# emoji as surrogate pairs, for example, can't be written to disk on Kaggle).
_ns = {}
exec(f"FILES = {json.dumps(files, ensure_ascii=False)}", _ns)
for _rel, _text in _ns["FILES"].items():
    _text.encode("utf-8")
    assert _text == files[_rel], f"{_rel} does not round-trip"

(ROOT / "influencer_studio.ipynb").write_text(json.dumps(nb, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"wrote influencer_studio.ipynb ({len(cells)} cells, {len(EMBED)} embedded files)")
