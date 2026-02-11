import json
import string
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Iterable, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# -----------------------------
# File paths (JSON Lines)
# -----------------------------
HAND_SPEAK_DICT_PATH = "handspeak-dict.txt"
LIFEPRINT_DICT_PATH = "lifeprint-dict.txt"
ON_DEMAND_DICT_PATH = "ondemand-dict.txt"

# -----------------------------
# Updater configuration
# -----------------------------
REQUEST_DELAY_SECONDS = 0.5
MAX_CONSECUTIVE_404 = 3

HEADERS = {
    "User-Agent": "signbot-dict-updater/1.0 (+local-script)",
}

HAND_SPEAK_URL_TEMPLATE = "https://www.handspeak.com/word/{id}"
LIFEPRINT_LETTER_URL_TEMPLATE = "https://lifeprint.com/asl101/index/{letter}.htm"

# -----------------------------
# Shared helpers (JSONL)
# -----------------------------
def _iter_jsonl(path: str) -> Iterable[Dict]:
    """Yield dict objects from a JSONL file. Skips blank/bad lines."""
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


def _append_jsonl(path: str, obj: Dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _get_saved_urls(path: str) -> set[str]:
    saved = set()
    for obj in _iter_jsonl(path):
        url = obj.get("url")
        if isinstance(url, str) and url:
            saved.add(url)
    return saved


# -----------------------------
# Handspeak updater
# -----------------------------
@dataclass(frozen=True)
class UpdateResult:
    wrote: int
    last_id_before: int
    last_id_after: int
    stopped_reason: str

def _clean_handspeak_title(raw_title: str) -> str:
    title = (raw_title or "").strip()

    if "•" in title:
        title = title.split("•", 1)[0].strip()

    for sep in ("|", " - "):
        if sep in title:
            title = title.split(sep, 1)[0].strip()

    lowered = title.lower()
    suffix = "asl dictionary"
    if lowered.endswith(suffix):
        title = title[: -len(suffix)].strip(" -|•\t")

    return title

def get_last_saved_handspeak_id(path: str = HAND_SPEAK_DICT_PATH) -> int:
    max_id = 0
    for obj in _iter_jsonl(path):
        try:
            max_id = max(max_id, int(obj.get("id", 0)))
        except (TypeError, ValueError):
            continue
    return max_id

def _parse_handspeak_entry(html: str, entry_id: int, url: str) -> Dict:
    soup = BeautifulSoup(html, "html.parser")
    raw_title = (soup.title.get_text(strip=True) if soup.title else "") or ""
    title = _clean_handspeak_title(raw_title)

    canonical = soup.find("link", rel="canonical")
    canonical_url = canonical.get("href", "") if canonical else ""

    return {
        "id": entry_id,
        "url": canonical_url or url,
        "title": title,
    }

def _fetch_handspeak_entry(session: requests.Session, entry_id: int) -> Tuple[Optional[Dict], int]:
    url = HAND_SPEAK_URL_TEMPLATE.format(id=entry_id)
    resp = session.get(url, headers=HEADERS, timeout=20)

    if resp.status_code == 404:
        return None, 404

    resp.raise_for_status()
    return _parse_handspeak_entry(resp.text, entry_id=entry_id, url=url), resp.status_code

def update_handspeak_dict(
    *,
    output_path: str = HAND_SPEAK_DICT_PATH,
    start_id: Optional[int] = None,
    max_new: Optional[int] = 500,
    request_delay_seconds: float = REQUEST_DELAY_SECONDS,
    max_consecutive_404: int = MAX_CONSECUTIVE_404,
) -> UpdateResult:
    last_before = get_last_saved_handspeak_id(output_path)
    entry_id = (last_before + 1) if start_id is None else int(start_id)

    wrote = 0
    consecutive_404 = 0
    last_after = last_before

    with requests.Session() as session:
        while True:
            if max_new is not None and wrote >= max_new:
                return UpdateResult(wrote, last_before, last_after, f"reached max_new={max_new}")

            try:
                entry, status = _fetch_handspeak_entry(session, entry_id)
            except requests.RequestException as e:
                return UpdateResult(wrote, last_before, last_after, f"request error: {e}")

            if status == 404 or entry is None:
                consecutive_404 += 1
                if consecutive_404 >= max_consecutive_404:
                    return UpdateResult(wrote, last_before, last_after, f"hit {max_consecutive_404} consecutive 404s")
            else:
                consecutive_404 = 0
                _append_jsonl(output_path, entry)
                wrote += 1
                last_after = entry_id

            entry_id += 1
            time.sleep(request_delay_seconds)


# -----------------------------
# Lifeprint updater
# -----------------------------
def _is_lifeprint_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("lifeprint.com")


def _normalize_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    abs_url = urljoin(base, href).split("#", 1)[0]
    return abs_url


def _extract_lifeprint_word_links(html: str, base_url: str) -> list[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Dict] = []

    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        if not text:
            continue

        href = a.get("href", "")
        url = _normalize_url(base_url, href)
        if not url or not _is_lifeprint_url(url):
            continue

        if "/asl101/" not in url:
            continue

        out.append({"url": url, "title": text})

    return out


def update_lifeprint_dict(
    *,
    output_path: str = LIFEPRINT_DICT_PATH,
    letter_url_template: str = LIFEPRINT_LETTER_URL_TEMPLATE,
    request_delay_seconds: float = REQUEST_DELAY_SECONDS,
) -> Dict:
    saved_urls = _get_saved_urls(output_path)
    wrote = 0
    skipped = 0

    with requests.Session() as session:
        for letter in string.ascii_lowercase:
            index_url = letter_url_template.format(letter=letter)

            try:
                resp = session.get(index_url, headers=HEADERS, timeout=20)
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
            except requests.RequestException:
                continue

            for rec in _extract_lifeprint_word_links(resp.text, base_url=index_url):
                if rec["url"] in saved_urls:
                    skipped += 1
                    continue
                _append_jsonl(output_path, rec)
                saved_urls.add(rec["url"])
                wrote += 1

            time.sleep(request_delay_seconds)

    return {"wrote": wrote, "skipped_existing": skipped, "total_saved": len(saved_urls)}


# -----------------------------
# Daily random pick helpers
# -----------------------------
def load_dictionary_entries(path: str) -> list[Dict]:
    """Load entries as a list of {title, url, ...} dicts."""
    entries: list[Dict] = []
    for obj in _iter_jsonl(path):
        title = obj.get("title")
        url = obj.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            entries.append(obj)
    return entries


def urls_used_within_days(history: Iterable[Dict], days: int = 365) -> set[str]:
    """Return URLs used within the last N days (UTC)."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used: set[str] = set()

    for item in history:
        url = item.get("url")
        ts = item.get("ts")
        if not isinstance(url, str) or not url:
            continue
        if not isinstance(ts, str) or not ts:
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            used.add(url)

    return used


def choose_random_unused(
    entries: list[Dict],
    *,
    exclude_urls: set[str],
) -> Optional[Dict]:
    """Pick a random entry whose URL is not excluded."""
    import random

    candidates = [e for e in entries if isinstance(e.get("url"), str) and e["url"] not in exclude_urls]
    if not candidates:
        return None
    return random.choice(candidates)


def build_daily_word_post(
    *,
    handspeak_entries: list[Dict],
    lifeprint_entries: list[Dict],
    exclude_urls: set[str],
    history: Optional[Iterable[Dict]] = None,
) -> Tuple[str, Iterable[Dict]]:
    """
    Returns (message_text, used_entries_to_record).

    Picks ONE canonical word, then shows that same word across
    all available dictionaries (local + web) when possible.
    """

    # Safety: prevent double-posting
    if history and has_posted_today(history):
        return "Daily word already posted today.", []

    # -----------------------------
    # Step 1: choose ONE anchor word
    # -----------------------------
    combined = handspeak_entries + lifeprint_entries
    anchor = choose_random_unused(combined, exclude_urls=exclude_urls)

    if anchor is None:
        return (
            "Daily word: no eligible entries found "
            "(dictionaries empty or all entries recently used).",
            []
        )

    word = anchor["title"]

    # -----------------------------
    # Step 2: search all providers for this word
    # -----------------------------
    results = search_all_providers(word)

    if not results["exact"] and not results["partial"]:
        return f"Daily word: **{word}** (no additional sources found).", []

    lines = [
        "**Daily sign practice word:**",
        f"**{word.upper()}**",
    ]

    used: list[Dict] = []

    # Prefer exact matches
    for entry in results["exact"]:
        lines.append(
            f"- {entry['provider'].title()}: {entry['title']} — {entry['url']}"
        )
        used.append({
            "source": entry["provider"],
            "title": entry["title"],
            "url": entry["url"],
        })

    # Mention partial matches without listing all of them
    if results["partial"]:
        lines.append(
            f"_Additional matches available in {len(results['partial'])} other entries._"
        )

    return "\n".join(lines), used

def perform_web_search(query: str) -> str:
    """
    Your bot command helper. (Unchanged behavior expectation: return a readable string.)
    """
    results = []
    q = query.strip().lower()
    if not q:
        return "Please provide a search term."

    for obj in _iter_jsonl(LIFEPRINT_DICT_PATH):
        title = str(obj.get("title", "")).strip()
        url = str(obj.get("url", "")).strip()
        if title and url and q in title.lower():
            results.append((title, url))
            if len(results) >= 5:
                break

    for obj in _iter_jsonl(HAND_SPEAK_DICT_PATH):
        title = str(obj.get("title", "")).strip()
        url = str(obj.get("url", "")).strip()
        if title and url and q in title.lower():
            results.append((title, url))
            if len(results) >= 10:
                break

    if not results:
        return f"No local dictionary matches found for: {query!r}"

    lines = [f"Results for {query!r}:"]
    for title, url in results[:8]:
        lines.append(f"- {title}: {url}")
    return "\n".join(lines)

import requests
from bs4 import BeautifulSoup

def search_signingsavvy(word):
    url = f"https://www.signingsavvy.com/search/{word}"
    r = requests.get(url, timeout=10)

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # SigningSavvy usually links results like /sign/WORD/ID
    link = soup.select_one("a[href^='/sign/']")
    if not link:
        return None

    full_url = "https://www.signingsavvy.com" + link["href"]

    return {
        "source": "signingsavvy",
        "url": full_url
    }

def search_spreadthesign(word):
    url = f"https://www.spreadthesign.com/en.us/search/?q={word}"
    r = requests.get(url, timeout=10)

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("a.search-result")

    if not link:
        return None

    return {
        "source": "spreadthesign",
        "url": "https://www.spreadthesign.com" + link["href"]
    }

def search_signasl(word):
    url = f"https://www.signasl.org/sign/{word}"
    r = requests.get(url, timeout=10)

    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # SignASL returns 404-like pages without error codes sometimes
    if "No sign found" in soup.text:
        return None

    return {
        "source": "signasl",
        "url": url
    }

def _normalize_word(word: str) -> str:
    """
    Normalize user input so lookups are consistent.
    Example: 'Hello!' → 'hello'
    """
    return word.strip().lower().strip(string.punctuation)

def lookup_local_word(word: str) -> Optional[Dict]:
    """
    Look for a word in existing local dictionaries.
    Returns the matching record if found, otherwise None.
    """
    q = _normalize_word(word)

    # Check Lifeprint
    for obj in _iter_jsonl(LIFEPRINT_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "lifeprint"}

    # Check Handspeak
    for obj in _iter_jsonl(HAND_SPEAK_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "handspeak"}

    # Check previously on-demand saved words
    for obj in _iter_jsonl(ON_DEMAND_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return obj

    return None
def search_all_providers(word: str) -> Dict[str, list[Dict]]:
    """
    Search all ASL providers (local + web).

    Returns:
    {
        "exact": [ {provider, title, url}, ... ],
        "partial": [ {provider, title, url}, ... ]
    }
    """
    q = _normalize_word(word)

    results_exact: list[Dict] = []
    results_partial: list[Dict] = []
    seen_urls: set[str] = set()

    # -----------------------------
    # Local dictionaries (Lifeprint / Handspeak / On-demand)
    # -----------------------------
    for path, provider in (
        (LIFEPRINT_DICT_PATH, "lifeprint"),
        (HAND_SPEAK_DICT_PATH, "handspeak"),
        (ON_DEMAND_DICT_PATH, "ondemand"),
    ):
        for obj in _iter_jsonl(path):
            title = str(obj.get("title", "")).strip()
            url = str(obj.get("url", "")).strip()
            if not title or not url or url in seen_urls:
                continue

            title_l = title.lower()
            if q == title_l:
                results_exact.append({
                    "provider": provider,
                    "title": title,
                    "url": url,
                })
                seen_urls.add(url)
            elif q in title_l:
                results_partial.append({
                    "provider": provider,
                    "title": title,
                    "url": url,
                })
                seen_urls.add(url)

    # -----------------------------
    # Live providers (web search)
    # -----------------------------
    for provider_func in SEARCH_PROVIDERS:
        try:
            result = provider_func(q)
        except requests.RequestException:
            continue

        if not result:
            continue

        url = result.get("url")
        if not url or url in seen_urls:
            continue

        results_exact.append({
            "provider": result["source"],
            "title": q,
            "url": url,
        })
        seen_urls.add(url)

        time.sleep(REQUEST_DELAY_SECONDS)

    return {
        "exact": results_exact,
        "partial": results_partial,
    }

SEARCH_PROVIDERS = [
    search_signingsavvy,
    search_spreadthesign,
    search_signasl,
]

def save_ondemand_word(word: str, result: Dict) -> Dict:
    """
    Save a newly discovered ASL word into the on-demand dictionary.
    """
    record = {
        "title": word,
        "url": result["url"],
        "source": result["source"],
        "added": datetime.now(timezone.utc).isoformat(),
    }

    _append_jsonl(ON_DEMAND_DICT_PATH, record)
    return record

def lookup_or_fetch_word(word: str) -> Tuple[Optional[Dict], bool]:
    """
    1. Check local dictionaries
    2. If missing, search the web
    3. Save result if found

    Returns:
        (record, was_added)
    """
    normalized = _normalize_word(word)
    if not normalized:
        return None, False

    # Step 1: local lookup
    local = lookup_local_word(normalized)
    if local:
        return local, False

    # Step 2: web search fallback
    for provider in SEARCH_PROVIDERS:
        try:
            result = provider(normalized)
        except requests.RequestException:
            continue

        if result:
            saved = save_ondemand_word(normalized, result)
            return saved, True

        time.sleep(REQUEST_DELAY_SECONDS)

    return None, False

def has_posted_today(history: Iterable[Dict]) -> bool:
    """
    Returns True if a daily word was already posted today (UTC).
    """
    today = datetime.now(timezone.utc).date()

    for item in history:
        ts = item.get("ts")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when.date() == today:
            return True

    return False
