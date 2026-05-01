import discord
from discord import app_commands
from discord.ext import commands

from config import ANONYMOUS_FORUM_CHANNEL_ID, STAFF_LOG_CHANNEL_ID, TITLE_PREFIX
from utils.forum_formatting import build_anonymous_forum_post, build_staff_log


class AnonymousForumModal(discord.ui.Modal, title="Anonymous Forum Submission"):
    general_location = discord.ui.TextInput(
        label="General location",
        placeholder="Example: East TN, online, school, workplace, etc.",
        max_length=100,
        required=True,
    )

    situation = discord.ui.TextInput(
        label="Short title / situation",
        placeholder="Example: Need advice about an ASL class issue",
        max_length=100,
        required=True,
    )

    details = discord.ui.TextInput(
        label="Details",
        placeholder="Share the information you want posted anonymously.",
        style=discord.TextStyle.paragraph,
        max_length=1500,
        required=True,
    )

    def __init__(self, bot: commands.Bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        forum_channel = interaction.guild.get_channel(ANONYMOUS_FORUM_CHANNEL_ID)
        staff_log_channel = interaction.guild.get_channel(STAFF_LOG_CHANNEL_ID)

        if forum_channel is None:
            await interaction.response.send_message(
                "The anonymous forum channel could not be found.",
                ephemeral=True,
            )
            return

        if not isinstance(forum_channel, discord.ForumChannel):
            await interaction.response.send_message(
                "The configured channel is not a forum channel.",
                ephemeral=True,
            )
            return

        title = f"{TITLE_PREFIX}: {self.situation.value}"

        post_body = build_anonymous_forum_post(
            general_location=self.general_location.value,
            situation=self.situation.value,
            details=self.details.value,
        )

        try:
            thread, starter_message = await forum_channel.create_thread(
                name=title[:100],
                content=post_body,
                reason=f"Anonymous submission by {interaction.user} ({interaction.user.id})",
            )

            await interaction.response.send_message(
                "Your anonymous post has been submitted.",
                ephemeral=True,
            )

            if staff_log_channel is not None:
                staff_log = build_staff_log(
                    submitter_id=interaction.user.id,
                    submitter_name=str(interaction.user),
                    thread_url=thread.jump_url,
                    general_location=self.general_location.value,
                    situation=self.situation.value,
                    details=self.details.value,
                )

                await staff_log_channel.send(staff_log)

        except discord.Forbidden:
            await interaction.response.send_message(
                "I do not have permission to create posts in that forum.",
                ephemeral=True,
            )

        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Something went wrong while creating the post: `{e}`",
                ephemeral=True,
            )


class AnonymousForum(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="anonymous_submit",
        description="Submit information anonymously to the forum."
    )
    async def anonymous_submit(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AnonymousForumModal(self.bot))


async def setup(bot: commands.Bot):
    await bot.add_cog(AnonymousForum(bot))