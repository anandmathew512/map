#!/usr/bin/env bash
set -e

# Install dependencies if needed
if ! python3 -c "import fastapi" 2>/dev/null; then
  echo "Installing dependencies..."
  pip install -r requirements.txt -q
fi

# Check Ollama
if ! curl -sf http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "⚠  Ollama not running. Start it with: ollama serve"
  echo "   Then pull a model:  ollama pull llama3.2"
  echo ""
fi

MODEL="${OLLAMA_MODEL:-llama3.2}"
echo "Using model: $MODEL  (set OLLAMA_MODEL to change)"
echo "Starting Memory at http://localhost:8000"
echo ""

uvicorn main:app --host 0.0.0.0 --port 8000 --reload
