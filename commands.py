import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import discord
from discord.ext import commands

import Paginator
import web_search

ERROR_LOG = "discord-error-handling.log"

# Store per-guild daily feature settings.
DAILY_CONFIG_PATH = Path("daily-task-config.json")
# Store per-guild daily posting history.
DAILY_HISTORY_PATH = Path("daily-word-history.json")


# Read a JSON file and return an object dictionary.
def load_json(path: Path) -> dict:
    # Return an empty object when the file does not exist yet.
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    # Fall back to an empty object when file contents are invalid JSON.
    except json.JSONDecodeError:
        return {}


# Write a dictionary to disk in pretty JSON format.
def save_json(path: Path, data: dict):
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# Fetch daily settings for a guild and fill defaults if missing.
def _get_daily_cfg(guild_id: int) -> dict:
    cfg = load_json(DAILY_CONFIG_PATH)

    # Create default settings when this guild has no saved config.
    if str(guild_id) not in cfg:
        cfg[str(guild_id)] = {
            "enabled": False,
            "channel_id": None,
        }

    return cfg[str(guild_id)]


# Persist daily settings for a single guild.
def _save_daily_cfg(guild_id: int, data: dict):
    cfg = load_json(DAILY_CONFIG_PATH)
    cfg[str(guild_id)] = data
    save_json(DAILY_CONFIG_PATH, cfg)


# Return historical daily-word entries for a guild.
def _get_daily_history(guild_id: int) -> list[dict]:
    hist = load_json(DAILY_HISTORY_PATH)
    return hist.setdefault(str(guild_id), [])


# Append newly used daily-word entries to guild history.
def _append_daily_history(guild_id: int, items: Iterable[dict]):
    hist = load_json(DAILY_HISTORY_PATH)
    hist.setdefault(str(guild_id), []).extend(items)
    save_json(DAILY_HISTORY_PATH, hist)


# Post today's daily word if one has not already been posted.
async def _post_daily_word(channel, guild_id: int) -> bool:
    history = _get_daily_history(guild_id)

    # Skip posting when this guild already posted today.
    if web_search.has_posted_today(history):
        return False

    exclude_urls = web_search.urls_used_within_days(history, days=365)

    handspeak_entries = web_search.load_dictionary_entries(web_search.HAND_SPEAK_DICT_PATH)
    lifeprint_entries = web_search.load_dictionary_entries(web_search.LIFEPRINT_DICT_PATH)

    message, used = web_search.build_daily_word_post(
        handspeak_entries=handspeak_entries,
        lifeprint_entries=lifeprint_entries,
        exclude_urls=exclude_urls,
        history=history,
    )

    # Stop when there is nothing valid to record/send.
    if not used:
        return False

    # Wait for Discord to send the generated daily message.
    await channel.send(message)

    now = datetime.now(timezone.utc).isoformat()
    history_items = [{"ts": now, **u} for u in used]
    _append_daily_history(guild_id, history_items)

    return True


# Append the current traceback to the bot error log file.
def log_error():
    with open(ERROR_LOG, "a", encoding="utf-8") as f:
        f.write(traceback.format_exc() + "\n")


