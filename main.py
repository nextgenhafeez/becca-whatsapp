"""Becca — smart conversational WhatsApp helper for an ECE student.

Every message goes to Becca's brain (Claude). She understands plain English,
reads uploaded files (photos, PDFs, Word docs), follows their instructions,
asks questions, chats, and writes finished documents in Rebecca's simple voice.

Reliability features:
  - logging of every message in/out
  - a daily outbound counter (Twilio free trial = 50/day) + low-quota warning
  - clear replies when Claude fails (credit, rate limit, key)
  - a friendly /status + home dashboard so you always know what's going on
"""
import os
import io
import time
import uuid
import logging
import datetime
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response, FileResponse, JSONResponse, HTMLResponse
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.messaging_response import MessagingResponse
from docx import Document as DocxReader

import becca_brain
from sheet_specs import SUBTITLE
from docx_builder import build_docx

load_dotenv()

# ---------------------------------------------------------------- logging
LOG_PATH = os.environ.get("PLAYDOC_LOG", "/tmp/playdoc-server.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s",
    handlers=[logging.FileHandler(LOG_PATH), logging.StreamHandler()],
)
log = logging.getLogger("becca")

ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
WHATSAPP_FROM = os.environ["TWILIO_WHATSAPP_FROM"]
_space_host = os.environ.get("SPACE_HOST", "")
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL")
                   or os.environ.get("RENDER_EXTERNAL_URL")
                   or (("https://" + _space_host) if _space_host else "")).rstrip("/")

DAILY_LIMIT = int(os.environ.get("TWILIO_DAILY_LIMIT", "50"))

IMAGE_TYPES = becca_brain.IMAGE_TYPES
PDF_TYPE = "application/pdf"
DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
app = FastAPI(title="Becca")

FILES_DIR = os.path.join(os.path.dirname(__file__), "generated")
os.makedirs(FILES_DIR, exist_ok=True)

# Per-user conversation memory (text turns) so Becca remembers the chat.
HISTORY = {}
HISTORY_TS = {}
HISTORY_TTL = 3 * 3600       # forget after 3 hours idle
HISTORY_MAX = 8              # keep last 8 turns (4 exchanges)

STATE = {"date": None, "sent": 0, "last_error": None, "last_error_ts": None,
         "twilio_capped": False}


# ---------------------------------------------------------------- quota helpers
def _today():
    return datetime.date.today().isoformat()


def _roll():
    if STATE["date"] != _today():
        STATE["date"] = _today()
        STATE["sent"] = 0
        STATE["twilio_capped"] = False


def _remaining():
    _roll()
    return max(0, DAILY_LIMIT - STATE["sent"])


def _count_sent(n=1):
    _roll()
    STATE["sent"] += n


def _quota_note():
    left = _remaining()
    if left <= 0:
        return ("\n\n⚠️ The free trial's daily message limit is used up. I may not be "
                "able to reply again until it resets (about 24 hours).")
    if left <= 6:
        return f"\n\n⚠️ Note: only about {left} free messages left today (resets in ~24h)."
    return ""


def _send(to_number, body, media_url=None, with_quota=True):
    """Send a WhatsApp message via Twilio REST. Logs + counts + handles the cap."""
    if with_quota:
        body = (body or "")[:1400] + _quota_note()
    try:
        kwargs = {"from_": WHATSAPP_FROM, "to": to_number, "body": body[:1590]}
        if media_url:
            kwargs["media_url"] = media_url
        msg = twilio_client.messages.create(**kwargs)
        _count_sent(1)
        log.info("SENT to %s sid=%s%s", to_number, msg.sid, " (+file)" if media_url else "")
        return True
    except TwilioRestException as e:
        STATE["last_error"] = f"Twilio send failed ({e.code}): {e.msg}"
        STATE["last_error_ts"] = _today()
        if e.code == 63038:
            STATE["twilio_capped"] = True
            STATE["sent"] = DAILY_LIMIT
            log.error("TWILIO DAILY LIMIT HIT — cannot message %s. Resets at midnight UTC.", to_number)
        else:
            log.error("TWILIO send error to %s: %s", to_number, e)
        return False
    except Exception as e:  # noqa: BLE001
        STATE["last_error"] = f"Send failed: {e}"
        STATE["last_error_ts"] = _today()
        log.exception("Unexpected send error to %s", to_number)
        return False


def _explain_ai_error(e):
    name = type(e).__name__
    text = str(e).lower()
    status = getattr(e, "status_code", None)
    if "credit" in text or "billing" in text or "insufficient" in text:
        return ("⚠️ The AI credit (Claude) has run out, so I can't write right now. Once it's "
                "topped up, send your message again. Nothing you sent was lost.")
    if name == "RateLimitError" or status == 429:
        return "⏳ The AI is busy right now. Please wait about a minute and send it again."
    if name == "AuthenticationError" or status in (401, 403):
        return "⚠️ There's a problem with my AI key. I've logged it. Please try again later."
    if name in ("APIConnectionError", "APITimeoutError"):
        return "🌐 I couldn't reach the AI just now. Please send it again in a minute."
    return None


