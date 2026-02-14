from __future__ import annotations
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import discord
from discord.ext import commands

import Paginator
import web_search

from commands.static_commands import register_static_link_commands

ERROR_LOG = "discord-error-handling.log"

# ✅ Personal server for error reporting ONLY
ERROR_REPORT_GUILD_ID = 1469744304711930145
ERROR_REPORT_CHANNEL_NAME = "error-log"

# Store per-guild daily feature settings.
DAILY_CONFIG_PATH = Path("../data/daily/daily-task-config.json")
# Store per-guild daily posting history.
DAILY_HISTORY_PATH = Path("../data/daily/daily-word-history.json")

PROVIDER_DISPLAY_NAMES = {
    "handspeak": "HandSpeak",
    "lifeprint": "LifePrint",
    "lifeprint_youtube": "LifePrint",
    "signingsavvy": "SigningSavvy",
    "signasl": "SignASL",
    "aslcore": "ASLCore",
    "spreadthesign": "SpreadTheSign"
}

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return {}


def save_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _get_daily_cfg(guild_id: int) -> dict:
    cfg = load_json(DAILY_CONFIG_PATH)
    if str(guild_id) not in cfg:
        cfg[str(guild_id)] = {
            "enabled": False,
            "channel_id": None,
        }
    return cfg[str(guild_id)]


def _save_daily_cfg(guild_id: int, data: dict):
    cfg = load_json(DAILY_CONFIG_PATH)
    cfg[str(guild_id)] = data
    save_json(DAILY_CONFIG_PATH, cfg)


def _get_daily_history(guild_id: int) -> list[dict]:
    hist = load_json(DAILY_HISTORY_PATH)
    return hist.setdefault(str(guild_id), [])


def _append_daily_history(guild_id: int, items: Iterable[dict]):
    hist = load_json(DAILY_HISTORY_PATH)
    hist.setdefault(str(guild_id), []).extend(items)
    save_json(DAILY_HISTORY_PATH, hist)


async def _post_daily_word(channel, guild_id: int) -> bool:
    history = _get_daily_history(guild_id)

    if web_search.has_posted_today(history):
        return False

    exclude_urls = web_search.urls_used_within_days(history, days=365)

    handspeak_entries = web_search.load_dictionary_entries(web_search.HAND_SPEAK_DICT_PATH)
    lifeprint_entries = web_search.load_dictionary_entries(web_search.LIFEPRINT_DICT_PATH)

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
    _append_daily_history(guild_id, history_items)

    return True


def log_error():
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")


class BotCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ============================
    # ✅ ERROR REPORTING (TO PERSONAL SERVER ONLY)
    # ============================
    async def _send_error_to_personal_server(
        self,
        *,
        command_name: str,
        where: str,
        origin_guild: discord.Guild | None,
        origin_channel: discord.abc.GuildChannel | discord.abc.PrivateChannel | None,
        author: discord.abc.User | None,
        error: BaseException,
    ) -> None:
        target_guild = self.bot.get_guild(ERROR_REPORT_GUILD_ID)
        if not target_guild:
            return

        error_log_channel = discord.utils.get(target_guild.text_channels, name=ERROR_REPORT_CHANNEL_NAME)
        if not error_log_channel:
            return

        tb_full = "".join(traceback.format_exception(type(error), error, error.__traceback__))

        now_utc = datetime.now(timezone.utc)
        ts_for_thread = now_utc.strftime("%Y-%m-%d %H-%M-%S UTC")
        thread_name = f"{command_name} — {ts_for_thread}"
        if len(thread_name) > 100:
            thread_name = thread_name[:100]

        origin_guild_name = origin_guild.name if origin_guild else "Direct Message"
        origin_guild_id = origin_guild.id if origin_guild else "N/A"

        origin_channel_name = getattr(origin_channel, "name", str(origin_channel)) if origin_channel else "N/A"
        origin_channel_id = getattr(origin_channel, "id", "N/A") if origin_channel else "N/A"

        author_name = str(author) if author else "N/A"
        author_id = getattr(author, "id", "N/A") if author else "N/A"

        header = (
            f"🚨 **Error Report**\n"
            f"**Command:** `{command_name}`\n"
            f"**Where:** {where}\n"
            f"**Time (UTC):** {now_utc.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"**Origin Server:** {origin_guild_name} ({origin_guild_id})\n"
            f"**Origin Channel:** {origin_channel_name} ({origin_channel_id})\n"
            f"**User:** {author_name} ({author_id})"
        )

        starter = await error_log_channel.send(header)

        thread = await starter.create_thread(
            name=thread_name,
            auto_archive_duration=1440,
        )

        max_tb_chars = 1800
        tb_to_send = tb_full if len(tb_full) <= max_tb_chars else tb_full[-max_tb_chars:]
        await thread.send(f"```py\n{tb_to_send}\n```")

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if ctx.command and hasattr(ctx.command, "on_error"):
            return

        original = getattr(error, "original", error)
        log_error()

        try:
            cmd_name = ctx.command.qualified_name if ctx.command else "unknown-command"
            await self._send_error_to_personal_server(
                command_name=cmd_name,
                where="on_command_error (prefix/hybrid)",
                origin_guild=ctx.guild,
                origin_channel=ctx.channel,
                author=ctx.author,
                error=original,
            )
        except Exception:
            log_error()

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        original = getattr(error, "original", error)
        log_error()

        try:
            cmd_name = interaction.command.name if interaction.command else "unknown-app-command"
            await self._send_error_to_personal_server(
                command_name=cmd_name,
                where="on_app_command_error (slash/app)",
                origin_guild=interaction.guild,
                origin_channel=interaction.channel,
                author=interaction.user,
                error=original,
            )
        except Exception:
            log_error()

    # ============================
    # ✅ END ERROR REPORTING
    # ============================

    def _brand_embed(self, *, title: str, description: str = "", ctx: Optional[commands.Context] = None) -> discord.Embed:
        color = discord.Color.blurple()
        if ctx and ctx.guild and ctx.me and ctx.me.color:
            color = ctx.me.color

        embed = discord.Embed(
            title=title,
            description=description,
            color=color,
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_footer(text="ASL Bot • Use /asl-help for commands")
        return embed

    def _pretty_usage(self, bot: commands.Bot, cmd: commands.Command, prefix: str) -> str:
        # Show both slash + prefix for hybrid commands
        if isinstance(cmd, commands.HybridCommand):
            return f"`/{cmd.name}` • `{prefix}{cmd.name}`"
        return f"`{prefix}{cmd.name}`"

    async def _can_user_run(self, ctx: commands.Context, cmd: commands.Command) -> bool:
        # Filters based on command checks (permissions, guild-only, etc.)
        try:
            return await cmd.can_run(ctx)
        except commands.CheckFailure:
            return False
        except Exception:
            # If a check errors, treat as not runnable to avoid leaking/buggy listing
            return False

    def _command_desc(self, cmd: commands.Command) -> str:
        # Prefer hybrid/app description; fallback to help/brief
        desc = getattr(cmd, "description", None) or getattr(cmd, "help", None) or getattr(cmd, "brief", None) or ""
        desc = str(desc).strip().replace("\n", " ")
        return desc if desc else "No description set."

    # Commands that should always appear on page 1 (in this order if available)
    PINNED_FIRST_PAGE = ["sign", "parameters", "practice-rooms", "asl-help"]

    # Commands that should only appear in staff help (not regular /asl-help)
    STAFF_ONLY = {"daily-enable", "daily-disable", "daily-status"}

    def _cmd_key(self, cmd: commands.Command) -> str:
        return cmd.qualified_name.lower()

    def _is_staff_only(self, cmd: commands.Command) -> bool:
        return cmd.name in self.STAFF_ONLY

    def _chunk(self, items: list, size: int) -> list[list]:
        return [items[i:i + size] for i in range(0, len(items), size)]

    def _make_help_page(
            self,
            *,
            ctx: commands.Context,
            title: str,
            prefix: str,
            commands_list: list[commands.Command],
            page_num: int,
            total_pages: int,
            note: str = "",
    ) -> discord.Embed:
        desc = note.strip()
        embed = self._brand_embed(title=title, description=desc, ctx=ctx)

        for cmd in commands_list:
            usage = self._pretty_usage(ctx.bot, cmd, prefix)
            embed.add_field(name=usage, value=self._command_desc(cmd), inline=False)

        embed.set_footer(text=f"ASL Bot • Page {page_num}/{total_pages}")
        return embed

    @commands.hybrid_command(name="asl-help", description="Show commands you can use in this server")
    async def asl_help(self, ctx: commands.Context):
        prefix = "!"
        if getattr(ctx, "prefix", None):
            prefix = ctx.prefix

        # Collect commands user can run here
        available: list[commands.Command] = []
        for cmd in ctx.bot.walk_commands():
            if getattr(cmd, "hidden", False):
                continue
            if cmd.parent is not None:
                continue
            if self._is_staff_only(cmd):
                continue  # hide daily cmds from regular help
            if await self._can_user_run(ctx, cmd):
                available.append(cmd)

        # De-dup by qualified name (safe if any duplicates sneak in)
        by_name = {c.qualified_name: c for c in available}
        available = list(by_name.values())

        # Sort: pinned first (in the exact order), then alphabetical
        pinned: list[commands.Command] = []
        remaining: list[commands.Command] = []

        pinned_set = set(self.PINNED_FIRST_PAGE)

        for name in self.PINNED_FIRST_PAGE:
            c = ctx.bot.get_command(name)
            if c and c.qualified_name in by_name and await self._can_user_run(ctx, c):
                pinned.append(c)

        for cmd in sorted(available, key=lambda c: c.qualified_name.lower()):
            if cmd.name in pinned_set:
                continue
            remaining.append(cmd)

        # Build pages: page 1 has pinned + fill up to per_page
        per_page = 6
        page1 = pinned[:]
        fill_needed = max(0, per_page - len(page1))
        page1.extend(remaining[:fill_needed])
        remaining = remaining[fill_needed:]

        pages_cmds = [page1] + self._chunk(remaining, per_page)

        # Remove empty pages if any
        pages_cmds = [p for p in pages_cmds if p]

        if not pages_cmds:
            embed = self._brand_embed(
                title="ASL Bot Help",
                description="No commands available here.",
                ctx=ctx,
            )
            await ctx.send(embed=embed)
            return

        pages: list[discord.Embed] = []
        total_pages = len(pages_cmds)

        for idx, cmds_on_page in enumerate(pages_cmds, start=1):
            note = ""
            if idx == 1:
                note = (
                    "Here are the main commands to get started.\n"
                    f"Staff? Use `/signbot` to see admin tools."
                ).replace("{/ 'signbot'}", "/signbot")  # avoid formatting weirdness
            pages.append(
                self._make_help_page(
                    ctx=ctx,
                    title="ASL Bot Help",
                    prefix="/",
                    commands_list=cmds_on_page,
                    page_num=idx,
                    total_pages=total_pages,
                    note=note,
                )
            )

        await Paginator.Simple().start(ctx, pages=pages)

    @commands.hybrid_command(name="signbot", description="Show staff/admin commands available to you")
    @commands.has_guild_permissions(manage_guild=True)
    async def asl_staff_help(self, ctx: commands.Context):
        prefix = "!"
        if getattr(ctx, "prefix", None):
            prefix = ctx.prefix

        cmds: list[commands.Command] = []
        for cmd in ctx.bot.walk_commands():
            if getattr(cmd, "hidden", False):
                continue
            if cmd.parent is not None:
                continue
            if await self._can_user_run(ctx, cmd):
                cmds.append(cmd)

        # De-dup
        by_name = {c.qualified_name: c for c in cmds}
        cmds = list(by_name.values())

        # Staff-first ordering: staff-only commands first, then the rest alphabetical
        staff_cmds = sorted([c for c in cmds if c.name in self.STAFF_ONLY], key=lambda c: c.name)
        other_cmds = sorted([c for c in cmds if c.name not in self.STAFF_ONLY], key=lambda c: c.qualified_name.lower())

        ordered = staff_cmds + other_cmds

        per_page = 6
        pages_cmds = self._chunk(ordered, per_page)

        pages: list[discord.Embed] = []
        total_pages = len(pages_cmds)

        for idx, cmds_on_page in enumerate(pages_cmds, start=1):
            note = "Staff/admin tools you can use in this server." if idx == 1 else ""
            pages.append(
                self._make_help_page(
                    ctx=ctx,
                    title="ASL Bot Staff Help",
                    prefix=prefix,
                    commands_list=cmds_on_page,
                    page_num=idx,
                    total_pages=total_pages,
                    note=note,
                )
            )

        await Paginator.Simple().start(ctx, pages=pages)

    @commands.hybrid_command(name="feedback", description="Send feedback to the bot developer")
    async def feedback(self, ctx, *, message: str):
        try:
            bot_guild_id = 1469744304711930145
            target_guild = ctx.bot.get_guild(bot_guild_id)

            if not target_guild:
                await ctx.send("Target guild not found.")
                return

            channel = discord.utils.get(target_guild.text_channels, name="feedback")
            if not channel:
                await ctx.send("Feedback channel not found.")
                return

            thread_name = f"Feedback - {datetime.now():%Y-%m-%d}"
            thread = discord.utils.get(channel.threads, name=thread_name)

            if not thread:
                starter = await channel.send(thread_name)
                thread = await starter.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440
                )

            guild_name = ctx.guild.name if ctx.guild else "Direct Message"
            guild_id = ctx.guild.id if ctx.guild else "N/A"

            await thread.send(
                f"**Server:** {guild_name} ({guild_id})\n"
                f"**User:** {ctx.author} ({ctx.author.id})\n"
                f"**Channel:** {ctx.channel} ({ctx.channel.id})\n\n"
                f"{message}"
            )

            await ctx.send("✅ Feedback sent!")

        except Exception:
            log_error()
            await ctx.send("⚠️ Failed to send feedback.")

    DAILY_CONFIG_PATH = "../data/daily/daily-task-config.json"
    DAILY_HISTORY_PATH = "../data/daily/daily-word-history.json"

    def _get_daily_cfg(guild_id: int) -> dict:
        cfg = load_json(DAILY_CONFIG_PATH)
        return cfg.setdefault(
            str(guild_id),
            {
                "enabled": False,
                "channel_id": None,
            },
        )

    def _save_daily_cfg(guild_id: int, data: dict):
        cfg = load_json(DAILY_CONFIG_PATH)
        cfg[str(guild_id)] = data
        save_json(DAILY_CONFIG_PATH, cfg)

    def _get_daily_history(guild_id: int) -> list[dict]:
        hist = load_json(DAILY_HISTORY_PATH)
        return hist.setdefault(str(guild_id), [])

    def _append_daily_history(guild_id: int, items: list[dict]):
        hist = load_json(DAILY_HISTORY_PATH)
        hist.setdefault(str(guild_id), []).extend(items)
        save_json(DAILY_HISTORY_PATH, hist)

    async def _post_daily_word(channel, guild_id: int) -> bool:
        history = _get_daily_history(guild_id)
        exclude_urls = web_search.urls_used_within_days(history, days=365)

        handspeak = web_search.load_dictionary_entries(web_search.HAND_SPEAK_DICT_PATH)
        lifeprint = web_search.load_dictionary_entries(web_search.LIFEPRINT_DICT_PATH)

        message, used = await web_search.build_daily_word_post(
            handspeak_entries=handspeak,
            lifeprint_entries=lifeprint,
            exclude_urls=exclude_urls,
            history=history,
        )

        if not used:
            return False

        await channel.send(message)

        now_iso = datetime.now(timezone.utc).isoformat()
        history_items = [{"ts": now_iso, **u} for u in used]
        _append_daily_history(guild_id, history_items)
        return True

    @commands.hybrid_command(name="daily-status", description="Show daily word status for this server")
    async def daily_status(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)
        history = _get_daily_history(ctx.guild.id)

        channel = None
        if cfg.get("channel_id"):
            channel = ctx.guild.get_channel(cfg["channel_id"])

        posted_today = web_search.has_posted_today(history)
        loop_running = self.bot.get_cog("BotCommands") is not None

        lines = [
            "**Daily Word Status**",
            f"- Enabled: **{cfg.get('enabled')}**",
            f"- Posted today: **{posted_today}**",
            f"- Loop running: **{loop_running}**",
            f"- Channel: {channel.mention if channel else '(not set)'}",
        ]

        await ctx.send("\n".join(lines))

    @commands.hybrid_command(
        name="daily-enable",
        description="Enable the daily word (posts immediately if not posted today)",
    )
    @commands.has_guild_permissions(administrator=True)
    async def daily_enable(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)

        if not cfg.get("channel_id"):
            await ctx.send(
                "❌ No daily channel set.\n"
                "Ask an admin to set one with `/daily-set-channel`."
            )
            return

        cfg["enabled"] = True
        _save_daily_cfg(ctx.guild.id, cfg)

        channel = ctx.guild.get_channel(cfg["channel_id"])
        posted = await _post_daily_word(channel, ctx.guild.id)

        if posted:
            await ctx.send("✅ Daily word enabled and posted for today.")
        else:
            await ctx.send("✅ Daily word enabled. Today’s word was already posted.")

    @commands.hybrid_command(name="daily-disable", description="Disable the daily word for this server")
    @commands.has_guild_permissions(administrator=True)
    async def daily_disable(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)
        cfg["enabled"] = False
        _save_daily_cfg(ctx.guild.id, cfg)
        await ctx.send("Daily word has been disabled.")

    @commands.hybrid_command(name="parameters", description="The 5 parameters of ASL")
    async def parameters(self, ctx):
        await ctx.send(
            "- Handshape\n"
            "- Palm Orientation\n"
            "- Location\n"
            "- Movement\n"
            "- Non-Manual Markers"
        )

    # ----------------------------
    # SIGN COMMAND (paginate if > 5)
    # ----------------------------

    def _format_result_line(self, entry: dict, fallback_word: str) -> str:
        """
        Returns a markdown linked label like:
          [HandSpeak: mother](https://...)
        """

        raw_provider = entry.get("source", "unknown")
        provider = PROVIDER_DISPLAY_NAMES.get(raw_provider.lower(), raw_provider)

        title = entry.get("title") or fallback_word
        title = str(title).strip()
        url = str(entry.get("url", "")).strip()

        if not url:
            return f"**{provider}:** {title}"

        return f"[{provider}: {title}]({url})"

    @commands.hybrid_command(
        name="sign",
        description="Search ASL dictionaries for a word"
    )
    async def sign(self, ctx, *, word: str = None):
        if not word or not word.strip():
            example = "!sign hello" if getattr(ctx, "prefix", None) else "/sign hello"

            embed = self._brand_embed(
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
                embed = self._brand_embed(
                    title="No Results",
                    description=f"❌ No ASL sign found for **{word}**.",
                    ctx=ctx,
                )
                await ctx.send(embed=embed)
                return

            # If <= 5 results, single embed
            if len(results) <= 5:
                embed = self._brand_embed(
                    title=f"Results for: {word.strip().lower()}",
                    description="Here are the best matches I found:",
                    ctx=ctx,
                )
                for entry in results:
                    embed.add_field(
                        name="",
                        value=self._format_result_line(entry, fallback_word=word.strip().lower()),
                        inline=False,
                    )

                await ctx.send(embed=embed)
                return

            # Otherwise paginate (5 results per page)
            pages: list[discord.Embed] = []
            per_page = 5
            total = len(results)

            for i in range(0, total, per_page):
                chunk = results[i:i + per_page]
                page_num = (i // per_page) + 1
                max_pages = (total + per_page - 1) // per_page

                embed = self._brand_embed(
                    title=f"Results for: {word.strip().lower()}",
                    description=f"Showing results **{i + 1}-{min(i + per_page, total)}** of **{total}**",
                    ctx=ctx,
                )
                embed.set_footer(text=f"ASL Bot • Page {page_num}/{max_pages}")

                for entry in chunk:
                    embed.add_field(
                        name="",
                        value=self._format_result_line(entry, fallback_word=word.strip().lower()),
                        inline=False,
                    )

                pages.append(embed)

            await Paginator.Simple().start(ctx, pages=pages)

        except Exception:
            log_error()
            await ctx.send("⚠️ An unexpected error occurred while searching.")

async def setup(bot):
    await bot.add_cog(BotCommands(bot))
    register_static_link_commands(bot)
