"""Becca's conversational brain.

One Claude call per message. Becca understands plain-English requests, reads
uploaded assignment files (images, PDFs, Word docs), follows their instructions,
asks a question when she needs more, chats normally, and writes finished
documents in Rebecca's simple voice.

respond() returns a dict:
  {
    "reply": "<short WhatsApp message to send back>",
    "make_document": true/false,
    "document": {"title","subtitle","sections":[{"heading","body"}], "embed_photo"}
  }
"""
import os
import json
import base64
from dotenv import load_dotenv
from anthropic import Anthropic

from sheet_specs import FRAMEWORK_SYSTEM

load_dotenv()
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-4-8")
IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp"}

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


def _despace(text):
    """Hard guarantee: no em/en dashes (the instructor flags them as AI)."""
    if not isinstance(text, str):
        return text
    t = text.replace(" — ", ", ").replace(" – ", ", ")
    t = t.replace("—", ", ").replace("–", ", ")
    return t.replace(" ,", ",").replace(",,", ",").replace(", .", ".")


BEHAVIOUR = (
    "\n\n--- YOU ARE BECCA, A WHATSAPP HELPER ---\n"
    "You are Becca, a warm, friendly helper on WhatsApp for an Early Childhood "
    "Education student (Rebecca). You talk in short, simple WhatsApp messages.\n\n"
    "You can do three things:\n"
    "1. CHAT: answer normal questions, explain what you can do, help her think.\n"
    "2. READ FILES: when she sends an assignment file (photo, PDF, or Word doc) and "
    "asks you to do it, READ it carefully, understand exactly what the assignment "
    "asks for, and write the full answer that follows ITS instructions.\n"
    "3. WRITE DOCUMENTS: produce finished assignment text she can hand in.\n\n"
    "RULES:\n"
    "- If you do not have enough information, ask ONE short, simple question instead "
    "of guessing.\n"
    "- Keep chat replies short and kind, like a real person texting.\n"
    "- For documents, write the FULL content, well organised into sections.\n"
    "- Always use the very simple English voice described above. No em dashes. No "
    "fancy words.\n\n"
    "ALWAYS answer with ONE JSON object and nothing else, in this exact shape:\n"
    "{\n"
    '  "reply": "<the short message to send her on WhatsApp>",\n'
    '  "make_document": true or false,\n'
    '  "document": {\n'
    '    "style": "plain or pretty",\n'
    '    "title": "<short title for the document>",\n'
    '    "subtitle": "<short subtitle, or empty string>",\n'
    '    "cover_lines": ["<title-page lines, see below; empty list if none>"],\n'
    '    "student_id": "<the student id number for the footer, or empty>",\n'
    '    "title_emoji": "<one emoji, ONLY when style is pretty>",\n'
    '    "decor": "<a few emojis, ONLY when style is pretty>",\n'
    '    "sections": [\n'
    '      {"emoji": "<one emoji ONLY when pretty>", "heading": "<section heading>", "body": "<the written text; use \\n between paragraphs>"}\n'
    "    ]\n"
    "  }\n"
    "}\n\n"

    "STYLE: default is \"plain\" — a simple white page, plain black text, no banner, "
    "no colours, no emojis. This is what to use for anything she will hand in. Only "
    "use \"pretty\" (colours, banner, emojis) if the user clearly asks to make it "
    "colourful, pink, fancy, decorated, or nice looking. When style is plain, leave "
    "title_emoji, decor, and the section emoji fields as empty strings.\n\n"

    "COVER PAGE: if the user gives title-page information (course number and name, "
    "assignment number and name, student name, student id, instructor, date), put each "
    "piece on its own line in cover_lines, in the order they gave it. You may add an "
    "empty string \"\" to make a blank line between groups. This appears on the FIRST "
    "PAGE only. If they give a student id number, also put just the number in "
    "student_id. If no cover information is given, use an empty list for cover_lines.\n\n"
    "When you are only chatting or asking a question, set \"make_document\": false and "
    "set \"document\": null.\n"
    "When you write a document, set \"make_document\": true, put the FULL written content "
    "in document.sections, and make \"reply\" a short friendly note like: "
    '"Here is your assignment. Please read it and change anything before you hand it in."\n'
    "Never put the document text inside \"reply\". Never add anything outside the JSON."
)

SYSTEM = FRAMEWORK_SYSTEM + BEHAVIOUR


def _parse(text):
    s, e = text.find("{"), text.rfind("}")
    if s == -1 or e == -1:
        return None
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return None


def respond(history, user_text, attachments):
    """history: list of {role, content(str)}. attachments: list of dicts with
    kind in {image, pdf, text}. Returns the decision dict (always)."""
    content = []
    for a in attachments:
        if a["kind"] == "image":
            content.append({"type": "image", "source": {
                "type": "base64", "media_type": a["mtype"],
                "data": base64.standard_b64encode(a["bytes"]).decode("utf-8")}})
        elif a["kind"] == "pdf":
            content.append({"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf",
                "data": base64.standard_b64encode(a["bytes"]).decode("utf-8")}})
        elif a["kind"] == "text":
            content.append({"type": "text", "text":
                f"[The user uploaded a file named '{a['name']}'. Here is the text inside it:]\n"
                + a["text"][:24000]})
    content.append({"type": "text", "text": user_text or "(she sent a file with no message)"})

    messages = list(history) + [{"role": "user", "content": content}]
    resp = _get_client().messages.create(
        model=MODEL, max_tokens=8000, system=SYSTEM, messages=messages)
    raw = next((b.text for b in resp.content if b.type == "text"), "")

    data = _parse(raw)
    if data is None:
        # Not valid JSON: treat the whole thing as a chat reply so she never goes silent.
        return {"reply": _despace(raw.strip())[:1400] or
                "Sorry, I had a little trouble there. Can you say that again?",
                "make_document": False, "document": None}

    data["reply"] = _despace(str(data.get("reply", "")).strip()) or "Done."
    if data.get("make_document") and isinstance(data.get("document"), dict):
        doc = data["document"]
        doc["style"] = "pretty" if str(doc.get("style", "")).strip().lower() == "pretty" else "plain"
        doc["title"] = _despace(str(doc.get("title", "Assignment")).strip()) or "Assignment"
        doc["subtitle"] = _despace(str(doc.get("subtitle", "")).strip())
        doc["title_emoji"] = str(doc.get("title_emoji", "")).strip()
        doc["decor"] = str(doc.get("decor", "")).strip()
        doc["student_id"] = str(doc.get("student_id", "")).strip()
        cover = doc.get("cover_lines") or []
        doc["cover_lines"] = [_despace(str(x)) for x in cover] if isinstance(cover, list) else []
        clean_sections = []
        for s in doc.get("sections", []) or []:
            if not isinstance(s, dict):
                continue
            clean_sections.append({
                "emoji": str(s.get("emoji", "")).strip(),
                "heading": _despace(str(s.get("heading", "")).strip()),
                "body": _despace(str(s.get("body", "")).strip()),
            })
        doc["sections"] = clean_sections
        if not clean_sections:  # nothing to build -> downgrade to a chat reply
            data["make_document"] = False
    else:
        data["make_document"] = False
    return data