# ---------------------------------------------------------------- file reading
def _extract_docx(data_bytes):
    try:
        d = DocxReader(io.BytesIO(data_bytes))
        parts = [p.text for p in d.paragraphs if p.text.strip()]
        for t in d.tables:
            for row in t.rows:
                cells = [c.text.strip() for c in row.cells if c.text.strip()]
                if cells:
                    parts.append(" | ".join(cells))
        return "\n".join(parts)
    except Exception:  # noqa: BLE001
        return ""


def _history(from_number):
    if from_number in HISTORY_TS and time.time() - HISTORY_TS[from_number] > HISTORY_TTL:
        HISTORY.pop(from_number, None)
    return HISTORY.get(from_number, [])


def _remember(from_number, user_summary, assistant_summary):
    h = HISTORY.get(from_number, [])
    h.append({"role": "user", "content": user_summary[:4000] or "(file only)"})
    h.append({"role": "assistant", "content": assistant_summary[:4000] or "Done."})
    HISTORY[from_number] = h[-HISTORY_MAX:]
    HISTORY_TS[from_number] = time.time()


# ---------------------------------------------------------------- routes
@app.get("/", response_class=HTMLResponse)
def home():
    _roll()
    left = _remaining()
    if STATE["twilio_capped"]:
        big, color, line = "⚠️ Daily limit reached", "#E8590C", \
            "WhatsApp's free daily message limit is used up. It resets at midnight UTC. " \
            "Becca still receives messages, but can't reply until then."
    elif left <= 6:
        big, color, line = "🟡 Running low", "#F08C00", \
            f"Becca is running, but only about {left} free messages are left today."
    else:
        big, color, line = "✅ Becca is running", "#2B8A3E", \
            "Everything is working. Send a message or a photo on WhatsApp."
    err = STATE["last_error"]
    err_html = (f"<p class='err'><b>Last problem logged:</b><br>{err}<br>"
                f"<small>(on {STATE['last_error_ts']})</small></p>") if err else \
               "<p class='ok'>No problems logged. 🎉</p>"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="15"><title>Becca status</title>
