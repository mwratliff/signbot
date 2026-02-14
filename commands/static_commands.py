from __future__ import annotations
from discord.ext import commands

# ============================
# ✅ STATIC LINK COMMANDS (EDIT HERE ONLY)
# ============================
STATIC_LINK_COMMANDS: dict[str, dict[str, str]] = {
    "rules": {
        "description": "View the server rules.",
        "message": ":scroll:**Server Rules**\nRead them here:\nhttps://discord.com/channels/566145505587888128/566146484173537281/1362438139095814365",
    },
    "fluency": {
        "description": "Learn more about fluency level",
        "message": "**Fluency**\nDetails here:\nhttps://discord.com/channels/566145505587888128/1430191460929769585/1430192787382468729",
    },
    "practice-rooms": {
        "description": "Practice Rooms",
        "message": ":raised_hands:**Practice Rooms**\nDescription:\nhttps://discord.com/channels/566145505587888128/1430191460929769585/1430204216760209448",
    },
    "resources": {
        "description": "Useful learning resources.",
        "message": ":books: **Resources**\nStart here:\nhttps://discord.com/channels/566145505587888128/1430191561442070638",
    },
    "deaf-culture": {
        "description": "Learn about Deaf Culture a bit!",
        "message": "**Deaf Culture**\nhttps://discord.com/channels/566145505587888128/1430191697924722709",
    },
    "deaf-resources-usa": {
        "description": "Learn how to best support Deaf peers in the USA!",
        "message": ":flag_us: **USA Deaf Support**\nThread here:\nhttps://discord.com/channels/566145505587888128/1430371522899476600",
    },
    "deaf-resources-ca": {
        "description": "Learn how to best support Deaf peers in Canada!",
        "message": ":flag_ca: **CA Deaf Support**\nThread here:\nhttps://discord.com/channels/566145505587888128/1430373535808880680",
    },
    "tonetags": {
        "description": "Learn more about tonetags and what they mean.",
        "message": "**Tone Tag Descriptions**\nThread here:\nhttps://discord.com/channels/566145505587888128/1430660544775458956/1430660547195441265",
    }
}

def _make_static_hybrid_command(name: str, description: str, message: str) -> commands.HybridCommand:
    # Keep callback signature minimal so slash parsing never gets confused
    async def _callback(ctx):
        await ctx.reply(message)

    return commands.hybrid_command(name=name, description=description)(_callback)


def register_static_link_commands(bot: commands.Bot) -> None:
    """
    Registers /rules, /faq, etc as top-level hybrid commands on the bot.

    Safe for extension reloads: removes old commands before re-adding.
    """
    for cmd_name, data in STATIC_LINK_COMMANDS.items():
        # If hot-reloading, remove existing command first
        existing = bot.get_command(cmd_name)
        if existing:
            bot.remove_command(cmd_name)

        cmd = _make_static_hybrid_command(
            name=cmd_name,
            description=data["description"],
            message=data["message"],
        )
        bot.add_command(cmd)
