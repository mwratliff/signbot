import json
import asyncio
import aiohttp
import string
import time
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, Iterable, Optional, Tuple
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

# Define JSONL dictionary storage paths used by the bot.
HAND_SPEAK_DICT_PATH = "../dictionaries/handspeak-dict.txt"
LIFEPRINT_DICT_PATH = "../dictionaries/lifeprint-dict.txt"
ON_DEMAND_DICT_PATH = "../dictionaries/ondemand-dict.txt"

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

# =============================
# Provider ordering
# =============================
# Desired order:
# LifePrint, HandSpeak, SigningSavvy, SignASL, ASLCore, SpreadTheSign
# YouTube is NOT in your list, but you asked for it "near the top" ONLY when no local match exists,
# so we slot it right after LifePrint when it is included.
PROVIDER_ORDER = [
    "lifeprint",
    "lifeprint_youtube",
    "handspeak",
    "signingsavvy",
    "signasl",
    "aslcore",
    "spreadthesign",
]

_PROVIDER_RANK = {name: idx for idx, name in enumerate(PROVIDER_ORDER)}


def _provider_sort_key(provider: str) -> tuple[int, str]:
    p = (provider or "").lower()
    return (_PROVIDER_RANK.get(p, 999), p)


# =============================
# Single Logging Function (ONLY)
# =============================

DEBUG_LOG_DIR = os.path.join(tempfile.gettempdir(), "asl_provider_logs")
os.makedirs(DEBUG_LOG_DIR, exist_ok=True)


def _log_provider(provider: str, message: str) -> None:
    """
    Writes provider debug info to a temp log file:
      <temp>/asl_provider_logs/debug-<provider>.log
    """
    filename = os.path.join(DEBUG_LOG_DIR, f"debug-{provider}.log")
    timestamp = datetime.now(timezone.utc).isoformat()
    with open(filename, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


# =============================
# JSONL Helpers
# =============================

def _iter_jsonl(path: str) -> Iterable[Dict]:
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
    """
    Append one dictionary object as a single JSONL line.
    Forces a consistent key order for readability:
      title, url, then any remaining keys alphabetically.
    """
    if not isinstance(obj, dict):
        return

    ordered: Dict = {}
    if "title" in obj:
        ordered["title"] = obj.get("title")
    if "url" in obj:
        ordered["url"] = obj.get("url")

    for k in sorted(obj.keys()):
        if k in ("title", "url"):
            continue
        ordered[k] = obj.get(k)

    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(ordered, ensure_ascii=False) + "\n")


def _get_saved_urls(path: str) -> set[str]:
    saved = set()
    for obj in _iter_jsonl(path):
        url = obj.get("url")
        if isinstance(url, str) and url:
            saved.add(url)
    return saved


# =============================
# Handspeak Local Dictionary Builder
# (You said you are intentionally ignoring live Handspeak searches)
# =============================

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
                    return UpdateResult(
                        wrote,
                        last_before,
                        last_after,
                        f"hit {max_consecutive_404} consecutive 404s",
                    )
            else:
                consecutive_404 = 0
                _append_jsonl(output_path, entry)
                wrote += 1
                last_after = entry_id

            entry_id += 1
            time.sleep(request_delay_seconds)


# =============================
# Lifeprint Dictionary Builder
# =============================

