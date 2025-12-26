#!/bin/bash
# Simple helper to run the streamer
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
    echo "Creating venv..."
    python3 -m venv venv
    ./venv/bin/pip install -r requirements.txt
fi

echo "Starting Tijdvorm Streamer on port 8008..."
./venv/bin/uvicorn main:app --host 0.0.0.0 --port 8008

