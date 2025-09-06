#!/bin/bash

echo "Test 1: Single URL"
./run_pipeline.sh https://www.example.com

echo ""
echo "Test 2: Multiple URLs from file"
./run_pipeline.sh $(cat test_urls.txt)

echo ""
echo "Test 3: Verify output structure"
python3 -c "
import json
with open('output/final_report.json') as f:
    data = json.load(f)
    assert 'documents_processed' in data
    assert 'top_100_words' in data
    assert 'document_similarity' in data
    print('Output validation passed')
"