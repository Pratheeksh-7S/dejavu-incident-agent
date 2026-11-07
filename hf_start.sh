#!/bin/bash
# Start order: memory server -> wait until healthy -> load history in background -> web app.
export HINDSIGHT_API_LLM_API_KEY="${HINDSIGHT_API_LLM_API_KEY:-$GROQ_API_KEY}"

hindsight-api > memory_server.log 2>&1 &
echo "Starting Hindsight memory server..."
until curl -sf http://localhost:8888/health > /dev/null; do sleep 3; done
echo "Memory server is up."

# A fresh container has an empty memory, so teach it the history (about 15 min on Groq free tier).
python load_memory.py > load_memory.log 2>&1 &

exec streamlit run app.py --server.port 7860 --server.address 0.0.0.0 \
  --server.headless true --server.enableCORS false --server.enableXsrfProtection false \
  --theme.base dark --theme.primaryColor "#D4A853" --theme.backgroundColor "#09090B" \
  --theme.secondaryBackgroundColor "#11131C" --theme.textColor "#D9DCE6"
