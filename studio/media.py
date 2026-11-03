"""ffmpeg steps: stretch base takes under the voice-over, a plain finishing fallback, loudness."""

import subprocess
import tempfile
from pathlib import Path


def run(*cmd):
    subprocess.run([str(c) for c in cmd], check=True)


def duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
        check=True, capture_output=True, text=True,
    )
    return float(out.stdout)


def fit_to_audio(voice, clips, out_video, out_wav, keep=None, fps=25, size=(480, 832)):
    """Chain the base takes under the voice-over, ready for lip-sync.

    Each take plays forward then backward (ping-pong), so it ends on its own first frame; takes made from
    the same start frame share that frame, so chaining them gives variety with no visible jump. The chain
    repeats as needed and is cut to the voice length. `keep` maps a clip path to the seconds to keep from
    its start (to drop an unwanted gesture at the end). LatentSync expects 25 fps and 16 kHz mono audio.
    """
    keep = keep or {}
    w, h = size
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        listing = tmp / "list.txt"
        with listing.open("w") as f:
            for i, clip in enumerate(clips):
                trim = f"trim=end={keep[clip]}," if clip in keep else ""
                pp = tmp / f"pp{i}.mp4"
                run(
                    "ffmpeg", "-v", "error", "-y", "-i", clip, "-filter_complex",
                    f"[0:v]{trim}fps={fps},scale={w}:{h}:flags=lanczos,setsar=1,split[f][b];"
                    "[b]reverse,trim=start_frame=1,setpts=PTS-STARTPTS[r];[f][r]concat=n=2:v=1:a=0[v]",
                    "-map", "[v]", "-an", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p", pp,
                )
                f.write(f"file '{pp}'\n")
        chain = tmp / "chain.mp4"
        run("ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", listing, "-c", "copy", chain)
        run(
            "ffmpeg", "-v", "error", "-y", "-stream_loop", "-1", "-i", chain, "-i", voice,
            "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-crf", "14", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{duration(voice):.3f}", out_video,
        )
    run("ffmpeg", "-v", "error", "-y", "-i", voice, "-ar", "16000", "-ac", "1", out_wav)


def _font(size):
    from matplotlib import font_manager
    from PIL import ImageFont

    path = font_manager.findfont(font_manager.FontProperties(family="DejaVu Sans", weight="bold"))
    return ImageFont.truetype(path, size)


def _text_card(text, path, size, fg, bg, top=None, bottom=None, W=1080, H=1920, max_w=900):
    """A full-frame transparent PNG with `text` wrapped in a rounded box (drawn with PIL, so ffmpeg needs no libass)."""
    from PIL import Image, ImageDraw

    font = _font(size)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    rows, row = [], ""
    for word in text.split():
        trial = f"{row} {word}".strip()
        if d.textlength(trial, font=font) <= max_w - 64 or not row:
            row = trial
        else:
            rows.append(row)
            row = word
    rows.append(row)
    lh = int(size * 1.25)
    bw = int(max(d.textlength(r, font=font) for r in rows)) + 64
    bh = lh * len(rows) + 36
    y0 = top if top is not None else H - bottom - bh
    x0 = (W - bw) // 2
    d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=24, fill=bg)
    for i, r in enumerate(rows):
        d.text((W // 2, y0 + 18 + i * lh + lh // 2), r, font=font, fill=fg, anchor="mm")
    img.save(path)


def finish_ffmpeg(video, voice, lines, hook, out, ambient=None, ambient_volume=0.18):
    """Plain finishing without Remotion: 1080x1920, boxed subtitles, hook title, ambient bed."""
    dur = duration(voice)
    with tempfile.TemporaryDirectory() as tmp:
        cards = [(l["text"], l["from"], l["to"], dict(size=60, fg="white", bg=(12, 16, 10, 158), bottom=300)) for l in lines]
        if hook:
            cards.append((hook, 0.15, 4.0, dict(size=64, fg=(17, 17, 17), bg="white", top=210)))
        inputs, chain, last = ["-i", video, "-i", voice], ["[0:v]scale=1080:1920:flags=lanczos,setsar=1[v0]"], "v0"
        for i, (text, a, b, style) in enumerate(cards):
            png = Path(tmp) / f"card{i}.png"
            _text_card(text, png, **style)
            inputs += ["-loop", "1", "-t", f"{dur:.3f}", "-i", png]
            chain.append(f"[{last}][{i + 2}:v]overlay=0:0:enable='between(t,{a},{b})'[v{i + 1}]")
            last = f"v{i + 1}"
        if ambient:
            inputs += ["-stream_loop", "-1", "-i", ambient]
            chain.append(f"[{len(cards) + 2}:a]volume={ambient_volume}[bed];[1:a][bed]amix=inputs=2:duration=first:normalize=0[a]")
        else:
            chain.append("[1:a]anull[a]")
        run(
            "ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", ";".join(chain),
            "-map", f"[{last}]", "-map", "[a]", "-c:v", "libx264", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", out,
        )


def loudnorm(src, out, target=-14):
    """Normalise to social-media loudness (about -14 LUFS), video copied as is."""
    run(
        "ffmpeg", "-v", "error", "-y", "-i", src, "-c:v", "copy",
        "-af", f"loudnorm=I={target}:TP=-1.5:LRA=11", "-ar", "48000", "-c:a", "aac", "-b:a", "192k", out,
    )
