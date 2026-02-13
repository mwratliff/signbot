import logging
import os

import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env into the process.
load_dotenv()

# Read the bot token from environment configuration.
TOKEN = os.getenv("DISCORD_TOKEN")

# Configure a log file for Discord internals.
handler = logging.FileHandler(filename="discord.log", encoding="utf-8", mode="w")

# Enable message content intent so text commands can be read.
intents = discord.Intents.default()
intents.message_content = True

# Create the Discord bot with prefix commands and slash commands.
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)


@bot.event
# Handle startup tasks once Discord reports the bot is ready.
async def on_ready():
    # Wait for global slash commands to sync with Discord.
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")


# Start the bot and load the command extension.
async def main():
    # Keep bot resources open for the lifetime of the app.
    async with bot:
        # Wait for the commands extension module to register cogs.
        await bot.load_extension("commands")
        # Wait for the bot connection loop until shutdown.
        await bot.start(TOKEN)


# Run the async entry point when this file is executed directly.
if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
