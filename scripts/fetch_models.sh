#!/usr/bin/env bash
# Fetch the pretrained model files the live path needs into models/ (gitignored).
# YOLO-World weights download themselves on first use; run from models/ so they land there.
set -euo pipefail
cd "$(dirname "$0")/../models" 2>/dev/null || { mkdir -p "$(dirname "$0")/../models"; cd "$(dirname "$0")/../models"; }
[ -f hand_landmarker.task ] || curl -fL -o hand_landmarker.task \
  https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
echo "models ready in $(pwd)"
