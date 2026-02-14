from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from discord.ext import commands
import discord

import web_search
from .shared import log_error

from paths import DAILY_CONFIG_PATH, DAILY_HISTORY_PATH
DAILY_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)




def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_json(path: Path, data: dict) -> None:
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def get_daily_cfg(guild_id: int) -> dict:
    cfg = load_json(DAILY_CONFIG_PATH)
    if str(guild_id) not in cfg:
        cfg[str(guild_id)] = {"enabled": False, "channel_id": None}
    return cfg[str(guild_id)]


def save_daily_cfg(guild_id: int, data: dict) -> None:
    cfg = load_json(DAILY_CONFIG_PATH)
    cfg[str(guild_id)] = data
    save_json(DAILY_CONFIG_PATH, cfg)


def get_daily_history(guild_id: int) -> list[dict]:
    hist = load_json(DAILY_HISTORY_PATH)
    return hist.setdefault(str(guild_id), [])


def append_daily_history(guild_id: int, items: Iterable[dict]) -> None:
    hist = load_json(DAILY_HISTORY_PATH)
    hist.setdefault(str(guild_id), []).extend(items)
    save_json(DAILY_HISTORY_PATH, hist)


async def post_daily_word(channel: discord.TextChannel, guild_id: int) -> bool:
    history = get_daily_history(guild_id)

    if web_search.has_posted_today(history):
        return False

    exclude_urls = web_search.urls_used_within_days(history, days=365)

    handspeak_entries = web_search.load_dictionary_entries(web_search.HAND_SPEAK_DICT_PATH)
    lifeprint_entries = web_search.load_dictionary_entries(web_search.LIFEPRINT_DICT_PATH)

    # build_daily_word_post is async in your refactor
    message, used = await web_search.build_daily_word_post(
        handspeak_entries=handspeak_entries,
        lifeprint_entries=lifeprint_entries,
        exclude_urls=exclude_urls,
        history=history,
    )

    if not used:
        return False

    await channel.send(message)

    now = datetime.now(timezone.utc).isoformat()
    history_items = [{"ts": now, **u} for u in used]
    append_daily_history(guild_id, history_items)
    return True


class DailyAdmin(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="daily-status", description="Show daily word status for this server")
    async def daily_status(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        cfg = get_daily_cfg(ctx.guild.id)
        history = get_daily_history(ctx.guild.id)

        channel = None
        if cfg.get("channel_id"):
            channel = ctx.guild.get_channel(cfg["channel_id"])

        posted_today = web_search.has_posted_today(history)

        lines = [
            "**Daily Word Status**",
            f"- Enabled: **{cfg.get('enabled')}**",
            f"- Posted today: **{posted_today}**",
            f"- Channel: {channel.mention if channel else '(not set)'}",
        ]
        await ctx.send("\n".join(lines))

    @commands.hybrid_command(
        name="daily-enable",
        description="Enable the daily word (posts immediately if not posted today)",
    )
    @commands.has_guild_permissions(administrator=True)
    async def daily_enable(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        cfg = get_daily_cfg(ctx.guild.id)

        if not cfg.get("channel_id"):
            await ctx.send("❌ No daily channel set. Add a /daily-set-channel command later, or set it in the JSON.")
            return

        cfg["enabled"] = True
        save_daily_cfg(ctx.guild.id, cfg)

        channel = ctx.guild.get_channel(cfg["channel_id"])
        if not channel:
            await ctx.send("❌ Configured daily channel no longer exists.")
            return

        try:
            posted = await post_daily_word(channel, ctx.guild.id)
            await ctx.send("✅ Daily word enabled and posted for today." if posted else "✅ Daily word enabled. Today’s word was already posted.")
        except Exception:
            log_error()
            await ctx.send("⚠️ Failed while trying to post the daily word.")

    @commands.hybrid_command(name="daily-disable", description="Disable the daily word for this server")
    @commands.has_guild_permissions(administrator=True)
    async def daily_disable(self, ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used in a server.")
            return

        cfg = get_daily_cfg(ctx.guild.id)
        cfg["enabled"] = False
        save_daily_cfg(ctx.guild.id, cfg)
        await ctx.send("🛑 Daily word has been disabled.")


async def setup(bot: commands.Bot):
    await bot.add_cog(DailyAdmin(bot))
