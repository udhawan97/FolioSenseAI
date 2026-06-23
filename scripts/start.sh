#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ ! -d venv ]]; then
  echo "No virtual environment found. Run ./scripts/setup.sh first."
  exit 1
fi

source venv/bin/activate
mkdir -p database

echo "Starting FolioSenseAI at http://localhost:8000"
python run.py
