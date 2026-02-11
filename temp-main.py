import traceback

import discord
from discord import app_commands
from discord.ext import commands, tasks
import logging
from dotenv import load_dotenv
import os
import Paginator
import web_search
from web_search import perform_web_search
from datetime import datetime
import asyncio
import json


# Load config from .env (keep your token out of the codebase)
load_dotenv()

token = os.getenv("DISCORD_TOKEN")

# Bot owner (your user ID).
OWNER_ID = int(os.getenv("OWNER_ID", "0"))
# Log discord.py output to a file to help debug issues later
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# Intents control what events/data Discord sends your bot
intents = discord.Intents.default()
intents.message_content = True  # needed for prefix commands in many setups
intents.members = True

# Main bot instance (disable default help so you can use your own)
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

@bot.command()
async def parameters(ctx, arg: discord.Member = commands.Author):
    # Quick info dump + links about the 5 sign parameters
    await ctx.send(
        f"{arg.mention}"
        f"\n### The 5 Sign Parameters"
        f"\n- [Handshape](<https://www.lifeprint.com/asl101/pages-layout/handshapes.htm>)"
        f"\n- [Palm Orientation](<https://books.openbookpublishers.com/10.11647/obp.0205/ch12.xhtml>)"
        f"\n- [Location](<https://en.wikipedia.org/wiki/Location_(sign_language)>)"
        f"\n- Movement: Which way the hand moves, away from body, towards body, motionless, circular, etc."
        f"\n- [Non-Manual Markers](<https://www.lifeprint.com/asl101/pages-layout/nonmanualmarkers.htm>): "
        f"Facial expressions and body movements that accompany the sign"
        f"\n### Learn More About Sign Parameters"
        f"\n- [LifePrint](<https://www.lifeprint.com/asl101/topics/parameters-asl.htm>)"
        f"\n- [HandSpeak](<https://www.handspeak.com/learn/index.php?id=397>)"
    )


@bot.command(name="asl-help")
async def asl_help(ctx):
    # Paginated help menu (kept short per page for readability)
    page1 = discord.Embed(
        title="Sign Bot Help",
        description="Here's a list of commands that can be used",
        color=0x00FF00,
    )
    page1.add_field(name="!parameters", value="Shows the 5 Sign Parameters", inline=False)
    page1.add_field(name="!sign-help", value="Shows how to sign a word", inline=False)
    page1.add_field(name="!deaf-history", value="Shows a brief history of deaf culture", inline=False)
    page1.add_field(
        name="!nd_resources",
        value="Shows a list of resources on how to help neurodivergent individuals",
        inline=False,
    )

    page2 = discord.Embed(title="", description="", color=0x00FF00)
    page2.add_field(name="!fluency_level", value="A brief list of fluency levels for ASL", inline=False)
    page2.add_field(name="!asl_resources", value="A list of resources on ASL", inline=False)
    page2.add_field(name="!practice_rooms", value="Explains what happens in practice rooms", inline=False)
    page2.add_field(name="!ai_translations", value="Why we typically don't promote AI Translation apps", inline=False)

    # Note: page3 exists but isn't added to embeds yet (add it when ready)
    page3 = discord.Embed(title="", description="", color=0x00FF00)
    page3.add_field(name="!sign-meaning", value="A glossary of ASL terms", inline=False)
    page3.add_field(name="!practice-games", value="A list of games to play with friends to practice ASL", inline=False)
    page3.add_field(name="!feedback", value="Send feedback to the bot developer", inline=False)

    embeds = [page1, page2, page3]
    await Paginator.Simple().start(ctx, pages=embeds)


@bot.command(name="sign-help")
async def sign_help(ctx, *, word: str):
    """
    Look up a sign locally; if missing, fetch it from the web and save it.
    """
    result, added = web_search.lookup_or_fetch_word(word)

    if not result:
        await ctx.send(f"❌ No ASL sign found for **{word}**.")
        return

    status = "🆕 added to dictionary" if added else "📖 found locally"

    await ctx.send(
        f"**{word.upper()}** ({status})\n"
        f"Source: {result['source']}\n"
        f"{result['url']}"
    )


