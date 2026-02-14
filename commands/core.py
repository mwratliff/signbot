from __future__ import annotations

import traceback
from datetime import datetime, timezone

import discord
from discord.ext import commands

import Paginator
from commands.static_commands import register_static_link_commands
from .shared import brand_embed, log_error, can_user_run, pretty_usage, command_desc, chunk

# ✅ Personal server for error reporting ONLY
ERROR_REPORT_GUILD_ID = 1469744304711930145
ERROR_REPORT_CHANNEL_NAME = "error-log"

# Commands pinned to page 1 (in this order if available)
PINNED_FIRST_PAGE = ["sign", "parameters", "practice-rooms", "asl-help"]

# Commands hidden from /asl-help, visible in staff help
STAFF_ONLY = {"daily-enable", "daily-disable", "daily-status"}


class Core(commands.Cog):
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
        thread_name = f"{command_name} — {ts_for_thread}"[:100]

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
        thread = await starter.create_thread(name=thread_name, auto_archive_duration=1440)

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
    # ✅ HELP (paged, 6 per page)
    # ============================
    def _make_help_page(
        self,
        *,
        ctx: commands.Context,
        title: str,
        commands_list: list[commands.Command],
        page_num: int,
        total_pages: int,
        note: str = "",
    ) -> discord.Embed:
        embed = brand_embed(title=title, description=note.strip(), ctx=ctx)
        for cmd in commands_list:
            embed.add_field(
                name=pretty_usage(ctx.bot, cmd),
                value=command_desc(cmd),
                inline=False,
            )
        embed.set_footer(text=f"ASL Bot • Page {page_num}/{total_pages}")
        return embed

    @commands.hybrid_command(name="asl-help", description="Show commands you can use in this server")
    async def asl_help(self, ctx: commands.Context):
        per_page = 6

        available: list[commands.Command] = []
        for cmd in ctx.bot.walk_commands():
            if getattr(cmd, "hidden", False):
                continue
            if cmd.parent is not None:
                continue
            if cmd.name in STAFF_ONLY:
                continue
            if await can_user_run(ctx, cmd):
                available.append(cmd)

        # De-dup
        by_qn = {c.qualified_name: c for c in available}
        available = list(by_qn.values())

        # Build pinned list in order
        pinned: list[commands.Command] = []
        for name in PINNED_FIRST_PAGE:
            c = ctx.bot.get_command(name)
            if c and c.qualified_name in by_qn and await can_user_run(ctx, c):
                pinned.append(c)

        pinned_names = {c.name for c in pinned}

        # Remaining alphabetical
        remaining = sorted(
            [c for c in available if c.name not in pinned_names],
            key=lambda c: c.qualified_name.lower(),
        )

        # Page 1 = pinned + fill
        page1 = pinned[:]
        fill = max(0, per_page - len(page1))
        page1.extend(remaining[:fill])
        remaining = remaining[fill:]

        pages_cmds = [page1] + chunk(remaining, per_page)
        pages_cmds = [p for p in pages_cmds if p]

        if not pages_cmds:
            await ctx.send(embed=brand_embed(title="ASL Bot Help", description="No commands available here.", ctx=ctx))
            return

        pages: list[discord.Embed] = []
        total_pages = len(pages_cmds)

        for i, cmds_on_page in enumerate(pages_cmds, start=1):
            note = "Main commands to get started.\nStaff? Use `/signbot` for admin tools." if i == 1 else ""
            pages.append(
                self._make_help_page(
                    ctx=ctx,
                    title="ASL Bot Help",
                    commands_list=cmds_on_page,
                    page_num=i,
                    total_pages=total_pages,
                    note=note,
                )
            )

        await Paginator.Simple().start(ctx, pages=pages)

    @commands.hybrid_command(name="signbot", description="Show staff/admin commands available to you")
    @commands.has_guild_permissions(manage_guild=True)
    async def asl_staff_help(self, ctx: commands.Context):
        per_page = 6

        cmds: list[commands.Command] = []
        for cmd in ctx.bot.walk_commands():
            if getattr(cmd, "hidden", False):
                continue
            if cmd.parent is not None:
                continue
            if await can_user_run(ctx, cmd):
                cmds.append(cmd)

        # De-dup
        by_qn = {c.qualified_name: c for c in cmds}
        cmds = list(by_qn.values())

        staff_cmds = sorted([c for c in cmds if c.name in STAFF_ONLY], key=lambda c: c.name)
        other_cmds = sorted([c for c in cmds if c.name not in STAFF_ONLY], key=lambda c: c.qualified_name.lower())

        ordered = staff_cmds + other_cmds
        pages_cmds = chunk(ordered, per_page)

        pages: list[discord.Embed] = []
        total_pages = len(pages_cmds)

        for i, cmds_on_page in enumerate(pages_cmds, start=1):
            note = "Staff/admin tools you can use in this server." if i == 1 else ""
            pages.append(
                self._make_help_page(
                    ctx=ctx,
                    title="ASL Bot Staff Help",
                    commands_list=cmds_on_page,
                    page_num=i,
                    total_pages=total_pages,
                    note=note,
                )
            )

        await Paginator.Simple().start(ctx, pages=pages)


async def setup(bot: commands.Bot):
    await bot.add_cog(Core(bot))
    # Static hybrid commands are bot-level; register once here.
    register_static_link_commands(bot)
