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
            results, _added = await web_search.lookup_or_fetch_word(word)

            if not results:
                await ctx.send(embed=brand_embed(title="No Results", description=f"❌ No ASL sign found for **{word}**.", ctx=ctx))
                return

            if len(results) <= 5:
                embed = brand_embed(
                    title=f"Results for: {word.strip().lower()}",
                    description="Here are the best matches I found:",
                    ctx=ctx,
                )
                for entry in results:
                    embed.add_field(name="", value=self._format_result_line(entry, fallback_word=word.strip().lower()), inline=False)
                await ctx.send(embed=embed)
                return

            # Paginate
            pages: list[discord.Embed] = []
            per_page = 5
            total = len(results)

            for i in range(0, total, per_page):
                chunk_results = results[i:i + per_page]
                page_num = (i // per_page) + 1
                max_pages = (total + per_page - 1) // per_page

                embed = brand_embed(
                    title=f"Results for: {word.strip().lower()}",
                    description=f"Showing results **{i + 1}-{min(i + per_page, total)}** of **{total}**",
                    ctx=ctx,
                )
                embed.set_footer(text=f"ASL Bot • Page {page_num}/{max_pages}")

                for entry in chunk_results:
                    embed.add_field(name="", value=self._format_result_line(entry, fallback_word=word.strip().lower()), inline=False)

                pages.append(embed)

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
