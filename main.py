import discord
from discord import app_commands
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import Paginator
import web_scrape
from web_scrape import perform_web_search

load_dotenv()
token = os.getenv("DISCORD_TOKEN")

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents, help_command=None)

#@bot.event
#async def on_ready():
#    print(f'{bot.user.name} has connected to Discord!')

#@bot.event
#async def on_member_join(member):
#    await member.send("Welcome!")

#@bot.event
#async def on_message(message):
#    if message.author == bot.user:
#        return

@bot.command()
async def parameters(ctx, arg: discord.Member = commands.Author):

    await ctx.send(f"{arg.mention}"
                   f"\n### The 5 Sign Parameters"
                   f"\n- [Handshape](<https://www.lifeprint.com/asl101/pages-layout/handshapes.htm>)"
                   f"\n- [Palm Orientation](<https://books.openbookpublishers.com/10.11647/obp.0205/ch12.xhtml>)"
                   f"\n- [Location](<https://en.wikipedia.org/wiki/Location_(sign_language)>)"
                   f"\n- Movement: Which way the hand moves, away from body, towards body, motionless, circular, etc."
                   f"\n- [Non-Manual Markers](<https://www.lifeprint.com/asl101/pages-layout/nonmanualmarkers.htm>): Facial expressions and body movements that accompany the sign"
                   f"\n### Learn More About Sign Parameters"
                   f"\n- [LifePrint](<https://www.lifeprint.com/asl101/topics/parameters-asl.htm>)"
                   f"\n- [HandSpeak](<https://www.handspeak.com/learn/index.php?id=397>)")
    pass

@bot.command()
# Bring up a list of commands that can be used - if user does command again to get more information about each command, add a subcommand
async def asl_help(ctx):
    #limit each page to 4 commands max
    page1 = discord.Embed(title="Sign Bot Help", description="Here's a list of commands that can be used", color=0x00ff00)
    page1.add_field(name="!parameters", value="Shows the 5 Sign Parameters", inline=False)
    page1.add_field(name="!sign_help", value="Shows how to sign a word", inline=False)
    page1.add_field(name="!deaf_history", value="Shows a brief history of deaf culture", inline=False)
    page1.add_field(name="!nd_resources", value="Shows a list of resources on how to help neurodivergent individuals", inline=False)
    page2 = discord.Embed(title="", description="", color=0x00ff00)
    page2.add_field(name="!fluency_level", value="A brief list of fluency levels for ASL", inline=False)
    page2.add_field(name="!asl_resources", value="A list of resources on ASL", inline=False)
    page2.add_field(name="!practice_rooms", value="Explains what happens in practice rooms", inline=False)
    page2.add_field(name="!ai_translations", value="Why we typically don't promote AI Translation apps", inline=False)

    embeds = [page1, page2]
    await Paginator.Simple().start(ctx, pages=embeds)
    pass

@bot.command(name="sign_help")
async def sign_help(ctx, word):
    # search LifePrint, HandSpeak, SigningSavvy, etc. for word
    await ctx.send("Searching the web for "+word)
    search_results = perform_web_search(query=word)
    await ctx.send(search_results)

@sign_help.error
async def sign_help_error(ctx, error: commands.MissingRequiredArgument):
    await ctx.send("Please type a word to search!"
                   "\nExample: !sign_help hello")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)