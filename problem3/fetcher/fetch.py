#!/usr/bin/env python3
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone


def main():
    print(f"[{datetime.now(timezone.utc).isoformat()}] Fetcher starting", flush=True)

    os.makedirs("/shared/input", exist_ok=True)
    # Wait for input file
    input_file = "/shared/input/urls.txt"
    while not os.path.exists(input_file):
        print(f"Waiting for {input_file}...", flush=True)
        time.sleep(2)

    # Read URLs
    with open(input_file, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]

    # Create output directory
    os.makedirs("/shared/raw", exist_ok=True)
    os.makedirs("/shared/status", exist_ok=True)

    # Fetch each URL
    results = []
    for i, url in enumerate(urls, 1):
        output_file = f"/shared/raw/page_{i}.html"
        try:
            print(f"Fetching {url}...", flush=True)
            with urllib.request.urlopen(url, timeout=10) as response:
                content = response.read()
                with open(output_file, 'wb') as f:
                    f.write(content)
            results.append({
                "url": url,
                "file": f"page_{i}.html",
                "size": len(content),
                "status": "success"
            })
        except Exception as e:
            results.append({
                "url": url,
                "file": None,
                "error": str(e),
                "status": "failed"
            })
        time.sleep(1)  # Rate limiting

    # Write completion status
    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "urls_processed": len(urls),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "results": results
    }

    with open("/shared/status/fetch_complete.json", 'w') as f:
        json.dump(status, f, indent=2)

    print(f"[{datetime.now(timezone.utc).isoformat()}] Fetcher complete", flush=True)


if __name__ == "__main__":
    main()
