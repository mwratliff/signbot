import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env into the process.
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

# Your personal/dev guild for fast command iteration + receiving reports
DEV_GUILD_ID = os.getenv("DEV_GUILD_ID", "1469744304711930145")

# Application ID MUST be an int (discord.py will choke on a string)
APP_ID_RAW = os.getenv("DISCORD_APP_ID")
APP_ID = int(APP_ID_RAW) if APP_ID_RAW else None
if APP_ID is None:
    raise RuntimeError("DISCORD_APP_ID is missing. Put it in your .env as a number.")

# Configure a log file for Discord internals.
from paths import DISCORD_LOG_PATH
DISCORD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

handler = logging.FileHandler(filename=str(DISCORD_LOG_PATH), encoding="utf-8", mode="w")
discord.utils.setup_logging(handler=handler, level=logging.INFO)

# Enable message content intent so text commands can be read.
intents = discord.Intents.default()
intents.message_content = True

# Env toggles:
# - SYNC_GLOBAL_COMMANDS=1 -> sync commands globally (needed for other servers to see /commands)
# - NUKE_GLOBAL_COMMANDS=1 -> wipes ALL global commands (one-time cleanup if you had duplicates)
SYNC_GLOBAL = os.getenv("SYNC_GLOBAL_COMMANDS", "0") == "1"
NUKE_GLOBAL = os.getenv("NUKE_GLOBAL_COMMANDS", "0") == "1"


class MyBot(commands.Bot):
    async def setup_hook(self):
        print("loading extension...")
        await self.load_extension("commands")
        print("loaded extension.")

        # ✅ ONE-TIME global cleanup (removes old global slash commands that cause duplicates)
        if NUKE_GLOBAL:
            self.tree.clear_commands(guild=None)
            await self.tree.sync()
            print("🧨 Removed ALL global application commands from Discord (global).")
            # Do NOT keep this on, or you'll keep wiping your globals every restart.

        # ✅ GLOBAL SYNC (for other servers)
        # Only do this when you're ready. Global propagation can take time.
        if SYNC_GLOBAL:
            await self.tree.sync()
            print("✅ Synced commands globally (other servers will receive them).")
        else:
            print("ℹ️ Global sync skipped. Set SYNC_GLOBAL_COMMANDS=1 to enable.")

        # ✅ Dev guild sync (fast iteration & instant updates in your dev server)
        dev_guild = discord.Object(id=DEV_GUILD_ID)
        self.tree.clear_commands(guild=dev_guild)
        self.tree.copy_global_to(guild=dev_guild)
        await self.tree.sync(guild=dev_guild)
        print(f"✅ Clean synced commands to dev guild {DEV_GUILD_ID}")


bot = MyBot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    application_id=APP_ID,
)


async def main():
    async with bot:
        await bot.start(TOKEN)


if __name__ == "__main__":
    import asyncio

    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot shutdown requested. Exiting cleanly.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        print(f"Bot didn't respond to: {ctx.message.content}")
        await ctx.send("Command doesn't exist.")
    else:
        print(f"Command Error: {error}")