# Hold slash/prefix commands and daily-word behavior.
class BotCommands(commands.Cog):
    # Save a bot reference for command handlers.
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="asl-help", description="Show all ASL bot commands")
    # Show users a paginated list of available bot commands.
    async def asl_help(self, ctx):
        page1 = discord.Embed(
            title="ASL Bot Commands",
            description="Lookup, learning, and daily practice tools",
            color=0x00FF00,
        )
        page1.add_field(name="/sign | !sign", value="Search ASL dictionaries", inline=False)
        page1.add_field(name="/parameters", value="The 5 parameters of ASL", inline=False)
        page1.add_field(name="/feedback", value="Send feedback to the developer", inline=False)

        page2 = discord.Embed(color=0x00FF00)
        page2.add_field(name="/daily-on", value="Enable daily word", inline=False)
        page2.add_field(name="/daily-off", value="Disable daily word", inline=False)
        page2.add_field(name="/daily-status", value="Check daily word settings", inline=False)

        # Wait for the paginator helper to send both embed pages.
        await Paginator.Simple().start(ctx, pages=[page1, page2])

    @commands.hybrid_command(name="feedback", description="Send feedback to the bot developer")
    # Handle user feedback command flow (currently exits early by design).
    async def feedback(self, ctx, *, message: str):
        try:
            # Use a fixed guild id to look up the feedback destination.
            bot_guild_id = 1469744304711930145
            target_guild = discord.utils.get(ctx.guild.channels, id=bot_guild_id)
            print(f"{target_guild}")
            # fb_channel = discord.utils.get(guild=target_guild.channels, name="feedback")
            # channel = ctx.bot.get_channel(fb_channel)
            """"
            if not channel:
                print(f"{fb_channel}")
                await ctx.send("Feedback channel not found.")
                return
            else:
                print(f"{fb_channel}")
                return
            """
            return
            thread_name = f"Feedback - {datetime.now():%Y-%m-%d}"
            # Wait for Discord to fetch active feedback threads.
            threads = await channel.fetch_active_threads()
            thread = discord.utils.get(threads.threads, name=thread_name)

            # Create a daily feedback thread when one does not exist.
            if not thread:
                # Wait for a starter message so a thread can be created.
                starter = await channel.send(thread_name)
                # Wait for thread creation attached to the starter message.
                thread = await starter.create_thread(name=thread_name, auto_archive_duration=1440)

            # Wait for sending the formatted feedback message into the thread.
            await thread.send(
                f"From {ctx.author} ({ctx.author.id})\n"
                f"Channel: {ctx.channel}\n\n{message}"
            )
            # Wait for user confirmation response.
            await ctx.send("✅ Feedback sent!")

        # Handle unexpected failures and report to the user.
        except Exception:
            log_error()
            # Wait for error response message to be sent.
            await ctx.send("⚠️ Failed to send feedback.")

    DAILY_CONFIG_PATH = "daily-task-config.json"
    DAILY_HISTORY_PATH = "daily-word-history.json"

    # Keep a class-scoped copy of config helper (legacy structure).
    def _get_daily_cfg(guild_id: int) -> dict:
        cfg = load_json(DAILY_CONFIG_PATH)
        return cfg.setdefault(
            str(guild_id),
            {
                "enabled": False,
                "channel_id": None,
            },
        )

    # Keep a class-scoped copy of save helper (legacy structure).
    def _save_daily_cfg(guild_id: int, data: dict):
        cfg = load_json(DAILY_CONFIG_PATH)
        cfg[str(guild_id)] = data
        save_json(DAILY_CONFIG_PATH, cfg)

    # Keep a class-scoped copy of history loader (legacy structure).
    def _get_daily_history(guild_id: int) -> list[dict]:
        hist = load_json(DAILY_HISTORY_PATH)
        return hist.setdefault(str(guild_id), [])

    # Keep a class-scoped copy of history appender (legacy structure).
    def _append_daily_history(guild_id: int, items: list[dict]):
        hist = load_json(DAILY_HISTORY_PATH)
        hist.setdefault(str(guild_id), []).extend(items)
        save_json(DAILY_HISTORY_PATH, hist)

    # Keep a class-scoped copy of posting helper (legacy structure).
    async def _post_daily_word(channel, guild_id: int) -> bool:
        history = _get_daily_history(guild_id)

        # if web_search.has_posted_today(history):
        #     return False

        exclude_urls = web_search.urls_used_within_days(history, days=365)

        handspeak = web_search.load_dictionary_entries(web_search.HAND_SPEAK_DICT_PATH)
        lifeprint = web_search.load_dictionary_entries(web_search.LIFEPRINT_DICT_PATH)

        message, used = web_search.build_daily_word_post(
            handspeak_entries=handspeak,
            lifeprint_entries=lifeprint,
            exclude_urls=exclude_urls,
            history=history,
        )

        # Stop when no daily message candidates are produced.
        if not used:
            return False

        # Wait for the daily message to be sent to Discord.
        await channel.send(message)

        now_iso = datetime.now(timezone.utc).isoformat()
        history_items = [{"ts": now_iso, **u} for u in used]
        _append_daily_history(guild_id, history_items)

        return True

    @commands.hybrid_command(name="daily-status", description="Show daily word status for this server")
    # Show whether daily posting is enabled and where it posts.
    async def daily_status(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)
        history = _get_daily_history(ctx.guild.id)

        channel = None
        # Resolve the configured channel only when an id is stored.
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

        # Wait for Discord to post the status summary.
        await ctx.send("\n".join(lines))

    @commands.hybrid_command(
        name="daily-enable",
        description="Enable the daily word (posts immediately if not posted today)",
    )
    @commands.has_guild_permissions(administrator=True)
    # Enable daily posting and optionally post immediately.
    async def daily_enable(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)

        # Block enabling when no channel has been configured yet.
        if not cfg.get("channel_id"):
            # Wait for Discord to send setup guidance to admins.
            await ctx.send(
                "❌ No daily channel set.\n"
                "Ask an admin to set one with `/daily-set-channel`."
            )
            return

        cfg["enabled"] = True
        _save_daily_cfg(ctx.guild.id, cfg)

        channel = ctx.guild.get_channel(cfg["channel_id"])
        # Wait for posting attempt so command reflects current result.
        posted = await _post_daily_word(channel, ctx.guild.id)

        # Confirm whether a new post was made during enable.
        if posted:
            await ctx.send("✅ Daily word enabled and posted for today.")
        else:
            await ctx.send("✅ Daily word enabled. Today’s word was already posted.")

    @commands.hybrid_command(name="daily-disable", description="Disable the daily word for this server")
    @commands.has_guild_permissions(administrator=True)
    # Disable daily posting for the current guild.
    async def daily_disable(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)
        cfg["enabled"] = False
        _save_daily_cfg(ctx.guild.id, cfg)

        # Wait for Discord to confirm disabling to the user.
        await ctx.send("🛑 Daily word has been disabled.")

    @commands.hybrid_command(name="parameters", description="The 5 parameters of ASL")
    # Send a quick list of ASL parameters.
    async def parameters(self, ctx):
        # Wait for Discord to send the static parameter list.
        await ctx.send(
            "- Handshape\n"
            "- Palm Orientation\n"
            "- Location\n"
            "- Movement\n"
            "- Non-Manual Markers"
        )

    @commands.hybrid_command(name="sign", description="Search ASL dictionaries")
    # Search dictionaries/providers and return best ASL matches.
    async def sign(self, ctx, *, word: str):
        try:
            results = web_search.search_all_providers(word)

            # Return early when no exact or partial matches are found.
            if not results["exact"] and not results["partial"]:
                await ctx.send(f"No ASL results found for **{word}**.")
                return

            lines = [f"**Best match for:** {word}"]
            # Add every exact result to the outgoing response lines.
            for r in results["exact"]:
                lines.append(f"- {r['provider'].title()}: {r['title']} — {r['url']}")

            # Mention that extra partial matches exist without listing all.
            if results["partial"]:
                lines.append(f"\nℹ️ {len(results['partial'])} additional partial matches available.")

            # Wait for Discord to send the final sign search response.
            await ctx.send("\n".join(lines))

        # Catch unexpected search errors and send a user-facing warning.
        except Exception:
            log_error()
            # Wait for Discord to send the error message.
            await ctx.send("⚠️ Error during sign lookup.")


# Register this cog with the main bot during extension load.
async def setup(bot):
    # Wait for Discord.py to finish adding the cog instance.
    await bot.add_cog(BotCommands(bot))
