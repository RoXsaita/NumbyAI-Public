#!/usr/bin/env bash
set -euo pipefail

MODEL="qwen3.5:9b"
OLLAMA_URL="http://localhost:11434"

echo "=== Ollama Setup ==="
echo ""

# 1. Check if ollama binary is on PATH
if ! command -v ollama &>/dev/null; then
    echo "✗ ollama not found on PATH."
    echo "  Install with:  brew install ollama"
    echo "  Then re-run this script."
    exit 1
fi
echo "✓ ollama binary found: $(command -v ollama)"

# 2. Check if ollama serve is running
if curl -sf "$OLLAMA_URL" >/dev/null 2>&1; then
    echo "✓ Ollama server already running at $OLLAMA_URL"
else
    echo "  Starting ollama serve in background..."
    ollama serve &>/dev/null &
    sleep 3
    if curl -sf "$OLLAMA_URL" >/dev/null 2>&1; then
        echo "✓ Ollama server started at $OLLAMA_URL"
    else
        echo "✗ Failed to start Ollama server. Try running 'ollama serve' manually."
        exit 1
    fi
fi

# 3. Check if the model is already pulled
if ollama list 2>/dev/null | grep -q "$MODEL"; then
    echo "✓ Model $MODEL already available"
else
    echo "  Pulling $MODEL (this may take a few minutes on first run)..."
    ollama pull "$MODEL"
    echo "✓ Model $MODEL pulled successfully"
fi

echo ""
echo "=== Ollama ready ==="
echo "  URL:   $OLLAMA_URL"
echo "  Model: $MODEL"
