"""AI Influencer Studio web UI (Gradio). Each tab is one step; the steps themselves live in pipeline.py.

  python app.py               # local
  launch(share=True, password="...")   # from the notebook: a public link, protected by a password
"""

import html
import inspect
import json
import threading
import time
from pathlib import Path

import gradio as gr

import pipeline as P

GUIDE = (Path(__file__).parent / "guide.md").read_text()
FIELDS = ["name", "niche", "audience", "backstory", "usp", "tone", "catchphrase", "hard_limits", "look", "setting", "light"]
LABELS = {
    "name": ("Name", 1, "Ada Brooks"),
    "niche": ("Niche", 1, "mobility and back pain for desk workers"),
    "audience": ("Audience", 1, "people with desk jobs, sore backs and no time"),
    "backstory": ("Backstory", 4, "Former NHS physiotherapist, 10 years on hospital wards, burned out in a desk job "
                  "herself, rebuilt with five-minute routines between meetings."),
    "usp": ("What makes them different", 2, "One small, evidence-based move per video; says plainly when the evidence is thin."),
    "tone": ("Tone of voice", 1, "warm, practical, a little dry; talks with you, not at you"),
    "catchphrase": ("Catchphrase", 1, "Small moves, every day."),
    "hard_limits": ("Hard limits", 2, "no diagnosing, no cure claims, no invented studies; sends anything serious to a professional"),
    "look": ("Look in the start frame (for the video prompt)", 2, "a woman in her late 30s with shoulder-length dark hair "
             "tied back, light freckles, small silver hoops, wearing a soft grey crew-neck jumper"),
    "setting": ("Setting in the start frame", 1, "a bright small kitchen with plants on the windowsill"),
    "light": ("Light", 1, "soft daylight from a window on the left, exposure constant"),
}
DEFAULT_VOICE = (
    "Warm, grounded British woman, late 30s, neutral modern English accent. Medium pitch, natural chest resonance, "
    "faint lived-in texture, not radio polish. Calm, unhurried pace with natural pauses. Plain-spoken and "
    "reassuring, dry warmth, never salesy or theatrical. Intimate close-mic podcast delivery."
)
LANGUAGES = ["English", "Chinese", "Japanese", "Korean", "German", "French", "Russian", "Portuguese", "Spanish", "Italian"]
MAX_TAKES = 4


CSS = """
.status {display: flex; align-items: center; gap: 14px; padding: 14px 18px; border-radius: 12px;
          font-size: 15px; line-height: 1.4; border: 1px solid var(--border-color-primary);
          background: var(--background-fill-secondary);}
.status b {white-space: nowrap;}
.status .detail {opacity: .75; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; flex: 1;}
.status .clock {font-variant-numeric: tabular-nums; opacity: .75;}
.spinner {width: 20px; height: 20px; flex: none; border-radius: 50%; border: 3px solid rgba(128, 128, 128, .3);
           border-top-color: var(--color-accent, #f97316); animation: spin .9s linear infinite;}
@keyframes spin {to {transform: rotate(360deg);}}
.status.done {border-color: #22c55e;} .status.fail {border-color: #ef4444;} .status.stopped {border-color: #f59e0b;}
"""


def status_html(state, title, detail="", seconds=0):
    """The bar above a step's output: a spinner while it runs, then a tick or a cross."""
    icon = {"busy": '<div class="spinner"></div>', "done": "✅", "fail": "❌", "stopped": "⏹"}[state]
    clock = f'<span class="clock">{int(seconds) // 60}:{int(seconds) % 60:02d}</span>' if seconds else ""
    return (f'<div class="status {state}">{icon}<b>{html.escape(title)}</b>'
            f'<span class="detail">{html.escape(detail)}</span>{clock}</div>')


