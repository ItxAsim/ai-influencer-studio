"""AI Influencer Studio web UI (Gradio). Each tab is one step; the steps themselves live in pipeline.py.

  python app.py               # local
  launch(share=True, password="...")   # from the notebook: a public link, protected by a password
"""

import json
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


def guarded(gen):
    """Turn exceptions inside a step into a visible error in the UI instead of a silent stop."""
    def run(*args):
        try:
            yield from gen(*args)
        except gr.Error:
            raise
        except Exception as e:  # noqa: BLE001
            raise gr.Error(str(e)) from e
    return run


def build():
    with gr.Blocks(title="AI Influencer Studio") as demo:
        video_dir = gr.State("")
        gr.Markdown("# AI Influencer Studio\nCharacter → idea → script → voice → video → lip-sync → finished vertical video. "
                    "Free GPU, open models, no API keys. New here? Start with the **Guide** tab.")

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
                    export_btn = gr.Button("Export character pack")
                    pack_out = gr.File(label="Character pack")

        # ---------------------------------------------------------------- script
        with gr.Tab("2 · Script"):
            gr.Markdown("Paste your own script, **or** get ideas and let the writer draft one. Blank line between beats. "
                        "Read it before you use it: you're responsible for what the character says.")
            with gr.Row():
                theme = gr.Textbox(label="Theme (optional)", placeholder="e.g. sleep, common myths", scale=3)
                ideas_btn = gr.Button("Suggest ideas", scale=1)
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
            prompt = gr.Textbox(label="Prompt", lines=5)
            negative = gr.Textbox(label="Negative prompt", lines=3, value=P.DEFAULT_NEGATIVE)
            with gr.Row():
                seeds = gr.Textbox(label="Seeds (one take each)", value="42, 7, 1234")
                steps = gr.Slider(20, 50, value=40, step=5, label="Steps (fewer = faster, softer)")
                takes_btn = gr.Button("Make takes", variant="primary")
            takes_log = gr.Textbox(label="Log", lines=8, autoscroll=True)
            with gr.Row():
                take_videos = [gr.Video(label=f"Take {i + 1}", height=360, visible=False) for i in range(MAX_TAKES)]

        # ---------------------------------------------------------------- lip-sync & finish
        with gr.Tab("5 · Lip-sync & finish"):
            use_takes = gr.CheckboxGroup([], label="Takes to use (in this order); skip any where the face warps")
            with gr.Row():
                keep = gr.Number(value=0, minimum=0, maximum=5, step=0.5, label="Keep only the first N seconds of each take (0 = all)")
                fp16 = gr.Checkbox(label="Faster lip-sync (fp16); turn off if the mouth looks noisy")
                ls_btn = gr.Button("Lip-sync", variant="primary")
            ls_log = gr.Textbox(label="Log", lines=8, autoscroll=True)
            ls_out = gr.Video(label="Lip-synced", height=480)
            with gr.Row():
                fin_hook = gr.Textbox(label="Hook title")
                ambient = gr.Slider(0, 0.5, value=0.18, step=0.02, label="Ambient sound")
                engine = gr.Radio(["remotion", "ffmpeg"], value="remotion", label="Finish with")
                fin_btn = gr.Button("Finish", variant="primary")
            fin_log = gr.Textbox(label="Log", lines=6, autoscroll=True)
            final = gr.Video(label="Final video", height=640)
            final_file = gr.File(label="Download")

        # ================================================================ wiring
        def fields_of(*vals):
            f = dict(zip(FIELDS, vals))
            if not f["name"].strip():
                raise gr.Error("Give the character a name first.")
            return f

        def voice_state(name):
            ref, meta = P.saved_voice(name) if name.strip() else (None, None)
            return ref, (meta or {}).get("description", DEFAULT_VOICE), (meta or {}).get("language", "English")

        def on_save(start_img, *vals):
            f = fields_of(*vals)
            d = P.save_character(f, start_img)
            has_start = (d / "start.png").exists()
            msg = f"Saved **{f['name']}**." + ("" if has_start else " ⚠ Upload a start frame before making video.")
            return msg, gr.update(choices=P.list_characters(), value=d.name), P.video_prompt(f), *voice_state(f["name"])

        def on_load(char_slug):
            if not char_slug:
                raise gr.Error("Pick a saved character.")
            f, start_img = P.load_character(char_slug)
            return (*[f.get(k, "") for k in FIELDS], start_img, P.video_prompt(f), *voice_state(f["name"]))

        def on_import(zip_file):
            if not zip_file:
                return gr.update()
            return gr.update(choices=P.list_characters(), value=P.import_pack(zip_file))

        save_btn.click(on_save, [start, *boxes.values()], [char_status, saved, prompt, current_voice, voice_desc, language])
        load_btn.click(on_load, [saved], [*boxes.values(), start, prompt, current_voice, voice_desc, language])
        pack_in.upload(on_import, [pack_in], [saved])
        export_btn.click(lambda name: P.export_pack(name), [boxes["name"]], [pack_out])

        def on_ideas(theme_, *vals):
            found = P.ideas(fields_of(*vals), theme_)
            return gr.update(choices=found, value=found[0] if found else None)

        def on_write(idea, secs, *vals):
            if not idea:
                raise gr.Error("Pick an idea first (or paste your own script).")
            return P.write_script(fields_of(*vals), idea, int(secs))

        def on_use(script_, hook_, *vals):
            f = fields_of(*vals)
            if not script_.strip():
                raise gr.Error("The script is empty.")
            d = P.new_video(f["name"], script_, hook_)
            return d, f"Script saved for **{f['name']}**. Next: the **Voice** tab.", hook_

        ideas_btn.click(on_ideas, [theme, *boxes.values()], [idea_pick])
        write_btn.click(on_write, [idea_pick, seconds, *boxes.values()], [script, hook])
        use_btn.click(on_use, [script, hook, *boxes.values()], [video_dir, script_status, fin_hook])

        @guarded
        def on_design(name, desc, lang, n):
            n = int(n)
            for log, paths in P.design_voice(name, desc, lang, n):
                audios = [gr.update(value=paths[i] if i < len(paths) else None, visible=i < n) for i in range(MAX_TAKES)]
                pick = gr.update(choices=[(f"Take {i + 1}", p) for i, p in enumerate(paths)],
                                 value=paths[0] if paths else None)
                yield log, *audios, pick

        def on_lock(name, take, desc, lang):
            if not take:
                raise gr.Error("Design the voice and pick a take first.")
            return P.lock_voice(name, take, desc, lang)

        @guarded
        def on_speak(name, vd):
            if not vd:
                raise gr.Error("Save a script first (Script tab → Use this script).")
            for log, path in P.speak(name, vd):
                yield log, path

        design_btn.click(on_design, [boxes["name"], voice_desc, language, n_takes], [voice_log, *take_audio, take_pick])
        lock_btn.click(on_lock, [boxes["name"], take_pick, voice_desc, language], [current_voice])
        speak_btn.click(on_speak, [boxes["name"], video_dir], [voice_log, voice_out])

        def parse_seeds(text):
            try:
                s = [int(x) for x in text.replace(",", " ").split()]
            except ValueError:
                raise gr.Error("Seeds must be whole numbers, e.g. 42, 7, 1234.") from None
            if not 1 <= len(s) <= MAX_TAKES:
                raise gr.Error(f"Use 1 to {MAX_TAKES} seeds.")
            return s

        def take_updates(paths):
            vids = [gr.update(value=paths[i] if i < len(paths) else None, visible=i < len(paths)) for i in range(MAX_TAKES)]
            choices = [(Path(p).stem.replace("take_", ""), p) for p in paths]
            return vids, gr.update(choices=choices, value=[p for _, p in choices])

        @guarded
        def on_takes(name, vd, prompt_, negative_, seeds_, steps_):
            if not vd:
                raise gr.Error("Save a script first (Script tab → Use this script).")
            for log, paths in P.make_takes(name, vd, prompt_, negative_, parse_seeds(seeds_), int(steps_)):
                vids, choices = take_updates(paths)
                yield log, *vids, choices

        takes_btn.click(on_takes, [boxes["name"], video_dir, prompt, negative, seeds, steps], [takes_log, *take_videos, use_takes])

        @guarded
        def on_lipsync(vd, takes, keep_, fp16_):
            if not vd:
                raise gr.Error("Save a script first.")
            for log, path in P.lipsync(vd, takes, float(keep_ or 0), fp16_):
                yield log, path

        @guarded
        def on_finish(vd, hook_, amb, eng):
            if not vd or not (Path(vd) / "lipsync.mp4").exists():
                raise gr.Error("Lip-sync first.")
            for log, path in P.finish(vd, hook_, float(amb), eng):
                yield log, path, path

        ls_btn.click(on_lipsync, [video_dir, use_takes, keep, fp16], [ls_log, ls_out])
        fin_btn.click(on_finish, [video_dir, fin_hook, ambient, engine], [fin_log, final, final_file])

        @guarded
        def on_auto(script_, hook_, prompt_, negative_, seeds_, steps_, amb, *vals):
            f = fields_of(*vals)
            if not P.saved_voice(f["name"])[0]:
                raise gr.Error("Autopilot needs a saved voice: design one on the Voice tab first.")
            if not script_.strip():
                raise gr.Error("The script is empty.")
            vd = P.new_video(f["name"], script_, hook_)
            history = []
            for title, gen in (
                ("VOICE", P.speak(f["name"], vd)),
                ("VIDEO", P.make_takes(f["name"], vd, prompt_ or P.video_prompt(f), negative_, parse_seeds(seeds_), int(steps_))),
            ):
                for log, _ in gen:
                    yield "\n".join(history + [f"== {title} ==", log]), None, vd
                history += [f"== {title} ==", log.splitlines()[-1] if log else ""]
            takes = sorted(str(p) for p in (Path(vd) / "takes").glob("take_seed*.mp4"))
            for title, gen in (("LIP-SYNC", P.lipsync(vd, takes, 0)), ("FINISH", P.finish(vd, hook_, float(amb)))):
                for log, path in gen:
                    yield "\n".join(history + [f"== {title} ==", log]), path if title == "FINISH" else None, vd
                history += [f"== {title} ==", log.splitlines()[-1] if log else ""]

        auto_btn.click(on_auto, [script, hook, prompt, negative, seeds, steps, ambient, *boxes.values()],
                       [auto_log, auto_out, video_dir])
    return demo


def launch(share=True, password=None):
    demo = build()
    auth = ("studio", password) if password else None
    demo.queue(default_concurrency_limit=1).launch(
        share=share, auth=auth, allowed_paths=[str(P.HOME.resolve()), "/tmp"], show_error=True, theme=gr.themes.Soft(),
    )
    return demo


if __name__ == "__main__":
    build().queue(default_concurrency_limit=1).launch(
        allowed_paths=[str(P.HOME.resolve())], show_error=True, theme=gr.themes.Soft()
    )
