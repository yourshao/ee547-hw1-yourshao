#!/usr/bin/env python3
import sys
import json
import os
import re
import time
from datetime import datetime, timezone
from urllib import request, error


def iso_utc_now() -> str:
    # ISO-8601 UTC, e.g. "2025-09-03T05:12:34.567890Z"
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


_WORD_RE = re.compile(r"[A-Za-z]+")


def count_words(text: str) -> int:
    # A word = any sequence of alphanumeric characters
    return len(_WORD_RE.findall(text)) or None


def fetch_once(url: str, timeout: float = 10.0) -> dict:
    rec = {
        "url": url,
        "status_code": None,
        "response_time_ms": None,
        "content_length": None,
        "word_count": None,
        "timestamp": iso_utc_now(),
        "error": None,
    }

    req = request.Request(url, headers={"User-Agent": "EE547-HTTP-Fetcher/1.0"})
    t0 = time.perf_counter()
    try:
        with request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            t1 = time.perf_counter()

            code = resp.getcode()
            rec["status_code"] = int(code)
            rec["response_time_ms"] = (t1 - t0) * 1000
            rec['content_length'] = len(body)

            ctype = (resp.headers.get('Content-Type')).lower()
            if "text" in ctype:
                rec["word_count"] = count_words(body.decode('utf-8'))

    except error.HTTPError as e:
        t1 = time.perf_counter()
        rec["status_code"] = int(e.code)
        rec["response_time_ms"] = (t1 - t0) * 1000

        try:
            body = e.read() or b""
        except Exception:
            body = b""

        rec["content_length"] = len(body)

        ctype = (e.headers.get('Content-Type') or "" ).lower()
        if "text" in ctype:
            rec["word_count"] = count_words(body.decode('utf-8'))

        rec["error"] = str(e)

    except error.URLError as e:
        t1 = time.perf_counter()
        rec["response_time_ms"] = (t1 - t0) * 1000.0
        rec["error"] = str(getattr(e, "reason", e))  # e.g. "<urlopen error timed out>"

    except Exception as e:
        t1 = time.perf_counter()
        rec["response_time_ms"] = (t1 - t0) * 1000.0
        rec["error"] = str(e)

    return rec



def summarize(records: list[dict], start_time: str, end_time: str) -> dict:
    total = len(records)
    success = 0
    fail = 0
    total_time = 0.0
    count_time = 0
    total_bytes = 0
    status_dist = {}

    for r in records:
        code = r.get("status_code")
        err = r.get("error")
        if code and 200 <= code < 400 and not err:
            success += 1
        else:
            fail += 1

        rt = r.get("response_time_ms")
        if isinstance(rt, (int, float)):
            total_time += rt
            count_time += 1

        clen = r.get("content_length")
        if isinstance(clen, int):
            total_bytes += clen

        if code is not None:
            code_str = str(code)
            status_dist[code_str] = status_dist.get(code_str, 0) + 1

    avg_time = (total_time / count_time) if count_time > 0 else None

    return {
        "total_urls": total,
        "successful_requests": success,
        "failed_requests": fail,
        "average_response_time_ms": avg_time,
        "total_bytes_downloaded": total_bytes,
        "status_code_distribution": status_dist,
        "processing_start": start_time,
        "processing_end": end_time,
    }

def write_errors_log(records: list[dict], path: str) -> None:
    lines = []
    for r in records:
        msg = None
        if r.get("error"):
            msg = r["error"]
        elif isinstance(r.get("status_code"), int) and r["status_code"] >= 400:
            msg = f"HTTP {r['status_code']}"
        if msg:
            lines.append(f"{r['timestamp']} {r['url']} : {msg}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def main():
    if len(sys.argv) != 2 and len(sys.argv) != 3:
        print("Usage: python fetch_and_process.py <input_file> <output_dir>", file=sys.stderr)
        sys.exit(1)

    input_file = sys.argv[1]
    output_dir = sys.argv[2]

    if not os.path.isfile(input_file):
        print(f"Input file not found: {input_file}", file=sys.stderr)
        sys.exit(2)

    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(input_file):
        raise SystemExit(f"Input file not found: {input_file}")

    os.makedirs(output_dir, exist_ok=True)

    # Read URLs
    with open(input_file, "r", encoding="utf-8") as f:
        urls = [line.strip() for line in f if line.strip()]

    # Fetch
    records = []

    start_time = iso_utc_now()

    for u in urls:
        print(f"Fetching: {u}")
        records.append(fetch_once(u))

    end_time = iso_utc_now()

    # Write responses.json
    responses_path = os.path.join(output_dir, "responses.json")
    with open(responses_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    # Write summary.json
    summary_path = os.path.join(output_dir, "summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summarize(records, start_time, end_time), f, indent=2, ensure_ascii=False)

    # Write errors.log
    errors_path = os.path.join(output_dir, "errors.log")
    write_errors_log(records, errors_path)

    print(f"Wrote:\n  {responses_path}\n  {summary_path}\n  {errors_path}")


if __name__ == "__main__":
    main()
