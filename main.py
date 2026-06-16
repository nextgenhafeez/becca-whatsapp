"""PlayDoc / Becca — WhatsApp server.

When a user sends files, Becca CONFIRMS what to make before building.
This version also has:
  - real logging (file + console) of every message in and out
  - a daily outbound counter (Twilio free trial = 50 messages/day) with a
    pre-emptive low-quota warning, so Rebecca is told BEFORE it goes silent
  - clear auto-replies when the Claude/AI step fails (credit, rate limit, key)
  - a /status page so we can see health, today's count, and the last error
"""
import os
import time
import uuid
import logging
import datetime
import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import Response, FileResponse, JSONResponse
from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException
from twilio.twiml.messaging_response import MessagingResponse

from sheet_specs import SHEETS, SUBTITLE, HELP_TEXT, route, sections_for
from claude_client import generate, IMAGE_TYPES
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
# On Render this is auto-set (RENDER_EXTERNAL_URL); locally we use the tunnel URL.
PUBLIC_BASE_URL = (os.environ.get("PUBLIC_BASE_URL")
                   or os.environ.get("RENDER_EXTERNAL_URL", "")).rstrip("/")

# Twilio free trial allows 50 outbound WhatsApp messages per day (sandbox).
DAILY_LIMIT = int(os.environ.get("TWILIO_DAILY_LIMIT", "50"))

READABLE = IMAGE_TYPES | {"application/pdf"}

twilio_client = Client(ACCOUNT_SID, AUTH_TOKEN)
app = FastAPI(title="Becca")

FILES_DIR = os.path.join(os.path.dirname(__file__), "generated")
os.makedirs(FILES_DIR, exist_ok=True)

# Simple in-memory "what should I do with these files?" state, per phone number.
PENDING = {}
PENDING_TTL = 1800  # 30 minutes

# Daily outbound counter + last error, for quota warnings and the /status page.
STATE = {"date": None, "sent": 0, "last_error": None, "last_error_ts": None}

CONFIRM_TEXT = (
    "📎 I got your file(s)! Before I build anything, what should I make?\n\n"
    "Reply with one word:\n"
    "• *aor* — observation sheet (uses a photo)\n"
    "• *plan* — planning sheet\n"
    "• *ppp* — provocation + observation\n"
    "• *board* — documentation board\n"
    "• *essay1* / *essay2* / *essay3*\n\n"
    "📸 Sent several photos and want a *separate* observation for each? Reply *each*.\n"
    "ℹ️ Each file is treated individually, one file makes one sheet."
)


# ---------------------------------------------------------------- quota helpers
def _today():
    return datetime.date.today().isoformat()


def _roll():
    """Reset the counter when the day changes."""
    if STATE["date"] != _today():
        STATE["date"] = _today()
        STATE["sent"] = 0


def _remaining():
    _roll()
    return max(0, DAILY_LIMIT - STATE["sent"])


def _count_sent(n=1):
    _roll()
    STATE["sent"] += n


def _quota_note():
    """A short warning to append when the free-trial quota is running low."""
    left = _remaining()
    if left <= 0:
        return ("\n\n⚠️ *Heads up:* the free trial's daily message limit is used up. "
                "I may not be able to reply again until it resets (about 24 hours). "
                "Your finished files are still saved.")
    if left <= 6:
        return (f"\n\n⚠️ *Note:* only about {left} free messages left today "
                "(free trial limit). It resets in about 24 hours.")
    return ""


def _reply(reply, text, with_quota=True):
    """Add a TwiML message (this counts against Twilio's daily cap)."""
    if with_quota:
        text = text + _quota_note()
    reply.message(text)
    _count_sent(1)
    return reply


def _send(to_number, body, media_url=None):
    """Send via Twilio REST (the finished file or an error). Logs + counts.
    If Twilio refuses (e.g. daily cap), we log it; we cannot reach her then."""
    try:
        kwargs = {"from_": WHATSAPP_FROM, "to": to_number, "body": body}
        if media_url:
            kwargs["media_url"] = media_url
        msg = twilio_client.messages.create(**kwargs)
        _count_sent(1)
        log.info("SENT to %s sid=%s%s", to_number, msg.sid, " (+file)" if media_url else "")
        return True
    except TwilioRestException as e:
        STATE["last_error"] = f"Twilio send failed ({e.code}): {e.msg}"
        STATE["last_error_ts"] = _today()
        # 63038 = daily message limit exceeded on the trial account.
        if e.code == 63038:
            log.error("TWILIO DAILY LIMIT HIT — cannot message %s. Resets in ~24h.", to_number)
        else:
            log.error("TWILIO send error to %s: %s", to_number, e)
        return False
    except Exception as e:  # noqa: BLE001
        STATE["last_error"] = f"Send failed: {e}"
        STATE["last_error_ts"] = _today()
        log.exception("Unexpected send error to %s", to_number)
        return False


def _xml(reply):
    return Response(content=str(reply), media_type="application/xml")


def _explain_ai_error(e):
    """Turn a Claude/AI exception into a clear WhatsApp message for Rebecca."""
    name = type(e).__name__
    text = str(e).lower()
    status = getattr(e, "status_code", None)
    if "credit" in text or "billing" in text or "insufficient" in text:
        return ("⚠️ The AI credit (Anthropic/Claude) has run out, so I can't write right now. "
                "Once the Claude account is topped up, send your photo + note again. "
                "Nothing you sent was lost.")
    if name == "RateLimitError" or status == 429:
        return ("⏳ The AI is busy at the moment (rate limit). Please wait about a minute "
                "and send it again.")
    if name == "AuthenticationError" or status in (401, 403):
        return ("⚠️ There's a problem with the AI key on my side. I've logged it. "
                "Please try again a bit later.")
    if name in ("APIConnectionError", "APITimeoutError"):
        return ("🌐 I couldn't reach the AI just now (connection issue). Please send it again "
                "in a minute.")
    return None  # fall back to the generic message


