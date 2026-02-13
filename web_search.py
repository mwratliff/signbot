import json
import string
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Define JSONL dictionary storage paths used by the bot.
HAND_SPEAK_DICT_PATH = "handspeak-dict.txt"
LIFEPRINT_DICT_PATH = "lifeprint-dict.txt"
ON_DEMAND_DICT_PATH = "ondemand-dict.txt"

# Configure web fetch pacing and stop conditions.
REQUEST_DELAY_SECONDS = 0.5
MAX_CONSECUTIVE_404 = 3

# Send a stable user-agent so sites can identify this updater.
HEADERS = {
    "User-Agent": "signbot-dict-updater/1.0 (+local-script)",
}

# Define source URL templates for provider crawls.
HAND_SPEAK_URL_TEMPLATE = "https://www.handspeak.com/word/{id}"
LIFEPRINT_LETTER_URL_TEMPLATE = "https://lifeprint.com/asl101/index/{letter}.htm"


# Yield valid dictionary objects from a JSONL file.
def _iter_jsonl(path: str) -> Iterable[Dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            # Read one JSONL record per line.
            for line in f:
                line = line.strip()
                # Skip empty lines.
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                # Skip malformed JSON lines.
                except json.JSONDecodeError:
                    continue
                # Yield only dict-shaped records.
                if isinstance(obj, dict):
                    yield obj
    # Return silently when the file is not created yet.
    except FileNotFoundError:
        return


# Append one dictionary object as a single JSONL line.
def _append_jsonl(path: str, obj: Dict) -> None:
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


# Collect all saved URLs from a JSONL dictionary file.
def _get_saved_urls(path: str) -> set[str]:
    saved = set()
    # Walk every record and capture non-empty URL fields.
    for obj in _iter_jsonl(path):
        url = obj.get("url")
        if isinstance(url, str) and url:
            saved.add(url)
    return saved


# Capture summary details for dictionary update runs.
@dataclass(frozen=True)
class UpdateResult:
    wrote: int
    last_id_before: int
    last_id_after: int
    stopped_reason: str


# Clean Handspeak page titles into normalized word titles.
def _clean_handspeak_title(raw_title: str) -> str:
    title = (raw_title or "").strip()

    # Keep only the left side when dot separators are present.
    if "•" in title:
        title = title.split("•", 1)[0].strip()

    # Remove common title suffix separators.
    for sep in ("|", " - "):
        if sep in title:
            title = title.split(sep, 1)[0].strip()

    lowered = title.lower()
    suffix = "asl dictionary"
    # Trim the trailing 'asl dictionary' suffix when present.
    if lowered.endswith(suffix):
        title = title[: -len(suffix)].strip(" -|•\t")

    return title


# Return the highest saved Handspeak entry id in local storage.
def get_last_saved_handspeak_id(path: str = HAND_SPEAK_DICT_PATH) -> int:
    max_id = 0
    # Read each record and track the largest valid numeric id.
    for obj in _iter_jsonl(path):
        try:
            max_id = max(max_id, int(obj.get("id", 0)))
        # Ignore records without a valid id value.
        except (TypeError, ValueError):
            continue
    return max_id


# Parse a Handspeak HTML page into a dictionary record.
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


# Fetch one Handspeak record by id and return parsed data + status.
def _fetch_handspeak_entry(session: requests.Session, entry_id: int) -> Tuple[Optional[Dict], int]:
    url = HAND_SPEAK_URL_TEMPLATE.format(id=entry_id)
    resp = session.get(url, headers=HEADERS, timeout=20)

    # Treat 404 as a non-fatal missing entry.
    if resp.status_code == 404:
        return None, 404

    resp.raise_for_status()
    return _parse_handspeak_entry(resp.text, entry_id=entry_id, url=url), resp.status_code


# Incrementally update the local Handspeak dictionary file.
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
        # Continue fetching until a stop condition is reached.
        while True:
            # Stop after writing the caller-requested max number of new rows.
            if max_new is not None and wrote >= max_new:
                return UpdateResult(wrote, last_before, last_after, f"reached max_new={max_new}")

            try:
                entry, status = _fetch_handspeak_entry(session, entry_id)
            # Stop and return context if the request layer fails.
            except requests.RequestException as e:
                return UpdateResult(wrote, last_before, last_after, f"request error: {e}")

            # Count missing entries and stop after too many consecutive 404s.
            if status == 404 or entry is None:
                consecutive_404 += 1
                if consecutive_404 >= max_consecutive_404:
                    return UpdateResult(
                        wrote,
                        last_before,
                        last_after,
                        f"hit {max_consecutive_404} consecutive 404s",
                    )
            else:
                # Reset missing counter and save successful entries.
                consecutive_404 = 0
                _append_jsonl(output_path, entry)
                wrote += 1
                last_after = entry_id

            entry_id += 1
            time.sleep(request_delay_seconds)


# Return True when a URL belongs to lifeprint.com.
def _is_lifeprint_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("lifeprint.com")


# Convert a possibly relative href into a normalized absolute URL.
def _normalize_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    abs_url = urljoin(base, href).split("#", 1)[0]
    return abs_url


# Extract candidate word links from a Lifeprint index HTML page.
def _extract_lifeprint_word_links(html: str, base_url: str) -> list[Dict]:
    soup = BeautifulSoup(html, "html.parser")
    out: list[Dict] = []

    # Inspect every anchor tag that has an href.
    for a in soup.find_all("a", href=True):
        text = a.get_text(strip=True)
        # Skip anchors without visible text.
        if not text:
            continue

        href = a.get("href", "")
        url = _normalize_url(base_url, href)
        # Keep only valid Lifeprint URLs.
        if not url or not _is_lifeprint_url(url):
            continue

        # Keep only links under the ASL section path.
        if "/asl101/" not in url:
            continue

        out.append({"url": url, "title": text})

    return out


# Crawl Lifeprint letter index pages and save unseen word links.
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
        # Visit each alphabetical index page on Lifeprint.
        for letter in string.ascii_lowercase:
            index_url = letter_url_template.format(letter=letter)

            try:
                resp = session.get(index_url, headers=HEADERS, timeout=20)
                # Skip letters that do not have an index page.
                if resp.status_code == 404:
                    continue
                resp.raise_for_status()
            # Continue to the next letter on network/HTTP errors.
            except requests.RequestException:
                continue

            # Process each extracted dictionary link from this letter page.
            for rec in _extract_lifeprint_word_links(resp.text, base_url=index_url):
                # Skip URLs already saved in output.
                if rec["url"] in saved_urls:
                    skipped += 1
                    continue
                _append_jsonl(output_path, rec)
                saved_urls.add(rec["url"])
                wrote += 1

            time.sleep(request_delay_seconds)

    return {"wrote": wrote, "skipped_existing": skipped, "total_saved": len(saved_urls)}


# Load valid dictionary entries from JSONL into a list.
def load_dictionary_entries(path: str) -> list[Dict]:
    entries: list[Dict] = []
    # Keep only records that include non-empty title and URL strings.
    for obj in _iter_jsonl(path):
        title = obj.get("title")
        url = obj.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            entries.append(obj)
    return entries


# Return URLs used in history during the last N days.
def urls_used_within_days(history: Iterable[Dict], days: int = 365) -> set[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used: set[str] = set()

    # Evaluate each history entry for validity and age cutoff.
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
        # Assume UTC for timestamps that are timezone-naive.
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when >= cutoff:
            used.add(url)

    return used


# Choose a random dictionary entry whose URL is not excluded.
def choose_random_unused(entries: list[Dict], *, exclude_urls: set[str]) -> Optional[Dict]:
    import random

    candidates = [e for e in entries if isinstance(e.get("url"), str) and e["url"] not in exclude_urls]
    # Return no result when every candidate URL is excluded.
    if not candidates:
        return None
    return random.choice(candidates)


# Build the daily word message and return entries to record.
def build_daily_word_post(
    *,
    handspeak_entries: list[Dict],
    lifeprint_entries: list[Dict],
    exclude_urls: set[str],
    history: Optional[Iterable[Dict]] = None,
) -> Tuple[str, Iterable[Dict]]:
    # Prevent duplicate daily posts when today's entry already exists.
    if history and has_posted_today(history):
        return "Daily word already posted today.", []

    combined = handspeak_entries + lifeprint_entries
    anchor = choose_random_unused(combined, exclude_urls=exclude_urls)

    # Return a fallback message if no eligible entry is available.
    if anchor is None:
        return (
            "Daily word: no eligible entries found "
            "(dictionaries empty or all entries recently used).",
            [],
        )

    word = anchor["title"]
    results = search_all_providers(word)

    # Return a minimal message when no providers return results.
    if not results["exact"] and not results["partial"]:
        return f"Daily word: **{word}** (no additional sources found).", []

    lines = [
        "**Daily sign practice word:**",
        f"**{word.upper()}**",
    ]

    used: list[Dict] = []

    # Add exact matches to the message and used-record payload.
    for entry in results["exact"]:
        lines.append(f"- {entry['provider'].title()}: {entry['title']} — {entry['url']}")
        used.append(
            {
                "source": entry["provider"],
                "title": entry["title"],
                "url": entry["url"],
            }
        )

    # Mention partial match count without listing all partial entries.
    if results["partial"]:
        lines.append(f"_Additional matches available in {len(results['partial'])} other entries._")

    return "\n".join(lines), used


# Search local dictionaries and return a compact readable text result.
def perform_web_search(query: str) -> str:
    results = []
    q = query.strip().lower()
    # Require a non-empty query.
    if not q:
        return "Please provide a search term."

    # Scan Lifeprint matches first and cap local result growth early.
    for obj in _iter_jsonl(LIFEPRINT_DICT_PATH):
        title = str(obj.get("title", "")).strip()
        url = str(obj.get("url", "")).strip()
        if title and url and q in title.lower():
            results.append((title, url))
            if len(results) >= 5:
                break

    # Scan Handspeak and continue until the wider cap is hit.
    for obj in _iter_jsonl(HAND_SPEAK_DICT_PATH):
        title = str(obj.get("title", "")).strip()
        url = str(obj.get("url", "")).strip()
        if title and url and q in title.lower():
            results.append((title, url))
            if len(results) >= 10:
                break

    # Return no-match text when nothing qualified.
    if not results:
        return f"No local dictionary matches found for: {query!r}"

    lines = [f"Results for {query!r}:"]
    # Emit at most eight lines for readability.
    for title, url in results[:8]:
        lines.append(f"- {title}: {url}")
    return "\n".join(lines)


# Search SigningSavvy for one matching sign page.
def search_signingsavvy(word):
    url = f"https://www.signingsavvy.com/search/{word}"
    r = requests.get(url, timeout=10)

    # Return nothing when the provider request fails.
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("a[href^='/sign/']")
    # Return nothing when no result link is present.
    if not link:
        return None

    full_url = "https://www.signingsavvy.com" + link["href"]

    return {
        "source": "signingsavvy",
        "url": full_url,
    }


# Search SpreadTheSign for one matching sign page.
def search_spreadthesign(word):
    url = f"https://www.spreadthesign.com/en.us/search/?q={word}"
    r = requests.get(url, timeout=10)

    # Return nothing when the provider request fails.
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    link = soup.select_one("a.search-result")

    # Return nothing when no result card was found.
    if not link:
        return None

    return {
        "source": "spreadthesign",
        "url": "https://www.spreadthesign.com" + link["href"],
    }


# Search SignASL for a direct sign page.
def search_signasl(word):
    url = f"https://www.signasl.org/sign/{word}"
    r = requests.get(url, timeout=10)

    # Return nothing when the provider request fails.
    if r.status_code != 200:
        return None

    soup = BeautifulSoup(r.text, "html.parser")

    # Return nothing for SignASL soft-not-found pages.
    if "No sign found" in soup.text:
        return None

    return {
        "source": "signasl",
        "url": url,
    }


# Normalize lookup input for consistent dictionary/provider matching.
def _normalize_word(word: str) -> str:
    return word.strip().lower().strip(string.punctuation)


# Search local dictionaries for an exact normalized title match.
def lookup_local_word(word: str) -> Optional[Dict]:
    q = _normalize_word(word)

    # Check Lifeprint local dictionary first.
    for obj in _iter_jsonl(LIFEPRINT_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "lifeprint"}

    # Check Handspeak local dictionary second.
    for obj in _iter_jsonl(HAND_SPEAK_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "handspeak"}

    # Check previously saved on-demand words last.
    for obj in _iter_jsonl(ON_DEMAND_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return obj

    return None


# Search all local and live providers for exact and partial matches.
def search_all_providers(word: str) -> Dict[str, list[Dict]]:
    q = _normalize_word(word)

    results_exact: list[Dict] = []
    results_partial: list[Dict] = []
    seen_urls: set[str] = set()

    # Iterate through each local dictionary file/provider pair.
    for path, provider in (
        (LIFEPRINT_DICT_PATH, "lifeprint"),
        (HAND_SPEAK_DICT_PATH, "handspeak"),
        (ON_DEMAND_DICT_PATH, "ondemand"),
    ):
        # Evaluate every local entry for exact/partial matching.
        for obj in _iter_jsonl(path):
            title = str(obj.get("title", "")).strip()
            url = str(obj.get("url", "")).strip()
            if not title or not url or url in seen_urls:
                continue

            title_l = title.lower()
            if q == title_l:
                results_exact.append(
                    {
                        "provider": provider,
                        "title": title,
                        "url": url,
                    }
                )
                seen_urls.add(url)
            elif q in title_l:
                results_partial.append(
                    {
                        "provider": provider,
                        "title": title,
                        "url": url,
                    }
                )
                seen_urls.add(url)

    # Query all live web providers as a fallback/expansion step.
    for provider_func in SEARCH_PROVIDERS:
        try:
            result = provider_func(q)
        except requests.RequestException:
            continue

        # Skip providers that return no usable payload.
        if not result:
            continue

        url = result.get("url")
        # Skip duplicate or empty URLs from live providers.
        if not url or url in seen_urls:
            continue

        results_exact.append(
            {
                "provider": result["source"],
                "title": q,
                "url": url,
            }
        )
        seen_urls.add(url)

        time.sleep(REQUEST_DELAY_SECONDS)

    return {
        "exact": results_exact,
        "partial": results_partial,
    }


# Keep the ordered list of live provider functions.
SEARCH_PROVIDERS = [
    search_signingsavvy,
    search_spreadthesign,
    search_signasl,
]


# Save a newly discovered web result into the on-demand dictionary.
def save_ondemand_word(word: str, result: Dict) -> Dict:
    record = {
        "title": word,
        "url": result["url"],
        "source": result["source"],
        "added": datetime.now(timezone.utc).isoformat(),
    }

    _append_jsonl(ON_DEMAND_DICT_PATH, record)
    return record


# Try local lookup first, then web fetch and save if missing.
def lookup_or_fetch_word(word: str) -> Tuple[Optional[Dict], bool]:
    normalized = _normalize_word(word)
    # Return quickly when the normalized query is empty.
    if not normalized:
        return None, False

    local = lookup_local_word(normalized)
    # Return local hit without writing new on-demand data.
    if local:
        return local, False

    # Query live providers until one returns a result.
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


# Return True when history already contains an entry from today (UTC).
def has_posted_today(history: Iterable[Dict]) -> bool:
    today = datetime.now(timezone.utc).date()

    # Check each timestamp in history against today's UTC date.
    for item in history:
        ts = item.get("ts")
        if not ts:
            continue
        try:
            when = datetime.fromisoformat(ts)
        except ValueError:
            continue
        # Assume UTC for naive datetimes stored in history.
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        if when.date() == today:
            return True

    return False
