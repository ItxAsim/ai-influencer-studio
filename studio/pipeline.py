"""The studio's steps, shared by the web UI. Everything for one character lives in one folder on disk:

  <home>/<character>/character.json, start.png, voice_ref.wav, voice_meta.json   (the "character pack")
  <home>/<character>/videos/<id>/script.txt, hook.txt, voice.wav, lines.json, takes/, lipsync.mp4, final.mp4

The GPU-heavy steps (voice, video, lip-sync) run as separate processes in their own environments; long steps
are generators that yield their log so the UI can show progress.
"""

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path

from PIL import Image, ImageOps

from media import duration, finish_ffmpeg, fit_to_audio, loudnorm
from text import subtitle_lines

HERE = Path(__file__).parent  # .../studio
REMOTION = HERE.parent / "remotion"
HOME = Path(os.environ.get("STUDIO_HOME", "/kaggle/working/studio" if Path("/kaggle/working").exists() else "studio_home"))
WIDTH, HEIGHT = 480, 832

TTS_ENV = Path("/tmp/venv_tts")
LATENTSYNC = Path("/tmp/LatentSync")
NODE = Path("/tmp/node-v20.18.0-linux-x64/bin")

TEST_LINE = (
    "Honestly, it wasn't anything clever. I just started doing the small things properly, "
    "every day, and stopped waiting to feel motivated. That's it, really."
)

DEFAULT_NEGATIVE = (
    "talking, looking down, looking away, turning away, head turned, profile, walking, leaving frame, hands near "
    "face, blurry eyes, closed eyes, glassy stare, face morphing, different person, deformed hands, extra fingers, "
    "text, watermark, camera pan, zoom, cuts, plastic skin, airbrushed, blurry, low quality, static image, slow motion"
)


# ------------------------------------------------------------------ helpers

def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "character"


