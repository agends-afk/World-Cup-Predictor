#!/bin/zsh
cd "$(dirname "$0")"
clear 2>/dev/null
echo "World Cup 2026 Predictor"
echo ""
echo "Updating predictions with the latest results (10 to 20 seconds)..."
if python3 update.py >/dev/null 2>&1; then
  echo "Up to date."
else
  echo "Update skipped (no internet connection?). Showing last saved predictions."
fi
echo ""
echo "Opening the dashboard in your browser: http://localhost:8642"
echo "Keep this window open while you use it. Close it to stop."
echo ""
python3 serve.py
