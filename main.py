import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env into the process.
load_dotenv()

# Read the bot token from environment configuration.
TOKEN = os.getenv("DISCORD_TOKEN")

DEV_GUILD_ID = 1469744304711930145

# Configure a log file for Discord internals.
from paths import DISCORD_LOG_PATH
DISCORD_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

handler = logging.FileHandler(filename=str(DISCORD_LOG_PATH), encoding="utf-8", mode="w")
discord.utils.setup_logging(handler=handler, level=logging.INFO)


# Enable message content intent so text commands can be read.
intents = discord.Intents.default()
intents.message_content = True

# Create the Discord bot with prefix commands and slash commands.
APP_ID = os.getenv("DISCORD_APP_ID")

class MyBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def setup_hook(self):
        await self.load_extension("commands")

        # ✅ ONE-TIME global cleanup (removes old global slash commands that cause duplicates)
        if os.getenv("NUKE_GLOBAL_COMMANDS", "0") == "1":
            self.tree.clear_commands(guild=None)   # clear local global tree
            await self.tree.sync()                 # push empty global set to Discord
            print("🧨 Removed ALL global application commands from Discord.")

        # ✅ Dev guild sync (fast iteration)
        guild = discord.Object(id=DEV_GUILD_ID)
        self.tree.clear_commands(guild=guild)      # wipe guild commands first
        self.tree.copy_global_to(guild=guild)      # copy current in-code commands into guild
        await self.tree.sync(guild=guild)
        print(f"✅ Clean synced commands to guild {DEV_GUILD_ID}")

bot = MyBot(
    command_prefix="!",
    intents=intents,
    help_command=None,
    application_id=APP_ID,
)

# Start the bot and load the command extension.
async def main():
    async with bot:
        await bot.start(TOKEN)



# Run the async entry point when this file is executed directly.
if __name__ == "__main__":
    import asyncio

    # Use selector policy on Windows for cleaner shutdown behavior.
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    try:
        asyncio.run(main())
    # Exit cleanly when the process is interrupted (Ctrl+C).
    except KeyboardInterrupt:
        print("Bot shutdown requested. Exiting cleanly.")


@bot.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        print(f"Bot didn't respond to: {ctx.message.content}")
        # Optionally reply to the user
        await ctx.send("Command doesn't exist.")
    else:
        print(f"Command Error: {error}")