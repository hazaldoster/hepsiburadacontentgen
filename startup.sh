#!/bin/bash
set -e

echo "Installing any missing dependencies..."
pip install --no-cache-dir -r requirements.txt || echo "Some dependencies may be missing but we'll try to run anyway"

echo "Starting application..."
python app.py 