from __future__ import annotations

from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands

import Paginator
import web_search
from .shared import brand_embed, log_error

PROVIDER_DISPLAY_NAMES = {
    "handspeak": "HandSpeak",
    "lifeprint": "LifePrint",
    "lifeprint_youtube": "LifePrint",
    "signingsavvy": "SigningSavvy",
    "signasl": "SignASL",
    "aslcore": "ASLCore",
    "spreadthesign": "SpreadTheSign",
    "tachyo": "Tachyo",
    "sldictionary": "SL Dictionary",
    "youglish": "YouGlish",
}

PROVIDER_ALIASES = {
    "lifeprint_youtube": "lifeprint",
}

MAX_RESULTS_PER_PROVIDER = 3
MAX_PROVIDER_FIELDS_PER_PAGE = 6


class SignLookup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _normalize_source(self, src: str) -> str:
        s = (src or "").strip().lower()
        return PROVIDER_ALIASES.get(s, s)

    def _provider_display(self, src: str) -> str:
        raw = self._normalize_source(src)
        return PROVIDER_DISPLAY_NAMES.get(raw, src or "Source")

    def _format_result_line(self, entry: dict, fallback_word: str) -> str:
        title = str(entry.get("title") or fallback_word).strip()
        url = str(entry.get("url", "")).strip()

        if not url:
            return title

        return f"[{title}]({url})"

    def _provider_sort_key(self, source: str) -> tuple[int, str]:
        provider_order = getattr(web_search, "PROVIDER_ORDER", [])
        normalized_order = [self._normalize_source(p) for p in provider_order]
        rank = normalized_order.index(source) if source in normalized_order else 999
        return (rank, source)

    def _result_sort_key(self, entry: dict) -> tuple[int, str, str, str]:
        source = self._normalize_source(str(entry.get("source", "unknown")))
        rank, source_name = self._provider_sort_key(source)
        return (
            rank,
            source_name,
            str(entry.get("title") or "").lower(),
            str(entry.get("url") or ""),
        )

    def _build_provider_pages(self, results: list[dict], query: str) -> list[list[tuple[str, str]]]:
        grouped: dict[str, list[dict]] = {}
        display_name_for: dict[str, str] = {}

        for entry in sorted(results, key=self._result_sort_key):
            raw_source = str(entry.get("source", "unknown"))
            source = self._normalize_source(raw_source)
            grouped.setdefault(source, []).append(entry)
            display_name_for.setdefault(source, self._provider_display(raw_source))

        ordered_sources = sorted(grouped.keys(), key=self._provider_sort_key)
        max_provider_results = max(len(items) for items in grouped.values())

        pages: list[list[tuple[str, str]]] = []
        for chunk_start in range(0, max_provider_results, MAX_RESULTS_PER_PROVIDER):
            provider_cards: list[tuple[str, str]] = []

            for source in ordered_sources:
                items = grouped[source]
                chunk = items[chunk_start: chunk_start + MAX_RESULTS_PER_PROVIDER]
                if not chunk:
                    continue

                display_name = display_name_for.get(source, source)
                if chunk_start:
                    display_name = f"{display_name} (more)"

                lines = [
                    f"- {self._format_result_line(entry, query)}"
                    for entry in chunk
                ]
                provider_cards.append((display_name, "\n".join(lines)))

            for i in range(0, len(provider_cards), MAX_PROVIDER_FIELDS_PER_PAGE):
                pages.append(provider_cards[i: i + MAX_PROVIDER_FIELDS_PER_PAGE])

        return pages

    @commands.hybrid_command(name="sign", description="Search ASL dictionaries for a word")
    @app_commands.describe(
        word="Word or phrase to search for",
        strict="Use exact for only the searched term, or broad for related phrase matches",
    )
    async def sign(
        self,
        ctx: commands.Context,
        word: str,
        strict: Literal["broad", "exact"] = "exact",
    ):
        if not word or not word.strip():
            example = "!sign hello" if getattr(ctx, "prefix", None) else "/sign hello"
            embed = brand_embed(
                title="How to Use /sign",
                description="Provide a word to search for ASL sign links.",
                ctx=ctx,
            )
            embed.add_field(name="Example", value=f"`{example}`", inline=False)
            embed.add_field(
                name="Tip",
                value="Use `strict:exact` when you only want exact title matches.",
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        try:
            query = word.strip().lower()
            strict_mode = (strict or "broad").strip().lower()
            if strict_mode not in {"broad", "exact"}:
                strict_mode = "broad"

            results, _added = await web_search.lookup_or_fetch_word(word, strict=strict_mode)

            if not results:
                await ctx.send(
                    embed=brand_embed(
                        title="No Results",
                        description=f"No ASL sign found for **{word}**.",
                        ctx=ctx,
                    )
                )
                return

            page_chunks = self._build_provider_pages(results, query)
            pages: list[discord.Embed] = []
            max_pages = len(page_chunks)

            for page_num, chunk in enumerate(page_chunks, start=1):
                embed = brand_embed(
                    title=f"Results for: {query}",
                    description=f"Grouped by source (recommended sources first). Search mode: **{strict_mode}**.",
                    ctx=ctx,
                )

                for provider, value in chunk:
                    embed.add_field(name=provider, value=value or "-", inline=True)

                if max_pages > 1:
                    embed.set_footer(text=f"ASL Bot - Page {page_num}/{max_pages}")

                pages.append(embed)

            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                await Paginator.Simple().start(ctx, pages=pages)

        except Exception:
            log_error()
            await ctx.send("An unexpected error occurred while searching.")

    @sign.error
    async def sign_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MissingRequiredArgument):
            example = "!sign hello" if getattr(ctx, "prefix", None) else "/sign hello"
            embed = brand_embed(
                title="How to Use !sign",
                description="Provide a word to search for ASL sign links.",
                ctx=ctx,
            )
            embed.add_field(name="Example", value=f"`{example}`", inline=False)
            embed.add_field(
                name="Tip",
                value="Use `strict:exact` when you only want exact title matches.",
                inline=False,
            )
            await ctx.send(embed=embed)
        else:
            raise error


async def setup(bot: commands.Bot):
    await bot.add_cog(SignLookup(bot))
