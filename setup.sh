#!/usr/bin/env bash
# One-time Codespace setup: system packages + Python packages (CPU-only torch).
# Runs automatically when the Codespace is created (see .devcontainer/devcontainer.json).
set -euo pipefail

echo "==> Installing system packages (ffmpeg, espeak-ng)..."
sudo apt-get update -qq
sudo apt-get install -y -qq ffmpeg espeak-ng > /dev/null

echo "==> Installing CPU-only PyTorch (skips the ~2 GB CUDA download)..."
pip install --upgrade pip -q
pip install torch --index-url https://download.pytorch.org/whl/cpu -q

echo "==> Installing Python packages..."
pip install -r requirements.txt -q

echo ""
echo "==> Setup done. Next steps:"
echo "    1. Drop copyright-free clips into  clips/"
echo "    2. Write your narration into       script.txt"
echo "    3. Run:  python build_video.py"
