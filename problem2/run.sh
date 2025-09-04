#!/bin/bash

# Check arguments
if [ $# -ne 3 ]; then
    echo "Usage: $0 <query> <max_results> <output_directory>"
    echo "Example: $0 'cat:cs.LG' 10 output/"
    exit 1
fi

QUERY="$1"
MAX_RESULTS="$2"
OUTPUT_DIR="$3"

# Validate max_results is a number
if ! [[ "$MAX_RESULTS" =~ ^[0-9]+$ ]]; then
    echo "Error: max_results must be a positive integer"
    exit 1
fi

# Check max_results is in valid range
if [ "$MAX_RESULTS" -lt 1 ] || [ "$MAX_RESULTS" -gt 100 ]; then
    echo "Error: max_results must be between 1 and 100"
    exit 1
fi

# Create output directory if it doesn't exist
mkdir -p "$OUTPUT_DIR"

# Run container
docker run --rm \
    --name arxiv-processor \
    -v "$(realpath $OUTPUT_DIR)":/data/output \
    arxiv-processor:latest \
    "$QUERY" "$MAX_RESULTS" "/data/output"