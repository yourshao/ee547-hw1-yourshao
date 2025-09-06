#!/bin/bash

if [ $# -lt 1 ]; then
    echo "Usage: $0 <url1> [url2] [url3] ..."
    echo "Example: $0 https://example.com https://wikipedia.org"
    exit 1
fi

echo "Starting Multi-Container Pipeline"
echo "================================="

# Clean previous runs
docker-compose down -v 2>/dev/null

# Create temporary directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

# Create URL list
for url in "$@"; do
    echo "$url" >> "$TEMP_DIR/urls.txt"
done

echo "URLs to process:"
cat "$TEMP_DIR/urls.txt"
echo ""

# Build containers
echo "Building containers..."
docker-compose build --quiet

# Start pipeline
echo "Starting pipeline..."
docker-compose up -d

# Wait for containers to initialize
sleep 3

# Inject URLs
echo "Injecting URLs..."
docker cp "$TEMP_DIR/urls.txt" pipeline-fetcher:/shared/input/urls.txt

# Monitor completion
echo "Processing..."
MAX_WAIT=300  # 5 minutes timeout
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    if docker exec pipeline-analyzer test -f /shared/analysis/final_report.json 2>/dev/null; then
        echo "Pipeline complete"
        break
    fi
    sleep 5
    ELAPSED=$((ELAPSED + 5))
done

if [ $ELAPSED -ge $MAX_WAIT ]; then
    echo "Pipeline timeout after ${MAX_WAIT} seconds"
    docker-compose logs
    docker-compose down
    exit 1
fi

# Extract results
mkdir -p output
docker cp pipeline-analyzer:/shared/analysis/final_report.json output/
docker cp pipeline-analyzer:/shared/status output/
# Cleanup
docker-compose down

# Display summary
if [ -f "output/final_report.json" ]; then
    echo ""
    echo "Results saved to output/final_report.json"
    python3 -m json.tool output/final_report.json | head -20
else
    echo "Pipeline failed - no output generated"
    exit 1
fi