"""Video ideas and scripts from the character profile, with a small open LLM on the GPU (no API key)."""

import gc
import json
import re

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen3-4B-Instruct-2507"


class Writer:
    def __init__(self, character, model=MODEL):
        self.character = character
        self.tok = AutoTokenizer.from_pretrained(model)
        self.model = AutoModelForCausalLM.from_pretrained(model, torch_dtype=torch.float16, device_map="cuda:0")

    def _ask(self, prompt, max_new_tokens=900):
        system = (
            "You write short-form vertical video content for this creator. Stay in their voice and inside their "
            "hard limits. Never invent statistics or studies; if a claim is uncertain, say so in the script.\n\n"
            "CREATOR PROFILE:\n" + json.dumps(self.character, indent=2)
        )
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        ids = self.tok.apply_chat_template(msgs, add_generation_prompt=True, return_tensors="pt").to("cuda:0")
        with torch.no_grad():
            out = self.model.generate(ids, max_new_tokens=max_new_tokens, do_sample=True, temperature=0.8, top_p=0.9)
        return self.tok.decode(out[0, ids.shape[1] :], skip_special_tokens=True).strip()

    def ideas(self, n=8, theme=""):
        text = self._ask(
            f"Give {n} video ideas{' about ' + theme if theme else ''}. One per line, numbered, in the form:\n"
            "1. <punchy title> | <one-sentence angle>\nNo other text."
        )
        return [re.sub(r"^\s*\d+[.)]\s*", "", l).strip() for l in text.splitlines() if re.match(r"^\s*\d+[.)]", l)]

    def script(self, idea, seconds=35):
        words = int(seconds * 2.4)
        text = self._ask(
            f"Write the spoken script for this video: {idea}\n\n"
            f"About {words} words ({seconds} seconds). Spoken to camera, like talking to a friend. Short sentences. "
            "Open with a hook in the first sentence, end with a one-line call to follow. Blank line between beats. "
            "Then, on a final line, write: HOOK: <on-screen title, max 7 words>\nNo stage directions, no emojis."
        )
        hook = ""
        m = re.search(r"^\s*HOOK:\s*(.+)$", text, flags=re.M)
        if m:
            hook = m.group(1).strip().strip('"')
            text = text[: m.start()].strip()
        return text, hook

    def close(self):
        del self.model
        gc.collect()
        torch.cuda.empty_cache()
