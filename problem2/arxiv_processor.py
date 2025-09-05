import sys, json, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime
import time, re, os

STOPWORDS = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
             'of', 'with', 'by', 'from', 'up', 'about', 'into', 'through', 'during',
             'is', 'are', 'was', 'were', 'be', 'been', 'being', 'have', 'has', 'had',
             'do', 'does', 'did', 'will', 'would', 'could', 'should', 'may', 'might',
             'can', 'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
             'we', 'they', 'what', 'which', 'who', 'when', 'where', 'why', 'how',
             'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some',
             'such', 'as', 'also', 'very', 'too', 'only', 'so', 'than', 'not'}

ARXIV_ENDPOINT = "http://export.arxiv.org/api/query"

_UNRESERVED = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.~"


def _percent_encode(s):
    out = []
    for ch in s:
        if ch in _UNRESERVED:
            out.append(ch)
        elif ch == " ":
            out.append("+")
        else:

            for b in ch.encode("utf-8"):
                out.append("%%%02X" % b)
    return "".join(out)


def build_query_url(search_query, start, max_results):
    return (
            ARXIV_ENDPOINT
            + "?search_query=" + _percent_encode(search_query)
            + "&start=" + str(start)
            + "&max_results=" + str(max_results)
    )


# ---------------- HTTP (simple retry) ----------------
def http_get(url, out_dir, timeout=20, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "ee547_hw1",
                    "Accept": "application/atom+xml",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries - 1:
                time.sleep(3)
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)  # backoff
                continue

            append_log(out_dir, "ERROR : unreachable")
            exit(1)


# ---------------- Text utilities ----------------


WORD_RE = re.compile(r"[A-Za-z0-9\-]+", flags=re.UNICODE)


def tokenize_preserve_case(text):
    # Keep letters/digits/hyphen to support "state-of-the-art" and "ResNet50"
    return WORD_RE.findall(text)


def tokenize_lower(text):
    return [t.lower() for t in WORD_RE.findall(text)]


def unique_keep_order(seq):
    seen = set()
    out = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def split_sentences(text):
    parts = re.split(r"[.!?]+", text)
    return [p.strip() for p in parts if p.strip()]


def compute_abstract_stats(abstract_text):
    # case-insensitive counting
    toks = tokenize_lower(abstract_text)
    total_words = len(toks)
    unique_words = len(set(toks))
    sentences = split_sentences(abstract_text)
    total_sentences = len(sentences)
    avg_words_per_sentence = (float(total_words) / total_sentences) if total_sentences else 0.0
    avg_word_length = (sum(len(t) for t in toks) / float(total_words)) if total_words else 0.0
    return {
        "total_words": total_words,
        "unique_words": unique_words,
        "total_sentences": total_sentences,
        "avg_words_per_sentence": avg_words_per_sentence,
        "avg_word_length": avg_word_length,
    }



# ---------------- XML parsing ----------------


def parse_feed(xml_bytes, out_dir):
    ns = {
        "atom": "http://www.w3.org/2005/Atom",
    }
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        append_log(out_dir, f"ERROR Invalid XML feed: {e}")
        return []

    entries = root.findall("atom:entry", ns)

    append_log(out_dir, f"Fetched { len(entries) } results from ArXiv API")

    out = []
    for e in entries:
        try:
            def _t(path):
                elem = e.find(path, ns)
                return (elem.text or "").strip() if elem is not None and elem.text else ""

            arxiv_full_id = _t("atom:id")
            arxiv_id = arxiv_full_id.rsplit("/", 1)[-1] if arxiv_full_id else ""

            if arxiv_id != "":
                append_log(out_dir, f"Processing paper: {arxiv_id} ")
            else:
                append_log(out_dir, f"WARN Missing fields [arxiv_id] in entry ")

            title = _t("atom:title")
            if title.strip() == "":
                append_log(out_dir, f"WARN Missing fields [title] in entry ")
            summary = _t("atom:summary")
            if summary.strip() == "":
                append_log(out_dir, f"WARN Missing fields [summary] in entry ")
            published = _t("atom:published")
            if published.strip() == "":
                append_log(out_dir, f"WARN Missing fields [published] in entry ")
            updated = _t("atom:updated")
            if updated.strip() == "":
                append_log(out_dir, f"WARN Missing fields [updated] in entry ")
            authors = []
            for a in e.findall("atom:author", ns):
                nm = a.find("atom:name", ns)
                if nm is not None and nm.text:
                    authors.append(nm.text.strip())
            if len(authors) == 0:
                append_log(out_dir, f"WARN Missing fields [authors] in entry ")
            cats = []
            for c in e.findall("atom:category", ns):
                term = c.attrib.get("term", "").strip()
                if term:
                    cats.append(term)
            if len(cats) == 0:
                append_log(out_dir, f"WARN Missing fields [categories] in entry ")

            stats = compute_abstract_stats(summary)
            out.append({
                "arxiv_id": arxiv_id,
                "title": title,
                "authors": authors,
                "abstract": summary,
                "categories": cats,
                "published": published,
                "updated": updated,
                "abstract_stats" : stats
            })
        except Exception as ex:
            append_log(out_dir, f"ERROR Invalid entry XML, skipped one paper: {ex}")
            continue
    return out