@sign_help.error
async def sign_help_error(ctx, error: commands.MissingRequiredArgument):
    # Missing the word to search for
    await ctx.send("Please type a word to search!\nExample: !sign-help hello")


@bot.command(name="feedback")
@bot.command(name="feedback")
async def feedback(ctx, *, message: str):
    """
    Sends feedback to a per-day thread in a central feedback channel.
    """
    target_channel_id = 1469745304785129542
    thread_name = f"Feedback - {datetime.utcnow():%Y-%m-%d}"

    target_channel = bot.get_channel(target_channel_id)
    if target_channel is None:
        await ctx.send("⚠️ Feedback channel not found.")
        return

    if not isinstance(target_channel, discord.TextChannel):
        await ctx.send("⚠️ Feedback channel is not a text channel.")
        return

    # Try to find an existing thread (including archived)
    threads = await target_channel.fetch_active_threads()
    thread = discord.utils.get(threads.threads, name=thread_name)

    if thread is None:
        starter = await target_channel.send(f"📬 {thread_name}")
        thread = await starter.create_thread(
            name=thread_name,
            auto_archive_duration=1440,
        )

    await thread.send(
        f"**From:** {ctx.author} ({ctx.author.id})\n"
        f"**Channel:** #{ctx.channel}\n\n"
        f"{message}"
    )

    await ctx.send("✅ Thank you for your feedback!")


@feedback.error
async def feedback_error(ctx, error):
    # Keep details in logs/console; keep message short for users
    print(traceback.format_exc())
    await ctx.send(f"An error occurred: {error}")