class Job:
    """One step running in a background thread on the server.

    It belongs to the server, not to a browser connection: closing the tab, losing the network or the share
    link dropping does not stop it. The page polls the job (see `tick` in build) and shows its latest output,
    so reopening the link picks the progress straight back up.
    """

    def __init__(self, kind, slot, title, detail, gen, log_first, heavy, on_end=None):
        self.kind, self.slot, self.title, self.detail, self.on_end = kind, slot, title, detail, on_end
        self.log_first, self.heavy = log_first, heavy
        self.out, self.version, self.state, self.error, self.quiet = None, 0, "busy", "", False
        self.t0, self.t1 = time.time(), None
        threading.Thread(target=self._run, args=(gen,), daemon=True).start()

    def _run(self, gen):
        try:
            for out in gen:
                self.out = out if isinstance(out, tuple) else (out,)
                if self.log_first and "❌ FAILED" in (self.out[0] or ""):
                    self.state = "fail"
                self.version += 1
            if self.state == "busy":
                self.state = "done"
        except P.Stopped as e:
            self.error, self.state = str(e), "stopped"
        except gr.Error as e:
            self.error, self.state = e.message, "fail"
            self.quiet = not getattr(e, "print_exception", True)  # a "do X first" message, not a failure
        except Exception as e:  # noqa: BLE001
            self.error, self.state = f"{type(e).__name__}: {e}", "fail"
        finally:
            self.t1 = time.time()
            self.version += 1
            if self.on_end:
                self.on_end()

    def status(self):
        seconds = (self.t1 or time.time()) - self.t0
        if self.state == "busy":
            log = (self.out[0] or "") if self.log_first and self.out else ""
            last = next((l for l in reversed(log.splitlines()) if l.strip()), "") or self.detail
            return status_html("busy", self.title + "...", last, max(seconds, 0.1))
        if self.state == "stopped":
            return status_html("stopped", self.title + " stopped", self.error, seconds)
        if self.state == "fail":
            return status_html("fail", self.title + " failed", self.error or "see the log below", seconds)
        return status_html("done", self.title + " done", "", seconds)


JOBS = {}  # slot -> its latest Job (one per area of the page)
SESSION_FILE = P.HOME / "session.json"


def session(**changes):
    """The current character and video, kept on disk so a reopened page (or a new browser) can restore them."""
    data = json.loads(SESSION_FILE.read_text()) if SESSION_FILE.exists() else {}
    if changes:
        data.update(changes)
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps(data))
    return data


def nope(message):
    """A 'please do X first' message: shown in the app, without a traceback in the notebook log."""
    return gr.Error(message, title="Not yet", print_exception=False)


def guarded(fn):
    """Show a step's real error message in the UI (Gradio otherwise shows only "Error")."""
    def message(e):
        return f"{type(e).__name__}: {e}" if str(e) else type(e).__name__

    if inspect.isgeneratorfunction(fn):
        # Long steps yield (log, ...). On failure, keep the log on screen and add the error to it, so the
        # user sees what went wrong instead of an "Error" badge over an empty box.
        def run(*args):
            last = None
            try:
                for last in fn(*args):
                    yield last
            except (gr.Error, P.Stopped):
                raise
            except Exception as e:  # noqa: BLE001
                if last is None:
                    raise gr.Error(message(e)) from e  # a real failure
                log = (last[0] or "") + f"\n\n❌ FAILED: {message(e)}"
                yield (log, *[gr.update() for _ in last[1:]])
    else:
        def run(*args):
            try:
                return fn(*args)
            except gr.Error:
                raise
            except Exception as e:  # noqa: BLE001
                raise gr.Error(message(e)) from e  # a real failure
    return run


