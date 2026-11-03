"""Script -> sentences (with pauses) for the voice, and sentence timings -> short subtitle lines."""

import re

PAUSE_SENTENCE = 0.35  # seconds of silence between sentences
PAUSE_PARAGRAPH = 0.7  # between paragraphs (blank line in the script)
LEAD_IN = 0.4  # silence before the first word
MAX_WORDS = 5  # words per subtitle line


def split_script(text):
    """-> list of (sentence, pause_after) in reading order."""
    out = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    for pi, para in enumerate(paragraphs):
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", " ".join(para.split())) if s.strip()]
        for si, s in enumerate(sentences):
            last_in_para = si == len(sentences) - 1
            last_overall = last_in_para and pi == len(paragraphs) - 1
            out.append((s, 0.0 if last_overall else PAUSE_PARAGRAPH if last_in_para else PAUSE_SENTENCE))
    return out


def _chunk(words):
    n = -(-len(words) // MAX_WORDS)
    size = -(-len(words) // n)
    return [" ".join(words[i : i + size]) for i in range(0, len(words), size)]


def subtitle_lines(sentences):
    """[{text, from, to}] per sentence -> shorter lines, split at commas first, timed by share of characters."""
    lines = []
    for s in sentences:
        pieces = [p for clause in re.split(r"(?<=,) ", s["text"]) for p in _chunk(clause.split(" "))]
        total = sum(len(p) for p in pieces)
        t = s["from"]
        for p in pieces:
            d = (s["to"] - s["from"]) * len(p) / total
            lines.append({"text": p, "from": round(t, 2), "to": round(t + d, 2)})
            t += d
    return lines
