from __future__ import annotations

from datetime import datetime

import discord
from discord.ext import commands

from .shared import log_error


class Feedback(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.hybrid_command(name="feedback", description="Send feedback to the bot developer")
    async def feedback(self, ctx: commands.Context, *, message: str):
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
                thread = await starter.create_thread(name=thread_name, auto_archive_duration=1440)

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


async def setup(bot: commands.Bot):
    await bot.add_cog(Feedback(bot))
