import discord
from discord.ext import commands
import json
from pathlib import Path
from typing import Iterable
from datetime import datetime, timezone
import traceback
import web_search
import Paginator

ERROR_LOG = "discord-error-handling.log"

# -----------------------------
# Daily word persistence files
# -----------------------------

DAILY_CONFIG_PATH = Path("daily-task-config.json")
DAILY_HISTORY_PATH = Path("daily-word-history.json")

# -----------------------------
# JSON utility helpers
# -----------------------------

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

# -----------------------------
# Daily config helpers
# -----------------------------

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

# -----------------------------
# Daily history helpers
# -----------------------------

def _get_daily_history(guild_id: int) -> list[dict]:
    hist = load_json(DAILY_HISTORY_PATH)
    return hist.setdefault(str(guild_id), [])


def _append_daily_history(guild_id: int, items: Iterable[dict]):
    hist = load_json(DAILY_HISTORY_PATH)
    hist.setdefault(str(guild_id), []).extend(items)
    save_json(DAILY_HISTORY_PATH, hist)
# -----------------------------
# Daily posting logic
# -----------------------------

async def _post_daily_word(channel, guild_id: int) -> bool:
    """
    Posts today's ASL word if it hasn't already been posted.
    Returns True if a post was made.
    """
    history = _get_daily_history(guild_id)

    if web_search.has_posted_today(history):
        return False

    exclude_urls = web_search.urls_used_within_days(history, days=365)

    handspeak_entries = web_search.load_dictionary_entries(
        web_search.HAND_SPEAK_DICT_PATH
    )
    lifeprint_entries = web_search.load_dictionary_entries(
        web_search.LIFEPRINT_DICT_PATH
    )

    message, used = web_search.build_daily_word_post(
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

    # -----------------------------
    # ASL HELP
    # -----------------------------
    @commands.hybrid_command(name="asl-help", description="Show all ASL bot commands")
    async def asl_help(self, ctx):
        page1 = discord.Embed(
            title="ASL Bot Commands",
            description="Lookup, learning, and daily practice tools",
            color=0x00FF00
        )
        page1.add_field(name="/sign | !sign", value="Search ASL dictionaries", inline=False)
        page1.add_field(name="/parameters", value="The 5 parameters of ASL", inline=False)
        page1.add_field(name="/feedback", value="Send feedback to the developer", inline=False)

        page2 = discord.Embed(color=0x00FF00)
        page2.add_field(name="/daily-on", value="Enable daily word", inline=False)
        page2.add_field(name="/daily-off", value="Disable daily word", inline=False)
        page2.add_field(name="/daily-status", value="Check daily word settings", inline=False)

        await Paginator.Simple().start(ctx, pages=[page1, page2])

    # -----------------------------
    # FEEDBACK
    # -----------------------------
    @commands.hybrid_command(name="feedback", description="Send feedback to the bot developer")
    async def feedback(self, ctx, *, message: str):
        try:
            # Set static guild id and then search for a channel named "feedback" (if it gets nuked, the id changes)
            bot_guild_id = 1469744304711930145
            target_guild = discord.utils.get(ctx.guild.channels, id=bot_guild_id)
            print(f"{target_guild}")
            #fb_channel = discord.utils.get(guild=target_guild.channels, name="feedback")
            #channel = ctx.bot.get_channel(fb_channel)
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
            threads = await channel.fetch_active_threads()
            thread = discord.utils.get(threads.threads, name=thread_name)

            if not thread:
                starter = await channel.send(thread_name)
                thread = await starter.create_thread(
                    name=thread_name,
                    auto_archive_duration=1440
                )

            await thread.send(
                f"From {ctx.author} ({ctx.author.id})\n"
                f"Channel: {ctx.channel}\n\n{message}"
            )
            await ctx.send("✅ Feedback sent!")

        except Exception:
            log_error()
            await ctx.send("⚠️ Failed to send feedback.")

    # -----------------------------
    # DAILY WORD COMMANDS
    # -----------------------------

    DAILY_CONFIG_PATH = "daily-task-config.json"
    DAILY_HISTORY_PATH = "daily-word-history.json"

    def _get_daily_cfg(guild_id: int) -> dict:
        cfg = load_json(DAILY_CONFIG_PATH)
        return cfg.setdefault(str(guild_id), {
            "enabled": False,
            "channel_id": None,
        })

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
        """
        Posts the daily word if possible.
        Returns True if a post was made.
        """
        history = _get_daily_history(guild_id)

        #if web_search.has_posted_today(history):
        #    return False

        exclude_urls = web_search.urls_used_within_days(history, days=365)

        handspeak = web_search.load_dictionary_entries(
            web_search.HAND_SPEAK_DICT_PATH
        )
        lifeprint = web_search.load_dictionary_entries(
            web_search.LIFEPRINT_DICT_PATH
        )

        message, used = web_search.build_daily_word_post(
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

    @commands.hybrid_command(
        name="daily-status",
        description="Show daily word status for this server"
    )
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
        description="Enable the daily word (posts immediately if not posted today)"
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

    @commands.hybrid_command(
        name="daily-disable",
        description="Disable the daily word for this server"
    )
    @commands.has_guild_permissions(administrator=True)
    async def daily_disable(self, ctx):
        cfg = _get_daily_cfg(ctx.guild.id)
        cfg["enabled"] = False
        _save_daily_cfg(ctx.guild.id, cfg)

        await ctx.send("🛑 Daily word has been disabled.")

    # -----------------------------
    # PARAMETERS
    # -----------------------------
    @commands.hybrid_command(name="parameters", description="The 5 parameters of ASL")
    async def parameters(self, ctx):
        await ctx.send(
            "- Handshape\n"
            "- Palm Orientation\n"
            "- Location\n"
            "- Movement\n"
            "- Non-Manual Markers"
        )

    # -----------------------------
    # SIGN LOOKUP (MULTI-PROVIDER)
    # -----------------------------
    @commands.hybrid_command(name="sign", description="Search ASL dictionaries")
    async def sign(self, ctx, *, word: str):
        try:
            results = web_search.search_all_providers(word)

            if not results["exact"] and not results["partial"]:
                await ctx.send(f"No ASL results found for **{word}**.")
                return

            lines = [f"**Best match for:** {word}"]
            for r in results["exact"]:
                lines.append(f"- {r['provider'].title()}: {r['title']} — {r['url']}")

            if results["partial"]:
                lines.append(
                    f"\nℹ️ {len(results['partial'])} additional partial matches available."
                )

            await ctx.send("\n".join(lines))

        except Exception:
            log_error()
            await ctx.send("⚠️ Error during sign lookup.")


async def setup(bot):
    await bot.add_cog(BotCommands(bot))