# ---------------------------------------------------------------- routes
@app.get("/")
def health():
    return {"status": "Becca running"}


@app.get("/status")
def status():
    """Quick health/quota view for us (not for Rebecca)."""
    _roll()
    return JSONResponse({
        "status": "Becca running",
        "date": STATE["date"],
        "messages_sent_today": STATE["sent"],
        "daily_limit": DAILY_LIMIT,
        "messages_left_today": _remaining(),
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
    has_readable = any(m in READABLE for _, m in media_list)
    has_video = any(m.startswith("video/") for _, m in media_list)

    log.info("IN  from=%s media=%d body=%r left_today=%d",
             from_number, num_media, note[:80], _remaining())

    sheet_key, context = route(note)
    reply = MessagingResponse()

    if sheet_key == "help":
        return _xml(_reply(reply, HELP_TEXT))

    # --- Files attached ---
    if has_readable:
        if sheet_key:  # explicit command WITH the files -> go ahead
            PENDING.pop(from_number, None)
            return _start(reply, from_number, sheet_key, context, media_list, background_tasks)
        # files but no command -> CONFIRM first
        PENDING[from_number] = {"media": media_list, "note": note, "ts": time.time()}
        return _xml(_reply(reply, CONFIRM_TEXT))

    if has_video:
        return _xml(_reply(reply, "🎬 I can read *photos* and *PDFs*, but not video files yet. "
                                  "Please send a photo + a note."))

    # --- No files. Is this an answer to a pending 'what should I make?' ---
    pend = PENDING.get(from_number)
    if pend and (time.time() - pend["ts"] < PENDING_TTL):
        low = note.lower().strip()
        if low.split()[0:1] == ["each"]:
            PENDING.pop(from_number, None)
            return _start_each(reply, from_number, pend["media"], background_tasks)
        if sheet_key:  # they chose a sheet type -> use the stored files
            PENDING.pop(from_number, None)
            ctx = context or pend.get("note", "")
            return _start(reply, from_number, sheet_key, ctx, pend["media"], background_tasks)
        return _xml(_reply(reply, "Please reply with one of: *aor*, *plan*, *ppp*, *board*, "
                                  "*essay1/2/3*, or *each*."))

    # --- No files, no pending: normal routing ---
    if sheet_key is None:
        return _xml(_reply(reply, HELP_TEXT))
    return _start(reply, from_number, sheet_key, context, [], background_tasks)


def _start(reply, to, sheet_key, context, media_list, bg):
    spec = SHEETS[sheet_key]
    if spec["needs_photo"] and not any(m in READABLE for _, m in media_list):
        return _xml(_reply(reply, f"📸 The *{spec['title']}* needs a photo. "
                                  "Please send a photo with your note."))
    _reply(reply, f"✨ Got it! Writing your *{spec['title']}*… about a minute. 📝")
    bg.add_task(process, to, sheet_key, context, media_list)
    return _xml(reply)


def _start_each(reply, to, media_list, bg):
    photos = [(u, m) for u, m in media_list if m in IMAGE_TYPES]
    if not photos:
        return _xml(_reply(reply, "I didn't find any photos to make separate observations from. "
                                  "Send photos and reply *each*."))
    _reply(reply, f"✨ Making {len(photos)} observation sheet(s), one per photo… 📝")
    for u, m in photos:
        bg.add_task(process, to, "aor", "", [(u, m)])
    return _xml(reply)


def process(to_number: str, sheet_key: str, context: str, media_list):
    spec = SHEETS[sheet_key]
    try:
        media_items = []
        for url, mtype in media_list:
            if mtype in READABLE:
                r = requests.get(url, auth=(ACCOUNT_SID, AUTH_TOKEN), timeout=45)
                r.raise_for_status()
                media_items.append((r.content, mtype))

        log.info("BUILD %s for %s (%d file(s))", sheet_key, to_number, len(media_items))
        data = generate(spec, context, media_items)
        photo_bytes = next((b for b, t in media_items if t in IMAGE_TYPES), None)

        filename = f"{sheet_key.upper()}_{uuid.uuid4().hex[:8]}.docx"
        build_docx(spec["title"], SUBTITLE, sections_for(spec, data),
                   os.path.join(FILES_DIR, filename), doc_type=spec.get("needs_photo", False),
                   photo_bytes=photo_bytes)

        file_url = f"{PUBLIC_BASE_URL}/files/{filename}"
        ok = _send(to_number,
                   f"✅ Here's your *{spec['title']}*. Review and edit before submitting. 💕",
                   media_url=[file_url])
        if not ok:
            log.warning("Built %s but could NOT deliver to %s (saved at %s)",
                        filename, to_number, file_url)
    except Exception as e:  # noqa: BLE001
        STATE["last_error"] = f"{type(e).__name__}: {e}"
        STATE["last_error_ts"] = _today()
        log.exception("BUILD FAILED (%s) for %s", sheet_key, to_number)
        msg = _explain_ai_error(e) or (
            f"⚠️ Sorry, something went wrong while writing the {spec['title']}. "
            "Please try again, or send a short note describing the play.")
        _send(to_number, msg)


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
