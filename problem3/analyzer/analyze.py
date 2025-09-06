import os
import json
import time
import glob
import re
from collections import Counter
from datetime import datetime, timezone
from itertools import combinations
from typing import List, Dict, Tuple

SHARED_DIR = "/shared"
PROCESSED_DIR = os.path.join(SHARED_DIR, "processed")
STATUS_DIR = os.path.join(SHARED_DIR, "status")
ANALYSIS_DIR = os.path.join(SHARED_DIR, "analysis")

PROCESS_MARKER = os.path.join(STATUS_DIR, "process_complete.json")
FINAL_REPORT = os.path.join(ANALYSIS_DIR, "final_report.json")


def log(msg: str) -> None:
    print(f"[analyzer] {msg}", flush=True)


def iso_utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    os.makedirs(ANALYSIS_DIR, exist_ok=True)
    os.makedirs(STATUS_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)


def wait_for_process_marker(path: str, poll_sec: float = 1.0) -> None:
    log(f"Waiting for process-complete marker: {path}")
    while not os.path.exists(path):
        time.sleep(poll_sec)
    log("Detected process_complete.json. Starting analysis...")


def tokenize(text: str) -> List[str]:
    # Lowercase, keep word characters only
    return re.findall(r"\b\w+\b", text.lower())


def split_sentences(text: str) -> List[str]:
    # Heuristic sentence split on punctuation
    return [s for s in re.split(r'(?<=[.!?])\s+', text) if s.strip()]


def ngrams(tokens: List[str], n: int) -> List[Tuple[str, ...]]:
    if n <= 0:
        return []
    return [tuple(tokens[i:i+n]) for i in range(len(tokens) - n + 1)]


def jaccard_similarity(doc1_words, doc2_words):
    """Calculate Jaccard similarity between two documents."""
    set1 = set(doc1_words)
    set2 = set(doc2_words)
    intersection = set1.intersection(set2)
    union = set1.union(set2)
    return len(intersection) / len(union) if union else 0.0


def load_processed_docs() -> List[Dict]:
    files = sorted(glob.glob(os.path.join(PROCESSED_DIR, "*.json")))
    docs = []
    for p in files:
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                data["_filename"] = os.path.basename(p)
                docs.append(data)
        except Exception as e:
            log(f"ERROR loading {p}: {e}")
    return docs


def compute_global_statistics(docs: List[Dict]) -> Dict:
    # Corpus accumulators
    all_tokens: List[str] = []
    per_doc_tokens: Dict[str, List[str]] = {}
    total_words = 0
    total_word_len = 0
    total_sentences = 0

    for d in docs:
        text = d.get("text", "")
        tokens = tokenize(text)
        per_doc_tokens[d["_filename"]] = tokens
        all_tokens.extend(tokens)

        total_words += len(tokens)
        total_word_len += sum(len(w) for w in tokens)
        total_sentences += len(split_sentences(text))

    # Word frequency
    word_counts = Counter(all_tokens)
    unique_words = len(word_counts)

    # Top-100 with relative frequency
    top_100 = word_counts.most_common(100)
    top_100_words = [
        {
            "word": w,
            "count": c,
            "frequency": (c / total_words) if total_words else 0.0,
        }
        for w, c in top_100
    ]

    # N-grams
    bigram_counts = Counter()
    trigram_counts = Counter()
    for toks in per_doc_tokens.values():
        bigram_counts.update(ngrams(toks, 2))
        trigram_counts.update(ngrams(toks, 3))

    top_bigrams = [{"bigram": " ".join(bg), "count": c} for bg, c in bigram_counts.most_common(50)]
    top_trigrams = [{"trigram": " ".join(tg), "count": c} for tg, c in trigram_counts.most_common(50)]

    # Document similarity (Jaccard over unique word sets)
    similarity_rows = []
    for (f1, t1), (f2, t2) in combinations(per_doc_tokens.items(), 2):
        sim = jaccard_similarity(t1, t2)
        similarity_rows.append({
            "doc1": f1,
            "doc2": f2,
            "similarity": sim
        })

    # Readability metrics
    avg_sentence_length = (total_words / total_sentences) if total_sentences else 0.0
    avg_word_length = (total_word_len / total_words) if total_words else 0.0

    # Gunning Fog–style heuristic:
    # complexity = 0.4 * (ASL + 100 * (complex_words / total_words))
    # Define "complex" as word length >= 7
    complex_words = sum(1 for w in all_tokens if len(w) >= 7)
    complexity = 0.4 * (avg_sentence_length + (100.0 * complex_words / total_words if total_words else 0.0))

    return {
        "processing_timestamp": iso_utc_now(),
        "documents_processed": len(docs),
        "total_words": total_words,
        "unique_words": unique_words,
        "top_100_words": top_100_words,
        "document_similarity": similarity_rows,
        "top_bigrams": top_bigrams,
        "top_trigrams": top_trigrams,
        "readability": {
            "avg_sentence_length": round(avg_sentence_length, 3),
            "avg_word_length": round(avg_word_length, 3),
            "complexity_score": round(complexity, 3),
        },
    }


def main():
    ensure_dirs()
    wait_for_process_marker(PROCESS_MARKER)

    docs = load_processed_docs()
    if not docs:
        log("No processed documents found. Writing empty report.")
        report = {
            "processing_timestamp": iso_utc_now(),
            "documents_processed": 0,
            "total_words": 0,
            "unique_words": 0,
            "top_100_words": [],
            "document_similarity": [],
            "top_bigrams": [],
            "top_trigrams": [],
            "readability": {
                "avg_sentence_length": 0.0,
                "avg_word_length": 0.0,
                "complexity_score": 0.0
            }
        }
        with open(FINAL_REPORT, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        log(f"Wrote empty report to {FINAL_REPORT}")
        return

    report = compute_global_statistics(docs)
    with open(FINAL_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log(f"Analysis complete. Report saved to {FINAL_REPORT}")


if __name__ == "__main__":
    main()
