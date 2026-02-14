from __future__ import annotations

import traceback
from datetime import datetime, timezone
from typing import Optional, Iterable, List

import discord
from discord.ext import commands

from paths import ERROR_HANDLING_LOG_PATH
ERROR_HANDLING_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

def log_error() -> None:
    with ERROR_HANDLING_LOG_PATH.open("a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")

def brand_embed(
    *,
    title: str,
    description: str = "",
    ctx: Optional[commands.Context] = None,
) -> discord.Embed:
    color = discord.Color.blurple()
    if ctx and ctx.guild and getattr(ctx, "me", None) and getattr(ctx.me, "color", None):
        color = ctx.me.color

    embed = discord.Embed(
        title=title,
        description=description,
        color=color,
        timestamp=datetime.now(timezone.utc),
    )
    embed.set_footer(text="ASL Bot • Use /asl-help for commands")
    return embed


async def can_user_run(ctx: commands.Context, cmd: commands.Command) -> bool:
    try:
        return await cmd.can_run(ctx)
    except commands.CheckFailure:
        return False
    except Exception:
        # Don’t let a buggy check leak commands into help
        return False


def display_prefix(bot: commands.Bot) -> str:
    p = bot.command_prefix
    if isinstance(p, str):
        return p
    if isinstance(p, (list, tuple)) and p and isinstance(p[0], str):
        return p[0]
    return "!"


def pretty_usage(bot: commands.Bot, cmd: commands.Command) -> str:
    prefix = display_prefix(bot)
    if isinstance(cmd, commands.HybridCommand):
        return f"`/{cmd.name}` • `{prefix}{cmd.name}`"
    return f"`{prefix}{cmd.name}`"


def command_desc(cmd: commands.Command) -> str:
    desc = getattr(cmd, "description", None) or getattr(cmd, "help", None) or getattr(cmd, "brief", None) or ""
    desc = str(desc).strip().replace("\n", " ")
    return desc if desc else "No description set."


def chunk(items: list, size: int) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]
