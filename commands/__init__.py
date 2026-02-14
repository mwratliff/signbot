from __future__ import annotations

from discord.ext import commands

EXTENSIONS = [
    "commands.core",
    "commands.sign_lookup",
    "commands.daily_admin",
    "commands.feedback",
]


async def setup(bot: commands.Bot):
    for ext in EXTENSIONS:
        await bot.load_extension(ext)
