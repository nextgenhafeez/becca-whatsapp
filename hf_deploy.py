"""One-shot deploy of Becca to a free Hugging Face Space (Docker, no card).

Usage:  HF_TOKEN=hf_xxx python hf_deploy.py

Creates/updates the Space, uploads the code + Dockerfile, sets the secrets as
Space env vars, and prints the permanent URL.
"""
import os
import sys
import tempfile
from dotenv import dotenv_values
from huggingface_hub import HfApi

TOKEN = os.environ.get("HF_TOKEN", "").strip()
if not TOKEN:
    print("ERROR: set HF_TOKEN env var first.")
    sys.exit(1)

HERE = os.path.dirname(os.path.abspath(__file__))
env = dotenv_values(os.path.join(HERE, ".env"))
api = HfApi(token=TOKEN)

who = api.whoami()
user = who["name"]
space_id = f"{user}/becca"
print("HF user:", user, "->", space_id)

# 1) create the Space (Docker SDK). Ignore error if it already exists.
api.create_repo(repo_id=space_id, repo_type="space", space_sdk="docker",
                exist_ok=True, private=False)

# 2) HF needs a README.md with frontmatter (sdk: docker, app_port: 7860).
readme = f"""---
title: Becca
emoji: 🍁
colorFrom: pink
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Becca — WhatsApp helper for an ECE student (always-on).
"""
with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as f:
    f.write(readme)
    readme_path = f.name
api.upload_file(path_or_fileobj=readme_path, path_in_repo="README.md",
                repo_id=space_id, repo_type="space")

# 3) upload the code (skip junk + secrets).
api.upload_folder(
    folder_path=HERE, repo_id=space_id, repo_type="space",
    ignore_patterns=["venv/*", ".env", "generated/*", ".git/*", "__pycache__/*",
                     "*.pyc", ".github/*", "*.log", "README.md"],
)

# 4) set the secrets as Space env vars (never in the repo).
secrets = {
    "TWILIO_ACCOUNT_SID": env.get("TWILIO_ACCOUNT_SID", ""),
    "TWILIO_AUTH_TOKEN": env.get("TWILIO_AUTH_TOKEN", ""),
    "ANTHROPIC_API_KEY": env.get("ANTHROPIC_API_KEY", ""),
    "TWILIO_WHATSAPP_FROM": env.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
    "CLAUDE_MODEL": env.get("CLAUDE_MODEL", "claude-opus-4-8"),
    "STUDENT_NAME": env.get("STUDENT_NAME", "Rebecca"),
    "STUDENT_ID": env.get("STUDENT_ID", "000000000"),
}
for k, v in secrets.items():
    api.add_space_secret(repo_id=space_id, key=k, value=v)
print("secrets set:", ", ".join(secrets.keys()))

host = f"{user}-becca.hf.space".lower().replace("_", "-")
print("\n=== DONE ===")
print("Space page :", f"https://huggingface.co/spaces/{space_id}")
print("Live URL   :", f"https://{host}")
print("WEBHOOK FOR TWILIO:", f"https://{host}/whatsapp")