<style>
 body{{font-family:-apple-system,Segoe UI,Roboto,sans-serif;background:#FFF4F9;margin:0;padding:24px;color:#3A2A38}}
 .card{{max-width:520px;margin:24px auto;background:#fff;border-radius:18px;padding:28px;box-shadow:0 8px 30px rgba(214,51,108,.12)}}
 h1{{font-size:26px;margin:.2em 0;color:{color}}}
 .pill{{display:inline-block;background:#FFE3EE;color:#D6336C;border-radius:999px;padding:4px 12px;font-size:13px;font-weight:600}}
 .row{{display:flex;justify-content:space-between;padding:10px 0;border-bottom:1px solid #f3e6ee}}
 .err{{background:#FFF0E6;border-radius:12px;padding:12px;color:#A0410C}}
 .ok{{background:#E6F7EA;border-radius:12px;padding:12px;color:#2B6E3C}}
 small{{color:#9b8a96}}
</style></head><body>
<div class="card">
 <span class="pill">🍁 Becca</span>
 <h1>{big}</h1>
 <p>{line}</p>
 <div class="row"><span>Messages sent today</span><b>{STATE['sent']}</b></div>
 <div class="row"><span>Free messages left today</span><b>{left}</b></div>
 <div class="row"><span>Daily limit hit?</span><b>{"yes" if STATE['twilio_capped'] else "no"}</b></div>
 {err_html}
 <p><small>Auto-refreshes every 15 seconds · {STATE['date']}</small></p>
</div></body></html>"""


@app.get("/status")
def status():
    _roll()
    return JSONResponse({
        "status": "Becca running",
        "date": STATE["date"],
        "messages_sent_today": STATE["sent"],
        "daily_limit": DAILY_LIMIT,
        "messages_left_today": _remaining(),
        "twilio_daily_cap_reached_today": STATE["twilio_capped"],
        "public_base_url": PUBLIC_BASE_URL,
        "last_error": STATE["last_error"],
        "last_error_day": STATE["last_error_ts"],
    })


@app.post("/whatsapp")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks):
    form = await request.form()
    from_number = form.get("From")
    note = (form.get("Body") or "").strip()
    num_media = int(form.get("NumMedia", "0") or "0")
    media_list = [
        (form.get(f"MediaUrl{i}"), (form.get(f"MediaContentType{i}") or "").split(";")[0].lower())
        for i in range(num_media)
    ]
    log.info("IN  from=%s media=%d body=%r left_today=%d",
             from_number, num_media, note[:80], _remaining())

    # Answer Twilio instantly (no message), then think + reply in the background.
    background_tasks.add_task(process_message, from_number, note, media_list)
    return Response(content=str(MessagingResponse()), media_type="application/xml")


def _download(url):
    """Download a Twilio media file, with one retry (handles transient hiccups)."""
    last = None
    for attempt in (1, 2):
        try:
            r = requests.get(url, auth=(ACCOUNT_SID, AUTH_TOKEN), timeout=60)
            r.raise_for_status()
            return r.content
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1)
    log.warning("download failed after retries: %s", last)
    return None


def process_message(from_number, user_text, media_list):
    try:
        attachments = []
        file_notes = []
        problems = []          # files we received but could not read
        photo_bytes = None
        for url, mtype in media_list:
            blob = _download(url)
            if blob is None:
                problems.append("a file that would not download (please resend it)")
                continue
            log.info("attachment type=%s bytes=%d", mtype, len(blob))
            if mtype in IMAGE_TYPES:
                attachments.append({"kind": "image", "bytes": blob, "mtype": mtype})
                if photo_bytes is None:
                    photo_bytes = blob
                file_notes.append("[a photo]")
            elif mtype == PDF_TYPE:
                attachments.append({"kind": "pdf", "bytes": blob})
                file_notes.append("[a PDF file]")
            elif mtype == DOCX_TYPE:
                text = _extract_docx(blob)
                if text.strip():
                    attachments.append({"kind": "text", "name": "Word document", "text": text})
                    file_notes.append("[a Word document]")
                else:
                    log.warning("docx extracted empty (bytes=%d)", len(blob))
                    problems.append("a Word file I could not read the text from "
                                    "(please resend it as a PDF, or paste the text)")
            elif mtype.startswith("text/"):
                attachments.append({"kind": "text", "name": "text file",
                                    "text": blob.decode("utf-8", "ignore")})
                file_notes.append("[a text file]")
            elif mtype.startswith("video/"):
                problems.append("a video (I cannot read videos, please send a photo or PDF)")
            else:
                problems.append(f"a file I cannot open ({mtype})")

        # If something failed, tell Becca so she explains it clearly instead of going vague.
        if problems:
            attachments.append({"kind": "text", "name": "system",
                "text": "IMPORTANT system note for you, Becca: the user sent "
                + ", and ".join(problems) + ". You did NOT receive readable content "
                "from it. Gently tell the user this exact problem and what to do, do "
                "not pretend you read it."})

        history = _history(from_number)
        data = becca_brain.respond(history, user_text, attachments)
        reply = data.get("reply") or "Done."

        made_doc = False
        if data.get("make_document") and data.get("document"):
            doc = data["document"]
            sections = [(f"{s.get('emoji','')} {s['heading']}".strip(), s["body"])
                        for s in doc["sections"]]
            title = f"{doc.get('title_emoji','')} {doc['title']}".strip()
            filename = f"BECCA_{uuid.uuid4().hex[:8]}.docx"
            path = os.path.join(FILES_DIR, filename)
            build_docx(title, doc.get("subtitle") or SUBTITLE, sections, path,
                       doc_type=False, photo_bytes=photo_bytes, decor=doc.get("decor"))
            file_url = f"{PUBLIC_BASE_URL}/files/{filename}"
            log.info("DOC built '%s' for %s -> %s", doc["title"], from_number, filename)
            ok = _send(from_number, reply, media_url=[file_url])
            made_doc = ok
            if not ok:
                log.warning("Built %s but could not deliver to %s", filename, from_number)
        else:
            _send(from_number, reply)

        user_summary = (user_text + " " + " ".join(file_notes)).strip()
        assistant_summary = reply
        if made_doc:
            head = "; ".join(s["heading"] for s in data["document"]["sections"][:6])
            assistant_summary += f"\n[I wrote the document '{data['document']['title']}' with sections: {head}]"
        _remember(from_number, user_summary, assistant_summary)

    except Exception as e:  # noqa: BLE001
        STATE["last_error"] = f"{type(e).__name__}: {e}"
        STATE["last_error_ts"] = _today()
        log.exception("PROCESS FAILED for %s", from_number)
        _send(from_number, _explain_ai_error(e) or
              "⚠️ Sorry, something went wrong on my side. Please try again in a moment.")


@app.get("/files/{filename}")
def serve_file(filename: str):
    safe = os.path.basename(filename)
    path = os.path.join(FILES_DIR, safe)
    if not os.path.isfile(path):
        return Response(status_code=404)
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=safe,
    )