@bot.command(name="fluency-level")
async def fluency_level(ctx):
    # Boilerplate: quick overview list (edit these levels to match what you want)
    embed = discord.Embed(title="ASL Fluency Levels (Overview)", color=0x00FF00)
    embed.add_field(name="Beginner", value="(TODO) Basic vocab, fingerspelling, simple sentences.", inline=False)
    embed.add_field(name="Intermediate", value="(TODO) More grammar, classifiers, storytelling basics.", inline=False)
    embed.add_field(name="Advanced", value="(TODO) Nuance, regional variation, natural speed.", inline=False)
    embed.add_field(name="Fluent", value="(TODO) Comfortable across topics + cultural competence.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="deaf-resources")
async def deaf_resources(ctx):
    # Boilerplate: resource list placeholder
    embed = discord.Embed(title="Deaf Resources", description="(TODO) Add curated links/resources.", color=0x00FF00)
    embed.add_field(name="Organizations", value="(TODO) Add org links here.", inline=False)
    embed.add_field(name="Learning", value="(TODO) Add learning links here.", inline=False)
    embed.add_field(name="Community", value="(TODO) Add community links here.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="nd-resources")
async def nd_resources(ctx):
    # Boilerplate: resource list placeholder
    embed = discord.Embed(
        title="Neurodivergent Resources",
        description="(TODO) Add resources/tips for supporting neurodivergent folks.",
        color=0x00FF00,
    )
    embed.add_field(name="Practical tips", value="(TODO) Add tips here.", inline=False)
    embed.add_field(name="Resources", value="(TODO) Add links here.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="deaf-history")
async def deaf_history(ctx):
    # Boilerplate: short summary placeholder
    embed = discord.Embed(title="Deaf History (Brief)", color=0x00FF00)
    embed.add_field(
        name="Overview",
        value="(TODO) Add a brief history summary here (key milestones, culture, education, etc.).",
        inline=False,
    )
    await ctx.send(embed=embed)

@bot.command(name="practice-rooms")
async def practice_rooms(ctx):
    # Boilerplate: explain what practice rooms are + simple guidelines
    embed = discord.Embed(title="Practice Rooms", color=0x00FF00)
    embed.add_field(
        name="What happens here?",
        value="(TODO) Explain how your server's practice rooms work.",
        inline=False,
    )
    embed.add_field(
        name="Quick guidelines",
        value="(TODO) Add etiquette (turn-taking, voice/text rules, encouragement, etc.).",
        inline=False,
    )
    await ctx.send(embed=embed)

@bot.command(name="practice-games")
async def practice_games(ctx):
    # Boilerplate: list of game ideas
    embed = discord.Embed(title="Practice Games", color=0x00FF00)
    embed.add_field(name="Charades", value="(TODO) Describe how to play in ASL.", inline=False)
    embed.add_field(name="20 Questions", value="(TODO) ASL-friendly rules/tips.", inline=False)
    embed.add_field(name="Story chain", value="(TODO) One sentence/sign at a time.", inline=False)
    await ctx.send(embed=embed)

@bot.command(name="ai-translations")
async def ai_translations(ctx):
    # Boilerplate: explain your stance + encourage best practices
    embed = discord.Embed(title="Why we typically don't promote AI Translation apps", color=0x00FF00)
    embed.add_field(
        name="Short version",
        value="(TODO) Add your explanation (accuracy, nuance, context, privacy, etc.).",
        inline=False,
    )
    embed.add_field(
        name="Better alternatives",
        value="(TODO) Suggest learning resources and/or working with qualified humans.",
        inline=False,
    )
    await ctx.send(embed=embed)


def is_owner_check():
    async def predicate(ctx: commands.Context) -> bool:
        return OWNER_ID != 0 and ctx.author.id == OWNER_ID
    return commands.check(predicate)


@bot.command(name="update-dicts")
@is_owner_check()
async def update_dicts(ctx):
    """Owner-only: manually update Handspeak/Lifeprint dictionary files."""
    await ctx.send("Starting dictionary update (this may take a bit)...")

    try:
        handspeak_result = await asyncio.to_thread(web_scrape.update_handspeak_dict, max_new=2000)
        lifeprint_result = await asyncio.to_thread(web_scrape.update_lifeprint_dict)

        await ctx.send(
            "Dictionary update complete.\n"
            f"Handspeak: {handspeak_result}\n"
            f"Lifeprint: {lifeprint_result}"
        )
    except Exception as e:
        print(traceback.format_exc())
        await ctx.send(f"Dictionary update failed: {e}")


@update_dicts.error
async def update_dicts_error(ctx, error):
    # Hide the command from non-owner users (no noisy error message)
    if isinstance(error, commands.CheckFailure):
        return
    print(traceback.format_exc())
    await ctx.send(f"An error occurred: {error}")

# -----------------------------
# Daily task configuration + history
# -----------------------------
_DAILY_TASK_CONFIG_PATH = "daily-task-config.json"
_DAILY_TASK_HISTORY_PATH = "daily-word-history.json"
_daily_loop_started = False


def _load_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            obj = json.load(f)
            return obj if isinstance(obj, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_json(path: str, obj: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def _get_guild_cfg(guild_id: int) -> dict:
    cfg = _load_json(_DAILY_TASK_CONFIG_PATH)
    guilds = cfg.setdefault("guilds", {})
    return guilds.setdefault(str(guild_id), {"enabled": False, "channel_id": None})


def _set_guild_cfg(guild_id: int, gcfg: dict) -> None:
    cfg = _load_json(_DAILY_TASK_CONFIG_PATH)
    cfg.setdefault("guilds", {})[str(guild_id)] = gcfg
    _save_json(_DAILY_TASK_CONFIG_PATH, cfg)


def _get_guild_history(guild_id: int) -> list[dict]:
    hist = _load_json(_DAILY_TASK_HISTORY_PATH)
    return hist.setdefault("guilds", {}).setdefault(str(guild_id), [])


def _append_guild_history(guild_id: int, items: list[dict]) -> None:
    hist = _load_json(_DAILY_TASK_HISTORY_PATH)
    guilds = hist.setdefault("guilds", {})
    arr = guilds.setdefault(str(guild_id), [])
    arr.extend(items)
    _save_json(_DAILY_TASK_HISTORY_PATH, hist)


async def _is_server_owner(ctx: commands.Context) -> bool:
    return ctx.guild is not None and ctx.author.id == ctx.guild.owner_id


def server_owner_check():
    return commands.check(_is_server_owner)


@tasks.loop(hours=24)
async def daily_word_loop():
    """
    Runs daily. If enabled, posts a random word that hasn't been used in the last year.
    """
    for guild in bot.guilds:
        gcfg = _get_guild_cfg(guild.id)
        if not gcfg.get("enabled"):
            continue

        channel_id = gcfg.get("channel_id")
        if not channel_id:
            continue

        channel = guild.get_channel(int(channel_id))
        if channel is None:
            continue

        try:
            history = _get_guild_history(guild.id)
            exclude_urls = web_scrape.urls_used_within_days(history, days=365)

            handspeak_entries = web_scrape.load_dictionary_entries(web_scrape.HAND_SPEAK_DICT_PATH)
            lifeprint_entries = web_scrape.load_dictionary_entries(web_scrape.LIFEPRINT_DICT_PATH)

            message, used = web_scrape.build_daily_word_post(
                handspeak_entries=handspeak_entries,
                lifeprint_entries=lifeprint_entries,
                exclude_urls=exclude_urls,
            )

            await channel.send(message)

            if used:
                now_iso = datetime.utcnow().isoformat()
                history_items = [{"ts": now_iso, **u} for u in used]
                _append_guild_history(guild.id, history_items)

        except Exception:
            print(traceback.format_exc())


@bot.command(name="daily-set-channel")
@server_owner_check()
async def daily_set_channel(ctx, channel: discord.TextChannel):
    gcfg = _get_guild_cfg(ctx.guild.id)
    gcfg["channel_id"] = channel.id
    _set_guild_cfg(ctx.guild.id, gcfg)
    await ctx.send(f"Daily word channel set to {channel.mention}.")


@bot.command(name="daily-on")
@server_owner_check()
async def daily_on(ctx):
    gcfg = _get_guild_cfg(ctx.guild.id)
    if not gcfg.get("channel_id"):
        await ctx.send("Please set a channel first: `!daily-set-channel #your-channel`")
        return
    gcfg["enabled"] = True
    _set_guild_cfg(ctx.guild.id, gcfg)
    await ctx.send("Daily word is now ON.")


@bot.command(name="daily-off")
@server_owner_check()
async def daily_off(ctx):
    gcfg = _get_guild_cfg(ctx.guild.id)
    gcfg["enabled"] = False
    _set_guild_cfg(ctx.guild.id, gcfg)
    await ctx.send("Daily word is now OFF.")


@bot.command(name="daily-status")
@server_owner_check()
async def daily_status(ctx):
    gcfg = _get_guild_cfg(ctx.guild.id)
    enabled = gcfg.get("enabled", False)
    channel_id = gcfg.get("channel_id")

    if channel_id:
        ch = ctx.guild.get_channel(int(channel_id))
        ch_text = ch.mention if ch else f"(channel id {channel_id}, not found)"
    else:
        ch_text = "(not set)"

    await ctx.send(f"Daily word status:\n- Enabled: **{enabled}**\n- Channel: {ch_text}")


@daily_set_channel.error
@daily_on.error
@daily_off.error
@daily_status.error
async def daily_config_errors(ctx, error):
    if isinstance(error, commands.CheckFailure):
        return
    if isinstance(error, commands.BadArgument):
        await ctx.send("Please mention a text channel.\nExample: `!daily-set-channel #general`")
        return
    print(traceback.format_exc())
    await ctx.send(f"An error occurred: {error}")


@bot.event
async def on_ready():
    global _daily_loop_started
    if not _daily_loop_started:
        daily_word_loop.start()
        _daily_loop_started = True
    print(f"Logged in as {bot.user}")



# Start the bot
bot.run(token, log_handler=handler, log_level=logging.DEBUG)