def _is_lifeprint_url(url: str) -> bool:
    try:
        host = urlparse(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("lifeprint.com")


def _normalize_url(base: str, href: str) -> Optional[str]:
    if not href:
        return None
    return urljoin(base, href).split("#", 1)[0]


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

        # Keep the "readable" key order when writing (append function handles ordering)
        out.append({"title": text, "url": url})

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


# =============================
# Dictionary Loading / Daily Helpers
# =============================

def load_dictionary_entries(path: str) -> list[Dict]:
    entries: list[Dict] = []
    for obj in _iter_jsonl(path):
        title = obj.get("title")
        url = obj.get("url")
        if isinstance(title, str) and isinstance(url, str) and title and url:
            entries.append(obj)
    return entries


def choose_random_unused(entries: list[Dict], *, exclude_urls: set[str]) -> Optional[Dict]:
    import random
    candidates = [e for e in entries if isinstance(e.get("url"), str) and e["url"] not in exclude_urls]
    if not candidates:
        return None
    return random.choice(candidates)



def perform_web_search(query: str) -> str:
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


# =============================
# Live Provider Searches (NO Handspeak live)
# =============================

async def search_aslcore(session, word: str):
    provider = "aslcore"
    search_url = f"https://aslcore.org/search/?query={word}"

    try:
        async with session.get(search_url) as resp:
            text = await resp.text()
            _log_provider(provider, f"URL={search_url} status={resp.status} bytes={len(text)}")

            if resp.status != 200:
                _log_provider(provider, "Non-200 response -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            if "No Entries Found" in text:
                _log_provider(provider, "Detected 'No Entries Found' -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            _log_provider(provider, "Results detected -> returning search URL")
            return {"provider": provider, "word": word, "url": search_url, "found": True}

    except Exception as e:
        _log_provider(provider, f"ERROR: {e}")
        return {"provider": provider, "word": word, "url": None, "found": False}


import re
import json as _json


def _normalize_title_for_exact_match(s: str) -> str:
    return " ".join((s or "").strip().lower().split())


def _extract_youtube_video_renderers(obj):
    if isinstance(obj, dict):
        if "videoRenderer" in obj and isinstance(obj["videoRenderer"], dict):
            yield obj["videoRenderer"]
        for v in obj.values():
            yield from _extract_youtube_video_renderers(v)
    elif isinstance(obj, list):
        for item in obj:
            yield from _extract_youtube_video_renderers(item)


async def search_lifeprint_youtube(session, word: str):
    provider = "lifeprint_youtube"
    query = (word or "").strip()
    if not query:
        return {"provider": provider, "word": word, "url": None, "found": False}

    search_url = f"https://www.youtube.com/@aslu/search?query={query}"

    try:
        async with session.get(search_url) as resp:
            text = await resp.text()
            _log_provider(provider, f"URL={search_url} status={resp.status} bytes={len(text)}")

            if resp.status != 200:
                _log_provider(provider, "Non-200 -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            m = re.search(r"var ytInitialData = (\{.*?\});", text, re.DOTALL)
            if not m:
                m = re.search(r"ytInitialData\s*=\s*(\{.*?\});", text, re.DOTALL)

            if not m:
                _log_provider(provider, "ytInitialData not found -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            try:
                data = _json.loads(m.group(1))
            except Exception as e:
                _log_provider(provider, f"Failed to parse ytInitialData JSON -> {e}")
                return {"provider": provider, "word": word, "url": None, "found": False}

            target = _normalize_title_for_exact_match(query)

            for vr in _extract_youtube_video_renderers(data):
                title_runs = (((vr.get("title") or {}).get("runs")) or [])
                title = "".join(r.get("text", "") for r in title_runs).strip()
                if not title:
                    continue

                if _normalize_title_for_exact_match(title) == target:
                    video_id = vr.get("videoId")
                    if not video_id:
                        continue

                    video_url = f"https://www.youtube.com/watch?v={video_id}"
                    _log_provider(provider, f"EXACT match -> {title} -> {video_url}")
                    return {"provider": provider, "word": word, "url": video_url, "found": True}

            _log_provider(provider, "No EXACT title matches found")
            return {"provider": provider, "word": word, "url": None, "found": False}

    except Exception as e:
        _log_provider(provider, f"ERROR: {e}")
        return {"provider": provider, "word": word, "url": None, "found": False}


async def search_signingsavvy(session, word: str):
    provider = "signingsavvy"
    url = f"https://www.signingsavvy.com/search/{word}"

    try:
        async with session.get(url) as resp:
            text = await resp.text()
            _log_provider(provider, f"URL={url} status={resp.status} bytes={len(text)}")

            if resp.status != 200:
                _log_provider(provider, "Non-200 -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            soup = BeautifulSoup(text, "html.parser")
            link = soup.select_one("a[href^='/sign/']")

            if not link:
                _log_provider(provider, "No /sign/ result link found -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            full_url = "https://www.signingsavvy.com" + link["href"]
            _log_provider(provider, f"Found result link: {full_url}")
            return {"provider": provider, "word": word, "url": full_url, "found": True}

    except Exception as e:
        _log_provider(provider, f"ERROR: {e}")
        return {"provider": provider, "word": word, "url": None, "found": False}


async def search_spreadthesign(session, word: str):
    provider = "spreadthesign"
    search_url = f"https://www.spreadthesign.com/en.us/search/?q={word}"

    try:
        async with session.get(search_url) as resp:
            text = await resp.text()
            _log_provider(provider, f"URL={search_url} status={resp.status} bytes={len(text)}")

            if resp.status != 200:
                _log_provider(provider, "Non-200 -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            soup = BeautifulSoup(text, "html.parser")
            page_text = soup.get_text(" ", strip=True).lower()

            no_result_phrases = (
                "no results",
                "no result",
                "0 results",
                "nothing found",
                "no matches",
                "we couldn't find",
                "we could not find",
                "try another search",
            )
            if any(p in page_text for p in no_result_phrases):
                _log_provider(provider, "Detected no-result phrase -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            candidate_selectors = [
                "a.search-result",
                "a[href*='/dictionary/']",
                "a[href*='/sign/']",
                "a[href*='/word/']",
                "a[href*='/translation/']",
                "a[href*='/en.us/']",
            ]

            found_links = []
            for sel in candidate_selectors:
                found_links = soup.select(sel)
                if found_links:
                    _log_provider(provider, f"Found links via selector '{sel}': {len(found_links)}")
                    break

            if found_links:
                return {"provider": provider, "word": word, "url": search_url, "found": True}

            _log_provider(provider, "No result markers/links detected -> no result")
            return {"provider": provider, "word": word, "url": None, "found": False}

    except Exception as e:
        _log_provider(provider, f"ERROR: {e}")
        return {"provider": provider, "word": word, "url": None, "found": False}


async def search_signasl(session, word: str):
    provider = "signasl"
    search_url = f"https://www.signasl.org/sign/{word}"

    try:
        async with session.get(search_url) as resp:
            text = await resp.text()
            _log_provider(provider, f"URL={search_url} status={resp.status} bytes={len(text)}")

            if resp.status != 200:
                _log_provider(provider, "Non-200 -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            soup = BeautifulSoup(text, "html.parser")
            page_text = soup.get_text(" ", strip=True).lower()

            no_result_phrases = (
                "no sign found",
                "sign not found",
                "no results",
                "no matches",
                "does not exist",
                "couldn't find",
                "could not find",
            )
            if any(p in page_text for p in no_result_phrases):
                _log_provider(provider, "Detected no-result phrase -> no result")
                return {"provider": provider, "word": word, "url": None, "found": False}

            og_video = soup.find("meta", property="og:video") or soup.find("meta", property="og:video:url")
            if og_video and og_video.get("content"):
                _log_provider(provider, "Found og:video meta -> result")
                return {"provider": provider, "word": word, "url": search_url, "found": True}

            if soup.find("video") or soup.find("source"):
                _log_provider(provider, "Found <video>/<source> tag -> result")
                return {"provider": provider, "word": word, "url": search_url, "found": True}

            iframe = soup.find("iframe")
            if iframe and (iframe.get("src") or ""):
                _log_provider(provider, "Found <iframe> -> result")
                return {"provider": provider, "word": word, "url": search_url, "found": True}

            _log_provider(provider, "No media/player markers detected -> no result")
            return {"provider": provider, "word": word, "url": None, "found": False}

    except Exception as e:
        _log_provider(provider, f"ERROR: {e}")
        return {"provider": provider, "word": word, "url": None, "found": False}


# =============================
# Core Lookup Logic
# =============================

def _normalize_word(word: str) -> str:
    return word.strip().lower().strip(string.punctuation)


def lookup_local_word(word: str) -> Optional[Dict]:
    q = _normalize_word(word)

    for obj in _iter_jsonl(LIFEPRINT_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "lifeprint"}

    for obj in _iter_jsonl(HAND_SPEAK_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return {**obj, "source": "handspeak"}

    for obj in _iter_jsonl(ON_DEMAND_DICT_PATH):
        title = str(obj.get("title", "")).lower()
        if q == title:
            return obj

    return None


async def search_all_providers(word: str) -> Dict[str, list[Dict]]:
    q = _normalize_word(word)

    results_exact: list[Dict] = []
    results_partial: list[Dict] = []
    seen_urls: set[str] = set()

    # 1) LOCAL DICTIONARIES
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
                results_exact.append({"provider": provider, "title": title, "url": url})
                seen_urls.add(url)
            elif q in title_l:
                results_partial.append({"provider": provider, "title": title, "url": url})
                seen_urls.add(url)

    # ✅ Only search LifePrint YouTube when there is NO local LifePrint exact match.
    has_lifeprint_local_exact = any(
        e.get("provider") == "lifeprint" for e in results_exact
    )

    # 2) LIVE PROVIDERS
    async with aiohttp.ClientSession(headers=HEADERS) as session:
        coros = [
            search_signingsavvy(session, q),
            search_signasl(session, q),
            search_aslcore(session, q),
            search_spreadthesign(session, q),
        ]

        # Only include YouTube if no local LifePrint match.
        if not has_lifeprint_local_exact:
            coros.append(search_lifeprint_youtube(session, q))

        live_results = await asyncio.gather(*coros)

        for result in live_results:
            if not result or not result.get("found"):
                continue

            url = result.get("url")
            if not url or url in seen_urls:
                continue

            results_exact.append({"provider": result["provider"], "title": q, "url": url})
            seen_urls.add(url)

    # ✅ Enforce the display order you want
    results_exact.sort(key=lambda e: _provider_sort_key(e.get("provider", "")))
    results_partial.sort(key=lambda e: _provider_sort_key(e.get("provider", "")))

    return {"exact": results_exact, "partial": results_partial}


async def lookup_or_fetch_word(word: str) -> Tuple[list[Dict], bool]:
    """
    Used by !sign command.
    Powered by search_all_providers so ALL providers return results.
    """
    normalized = _normalize_word(word)
    if not normalized:
        return [], False

    results_dict = await search_all_providers(normalized)

    results: list[Dict] = []
    seen_urls: set[str] = set()

    for group in ("exact", "partial"):
        for entry in results_dict.get(group, []):
            url = entry.get("url")
            if not url or url in seen_urls:
                continue

            results.append(
                {
                    "source": entry["provider"],
                    "url": url,
                    "title": entry.get("title", normalized),
                }
            )
            seen_urls.add(url)

    added_any = False
    return results, added_any



