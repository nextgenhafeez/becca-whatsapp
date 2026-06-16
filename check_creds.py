"""Quick credential check — prints only OK/FAIL, never the secret values."""
import os
from dotenv import load_dotenv
load_dotenv()

# --- Twilio ---
try:
    from twilio.rest import Client
    sid = os.environ["TWILIO_ACCOUNT_SID"]
    c = Client(sid, os.environ["TWILIO_AUTH_TOKEN"])
    acct = c.api.accounts(sid).fetch()
    print(f"Twilio:  OK  (account: {acct.friendly_name}, status: {acct.status})")
except Exception as e:
    print(f"Twilio:  FAIL  -> {type(e).__name__}: {e}")

# --- Claude / Anthropic ---
try:
    from anthropic import Anthropic
    a = Anthropic()
    a.messages.create(model="claude-haiku-4-5", max_tokens=5,
                      messages=[{"role": "user", "content": "ping"}])
    print("Claude:  OK")
except Exception as e:
    print(f"Claude:  FAIL  -> {type(e).__name__}: {e}")