def build():
    with gr.Blocks(title="AI Influencer Studio") as demo:
        video_dir = gr.State("")
        gr.Markdown("# AI Influencer Studio\nCharacter → idea → script → voice → video → lip-sync → finished vertical video. "
                    "Free GPU, open models, no API keys. New here? Start with the **Guide** tab.")

        with gr.Row():
            gr.Markdown("")
            stop_btn = gr.Button("⏹ Stop the running step", variant="stop", size="sm", scale=0)
        with gr.Row(visible=False) as resume_row:
            resume_note = gr.Markdown()
            resume_btn = gr.Button("▶ Resume", variant="primary", scale=0)

        # ---------------------------------------------------------------- guide
        with gr.Tab("Guide"):
            gr.Markdown(GUIDE)

        # ---------------------------------------------------------------- character
        with gr.Tab("1 · Character"):
            with gr.Row():
                saved = gr.Dropdown(P.list_characters(), label="Saved characters", scale=3)
                load_btn = gr.Button("Load", scale=1)
                pack_in = gr.File(label="Import character pack (.zip)", file_types=[".zip"], scale=2, height=120)
            with gr.Row():
                with gr.Column(scale=3):
                    boxes = {f: gr.Textbox(label=LABELS[f][0], lines=LABELS[f][1], value=LABELS[f][2]) for f in FIELDS}
                with gr.Column(scale=2):
                    start = gr.Image(label="Start frame (waist-up, face big, 9:16)", type="filepath", height=520)
                    save_btn = gr.Button("Save character", variant="primary")
                    char_status = gr.Markdown()
                    full_backup = gr.Checkbox(label="Full backup: include video takes and finished videos (bigger file). "
                                                    "Import it in a new Kaggle session to carry on where you stopped.")
                    export_btn = gr.Button("Export character pack")
                    pack_out = gr.File(label="Character pack")

        # ---------------------------------------------------------------- script
        with gr.Tab("2 · Script"):
            gr.Markdown("Paste your own script, **or** get ideas and let the writer draft one. Blank line between beats. "
                        "Read it before you use it: you're responsible for what the character says.")
            with gr.Row():
                theme = gr.Textbox(label="Theme (optional)", placeholder="e.g. sleep, common myths", scale=3)
                ideas_btn = gr.Button("Suggest ideas", scale=1)
            script_busy = gr.HTML()
            idea_pick = gr.Radio([], label="Ideas")
            with gr.Row():
                seconds = gr.Slider(15, 60, value=35, step=5, label="Length (seconds)")
                write_btn = gr.Button("Write script for this idea")
            script = gr.Textbox(label="Script", lines=10)
            hook = gr.Textbox(label="Hook title (on screen for the first 4 s; empty for none)")
            with gr.Row():
                use_btn = gr.Button("Use this script", variant="primary")
                auto_btn = gr.Button("Autopilot: voice → video → lip-sync → finish")
            script_status = gr.Markdown()
            auto_status = gr.HTML()
            auto_log = gr.Textbox(label="Autopilot log", lines=10, autoscroll=True)
            auto_out = gr.Video(label="Final video", height=560)

        # ---------------------------------------------------------------- voice
        with gr.Tab("3 · Voice"):
            gr.Markdown("**First time:** describe the voice, design a few takes, pick one, **Use this voice**. "
                        "It's saved with the character and reused for every script, so they always sound the same.")
            current_voice = gr.Audio(label="Saved voice", type="filepath", interactive=False)
            voice_desc = gr.Textbox(label="Voice description", lines=4, value=DEFAULT_VOICE)
            with gr.Row():
                language = gr.Dropdown(LANGUAGES, value="English", label="Language")
                n_takes = gr.Slider(2, MAX_TAKES, value=4, step=1, label="Takes")
                design_btn = gr.Button("Design voice")
            voice_status = gr.HTML()
            take_audio = [gr.Audio(label=f"Take {i + 1}", type="filepath", interactive=False, visible=False)
                          for i in range(MAX_TAKES)]
            with gr.Row():
                take_pick = gr.Radio([], label="Pick a take")
                lock_btn = gr.Button("Use this voice", variant="primary")
            speak_btn = gr.Button("Speak the script", variant="primary")
            voice_log = gr.Textbox(label="Log", lines=8, autoscroll=True)
            voice_out = gr.Audio(label="Voice-over", type="filepath", interactive=False)

        # ---------------------------------------------------------------- video
        with gr.Tab("4 · Video"):
            gr.Markdown("Each seed is one ~5 s take of the character facing the camera (about 20 min each on a T4). "
                        "Lip-sync adds the speaking later, so the mouth stays relaxed here.")
            video_info = gr.Markdown("⚠ No script yet: write one on the **Script** tab and click **Use this script**.")
            prompt = gr.Textbox(label="Prompt", lines=5)
            negative = gr.Textbox(label="Negative prompt", lines=3, value=P.DEFAULT_NEGATIVE)
            with gr.Row():
                seeds = gr.Textbox(label="Seeds (one take each)", value="42, 7, 1234")
                steps = gr.Slider(20, 50, value=40, step=5, label="Steps (fewer = faster, softer)")
                takes_btn = gr.Button("Make takes only")
            full_btn = gr.Button("🎬 Make the full video from this script  (voice → takes → lip-sync → finish)",
                                 variant="primary", size="lg")
            takes_status = gr.HTML()
            takes_log = gr.Textbox(label="Log", lines=8, autoscroll=True)
            with gr.Row():
                take_videos = [gr.Video(label=f"Take {i + 1}", height=360, visible=False) for i in range(MAX_TAKES)]
            full_out = gr.Video(label="Final video", height=640)

        # ---------------------------------------------------------------- lip-sync & finish
        with gr.Tab("5 · Lip-sync & finish"):
            ls_info = gr.Markdown("⚠ No script yet: save one on the **Script** tab.")
            use_takes = gr.CheckboxGroup([], label="Takes to use (in this order); skip any where the face warps")
            with gr.Row():
                keep = gr.Number(value=0, minimum=0, maximum=5, step=0.5, label="Keep only the first N seconds of each take (0 = all)")
                fp16 = gr.Checkbox(label="Faster lip-sync (fp16); turn off if the mouth looks noisy")
                ls_btn = gr.Button("Lip-sync", variant="primary")
            ls_status = gr.HTML()
            ls_log = gr.Textbox(label="Log", lines=8, autoscroll=True)
            ls_out = gr.Video(label="Lip-synced", height=480)
            with gr.Row():
                fin_hook = gr.Textbox(label="Hook title")
                ambient = gr.Slider(0, 0.5, value=0.18, step=0.02, label="Ambient sound")
                engine = gr.Radio(["remotion", "ffmpeg"], value="remotion", label="Finish with")
                fin_btn = gr.Button("Finish", variant="primary")
            fin_status = gr.HTML()
            fin_log = gr.Textbox(label="Log", lines=6, autoscroll=True)
            final = gr.Video(label="Final video", height=640)
            final_file = gr.File(label="Download")

        # ================================================================ wiring
        def fields_of(*vals):
            f = dict(zip(FIELDS, vals))
            if not f["name"].strip():
                raise nope("Give the character a name first.")
            return f

        def voice_state(name):
            ref, meta = P.saved_voice(name) if name.strip() else (None, None)
            return ref, (meta or {}).get("description", DEFAULT_VOICE), (meta or {}).get("language", "English")

        @guarded
        def on_save(start_img, *vals):
            f = fields_of(*vals)
            d = P.save_character(f, start_img)
            session(character=d.name)
            has_start = (d / "start.png").exists()
            msg = f"Saved **{f['name']}**." + ("" if has_start else " ⚠ Upload a start frame before making video.")
            return msg, gr.update(choices=P.list_characters(), value=d.name), P.video_prompt(f), *voice_state(f["name"])

        @guarded
        def on_load(char_slug):
            if not char_slug:
                raise nope("Pick a saved character.")
            f, start_img = P.load_character(char_slug)
            session(character=char_slug)
            return (*[f.get(k, "") for k in FIELDS], start_img, P.video_prompt(f), *voice_state(f["name"]))

        @guarded
        def on_import(zip_file):
            if not zip_file:
                return gr.update()
            return gr.update(choices=P.list_characters(), value=P.import_pack(zip_file))


        @guarded
        def on_ideas(theme_, *vals):
            found = P.ideas(fields_of(*vals), theme_)
            return gr.update(choices=found, value=found[0] if found else None)

        @guarded
        def on_write(idea, secs, theme_, *vals):
            idea = idea or theme_.strip()  # no idea picked: write straight from the theme
            if not idea:
                raise nope("Click **Suggest ideas** and pick one, type a theme, or paste your own script.")
            return P.write_script(fields_of(*vals), idea, int(secs))

        def script_info(vd):
            if not vd or not (Path(vd) / "script.txt").exists():
                return "⚠ No script yet: write one on the **Script** tab and click **Use this script**."
            text = (Path(vd) / "script.txt").read_text().strip()
            first = text.split("\n")[0][:110] + ("…" if len(text) > 110 else "")
            voice = Path(vd) / "voice.wav"
            spoken = f" · voice-over ready ({P.duration(voice):.0f} s)" if voice.exists() else " · not spoken yet (done automatically)"
            return f"🎙 **Using the script saved in step 2:** “{first}” ({len(text.split())} words){spoken}"

        def parse_seeds(text):
            try:
                s = [int(x) for x in text.replace(",", " ").split()]
            except ValueError:
                raise nope("Seeds must be whole numbers, e.g. 42, 7, 1234.") from None
            if not 1 <= len(s) <= MAX_TAKES:
                raise nope(f"Use 1 to {MAX_TAKES} seeds.")
            return s

        def take_updates(paths):
            vids = [gr.update(value=paths[i] if i < len(paths) else None, visible=i < len(paths)) for i in range(MAX_TAKES)]
            choices = [(Path(p).stem.replace("take_", ""), p) for p in paths]
            return vids, gr.update(choices=choices, value=[p for _, p in choices])

        def lipsync_info(vd, chosen=None):
            if not vd:
                return "⚠ No script yet: save one on the **Script** tab."
            voice = Path(vd) / "voice.wav"
            v = f"🎙 voice-over of the saved script ({P.duration(voice):.0f} s)" if voice.exists() else \
                "🎙 voice-over: not made yet (Voice tab → **Speak the script**, or the 🎬 button)"
            takes = chosen or saved_takes(vd)
            t = ("🎞 takes: " + ", ".join(Path(p).stem.replace("take_seed", "seed ") for p in takes)) if takes else \
                "🎞 takes: none yet (Video tab)"
            return f"**Lip-sync uses:** {v} · {t}"

        def saved_takes(vd):
            f = Path(vd) / "takes.json"
            return [p for p in json.loads(f.read_text()) if Path(p).exists()] if f.exists() else []

        @guarded
        def on_use(script_, hook_, prompt_, negative_, seeds_, steps_, *vals):
            f = fields_of(*vals)
            if not script_.strip():
                raise nope("The script is empty.")
            d = P.new_video(f["name"], script_, hook_)
            session(character=P.slug(f["name"]), video_dir=d)
            have = P.existing_takes(f["name"], prompt_ or P.video_prompt(f), negative_, steps_, parse_seeds(seeds_))
            if have:  # takes don't depend on the script: reuse the character's existing ones
                (Path(d) / "takes.json").write_text(json.dumps(have))
            vids, choices = take_updates(have)
            note = f" {len(have)} video take(s) from before will be reused." if have else ""
            return (d, f"Script saved for **{f['name']}**.{note} Next: the **Voice** tab.", hook_, script_info(d),
                    *vids, choices, lipsync_info(d))


        @guarded
        def on_design(name, desc, lang, n):
            n = int(n)
            for log, paths in P.design_voice(name, desc, lang, n):
                audios = [gr.update(value=paths[i] if i < len(paths) else None, visible=i < n) for i in range(MAX_TAKES)]
                pick = gr.update(choices=[(f"Take {i + 1}", p) for i, p in enumerate(paths)],
                                 value=paths[0] if paths else None)
                yield log, *audios, pick

        @guarded
        def on_lock(name, take, desc, lang):
            if not take:
                raise nope("Design the voice and pick a take first.")
            return P.lock_voice(name, take, desc, lang)

        @guarded
        def on_speak(name, vd):
            if not vd:
                raise nope("Save a script first (Script tab → Use this script).")
            for log, path in P.speak(name, vd):
                yield log, path


        @guarded
        def on_takes(name, vd, prompt_, negative_, seeds_, steps_):
            if not vd:
                raise nope("Save a script first (Script tab → Use this script).")
            for log, paths in P.make_takes(name, vd, prompt_, negative_, parse_seeds(seeds_), int(steps_)):
                vids, choices = take_updates(paths)
                yield log, *vids, choices


        @guarded
        def on_lipsync(vd, takes, keep_, fp16_):
            if not vd:
                raise nope("Save a script first.")
            takes = takes or saved_takes(vd)
            if not takes:
                raise nope("No video takes yet: make them on the Video tab.")
            if not (Path(vd) / "voice.wav").exists():
                raise nope("No voice-over yet: Voice tab → Speak the script.")
            for log, path in P.lipsync(vd, takes, float(keep_ or 0), fp16_):
                yield log, path

        @guarded
        def on_finish(vd, hook_, amb, eng):
            if not vd or not (Path(vd) / "lipsync.mp4").exists():
                raise nope("Lip-sync first.")
            for log, path in P.finish(vd, hook_, float(amb), eng):
                yield log, path, path


        def full_run(f, vd, prompt_, negative_, seeds_, steps_, hook_, amb):
            """Voice (if not spoken yet) -> takes -> lip-sync -> finish for the saved script in `vd`.
            Yields (log, take paths, final video or None)."""
            if not P.saved_voice(f["name"])[0]:
                raise nope("Design the voice first (Voice tab → Design voice → Use this voice).")
            if not (P.char_dir(f["name"]) / "start.png").exists():
                raise nope("Upload a start frame on the Character tab and save first.")
            seeds_list = parse_seeds(seeds_)
            takes = lambda: saved_takes(vd)
            spoken = (Path(vd) / "voice.wav").exists() and (Path(vd) / "lines.json").exists()
            stages = [] if spoken else [("1/4 VOICE", lambda: P.speak(f["name"], vd))]
            stages += [("2/4 TAKES", lambda: P.make_takes(f["name"], vd, prompt_ or P.video_prompt(f), negative_,
                                                          seeds_list, int(steps_)))]
            ls, inputs = Path(vd) / "lipsync.mp4", [Path(vd) / "voice.wav", Path(vd) / "takes.json"]
            synced = ls.exists() and all(i.exists() and ls.stat().st_mtime > i.stat().st_mtime for i in inputs)
            if not synced:  # resuming after a restart: a finished lip-sync for the same voice and takes is kept
                stages += [("3/4 LIP-SYNC", lambda: P.lipsync(vd, takes(), 0))]
            stages += [("4/4 FINISH", lambda: P.finish(vd, hook_, float(amb)))]
            history = ["Voice-over already made, reusing it."] if spoken else []
            for title, make in stages:
                log = ""
                for log, result in make():
                    final_ = result if title.endswith("FINISH") else None
                    shown = result if title.endswith("TAKES") else takes()
                    yield "\n".join(history + [f"== {title} ==", log]), shown, final_
                history += [f"== {title} ==", log.splitlines()[-1] if log else ""]

        @guarded
        def on_full(vd, prompt_, negative_, seeds_, steps_, hook_, amb, *vals):
            if not vd:
                raise nope("Save a script first (Script tab → Use this script).")
            for log, paths, final_ in full_run(fields_of(*vals), vd, prompt_, negative_, seeds_, steps_, hook_, amb):
                vids, choices = take_updates(paths)
                yield log, *vids, choices, final_ or gr.update()


        @guarded
        def on_auto(script_, hook_, prompt_, negative_, seeds_, steps_, amb, *vals):
            f = fields_of(*vals)
            if not script_.strip():
                raise nope("The script is empty.")
            vd = P.new_video(f["name"], script_, hook_)
            session(character=P.slug(f["name"]), video_dir=vd)
            for log, _, final_ in full_run(f, vd, prompt_, negative_, seeds_, steps_, hook_, amb):
                yield log, final_, vd

        # ================================================================ background jobs
        # slot = one area of the page with one status bar; it shows the latest job started there.
        SLOTS = {
            "script": (script_busy, [idea_pick, script, hook]),
            "voice": (voice_status, [voice_log, *take_audio, take_pick, voice_out, video_info, ls_info]),
            "video": (takes_status, [takes_log, *take_videos, use_takes, full_out, video_info, ls_info]),
            "lipsync": (ls_status, [ls_log, ls_out, ls_info]),
            "finish": (fin_status, [fin_log, final, final_file]),
            "auto": (auto_status, [auto_log, auto_out, video_dir, video_info, ls_info]),
        }
        # kind: (slot, title, detail while it has no log yet, handler, what the handler returns, log first?, GPU?)
        KINDS = {
            "ideas": ("script", "Thinking up ideas", "the first time this downloads the 8 GB script-writer model, about 1–3 min", on_ideas, [idea_pick], False, False),
            "write": ("script", "Writing the script", "the first time this downloads the 8 GB script-writer model, about 1–3 min", on_write, [script, hook], False, False),
            "design": ("voice", "Designing the voice", "", on_design, [voice_log, *take_audio, take_pick], True, True),
            "speak": ("voice", "Speaking the script", "", on_speak, [voice_log, voice_out], True, True),
            "takes": ("video", "Making the video takes", "", on_takes, [takes_log, *take_videos, use_takes], True, True),
            "full": ("video", "Making the full video", "", on_full, [takes_log, *take_videos, use_takes, full_out], True, True),
            "lipsync": ("lipsync", "Lip-syncing", "", on_lipsync, [ls_log, ls_out], True, True),
            "finish": ("finish", "Finishing the video", "", on_finish, [fin_log, final, final_file], True, False),
            "auto": ("auto", "Autopilot", "", on_auto, [auto_log, auto_out, video_dir], True, True),
        }

        def starter(kind):
            slot, title, detail, fn, _, log_first, heavy = KINDS[kind]

            def click(*args):
                running = [j for j in JOBS.values() if j.state == "busy" and (j.slot == slot or (heavy and j.heavy))]
                if running:
                    raise nope(f"“{running[0].title}” is still running (it keeps going even if you close the "
                                   "page). Wait for it to finish, then try again.")
                if inspect.isgeneratorfunction(fn):
                    gen = fn(*args)
                else:
                    def gen_once():
                        yield fn(*args)
                    gen = gen_once()
                if heavy:  # remembered on disk: if the app or notebook restarts mid-run, it can be resumed
                    session(pending={"kind": kind, "title": title, "args": list(args)})
                job = JOBS[slot] = Job(kind, slot, title, detail, gen, log_first, heavy,
                                       on_end=(lambda: session(pending=None)) if heavy else None)
                for _ in range(10):  # a quick validation error ("save a script first") is shown straight away
                    if job.state != "busy":
                        break
                    time.sleep(0.1)
                if job.state == "fail":
                    if job.quiet:
                        JOBS.pop(slot, None)  # nothing ran: don't leave a "failed" bar behind
                        if heavy:
                            session(pending=None)
                        raise nope(job.error)
                    raise gr.Error(job.error or "This step failed; see the log.")
                return job.status()
            return click

        def ticker(slot):
            status, comps = SLOTS[slot]

            def tick(seen):
                job = JOBS.get(slot)
                same = [gr.update()] * len(comps)
                if job is None:
                    return seen, *same, gr.update()
                if job.version == seen:  # nothing new: only the status bar's clock moves
                    return seen, *same, (job.status() if job.state == "busy" else gr.update())
                given = {id(c): v for c, v in zip(KINDS[job.kind][4], job.out or ())}
                vd = session().get("video_dir", "")
                values = []
                for c in comps:
                    if id(c) in given:
                        values.append(given[id(c)])
                    elif c is video_info:
                        values.append(script_info(vd))
                    elif c is ls_info:
                        values.append(lipsync_info(vd))
                    else:
                        values.append(gr.update())
                return job.version, *values, job.status()
            return tick

        timer = gr.Timer(2.0)
        for slot, (status, comps) in SLOTS.items():
            seen = gr.State(-1)
            timer.tick(ticker(slot), [seen], [seen, *comps, status], show_progress="hidden", queue=False)

        def go(kind, button, inputs):
            button.click(starter(kind), inputs, [SLOTS[KINDS[kind][0]][0]])

        go("ideas", ideas_btn, [theme, *boxes.values()])
        go("write", write_btn, [idea_pick, seconds, theme, *boxes.values()])
        go("design", design_btn, [boxes["name"], voice_desc, language, n_takes])
        go("speak", speak_btn, [boxes["name"], video_dir])
        go("takes", takes_btn, [boxes["name"], video_dir, prompt, negative, seeds, steps])
        go("full", full_btn, [video_dir, prompt, negative, seeds, steps, fin_hook, ambient, *boxes.values()])
        go("lipsync", ls_btn, [video_dir, use_takes, keep, fp16])
        go("finish", fin_btn, [video_dir, fin_hook, ambient, engine])
        go("auto", auto_btn, [script, hook, prompt, negative, seeds, steps, ambient, *boxes.values()])

        # quick steps stay ordinary requests
        save_btn.click(on_save, [start, *boxes.values()], [char_status, saved, prompt, current_voice, voice_desc, language])
        load_btn.click(on_load, [saved], [*boxes.values(), start, prompt, current_voice, voice_desc, language])
        pack_in.upload(on_import, [pack_in], [saved])
        export_btn.click(guarded(P.export_pack), [boxes["name"], full_backup], [pack_out])
        use_btn.click(on_use, [script, hook, prompt, negative, seeds, steps, *boxes.values()],
                      [video_dir, script_status, fin_hook, video_info, *take_videos, use_takes, ls_info])
        lock_btn.click(on_lock, [boxes["name"], take_pick, voice_desc, language], [current_voice])
        use_takes.change(lipsync_info, [video_dir, use_takes], [ls_info])

        # ================================================================ reopening the page
        def restore():
            """Put back the current character, script and results, so a reload or a new browser carries on."""
            data = session()
            char, vd = data.get("character"), data.get("video_dir", "")
            if not char or not (P.HOME / char / "character.json").exists():
                return [gr.update()] * len(restore_out)
            f, start_img = P.load_character(char)
            out = [gr.update(choices=P.list_characters(), value=char), *[f.get(k, "") for k in FIELDS], start_img,
                   P.video_prompt(f), *voice_state(f["name"])]
            v = Path(vd) if vd and Path(vd).exists() else None
            read = lambda name: (v / name).read_text() if v and (v / name).exists() else ""
            path = lambda name: str(v / name) if v and (v / name).exists() else None
            vids, choices = take_updates(saved_takes(vd) if v else [])
            out += [vd if v else "", read("script.txt"), read("hook.txt"), read("hook.txt"),
                    script_info(vd if v else ""), lipsync_info(vd if v else ""), *vids, choices,
                    path("voice.wav"), path("lipsync.mp4"), path("final.mp4"), path("final.mp4")]
            return out

        def resume_offer():
            pending = session().get("pending")
            if not pending or any(j.state == "busy" for j in JOBS.values()):
                return gr.update(visible=False), ""
            return (gr.update(visible=True),
                    f"⏸ **“{pending['title']}” was interrupted** (the app or notebook restarted). "
                    "Resume carries on from where it stopped: finished takes, voice-overs and lip-syncs are reused.")

        def on_resume():
            pending = session().get("pending")
            if not pending:
                return gr.update(visible=False)
            starter(pending["kind"])(*pending["args"])
            return gr.update(visible=False)

        resume_btn.click(on_resume, None, [resume_row])

        def on_stop():
            busy = [j for j in JOBS.values() if j.state == "busy"]
            if not busy:
                raise nope("Nothing is running.")
            if not P.stop_all():
                raise nope(f"“{busy[0].title}” can't be stopped mid-way (it isn't a GPU step); it ends on its own.")
            session(pending=None)
            gr.Info(f"Stopping “{busy[0].title}”. Change what you need, then start it again.")

        stop_btn.click(on_stop, None, None)
        demo.load(resume_offer, None, [resume_row, resume_note])

        restore_out = [saved, *boxes.values(), start, prompt, current_voice, voice_desc, language,
                       video_dir, script, hook, fin_hook, video_info, ls_info, *take_videos, use_takes,
                       voice_out, ls_out, final, final_file]
        demo.load(restore, None, restore_out)
    return demo


def launch(share=True, password=None):
    demo = build()
    auth = ("studio", password) if password else None
    demo.queue(default_concurrency_limit=1).launch(
        share=share, auth=auth, allowed_paths=[str(P.HOME.resolve()), "/tmp"], show_error=True, theme=gr.themes.Soft(), css=CSS,
    )
    return demo


if __name__ == "__main__":
    build().queue(default_concurrency_limit=1).launch(
        allowed_paths=[str(P.HOME.resolve())], show_error=True, theme=gr.themes.Soft(), css=CSS
    )
