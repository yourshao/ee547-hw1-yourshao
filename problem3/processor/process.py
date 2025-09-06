import os
import re
import json
import time
import glob
from datetime import datetime, timezone
from typing import List, Tuple, Dict

SHARED_DIR = "/shared"
RAW_DIR = os.path.join(SHARED_DIR, "raw")
PROCESSED_DIR = os.path.join(SHARED_DIR, "processed")
STATUS_DIR = os.path.join(SHARED_DIR, "status")

FETCH_MARKER = os.path.join(STATUS_DIR, "fetch_complete.json")
PROCESS_MARKER = os.path.join(STATUS_DIR, "process_complete.json")


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(f"[processor] {msg}", flush=True)


def ensure_dirs() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    os.makedirs(STATUS_DIR, exist_ok=True)


def wait_for_fetch_marker(path: str, poll_sec: float = 1.0) -> None:
    log(f"Waiting for fetch marker: {path}")
    while not os.path.exists(path):
        time.sleep(poll_sec)
    log("Detected fetch_complete.json. Starting processing...")


def strip_html(html_content):
    """Remove HTML tags and extract text."""
    # Remove script and style elements
    html_content = re.sub(r'<script[^>]*>.*?</script>', '', html_content, flags=re.DOTALL | re.IGNORECASE)
    html_content = re.sub(r'<style[^>]*>.*?</style>', '', html_content, flags=re.DOTALL | re.IGNORECASE)

    # Extract links before removing tags
    links = re.findall(r'href=[\'"]?([^\'" >]+)', html_content, flags=re.IGNORECASE)

    # Extract images
    images = re.findall(r'src=[\'"]?([^\'" >]+)', html_content, flags=re.IGNORECASE)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', html_content)

    # Clean whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text, links, images


def compute_statistics(text: str, original_html: str) -> Dict[str, object]:
    # Words: \b\w+\b keeps numbers/letters/underscore; adjust if needed
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)

    # Sentences: split on punctuation followed by space/newline
    # This is a heuristic; good enough for this assignment
    sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if s]
    sentence_count = len(sentences)

    # Paragraphs: count <p ...> tags in original HTML; fallback to 1 if text exists
    para_tags = re.findall(r'<\s*p\b[^>]*>', original_html, flags=re.IGNORECASE)
    paragraph_count = len(para_tags)
    if paragraph_count == 0:
        paragraph_count = 1 if text else 0

    avg_word_length = round(
        (sum(len(w) for w in words) / word_count) if word_count else 0.0, 3
    )

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "paragraph_count": paragraph_count,
        "avg_word_length": avg_word_length,
    }


def process_one_file(html_path: str) -> Dict[str, object]:
    with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
        html = f.read()

    text, links, images = strip_html(html)
    stats = compute_statistics(text, html)

    source_file = os.path.basename(html_path)
    result = {
        "source_file": source_file,
        "text": text,
        "statistics": stats,
        "links": links,
        "images": images,
        "processed_at": iso_utc_now(),
    }
    return result


def write_json(path: str, obj: Dict[str, object]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def main() -> None:
    ensure_dirs()
    wait_for_fetch_marker(FETCH_MARKER)

    html_files = sorted(glob.glob(os.path.join(RAW_DIR, "*.html")))
    if not html_files:
        log("No HTML files found in /shared/raw/. Writing empty process marker.")
        write_json(PROCESS_MARKER, {
            "status": "complete",
            "processed_files": 0,
            "processed_at": iso_utc_now()
        })
        return

    processed_count = 0
    for html_path in html_files:
        try:
            result = process_one_file(html_path)
            stem, _ = os.path.splitext(os.path.basename(html_path))
            out_path = os.path.join(PROCESSED_DIR, f"{stem}.json")
            write_json(out_path, result)
            processed_count += 1
            log(f"Processed {os.path.basename(html_path)} -> {os.path.basename(out_path)}")
        except Exception as e:
            # Fail soft: log and continue with other files
            log(f"ERROR processing {html_path}: {e}")

    # Write completion marker
    write_json(PROCESS_MARKER, {
        "status": "complete",
        "processed_files": processed_count,
        "processed_at": iso_utc_now()
    })
    log(f"Processing complete. Files processed: {processed_count}. Marker written to {PROCESS_MARKER}.")


if __name__ == "__main__":
    main()



