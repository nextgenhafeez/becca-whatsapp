# PlayDoc — Phase 1 server

**What it does:** Rebecca sends a **photo + a short note** to the Twilio WhatsApp Sandbox →
Claude writes a full **AOR observation sheet** → it comes back on WhatsApp as a formatted **.docx**.

```
WhatsApp (photo+note) → Twilio Sandbox → THIS server → Claude → .docx → reply on WhatsApp
```

---

## Files
- `main.py` — the web server (Twilio webhook + serves the .docx)
- `claude_client.py` — asks Claude to write the AOR fields from the photo+note
- `docx_builder.py` — renders the .docx (Times New Roman 12pt, double-spaced, header)
- `.env.example` — copy to `.env` and fill with your own keys (**never share/commit**)
- `requirements.txt` — Python dependencies

---

## One-time setup
```bash
cd phase1-server
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then open .env and fill in your values
```

Fill `.env` with:
- `TWILIO_ACCOUNT_SID` — from the Twilio dashboard (the `AC…` id; not secret)
- `TWILIO_AUTH_TOKEN` — your **freshly rotated** token (secret — stays in this file)
- `TWILIO_WHATSAPP_FROM` — `whatsapp:+14155238886` (your sandbox number)
- `ANTHROPIC_API_KEY` — Rebecca's Claude key (secret)
- `STUDENT_NAME`, `STUDENT_ID` — for the document header
- `PUBLIC_BASE_URL` — filled in step 3 below

---

## Run it (free, on your laptop)

**1) Start the server**
```bash
source venv/bin/activate
uvicorn main:app --port 8000
```

**2) Open a free public tunnel** (in a second terminal) so WhatsApp can reach you:
```bash
# option A — Cloudflare (no signup):
cloudflared tunnel --url http://localhost:8000
# option B — ngrok:
ngrok http 8000
```
Copy the public URL it prints, e.g. `https://abc-123.trycloudflare.com`.

**3) Tell the server its public address**
- Put that URL in `.env` as `PUBLIC_BASE_URL=…`
- **Restart** the server (Ctrl-C, then `uvicorn` again).

**4) Point Twilio at the server**
- Twilio Console → **Messaging → Try it out → Send a WhatsApp message → Sandbox settings**
- **“When a message comes in”** → `https://<your-tunnel>/whatsapp` , Method **POST** → **Save**.

**5) Join the sandbox from Rebecca's phone**
- From Rebecca's WhatsApp, send **`join foot-felt`** to **+1 415 523 8886**.

**6) Test it**
- From that same WhatsApp, send a **photo** of children playing + a short note.
- In ~a minute you get back a formatted **AOR .docx**. 🎉

---

## Notes
- Trial Twilio can only message numbers that have **joined the sandbox** — that's fine for testing.
- Set `CLAUDE_MODEL=claude-haiku-4-5` in `.env` for cheap test runs; switch to `claude-opus-4-8` for best quality.
- The tunnel URL changes each time you restart cloudflared/ngrok — update `PUBLIC_BASE_URL` and the Twilio webhook if it does.
- **Secrets live only in `.env` on your machine.** Don't commit it or paste its contents anywhere.
