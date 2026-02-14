from __future__ import annotations

import random
from datetime import datetime, timezone, timedelta
from typing import Dict, Iterable, Optional, Tuple, List, Set

# We expect search_all_providers to exist in your lookup module.
# If it's still in web_search.py for now, import path may differ.
try:
    from .lookup import search_all_providers
except Exception:  # pragma: no cover
    search_all_providers = None


def has_posted_today(history: Iterable[Dict]) -> bool:
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


def urls_used_within_days(history: Iterable[Dict], days: int = 365) -> Set[str]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    used: Set[str] = set()

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


def choose_random_unused(entries: List[Dict], *, exclude_urls: Set[str]) -> Optional[Dict]:
    candidates = [e for e in entries if isinstance(e.get("url"), str) and e["url"] and e["url"] not in exclude_urls]
    if not candidates:
        return None
    return random.choice(candidates)


async def build_daily_word_post(
    *,
    handspeak_entries: List[Dict],
    lifeprint_entries: List[Dict],
    exclude_urls: Set[str],
    history: Optional[Iterable[Dict]] = None,
) -> Tuple[str, List[Dict]]:
    if history and has_posted_today(history):
        return "Daily word already posted today.", []

    combined = list(handspeak_entries) + list(lifeprint_entries)
    anchor = choose_random_unused(combined, exclude_urls=exclude_urls)

    if anchor is None:
        return (
            "Daily word: no eligible entries found "
            "(dictionaries empty or all entries recently used).",
            [],
        )

    word = str(anchor.get("title") or "").strip() or "UNKNOWN"

    if search_all_providers is None:
        # Fallback message if your lookup split isn't finished yet
        return f"Daily sign practice word: **{word.upper()}**", [
            {"source": anchor.get("source", "unknown"), "title": word, "url": anchor.get("url", "")}
        ]

    results = await search_all_providers(word)

    # Expecting {"exact": [...], "partial": [...]}
    exact = results.get("exact") or []
    partial = results.get("partial") or []

    if not exact and not partial:
        return f"Daily word: **{word.upper()}** (no additional sources found).", []

    lines = [
        "**Daily sign practice word:**",
        f"**{word.upper()}**",
    ]

    used: List[Dict] = []
    for entry in exact:
        # entry keys: provider/title/url per your earlier format
        provider = entry.get("provider", "unknown")
        title = entry.get("title", word)
        url = entry.get("url", "")
        lines.append(f"- {provider}: {title} — {url}")
        used.append({"source": provider, "title": title, "url": url})

    if partial:
        lines.append(f"_Additional matches available in {len(partial)} other entries._")

    return "\n".join(lines), used
