#!/bin/bash

# Dev Publish Script - Run locally to test and publish
set -e

echo "=== BI Dashboard Dev Publish ==="

# Activate virtual environment
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# Install/update dependencies
echo "Installing dependencies..."
pip install -r requirements.txt -q

# Generate sample data if needed
if [ ! -f "data-archive/sample_optical_sales.csv" ]; then
    echo "Generating sample data..."
    python generate_sample_data.py
fi

# Kill existing app
pkill -f "python main.py" 2>/dev/null || true
sleep 1

# Run app in background
echo "Starting app..."
python main.py &
APP_PID=$!

# Wait for startup
echo "Waiting for app to start..."
sleep 10

# Test startup
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:7860)
if [ "$HTTP_CODE" = "200" ]; then
    echo "✓ App started successfully on port 7860"
else
    echo "✗ App startup failed (HTTP $HTTP_CODE)"
    kill $APP_PID 2>/dev/null || true
    exit 1
fi

# Run quick ingestion test
echo "Testing data ingestion..."
python -c "
import db_manager
result = db_manager.ingest_new_files()
print(f'Ingestion: {result}')
"

# Cleanup
kill $APP_PID 2>/dev/null || true

echo "=== Dev Publish Complete ==="
echo "App running at http://127.0.0.1:7860"
