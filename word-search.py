import json
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Iterable, Optional, Any


HANDSPEAK_DICT_PATH = "handspeak-dict.txt"
LIFEPRINT_DICT_PATH = "lifeprint-dict.txt"


# -----------------------------
# Data model
# -----------------------------
@dataclass(frozen=True)
class Entry:
    source: str   # "handspeak" | "lifeprint"
    title: str
    url: str

    @property
    def norm_title(self) -> str:
        return normalize_text(self.title)


@dataclass(frozen=True)
class RankedResult:
    entry: Entry
    score: float
    reason: str  # short breadcrumb for debugging/testing


# -----------------------------
# Normalization utilities
# -----------------------------
_WORD_CHARS_RE = re.compile(r"[^a-z0-9\s]")


def normalize_text(s: str) -> str:
    """
    Normalize for matching:
    - lowercase
    - remove punctuation
    - collapse whitespace
    """
    s = (s or "").lower().strip()
    s = _WORD_CHARS_RE.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def tokenize(s: str) -> list[str]:
    s = normalize_text(s)
    return [t for t in s.split(" ") if t]


def similarity(a: str, b: str) -> float:
    """0..1 similarity score using built-in SequenceMatcher."""
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


# -----------------------------
# Loading JSONL dictionaries
# -----------------------------
def iter_jsonl(path: str) -> Iterable[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict):
                    yield obj
    except FileNotFoundError:
        return


def load_entries() -> list[Entry]:
    entries: list[Entry] = []

    for obj in iter_jsonl(HANDSPEAK_DICT_PATH):
        title = obj.get("title")
        url = obj.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            entries.append(Entry(source="handspeak", title=title, url=url))

    for obj in iter_jsonl(LIFEPRINT_DICT_PATH):
        title = obj.get("title")
        url = obj.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            entries.append(Entry(source="lifeprint", title=title, url=url))

    return entries


# -----------------------------
# Basic "AI" ranking logic
# -----------------------------
def rank_entry(query_norm: str, query_tokens: list[str], entry: Entry) -> Optional[RankedResult]:
    """
    Score an entry for the query.

    Heuristic scoring (simple now, expandable later):
    - exact match gets highest score
    - prefix match and full-token match score high
    - substring match scores medium
    - typo similarity scores lower but still useful
    """
    title_norm = entry.norm_title
    if not title_norm:
        return None

    # Hard filter: ignore "too short" matches unless query is also short
    if len(query_norm) >= 3 and len(title_norm) <= 1:
        return None

    if title_norm == query_norm:
        return RankedResult(entry, 1.00, "exact match")

    if title_norm.startswith(query_norm):
        return RankedResult(entry, 0.92, "prefix match")

    # Token containment (good for multi-word titles)
    title_tokens = tokenize(entry.title)
    if query_tokens and all(t in title_tokens for t in query_tokens):
        return RankedResult(entry, 0.88, "all query tokens present")

    if query_norm in title_norm:
        return RankedResult(entry, 0.75, "substring match")

    # Similarity for typos / close phrasing
    sim = similarity(query_norm, title_norm)
    if sim >= 0.72:
        return RankedResult(entry, 0.50 + (sim * 0.40), f"similarity {sim:.2f}")

    return None


def search(query: str, *, limit: int = 8, explain: bool = False) -> list[RankedResult]:
    """
    Search both dictionaries and return ranked results.
    """
    query_norm = normalize_text(query)
    if not query_norm:
        return []

    query_tokens = tokenize(query_norm)
    entries = load_entries()

    ranked: list[RankedResult] = []
    for e in entries:
        rr = rank_entry(query_norm, query_tokens, e)
        if rr is not None:
            ranked.append(rr)

    ranked.sort(key=lambda r: (r.score, r.entry.source), reverse=True)
    ranked = ranked[:limit]

    if not explain:
        # Keep reason field but it won't be shown unless caller prints it
        return ranked

    return ranked


def format_results(query: str, results: list[RankedResult], *, include_reasons: bool = False) -> str:
    if not results:
        return f"No matches found for {query!r}."

    lines = [f"Results for {query!r}:"]
    for r in results:
        src = r.entry.source
        title = r.entry.title
        url = r.entry.url
        if include_reasons:
            lines.append(f"- [{src}] {title}: {url} ({r.reason}, score={r.score:.2f})")
        else:
            lines.append(f"- [{src}] {title}: {url}")
    return "\n".join(lines)


# -----------------------------
# CLI test harness
# -----------------------------
def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage: python word-search.py <query>")
        return 2

    query = " ".join(argv[1:])
    results = search(query, limit=10, explain=True)
    print(format_results(query, results, include_reasons=True))
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv))