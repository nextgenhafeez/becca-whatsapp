#!/usr/bin/env bash
# PlayDoc Phase 1 launcher: starts the tunnel, wires the URL into .env, runs the server.
cd "$(dirname "$0")" || exit 1
source venv/bin/activate

# 1) Make sure the real secrets were added
if grep -q "PASTE_YOUR" .env; then
  echo "⚠️  Your .env still has placeholder secrets."
  echo "    Open it and paste your Twilio Auth Token + Claude key first:"
  echo "    open -e \"$(pwd)/.env\""
  exit 1
fi

# 2) Start the Cloudflare tunnel and capture its public URL
echo "🌐 Starting tunnel..."
# --protocol http2 is more reliable than the default QUIC, which can silently die.
cloudflared tunnel --url http://localhost:8000 --protocol http2 > /tmp/playdoc-cf.log 2>&1 &
CF_PID=$!
URL=""
for i in $(seq 1 30); do
  URL=$(grep -oE "https://[a-zA-Z0-9.-]+\.trycloudflare\.com" /tmp/playdoc-cf.log 2>/dev/null | head -1)
  [ -n "$URL" ] && break
  sleep 1
done
if [ -z "$URL" ]; then
  echo "❌ Couldn't get a tunnel URL. See /tmp/playdoc-cf.log"
  kill "$CF_PID" 2>/dev/null
  exit 1
fi

# 3) Write the public URL into .env
if grep -q "^PUBLIC_BASE_URL=" .env; then
  sed -i '' "s|^PUBLIC_BASE_URL=.*|PUBLIC_BASE_URL=$URL|" .env
else
  echo "PUBLIC_BASE_URL=$URL" >> .env
fi

echo ""
echo "=================================================================="
echo " ✅ Tunnel live."
echo ""
echo " 1) Twilio → Messaging → Try it out → Sandbox settings"
echo "    \"When a message comes in\":   $URL/whatsapp     (Method: POST)  → Save"
echo ""
echo " 2) From Rebecca's WhatsApp, send:   join foot-felt"
echo "    to:   +1 415 523 8886"
echo ""
echo " 3) Then send a PHOTO + a short note. Your sheet comes back in ~1 min."
echo "=================================================================="
echo ""
echo "🚀 Starting server (press Ctrl-C to stop everything)..."
trap "kill $CF_PID 2>/dev/null" EXIT
uvicorn main:app --port 8000