# ---------------- Files & errors ----------------
def ensure_dir(p):
    if p and not os.path.isdir(p):
        os.makedirs(p, exist_ok=True)


def append_log(out_dir, msg):
    try:
        with open(os.path.join(out_dir, "processing.log"), "a", encoding="utf-8") as f:
            f.write("[%s] %s\n" % (datetime.utcnow().isoformat() + "Z", msg))
    except Exception:
        pass


def compute_corpus_analysis(papers, search_query):
    # Aggregate stats across all papers' abstracts
    total_abstracts = len(papers)

    global_total_words = 0
    global_unique_words = set()
    lengths = []  # per-abstract word counts

    # term frequency (case-insensitive) & document frequency
    tf = {}
    df = {}
    surface = {}      # first-seen surface form

    # technical terms (preserve original case; unique across corpus)
    upper_terms = []
    numeric_terms = []
    hyphen_terms = []

    # category distribution
    cat_dist = {}

    for p in papers:
        abstract = p.get("abstract", "") or ""
        # lengths + totals
        toks_lower = tokenize_lower(abstract)
        toks_raw   = tokenize_preserve_case(abstract)
        n_words = len(toks_lower)
        lengths.append(n_words)
        global_total_words += n_words
        for t in toks_lower:
            global_unique_words.add(t)

        # term frequency and doc frequency (exclude stopwords)
        seen_in_doc = set()
        for raw, low in zip(toks_raw, toks_lower):
            if low in STOPWORDS:
                continue
            tf[low] = tf.get(low, 0) + 1
            if low not in surface:
                surface[low] = raw  # first appearance surface form
            if low not in seen_in_doc:
                seen_in_doc.add(low)
        for w in seen_in_doc:
            df[w] = df.get(w, 0) + 1

        for t in toks_raw:
            if re.compile(r"^[A-Z]+$").fullmatch(t):
                upper_terms.append(t)
            if re.search(r"\d", t):
                numeric_terms.append(t)
            if "-" in t and len(t) > 1:
                hyphen_terms.append(t)

        for c in (p.get("categories") or []):
            cat_dist[c] = cat_dist.get(c, 0) + 1

    # corpus-level stats
    avg_len = (float(global_total_words) / total_abstracts) if total_abstracts else 0.0
    longest = max(lengths) if lengths else 0
    shortest = min(lengths) if lengths else 0

    # top-50 words by tf
    items = sorted(tf.items(), key=lambda kv: (-kv[1], kv[0]))
    top_50 = []
    for low, freq in items[:50]:
        top_50.append({
            "word": surface.get(low, low),
            "frequency": freq,
            "documents": df.get(low, 0)
        })

    return {
        "query": search_query,
        "papers_processed": total_abstracts,
        "processing_timestamp": datetime.utcnow().isoformat() + "Z",
        "corpus_stats": {
            "total_abstracts": total_abstracts,
            "total_words": global_total_words,
            "unique_words_global": len(global_unique_words),
            "avg_abstract_length": avg_len,
            "longest_abstract_words": longest,
            "shortest_abstract_words": shortest
        },
        "top_50_words": top_50,
        "technical_terms": {
            "uppercase_terms": unique_keep_order(upper_terms),
            "numeric_terms": unique_keep_order(numeric_terms),
            "hyphenated_terms": unique_keep_order(hyphen_terms)
        },
        "category_distribution": cat_dist
    }


# ---------------- Main ----------------
def main(argv):
    if len(argv) != 4:
        sys.stderr.write(
            "Usage: python arxiv_processor.py \"<search_query>\" <max_results 1..100> <output_dir>\n"
            "Example: python arxiv_processor.py \"cat:cs.LG\" 10 ./out\n"
        )
        return 1

    search_query = argv[1]
    try:
        max_results = int(argv[2])
    except ValueError:
        sys.stderr.write("max_results must be an integer 1..100\n");
        return 1
    if not (1 <= max_results <= 100):
        sys.stderr.write("max_results must be in [1, 100]\n");
        return 1

    out_dir = argv[3]
    ensure_dir(out_dir)

    url = build_query_url(search_query, start=0, max_results=max_results)
    try:
        append_log(out_dir, f"Starting ArXiv query: {argv[1]}")
        xml_bytes = http_get(url, out_dir)

    except Exception as e:
        append_log(out_dir, "ERROR : Fetch failed: %r" % e)
        sys.stderr.write("Failed to fetch ArXiv API. See errors.log?\n")
        return 2

    try:
        papers = parse_feed(xml_bytes, out_dir)
    except Exception as e:
        append_log(out_dir, "Parse failed: %r" % e)
        sys.stderr.write("Failed to parse XML. See errors.log?\n")
        return 3

    try:
        with open(os.path.join(out_dir, "papers.json"), "w", encoding="utf-8") as f:
            json.dump(papers, f, ensure_ascii=False, indent=2)
    except Exception as e:
        append_log(out_dir, "Write papers.json failed: %r" % e)

    analysis = compute_corpus_analysis(papers, search_query)
    try:
        with open(os.path.join(out_dir, "corpus_analysis.json"), "w", encoding="utf-8") as f:
            json.dump(analysis, f, ensure_ascii=False, indent=2)
    except Exception as e:
        append_log(out_dir, "Write corpus_analysis.json failed: %r" % e)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))

