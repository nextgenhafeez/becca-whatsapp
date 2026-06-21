"""One-shot Render deploy for Becca.

Usage:  RENDER_API_KEY=rnd_xxx python render_deploy.py

It reads the 3 secrets from .env, creates a free always-on web service from the
public GitHub repo, sets all env vars, and prints the permanent URL.
"""
import os
import sys
import json
import time
import urllib.request
import urllib.error
from dotenv import dotenv_values

API = "https://api.render.com/v1"
REPO = "https://github.com/nextgenhafeez/becca-whatsapp"
KEY = os.environ.get("RENDER_API_KEY", "").strip()

if not KEY:
    print("ERROR: set RENDER_API_KEY env var first.")
    sys.exit(1)

env = dotenv_values(os.path.join(os.path.dirname(__file__), ".env"))


def call(method, path, body=None):
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", "Bearer " + KEY)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode() or "null")


def main():
    # 1) owner id
    st, owners = call("GET", "/owners?limit=20")
    if st != 200 or not owners:
        print("Could not read owners:", st, owners)
        sys.exit(1)
    owner_id = owners[0]["owner"]["id"]
    print("owner:", owners[0]["owner"].get("name"), owner_id)

    # 2) env vars (the 3 secrets + the non-secret settings)
    env_vars = [
        {"key": "TWILIO_ACCOUNT_SID", "value": env.get("TWILIO_ACCOUNT_SID", "")},
        {"key": "TWILIO_AUTH_TOKEN", "value": env.get("TWILIO_AUTH_TOKEN", "")},
        {"key": "ANTHROPIC_API_KEY", "value": env.get("ANTHROPIC_API_KEY", "")},
        {"key": "TWILIO_WHATSAPP_FROM", "value": env.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")},
        {"key": "CLAUDE_MODEL", "value": env.get("CLAUDE_MODEL", "claude-opus-4-8")},
        {"key": "STUDENT_NAME", "value": env.get("STUDENT_NAME", "Rebecca")},
        {"key": "STUDENT_ID", "value": env.get("STUDENT_ID", "000000000")},
    ]

    # 3) create the free web service
    body = {
        "type": "web_service",
        "name": "becca",
        "ownerId": owner_id,
        "repo": REPO,
        "branch": "main",
        "autoDeploy": "yes",
        "serviceDetails": {
            "env": "python",
            "plan": "free",
            "region": "oregon",
            "envSpecificDetails": {
                "buildCommand": "pip install -r requirements.txt",
                "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT",
            },
        },
        "envVars": env_vars,
    }
    st, resp = call("POST", "/services", body)
    print("create service:", st)
    if st not in (200, 201):
        print(json.dumps(resp, indent=2)[:1500])
        sys.exit(1)
    svc = resp.get("service", resp)
    sid = svc.get("id")
    url = svc.get("serviceDetails", {}).get("url") or "(building...)"
    print("service id:", sid)
    print("URL:", url)
    print("\nDeploy started. It builds for ~3-5 min. Watch at https://dashboard.render.com")
    print("WEBHOOK TO PASTE IN TWILIO (once live):", (url or "") + "/whatsapp")


if __name__ == "__main__":
    main()
