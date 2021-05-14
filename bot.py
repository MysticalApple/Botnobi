# Libraries i may or may not use
import discord
from discord.ext import commands
import logging
from pathlib import Path
import json
import random
import platform

cwd = Path(__file__).parents[0]
cwd = str(cwd)
print(f"{cwd}\n-----")

# Defines some stuff idk
private_file = json.load(open(cwd+'/bot_config/private.json'))
command_prefix = "b:"
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=command_prefix, intents=intents)
bot.config_token = private_file['token']
logging.basicConfig(level=logging.INFO)

# Are yah ready kids?
@bot.event
async def on_ready():
    print(f"-----\nLogged in as: {bot.user.name} : {bot.user.id}\n-----\nCurrent prefix: '{command_prefix}'")

    await bot.change_presence(activity=discord.Game(name='Undergoing Renovations'))

# Command center
@bot.command(name='test')
async def test(ctx):
    """
    A simple test command
    """
    test_grades = ["an A","a B","a C","a D","an F"]

    await ctx.send(f"{ctx.author.mention} got {random.choice(test_grades)}")

@bot.command(name='info')
async def info(ctx):
    """
    Gives info about Botnobi
    """
    python_version = platform.python_version()
    dpy_version = discord.__version__
    server_count = len(bot.guilds)
    member_count = len(set(bot.get_all_members()))

    await ctx.send(f"Botnobi is in {server_count} servers and knows about {member_count} unique users.\nRunning discord.py {dpy_version} and Python {python_version}")

@bot.command(aliases=['dc,disconnect,logout'])
@commands.is_owner()
async def disconnect(ctx):
    """
    Takes Botnobi offline
    """
    await ctx.send('Disconnecting...')
    await bot.logout()

@disconnect.error
async def logout_error(ctx, error):
    """
    Prevents you peasants from spamming my logs
    """
    if isinstance(error, commands.CheckFailure):
        await ctx.send(f"!ban {ctx.author.mention} for trying to mess with Botnobi")
    else:
        raise error


# Run the damn thing already
bot.run(bot.config_token)