def stream(cmd, cwd=None, env=None):
    """Run a shell command, yielding its output line by line; raises if it fails."""
    # unbuffered, so a child's prints reach the UI as they happen instead of in one burst at the end
    p = subprocess.Popen(cmd, shell=True, cwd=cwd, env={**os.environ, "PYTHONUNBUFFERED": "1", **(env or {})},
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
    tail = []
    for line in p.stdout:
        line = line.rstrip()
        if line:
            tail = (tail + [line])[-15:]
            yield line
    if p.wait():
        raise RuntimeError(f"step failed (exit {p.returncode}). Last output:\n" + "\n".join(tail))


class Log:
    """Collects log lines; each step yields `log.text` so the UI shows the whole history."""

    def __init__(self):
        self.lines = []

    def add(self, line):
        if "%|" in line and self.lines and "%|" in self.lines[-1]:
            self.lines[-1] = line  # a progress bar redrawing itself: keep only its latest state
        else:
            self.lines.append(line)
        self.lines = self.lines[-400:]
        return self.text

    @property
    def text(self):
        return "\n".join(self.lines)


# ------------------------------------------------------------------ character

def char_dir(name):
    d = HOME / slug(name)
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_characters():
    return sorted(p.name for p in HOME.glob("*") if (p / "character.json").exists()) if HOME.exists() else []


def save_character(fields, start_image=None):
    d = char_dir(fields["name"])
    (d / "character.json").write_text(json.dumps(fields, indent=2))
    if start_image:
        img = ImageOps.exif_transpose(Image.open(start_image)).convert("RGB")
        w, h = img.size  # centre-crop to 480:832, then resize
        if w / h > WIDTH / HEIGHT:
            nw = int(h * WIDTH / HEIGHT)
            img = img.crop(((w - nw) // 2, 0, (w - nw) // 2 + nw, h))
        else:
            nh = int(w * HEIGHT / WIDTH)
            img = img.crop((0, (h - nh) // 2, w, (h - nh) // 2 + nh))
        img.resize((WIDTH, HEIGHT), Image.LANCZOS).save(d / "start.png")
    return d


def load_character(char_slug):
    d = HOME / char_slug
    fields = json.loads((d / "character.json").read_text())
    start = d / "start.png"
    return fields, str(start) if start.exists() else None


def import_pack(zip_path):
    """Unpack a character_pack.zip (from export_pack) into the studio; returns the character's slug."""
    tmp = HOME / "_import"
    shutil.rmtree(tmp, ignore_errors=True)
    shutil.unpack_archive(zip_path, tmp)
    found = next(tmp.rglob("character.json"))
    name = json.loads(found.read_text())["name"]
    dest = char_dir(name)
    for f in found.parent.iterdir():
        if f.is_file():
            shutil.copy(f, dest)
    shutil.rmtree(tmp)
    return dest.name


def export_pack(name):
    d = char_dir(name)
    files = [f for f in ("character.json", "start.png", "voice_ref.wav", "voice_meta.json") if (d / f).exists()]
    stage = HOME / "_export" / d.name
    shutil.rmtree(HOME / "_export", ignore_errors=True)
    stage.mkdir(parents=True)
    for f in files:
        shutil.copy(d / f, stage)
    return shutil.make_archive(str(d / f"{d.name}_character_pack"), "zip", HOME / "_export", d.name)


def video_prompt(fields):
    return (
        "Real vertical smartphone footage, waist-up, phone propped on a shelf, still camera. "
        f"{fields.get('look', '').strip().capitalize()}, in {fields.get('setting', '').strip()}. Faces the camera the whole time "
        "and looks into the lens as if about to speak to a friend: small natural head movements, a slight nod, gentle "
        "weight shifts, relaxed shoulders, natural blinks, warm engaged eyes, mouth relaxed and closed. "
        f"{fields.get('light', '').strip().capitalize()}. Sharp, natural colour, real skin texture."
    )


# ------------------------------------------------------------------ ideas and script (local LLM, in this process)

_writer = None


def _get_writer(fields):
    global _writer
    from ideas import Writer

    if _writer is None:
        _writer = Writer(fields)
    _writer.character = fields
    return _writer


def release_writer():
    """Free the LLM's GPU memory before a GPU-heavy step."""
    global _writer
    if _writer is not None:
        _writer.close()
        _writer = None


def ideas(fields, theme, n=8):
    return _get_writer(fields).ideas(n, theme)


def write_script(fields, idea, seconds):
    return _get_writer(fields).script(idea, seconds)


def new_video(name, script, hook):
    d = char_dir(name) / "videos" / time.strftime("%Y%m%d-%H%M%S")
    d.mkdir(parents=True)
    (d / "script.txt").write_text(script.strip())
    (d / "hook.txt").write_text(hook.strip())
    return str(d)


# ------------------------------------------------------------------ voice

def _ensure_tts(log):
    if not shutil.which("sox"):  # the voice library looks for SoX at start-up; install it to keep the log clean
        subprocess.run("apt-get -qq install -y sox", shell=True, capture_output=True)
    # The .ready marker is written only after a complete, verified install, so a half-finished install
    # (interrupted, out of disk, network blip) is redone instead of silently reused.
    if (TTS_ENV / ".ready").exists():
        return
    yield log.add("Installing the voice model environment (first time only, ~5 min)...")
    shutil.rmtree(TTS_ENV, ignore_errors=True)
    # torch from the CUDA 12.8 index: the newest PyPI build targets CUDA 13, which Kaggle's driver may not run.
    for line in stream(
        f"uv venv -q -p 3.10 {TTS_ENV} && "
        f"uv pip install -p {TTS_ENV} --index-url https://download.pytorch.org/whl/cu128 torch torchaudio && "
        f"uv pip install -p {TTS_ENV} qwen-tts soundfile numpy && "
        f"{TTS_ENV}/bin/python -c 'import torch, qwen_tts, soundfile, numpy; "
        "print(\"voice env OK, torch\", torch.__version__, \"cuda\", torch.cuda.is_available())'"
    ):
        if not line.startswith((" +", " -", "Resolved", "Prepared", "Installed", "Downloading", "Uninstalled")):
            yield log.add(line)
    (TTS_ENV / ".ready").touch()


def _tts(args):
    return f"{TTS_ENV}/bin/python {HERE}/tts.py {args}"


def saved_voice(name):
    d = char_dir(name)
    meta = d / "voice_meta.json"
    if (d / "voice_ref.wav").exists() and meta.exists():
        return str(d / "voice_ref.wav"), json.loads(meta.read_text())
    return None, None


def design_voice(name, description, language, takes, dtype="float32"):
    """Generator: yields (log, list of take paths)."""
    release_writer()
    log = Log()
    for t in _ensure_tts(log):
        yield t, []
    out = char_dir(name) / "voice_takes"
    shutil.rmtree(out, ignore_errors=True)
    spec = char_dir(name) / "voice_spec.txt"
    spec.write_text(description.strip())
    yield log.add(f"Designing {takes} voice takes..."), []
    line = TEST_LINE.replace('"', "'")
    for l in stream(_tts(f'--lang {language} --dtype {dtype} design --spec "{spec}" --line "{line}" --takes {takes} --out "{out}"')):
        # hand over each take as soon as it exists, so it can be played while the rest are made
        yield log.add(l), [str(out / f"take_{i}.wav") for i in range(1, takes + 1) if (out / f"take_{i}.wav").exists()]
    yield log.add("Listen and pick the one that sounds like your character."), [str(out / f"take_{i}.wav") for i in range(1, takes + 1)]


def lock_voice(name, take_path, description, language):
    d = char_dir(name)
    shutil.copy(take_path, d / "voice_ref.wav")
    (d / "voice_meta.json").write_text(
        json.dumps({"description": description.strip(), "ref_text": TEST_LINE, "language": language}, indent=2)
    )
    return str(d / "voice_ref.wav")


def speak(name, video_dir, dtype="float32"):
    """Generator: yields (log, voice path or None)."""
    release_writer()
    log = Log()
    ref, meta = saved_voice(name)
    if not ref:
        raise RuntimeError("No voice saved for this character yet: design one and click 'Use this voice'.")
    for t in _ensure_tts(log):
        yield t, None
    vd = Path(video_dir)
    (vd / "ref_text.txt").write_text(meta["ref_text"])
    yield log.add("Speaking the script in the character's voice..."), None
    cmd = _tts(f'--lang {meta["language"]} --dtype {dtype} speak --script "{vd}/script.txt" --ref "{ref}" '
               f'--ref-text "{vd}/ref_text.txt" --out "{vd}"')
    for l in stream(cmd):
        yield log.add(l), None
    lines = subtitle_lines(json.loads((vd / "sentences.json").read_text()))
    (vd / "lines.json").write_text(json.dumps(lines, indent=2))
    yield log.add(f"Voice ready: {duration(vd / 'voice.wav'):.1f}s, {len(lines)} subtitle lines."), str(vd / "voice.wav")


# ------------------------------------------------------------------ video takes

def make_takes(name, video_dir, prompt, negative, seeds, steps):
    """Generator: yields (log, list of take paths)."""
    release_writer()
    log = Log()
    vd = Path(video_dir)
    (vd / "prompt.txt").write_text(prompt.strip())
    (vd / "negative.txt").write_text(negative.strip())
    takes = vd / "takes"
    yield log.add(f"Making {len(seeds)} takes (about 20 min each on a T4)..."), []
    cmd = (f'python {HERE}/wan.py --image "{char_dir(name)}/start.png" --prompt "{vd}/prompt.txt" '
           f'--negative "{vd}/negative.txt" --seeds {" ".join(map(str, seeds))} --steps {steps} --out "{takes}"')
    for l in stream(cmd):
        yield log.add(l), sorted(map(str, takes.glob("take_seed*.mp4")))
    yield log.add("Takes ready. Pick the ones to use."), sorted(map(str, takes.glob("take_seed*.mp4")))


# ------------------------------------------------------------------ lip-sync

def _ensure_latentsync(log):
    if not (LATENTSYNC / ".ready").exists():
        yield log.add("Installing LatentSync (first time only, ~5 min)...")
        for line in stream(
            f"rm -rf {LATENTSYNC} && git clone -q https://github.com/bytedance/LatentSync.git {LATENTSYNC} && "
            f"(apt-get -qq install -y libgl1 > /dev/null 2>&1 || true) && cd {LATENTSYNC} && "
            "uv venv -q -p 3.10 .venv && uv pip install -q -p .venv -r requirements.txt && "
            ".venv/bin/huggingface-cli download ByteDance/LatentSync-1.5 whisper/tiny.pt latentsync_unet.pt "
            "--local-dir checkpoints"
        ):
            yield log.add(line)
        (LATENTSYNC / ".ready").touch()


def lipsync(video_dir, take_paths, keep_seconds, fp16=False, steps=20):
    """Generator: yields (log, lip-synced video path or None)."""
    release_writer()
    log = Log()
    vd = Path(video_dir)
    if not take_paths:
        raise RuntimeError("Pick at least one take.")
    yield log.add("Chaining the takes to the length of the voice..."), None
    keep = {p: keep_seconds for p in take_paths} if keep_seconds else None
    fit_to_audio(vd / "voice.wav", take_paths, vd / "lipsync_input.mp4", vd / "lipsync_voice.wav", keep=keep)
    for t in _ensure_latentsync(log):
        yield t, None
    sed = "s/get_device_capability()\\[0\\] > 7/get_device_capability()[0] >= 7/" if fp16 else \
          "s/get_device_capability()\\[0\\] >= 7/get_device_capability()[0] > 7/"
    subprocess.run(["sed", "-i", sed, str(LATENTSYNC / "scripts/inference.py")], check=True)
    yield log.add(f"Lip-syncing {duration(vd / 'lipsync_voice.wav'):.0f}s (about 1-3 min per second)..."), None
    out = vd / "lipsync.mp4"
    cmd = (".venv/bin/python -m scripts.inference --unet_config_path configs/unet/stage2.yaml "
           f"--inference_ckpt_path checkpoints/latentsync_unet.pt --inference_steps {steps} --guidance_scale 1.5 "
           f'--seed 1247 --enable_deepcache --video_path "{vd}/lipsync_input.mp4" --audio_path "{vd}/lipsync_voice.wav" '
           f'--video_out_path "{out}" --temp_dir /tmp/ls_temp')
    for l in stream(cmd, cwd=LATENTSYNC, env={"MPLBACKEND": "Agg"}):
        yield log.add(l), None
    for f in ("lipsync_input.mp4", "lipsync_voice.wav"):
        (vd / f).unlink(missing_ok=True)
    yield log.add("Lip-sync done."), str(out)


# ------------------------------------------------------------------ finishing

def _ensure_node(log):
    """Use the system's Node.js if there is one; otherwise (Kaggle) download a Linux build to /tmp."""
    if shutil.which("node") or (NODE / "node").exists():
        return
    yield log.add("Installing Node.js (first time only)...")
    for line in stream(f"curl -fsSL https://nodejs.org/dist/v20.18.0/node-v20.18.0-linux-x64.tar.xz | tar -xJ -C {NODE.parent.parent}"):
        yield log.add(line)


def finish(video_dir, hook, ambient_volume, engine="remotion"):
    """Generator: yields (log, final video path or None)."""
    log = Log()
    vd = Path(video_dir)
    voice, lipsynced = vd / "voice.wav", vd / "lipsync.mp4"
    lines = json.loads((vd / "lines.json").read_text())
    raw = vd / "finished_raw.mp4"
    ambient = REMOTION / "public/audio/ambient.wav"
    env = {"PATH": f"{NODE}:{os.environ['PATH']}"}
    try:  # Node.js renders with Remotion and generates the ambient bed
        for t in _ensure_node(log):
            yield t, None
        if not ambient.exists():
            for l in stream("node tools/make-audio.mjs", cwd=REMOTION, env=env):
                yield log.add(l), None
    except RuntimeError as e:
        yield log.add(f"Node.js unavailable ({e}); finishing with ffmpeg, without ambient sound."), None
        engine = "ffmpeg"

    if engine == "remotion":
        try:
            yield log.add("Installing headless-browser libraries..."), None
            for lib in ("libnss3 libdbus-1-3 libatk1.0-0 libgbm1 libasound2 libxrandr2 libxkbcommon0 libxfixes3 "
                        "libxcomposite1 libxdamage1 libatk-bridge2.0-0 libpango-1.0-0 libcairo2 libcups2").split():
                subprocess.run(f"apt-get -qq install -y {lib}", shell=True, capture_output=True)
            (REMOTION / "public/video").mkdir(parents=True, exist_ok=True)
            shutil.copy(lipsynced, REMOTION / "public/video/talking.mp4")
            shutil.copy(voice, REMOTION / "public/audio/voice.wav")
            (REMOTION / "props.json").write_text(json.dumps({
                "video": "video/talking.mp4", "voice": "audio/voice.wav", "lines": lines, "hook": hook,
                "durationSeconds": duration(voice), "ambientVolume": ambient_volume,
            }))
            yield log.add("Rendering with Remotion..."), None
            for l in stream("npm install --silent --no-audit --no-fund", cwd=REMOTION, env=env):
                yield log.add(l), None
            for l in stream(f'npx remotion render src/index.ts Talking "{raw}" --props=props.json --codec=h264 '
                            "--crf=18 --log=error", cwd=REMOTION, env=env):
                yield log.add(l), None
        except RuntimeError as e:
            yield log.add(f"Remotion failed ({e}); finishing with ffmpeg instead."), None
            engine = "ffmpeg"
    if engine == "ffmpeg":
        yield log.add("Finishing with ffmpeg..."), None
        finish_ffmpeg(lipsynced, voice, lines, hook, raw, ambient=ambient if ambient_volume and ambient.exists() else None,
                      ambient_volume=ambient_volume)
    final = vd / "final.mp4"
    loudnorm(raw, final)
    raw.unlink()
    yield log.add(f"Done: {final}"), str(final)
