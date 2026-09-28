#!/usr/bin/env bash
# Start the FeedForward backend so a phone on the same Wi-Fi can reach it.
set -e
cd "$(dirname "$0")"
python3 -m pip install -q -r requirements.txt
echo "Starting FeedForward API on http://0.0.0.0:8000  (docs at /docs)"
echo "On your phone, use Expo Go — the app auto-detects this backend."
exec uvicorn feedforward.api.main:app --host 0.0.0.0 --port 8000
