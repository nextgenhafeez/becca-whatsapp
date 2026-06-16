"""Calls Claude to fill any PlayDoc sheet (fields) or write an essay (prose).
Accepts multiple attachments: images (jpeg/png/gif/webp) and PDFs."""
import os
import json
import base64
from dotenv import load_dotenv
from anthropic import Anthropic

load_dotenv()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")

IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def _despace(text: str) -> str:
    """Hard guarantee: remove em/en dashes the instructor flags as AI.
    ' — ' becomes ', '; a bare dash becomes a comma or sentence break."""
    if not isinstance(text, str):
        return text
    t = text.replace(" — ", ", ").replace(" – ", ", ")
    t = t.replace("—", ", ").replace("–", ", ")
    t = t.replace(" ,", ",").replace(",,", ",").replace(", .", ".")
    return t


def _clean(data):
    """Apply the dash guard to every string in the result (essay or fields)."""
    if isinstance(data, dict):
        return {k: (_despace(v) if isinstance(v, str) else v) for k, v in data.items()}
    return data


def _media_block(data_bytes: bytes, media_type: str):
    """Return a Claude content block for an image or PDF, or None if unsupported."""
    mtype = (media_type or "").split(";")[0].lower()
    b64 = base64.standard_b64encode(data_bytes).decode("utf-8")
    if mtype in IMAGE_TYPES:
        return {"type": "image", "source": {"type": "base64", "media_type": mtype, "data": b64}}
    if mtype == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": b64}}
    return None  # video/audio/etc not supported


def generate(spec: dict, note: str = "", media_items=None) -> dict:
    """media_items: list of (bytes, media_type). Returns sheet data."""
    media_items = media_items or []
    content = []
    has_visual = False
    for data_bytes, mtype in media_items:
        block = _media_block(data_bytes, mtype)
        if block:
            content.append(block)
            has_visual = True

    if spec["mode"] == "prose":
        instruction = (
            f"{spec['question']}\n\n"
            + (f"Educator's own notes/context to weave in: {note}\n\n" if note else "")
            + ("Use the attached file(s) as supporting context.\n\n" if has_visual else "")
            + "Write a first-person reflection of about 3 to 5 short paragraphs. Use VERY "
            "simple English and short sentences, the way Rebecca writes. You may mention "
            "the FLIGHT framework and ideas like learning through play, anti-bias practice, "
            "or how children build their own understanding, but say them in plain everyday "
            "words, NOT in textbook language. Remember: no em dashes at all, and no fancy "
            "vocabulary. Return ONLY the reflection text, no headings, no preamble."
        )
        content.append({"type": "text", "text": instruction})
        resp = _get_client().messages.create(
            model=MODEL, max_tokens=4000, system=spec["system"],
            messages=[{"role": "user", "content": content}],
        )
        text = next(b.text for b in resp.content if b.type == "text")
        return {"essay": _despace(text.strip())}

    keys_block = "\n".join(f'  "{key}": "<{label}>"' for key, label in spec["fields"])
    sparse = (not note) and (not has_visual)
    instruction = (
        (f"Educator's note about this: {note}\n\n" if note else "")
        + f"Fill in a {spec['title']} sheet"
        + (" based on the attached file(s) and the note.\n\n" if has_visual else " based on the note.\n\n")
        + ("Few details were given — invent a realistic, age-appropriate example (for children "
           "about 3-6 years old) that a Canadian ECE student might genuinely use, so the educator "
           "has a strong draft to edit.\n\n" if sparse else "")
        + "Respond with ONLY a single valid JSON object — no markdown code fences, no questions, no "
        "commentary before or after — with EXACTLY these keys and a string value for each (about "
        "2-5 sentences each, unless the key asks for something specific):\n{\n" + keys_block + "\n}"
    )
    content.append({"type": "text", "text": instruction})

    data = _call_for_json(spec, content)
    if data is None:  # one firm retry
        content.append({"type": "text", "text": "Return ONLY the JSON object described above — nothing else."})
        data = _call_for_json(spec, content)
    if data is None:
        raise ValueError("I couldn't draft that sheet. Please resend with a short note (for example: what the children did, the week, and the big idea).")
    return _clean(data)


def _call_for_json(spec, content):
    resp = _get_client().messages.create(
        model=MODEL, max_tokens=4000, system=spec["system"],
        messages=[{"role": "user", "content": content}],
    )
    text = next((b.text for b in resp.content if b.type == "text"), "")
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None
