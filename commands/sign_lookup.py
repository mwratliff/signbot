from __future__ import annotations

import discord
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
}


class SignLookup(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def _format_result_line(self, entry: dict, fallback_word: str) -> str:
        raw_provider = entry.get("source", "unknown")
        provider = PROVIDER_DISPLAY_NAMES.get(str(raw_provider).lower(), str(raw_provider))

        title = entry.get("title") or fallback_word
        title = str(title).strip()
        url = str(entry.get("url", "")).strip()

        if not url:
            return f"**{provider}:** {title}"

        return f"[{provider}: {title}]({url})"

    @commands.hybrid_command(name="sign", description="Search ASL dictionaries for a word")
    async def sign(self, ctx: commands.Context, *, word: str):
        # Slash will require "word" if your signature is word: str,
        # but this keeps the friendly embed for prefix edge-cases.
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
                value="Try simple base words (no punctuation), e.g. `mother`, `hello`, `learn`.",
                inline=False,
            )
            await ctx.send(embed=embed)
            return

        try:
            query = word.strip().lower()
            results, _added = await web_search.lookup_or_fetch_word(word)

            if not results:
                await ctx.send(
                    embed=brand_embed(
                        title="No Results",
                        description=f"❌ No ASL sign found for **{word}**.",
                        ctx=ctx,
                    )
                )
                return

            # -------------------------------
            # Provider ordering (recommended first)
            # -------------------------------
            PROVIDER_ORDER = [
                "lifeprint",
                "handspeak",
                "signingsavvy",
                "signasl",
                "aslcore",
                "spreadthesign",
                "tachyo",
                "sldictionary"
            ]

            # If your pipeline emits "lifeprint_youtube", group it under LifePrint too
            PROVIDER_ALIASES = {
                "lifeprint_youtube": "lifeprint",
            }

            # How many items to show per provider before truncating
            # (you asked "all at once unless there's more than 3–4")
            MAX_PER_PROVIDER = 4

            # -------------------------------
            # Helpers
            # -------------------------------
            def normalize_source(src: str) -> str:
                s = (src or "").strip().lower()
                return PROVIDER_ALIASES.get(s, s)

            def provider_display(src: str) -> str:
                # Show pretty names from your existing map (lifeprint_youtube -> LifePrint too)
                raw = (src or "").strip().lower()
                if raw in PROVIDER_ALIASES:
                    raw = PROVIDER_ALIASES[raw]
                return PROVIDER_DISPLAY_NAMES.get(raw, src or "Source")

            def link_only(entry: dict) -> str:
                title = (entry.get("title") or query).strip()
                url = str(entry.get("url", "")).strip()
                if url:
                    return f"[{title}]({url})"
                return title

            # -------------------------------
            # Group results by provider
            # -------------------------------
            grouped: dict[str, list[dict]] = {}
            display_name_for: dict[str, str] = {}

            for entry in results:
                raw_source = str(entry.get("source", "unknown"))
                norm = normalize_source(raw_source)
                grouped.setdefault(norm, []).append(entry)
                display_name_for.setdefault(norm, provider_display(raw_source))

            # Sort items within each provider by title for stability (optional)
            for k in grouped.keys():
                grouped[k].sort(key=lambda e: str(e.get("title") or "").lower())

            # Build ordered provider list: recommended first, then anything else
            ordered_sources: list[str] = []
            for p in PROVIDER_ORDER:
                if p in grouped:
                    ordered_sources.append(p)

            extras = sorted([p for p in grouped.keys() if p not in ordered_sources], key=str.lower)
            ordered_sources.extend(extras)

            # Turn each provider into a "card" (field)
            provider_cards: list[tuple[str, str]] = []
            for src in ordered_sources:
                items = grouped[src]
                shown = items[:MAX_PER_PROVIDER]
                more = len(items) - len(shown)

                lines = [f"• {link_only(e)}" for e in shown]
                if more > 0:
                    lines.append(f"• *(+{more} more…)*")

                provider_cards.append((display_name_for.get(src, src), "\n".join(lines) if lines else "—"))

            # -------------------------------
            # Render embeds (2-column layout, paginate by providers)
            # -------------------------------
            # How many provider blocks per page (not results per page)
            PER_PAGE_PROVIDERS = 6  # 6 providers → 3 rows in a 2-col layout

            pages: list[discord.Embed] = []
            total_cards = len(provider_cards)

            for i in range(0, total_cards, PER_PAGE_PROVIDERS):
                chunk = provider_cards[i: i + PER_PAGE_PROVIDERS]
                page_num = (i // PER_PAGE_PROVIDERS) + 1
                max_pages = (total_cards + PER_PAGE_PROVIDERS - 1) // PER_PAGE_PROVIDERS

                embed = brand_embed(
                    title=f"Results for: {query}",
                    description="Grouped by source (recommended sources first).",
                    ctx=ctx,
                )

                # 2-column grid
                cols = 2
                col_count = 0

                for name, value in chunk:
                    embed.add_field(name=name, value=value, inline=True)
                    col_count += 1
                    if col_count == cols:
                        col_count = 0

                # Pad last row if odd number of fields
                if col_count != 0:
                    embed.add_field(name="\u200b", value="\u200b", inline=True)

                if max_pages > 1:
                    embed.set_footer(text=f"ASL Bot • Page {page_num}/{max_pages}")

                pages.append(embed)

            if len(pages) == 1:
                await ctx.send(embed=pages[0])
            else:
                await Paginator.Simple().start(ctx, pages=pages)

        except Exception:
            log_error()
            await ctx.send("⚠️ An unexpected error occurred while searching.")

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
                value="Try simple base words (no punctuation), e.g. `mother`, `hello`, `learn`.",
                inline=False,
            )
            await ctx.send(embed=embed)
        else:
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(SignLookup(bot))
