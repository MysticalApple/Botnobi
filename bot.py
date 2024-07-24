# Libraries I may or may not use
import contextlib
import csv
import io
import json
import math
import os
import platform
import random
import re
import sqlite3
import textwrap
import traceback
from datetime import datetime, timezone
from pathlib import Path
from time import sleep

import Levenshtein
import aiohttp
import discord
import feedparser
import gspread
from PIL import Image, ImageColor
from discord.ext import commands, tasks
from num2words import num2words

from utils.util import (config_get, config_set,
                        get_feeds_from_file, write_feeds_to_file, clean_code, )

cwd = Path(__file__).parents[0]
cwd = str(cwd)
print(f"{cwd}\n-----")

# Defines some stuff idk
secrets_file = json.load(open(cwd + "/secrets.json"))
command_prefix = "b:"
intents = discord.Intents.all()
bot = commands.Bot(command_prefix=command_prefix, intents=intents)
bot.config_token = secrets_file["token"]
us_words = []
rr_file = "reaction_roles.csv"
commit_feeds_file = "commitfeeds.txt"
google_creds_file = "google_credentials.json"
sqlConnection = sqlite3.connect("whois.db")
sqlPointer = sqlConnection.cursor()
sqlConnection.load_extension("sqlite-src/spellfix.so")

# Check if config.json has the required values
if config_get("server_id") is None:
    raise ValueError("server_id is not set in config.json")
if config_get("verification_sheet_url") is None:
    raise ValueError("verification_sheet_url is not set in config.json")

# Check if a database exists, if not, create one
sqlPointer.execute(
    "CREATE TABLE IF NOT EXISTS whois (user_id INTEGER PRIMARY KEY, first_name TEXT, last_name TEXT, email TEXT, "
    "discord_name TEXT,discord_display_name TEXT, server_join_date TEXT , school TEXT, graduation_year INTEGER, "
    "present INTEGER, opt_in INTEGER);")
sqlPointer.execute(
    "CREATE VIRTUAL TABLE IF NOT EXISTS discord_names USING spellfix1;")
sqlPointer.execute(
    "CREATE VIRTUAL TABLE IF NOT EXISTS discord_display_names USING spellfix1;")
sqlConnection.commit()


# Are yah ready kids?
@bot.event
async def on_ready():
    print(f"Logged in as: {bot.user.name} : {
          bot.user.id}\n-----\nCurrent prefix: '{command_prefix}'")
    with open("us_words.csv") as f:
        reader = csv.reader(f)
        for row in reader:
            us_words.append(row[0])

    await bot.change_presence(activity=discord.Game(name="Undergoing Renovations"))
    update_commit_feed.start()
    await sync_data()
    await set_user_status()
    print("All data synced")


async def fetch_remote():
    gc = gspread.service_account(filename=google_creds_file)
    gsheet = gc.open_by_url(config_get("verification_sheet_url"))
    sheet = gsheet.sheet1
    records = sheet.get_all_records()
    return records


async def fetch_local():
    db = []
    sqlPointer.execute("SELECT * FROM whois")
    for records in sqlPointer.fetchall():
        user_data = {"Timestamp": records[5], "Email Address": records[3], "First Name": records[1],
                     "Last Name": records[2], "School": records[6], "Graduation Year": records[7],
                     "UUID (do NOT change)": records[0]}
        db.append(user_data)
    return db


async def get_diff():
    remote = await fetch_remote()
    local = await fetch_local()
    diff_add = []
    diff_del = []
    for record in remote:
        if record not in local:
            diff_add.append(record)
    for record in local:
        if record not in remote:
            diff_del.append(record)
    diff = {"add": diff_add, "del": diff_del}
    return diff


@tasks.loop(minutes=10)
async def sync_data():
    diff = await get_diff()
    for element in diff["del"]:
        sqlPointer.execute("DELETE FROM whois WHERE user_id = ?", [
                           element["UUID (do NOT change)"]])
    for element in diff["add"]:
        discord_name_temp = bot.get_user(element["UUID (do NOT change)"])
        if discord_name_temp is None:
            discord_name = "unknown"
            discord_display_name = "unknown"
        else:
            discord_name = discord_name_temp.name
            discord_display_name = discord_name_temp.display_name
        user_info = (
            element["UUID (do NOT change)"], element["First Name"], element["Last Name"], element["Email Address"],
            discord_name, discord_display_name, element["Timestamp"], element["School"], element["Graduation Year"])
        sqlPointer.execute(
            "INSERT INTO whois (user_id, first_name, last_name, email, discord_name,discord_display_name, server_join_date, school, graduation_year) VALUES (?,?,?,?,?,?,?,?,?)",
            user_info)
    sqlConnection.commit()
    await set_user_status()
    await update_name_db()


async def set_user_status():
    guild = bot.get_guild(config_get("server_id"))
    role = discord.utils.get(guild.roles, name="b:whois opted-in")
    sqlPointer.execute("UPDATE whois SET opt_in = 0, present = 0")
    for member in bot.get_all_members():
        sqlPointer.execute(
            "Update whois SET present = 1 WHERE user_id = ?", [member.id])
        if role in member.roles:
            sqlPointer.execute(
                "Update whois SET opt_in = 1 WHERE user_id = ?", [member.id])
    sqlConnection.commit()


async def update_name_db():
    sqlPointer.execute("DELETE FROM discord_names")
    sqlPointer.execute("DELETE FROM discord_display_names")
    sqlPointer.execute(
        "INSERT INTO discord_names (word) SELECT discord_name FROM whois;")
    sqlPointer.execute(
        "INSERT INTO discord_display_names (word) SELECT discord_display_name FROM whois;")
    sqlConnection.commit()


@bot.command(name="sync_whois")
async def sync_whois(ctx):
    """
    Syncs the whois database with the Google sheet
    """
    await sync_data()
    await ctx.send("Synced!")


# Errors are not pog
@bot.event
async def on_command_error(ctx, error):
    ignored_errors = (commands.CommandNotFound, commands.UserInputError)
    if isinstance(error, ignored_errors):
        return

    if isinstance(error, commands.CheckFailure):
        await ctx.reply("Stop it. Get some perms.", mention_author=False)

    return error


# Runs something whenever a message is sent
@bot.event
async def on_message(message):
    # You are a bold one!
    if "hello there" in message.content.lower():
        await message.channel.send("General Kenobi!")

    # Pingus pongus
    if f"<@!{bot.user.id}>" in message.content or f"<@{bot.user.id}>" in message.content:
        await message.reply(f"pingus pongus your mother is {random.choice(us_words)}")

    # Says goodnight to henry
    henry = bot.get_user(289180942583463938)
    goodnight_message = "gn guys!"

    if message.author == henry and message.content.lower() == goodnight_message:
        sleep(1)
        await message.channel.send("gn Henry!")

    # Just because my knee hurts doesn't mean I have arthritis
    if "ow my knee" in message.content.lower():
        await message.reply(file=discord.File("owmyknee.png"), mention_author=False)

    await bot.process_commands(message)


# Reactions and stuff
@bot.event
async def on_raw_reaction_add(reaction):
    message = await bot.get_channel(reaction.channel_id).fetch_message(reaction.message_id)

    # Starboard
    star = "⭐"
    star_count = next(
        (r.count for r in message.reactions if r.emoji == star), 0)
    if star_count >= config_get("minimum_starboard_stars") and message.guild.id == 710932856251351111:
        starboard_messages = []
        with open("starboard.txt", "r") as file:
            starboard_messages = [
                int(message_id) for message_id in file.read().rstrip().split("\n")]

        if message.id not in starboard_messages:
            starboard_messages.append(message.id)
            with open("starboard.txt", "w") as file:
                file.write("\n".join([str(message_id)
                           for message_id in starboard_messages]))

            embed = discord.Embed(colour=message.author.colour,
                                  description=f"{message.content}\n\n[Click for context]({
                                      message.jump_url})",
                                  timestamp=message.created_at, )

            embed.set_author(name=message.author.display_name,
                             icon_url=message.author.avatar)
            embed.set_footer(text=f"{message.guild.name} | {
                             message.channel.name}")

            if message.attachments != [] and "image" in message.attachments[0].content_type:
                embed.set_image(url=message.attachments[0].url)

            await bot.get_channel(config_get("starboard_channel_id")).send(embed=embed)

    # Reaction Roles (adding)
    reaction_roles = []
    with open(rr_file, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            reaction_roles.append(row)

    for rr in reaction_roles:
        if message.id == int(rr["message_id"]) and str(reaction.emoji) == rr["emoji"]:
            await reaction.member.add_roles(message.guild.get_role(int(rr["role_id"])))


@bot.event
async def on_raw_reaction_remove(reaction):
    message = await bot.get_channel(reaction.channel_id).fetch_message(reaction.message_id)
    reaction.member = message.guild.get_member(reaction.user_id)

    # Reaction Roles (removing)
    reaction_roles = []
    with open(rr_file, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            reaction_roles.append(row)

    for rr in reaction_roles:
        if message.id == int(rr["message_id"]) and str(reaction.emoji) == rr["emoji"]:
            await reaction.member.remove_roles(message.guild.get_role(int(rr["role_id"])))


# Runs code whenever someone leaves the server
@bot.event
async def on_member_remove(member):
    # Checks that the leaver left the correct server
    if member.guild.id == 710932856251351111 and config_get("leave_log"):
        # Sets the channel to the one specified in config.json
        channel = bot.get_channel(config_get("alerts_channel_id"))
        join_date = member.joined_at

        # Creates an embed with info about who left and when
        # Format shamelessly stolen (and slightly changed) from https://github.com/ky28059
        embed = discord.Embed(description=f"{member.mention} {
                              member}", color=member.color, )

        embed.set_author(name="Member left the server", icon_url=member.avatar)
        embed.set_footer(
            text=f"Joined: {join_date.month}/{join_date.day}/{join_date.year}")

        # Sends it
        await channel.send(embed=embed)


# Github commit feeds
@tasks.loop(minutes=3)
async def update_commit_feed():
    feeds = get_feeds_from_file(commit_feeds_file)

    for feed in feeds:
        # Ignore old commits
        d = feedparser.parse(feed["link"])
        new_commits = [
            commit for commit in d.entries if commit.id not in feed["commits"]]
        feed["commits"].extend([commit.id for commit in new_commits])
        if not new_commits:
            continue

        # Prepare embed for sending (format stolen from https://github.com/Obi-Wan3/OB13-Cogs/blob/main/github/github.py
        channel = bot.get_channel(config_get("commits_channel_id"))

        count = len(new_commits)

        repo = d.feed.id.split("/")[-3]
        branch = d.feed.id.split("/")[-1]

        desc = ""
        for commit in new_commits:
            desc += f"[`{commit.link.split('/')[-1][:7]}`]({commit.link}) {
                commit.title} -- {commit.author}\n"

        embed = discord.Embed(title=f"[{repo}:{branch}] {count} new commit{'s' if count > 1 else ''}",
                              color=channel.guild.get_member(
                                  bot.user.id).color, description=desc,
                              url=feed["link"][:-5] if count > 1 else commit.link, )

        embed.timestamp = datetime.strptime(
            new_commits[0].updated, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)

        embed.set_author(name=new_commits[0].author, url=f"https://github.com/{new_commits[0].author}",
                         icon_url=new_commits[0].media_thumbnail[0]["url"], )

        await channel.send(embed=embed)

    write_feeds_to_file(commit_feeds_file, feeds)


# Command center
@bot.command(name="test")
async def test(ctx):
    """
    A simple test command
    """
    test_grades = ["an A", "a B", "a C", "a D", "an F"]

    await ctx.send(f"{ctx.author.mention} got {random.choice(test_grades)}")


@bot.command(name="info")
async def info(ctx):
    """
    Gives info about Botnobi
    """
    python_version = platform.python_version()
    dpy_version = discord.__version__
    server_count = len(bot.guilds)
    user_count = len(set(bot.get_all_members()))

    embed = discord.Embed(title=":information_source: Botnobi", description="\uFEFF", color=ctx.guild.me.color,
                          timestamp=ctx.message.created_at, )

    embed.add_field(name="<:github:1022443922133360640>",
                    value="[Repo](https://github.com/MysticalApple/Botnobi)", )
    embed.add_field(name="Python Version", value=python_version)
    embed.add_field(name="Discord.py Version", value=dpy_version)
    embed.add_field(name="Servers", value=server_count)
    embed.add_field(name="Users", value=user_count)
    embed.add_field(name="Bot Creator", value="<@!595719716560175149>")
    embed.add_field(name="Bot Maintainer", value="<@!1110811715169423381>")

    embed.set_footer(text="As of")
    embed.set_author(name=ctx.guild.me.display_name, icon_url=bot.user.avatar)

    await ctx.send(embed=embed)


@bot.command(name="disconnect")
@commands.is_owner()
async def disconnect(ctx):
    """
    Takes Botnobi offline
    """
    await ctx.send("Disconnecting...")
    await bot.close()


@bot.command(name="close")
@commands.is_owner()
async def close(ctx):
    """
    Alias for disconnect
    """
    await disconnect(ctx)


@bot.command(name="eval")
@commands.is_owner()
async def evaluate(ctx, *, code):
    """
    Runs python code
    """
    code = clean_code(code)

    local_variables = {"discord": discord,
                       "commands": commands, "bot": bot, "ctx": ctx}

    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(f"async def func():\n{textwrap.indent(
                code, '    ')}", local_variables)

            await local_variables["func"]()
            result = f"py\n‌{stdout.getvalue()}\n"

    except Exception as e:
        result = "".join(traceback.format_exception(e, e, e.__traceback__))

    await ctx.send(f"```{result}```")


@bot.command(name="sheep")
async def sheep(ctx):
    """
    Sends a sheep
    """
    await ctx.send("<a:seansheep:718186115294691482>```\n         ,ww\n   wWWWWWWW_)\n   `WWWWWW'\n    II  II```")


@bot.command(name="moo")
async def cow(ctx):
    await ctx.send(
        "```               _     _\n""              (_\\___( \\,\n""                )___   _  \n""               /( (_)-(_)    \n""    ,---------'         \\_\n""  //(  ',__,'      \\  (' ')\n"" //  )              '----'\n"" '' ; \\     .--.  ,/\n""    | )',_,'----( ;\n""    ||| '''     '||\n```The apt cow \n")


@bot.command(name="emotize")
async def emotize(ctx, *, message):
    """
    Converts text into discord emojis
    """
    output = ""

    for l in message:
        if l == " ":
            output += l
        elif l == "\n":
            output += l
        elif l.isdigit():
            numword = num2words(l)
            output += f":{numword}:"
        elif l.isalpha():
            l = l.lower()
            output += f":regional_indicator_{l}:"

    await ctx.send(output)


@bot.command(name="inspire")
async def inspire(ctx):
    """
    Uses InspiroBot to generate an inspirational quote"
    """
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            async with session.get("https://inspirobot.me/api?generate=true") as resp:
                r = await resp.text()
    await ctx.send(r)


@bot.command(name="color")
async def color(ctx, *, hex):
    """
    Sends a square of a solid color
    """
    try:
        color = ImageColor.getrgb(hex)

    except Exception:
        await ctx.reply(
            "Valid color codes can be found here: https://pillow.readthedocs.io/en/stable/reference/ImageColor.html",
            mention_author=False, )

    img = Image.new("RGBA", (480, 480), color=color)
    img.save("color.png")
    await ctx.send(file=discord.File("color.png"))


@bot.command(name="stackify")
async def stackify(ctx, count: int):
    """
    Converts an item count into Minecraft stacks
    """
    stacks = math.floor(count / 64)
    items = count % 64
    await ctx.send(f"{count} items can fit into {stacks} stacks and {items} items.")


@bot.command(name="shulkify")
async def shulkify(ctx, count: int):
    """
    Converts an item count into Minecraft shulkers (and stacks)
    """
    shulkers = math.floor(count / 64 / 27)
    stacks = math.floor(count / 64) % 27
    items = count % 64
    await ctx.send(f"{count} items can fit into {shulkers} shulkers, {stacks} stacks, and {items} items.")


@bot.command(name="toggle")
# Checks that user is Harvite
@commands.has_role(999078830973136977)
async def toggle(ctx, feature):
    """
    Toggles any boolean value in config.json
    """

    # Loads in config.json as a dict
    with open("config.json", "r") as config_file:
        config = json.load(config_file)

    # Toggles the value if it is a valid bool
    try:
        if isinstance(config[feature], bool):
            config[feature] = not config[feature]

            with open("config.json", "w") as config_file:
                json.dump(config, config_file)

            await ctx.send(f"{feature} has been toggled to {config[feature]}")

        else:
            raise ValueError

    # Returns an error if the value is not a bool or if it does not exist
    except Exception:
        await ctx.send(f"{feature} is not a valid toggleable value")


@bot.command(name="configset")
# Checks that user is Harvite
@commands.has_role(999078830973136977)
async def configset(ctx, feature, value):
    """
    Sets any value in config.json
    """
    try:
        config_set(feature, value)
        await ctx.send("I think it worked")

    except Exception:
        await ctx.send("Something went wrong")


@bot.command(name="delete")
@commands.is_owner()
async def delete(ctx, channel_id: int, message_id: int):
    """
    Deletes a specified message in a specified channel
    """
    channel = bot.get_channel(channel_id)
    message = await channel.fetch_message(message_id)
    await message.delete()


@bot.command(name="perlin")
async def perlin(ctx):
    """
    Generates random perlin noise
    """
    seed = random.randint(-128, 128)
    os.system(f"./perlin {seed}")

    perlin = Image.open("perlin.ppm")
    perlin.save("perlin.png")

    await ctx.send(file=discord.File("perlin.png"))


@bot.command(name="inrole")
async def inrole(ctx, *, given_role):
    """
    Lists members of a given role
    """
    members = []
    for member in ctx.guild.members:
        for role in member.roles:
            if (role.name == given_role) or (str(role.id) == given_role):
                members.append(member.name)

    member_list = "\n".join(members)
    if len(member_list) > 1990:
        await ctx.send("```Too many members in role```")
        return

    await ctx.send("```\n" + member_list + "```")


@bot.command(name="reactionrole")
# Checks that user is Harvite
@commands.has_role(999078830973136977)
async def reactionrole(ctx, message_id: int, emoji, role_id: int):
    """
    Adds a reaction role
    """
    with open(rr_file, "a") as csv_file:
        csv.writer(csv_file).writerow([message_id, emoji, role_id])

    await ctx.reply("Successfully added reaction role.", mention_author=False)


@bot.command(name="addrepo")
async def addrepo(ctx, link):
    """
    Adds a github repository to be tracked for commits
    """
    github_repo_pattern = r"^https?://github\.com/[\w-]+/[\w-]+/$"
    if not re.match(github_repo_pattern, link):
        await ctx.reply("That's not a valid GitHub repository link!")
        return

    feeds = get_feeds_from_file(commit_feeds_file)

    d = feedparser.parse(link + "commits.atom")
    commit_ids = [commit.id for commit in d.entries]

    new_feed = {"link": link + "commits.atom", "commits": commit_ids}
    feeds.append(new_feed)

    write_feeds_to_file(commit_feeds_file, feeds)

    await ctx.reply("Added!")


@bot.command(name="whois")
async def whois(ctx, pram):
    """
    Looks up a user in the whois database
    """
    pattern = re.compile("(<@|>)")
    if pattern.match(pram):
        pram = re.sub('(<@|>)', '', pram)
        sqlPointer.execute(
            "SELECT * FROM whois WHERE user_id = ? AND opt_in = 1", [pram])
        result = sqlPointer.fetchone()
        await send_embed(ctx, result)
    else:
        sqlPointer.execute(
            "SELECT * FROM whois WHERE discord_name LIKE ? AND opt_in = 1", ['%' + pram + '%'])
        result = sqlPointer.fetchone()
        if result is None:
            sqlPointer.execute("SELECT * FROM whois WHERE discord_display_name LIKE ? AND opt_in = 1",
                               ['%' + pram + '%'])
            result = sqlPointer.fetchone()
            if result is None:
                await fuzzy_find_discord_name(ctx, pram)
                return
            await send_embed(ctx, result)
        await send_embed(ctx, result)


async def send_embed(ctx, result):
    if result is None:
        await ctx.send("User not found, or has not opted in")
        return
    if result[9] == 0:
        await ctx.send("User is not in the server, placeholder msg")
        return
    user = await bot.fetch_user(result[0])
    embed = discord.Embed(colour=user.accent_colour,
                          title=f"{config_get('school_name')} Search result (`{
                              ctx.message.content.split(' ')[0]}`)",
                          description=f"This is an exact match for <@{result[0]}>")
    embed.set_thumbnail(url=user.avatar)
    embed.add_field(name="First Name", value=result[1])
    embed.add_field(name="Last Name", value=result[2])
    embed.add_field(name="Email", value=result[3])
    embed.add_field(name="Discord Username", value=result[4])
    embed.add_field(name="Discord Display Name", value=f"<@{result[0]}>")
    embed.add_field(name="Server Join Date", value=result[6])
    embed.add_field(name="School", value=result[7])
    embed.add_field(name="Graduation Year", value=result[8])
    await ctx.send(embed=embed, allowed_mentions=False)


async def fuzzy_find_discord_name(ctx, pram):
    return_val = []
    levenshtein_limit = math.ceil(len(pram) / 3 * 100)
    sqlPointer.execute("SELECT word FROM discord_display_names WHERE editdist3(lower(word), ?) < ?",
                       [pram.lower(), levenshtein_limit])
    result = sqlPointer.fetchall()
    for data in result:
        return_val.append(
            (Levenshtein.ratio(data[0].lower(), pram.lower()), data[0], "display_name"))
    sqlPointer.execute("SELECT word FROM discord_names WHERE editdist3(lower(word), ?) < ?",
                       [pram.lower(), levenshtein_limit])
    result = sqlPointer.fetchall()
    for data in result:
        return_val.append(
            (Levenshtein.ratio(data[0].lower(), pram.lower()), data[0], "user_name"))
    return_val.sort(key=lambda tup: tup[0], reverse=True)
    # Get top 5 results
    return_val = return_val[:10]
    if not return_val:
        await ctx.send("No user found, or has not opted in to the whois database")
        return
    top_result = return_val[0]
    if top_result[2] == "display_name":
        sqlPointer.execute(
            "SELECT * FROM whois WHERE discord_display_name = ? AND opt_in = 1", [top_result[1]])
    else:
        sqlPointer.execute(
            "SELECT * FROM whois WHERE discord_name = ? AND opt_in = 1", [top_result[1]])
    top_result = sqlPointer.fetchone()
    if top_result is None:
        await ctx.send("No user found, or has not opted in to the whois database")
        return
    user = await bot.fetch_user(top_result[0])
    embed = discord.Embed(colour=user.accent_colour,
                          title=f"{config_get('school_name')} Fuzzy Search result (`{
                              ctx.message.content.split(' ')[0]}`)",
                          description=f"Top results for`{pram}`")
    embed.add_field(name="Levenshtein ratio",
                    value=return_val[0][0], inline=False)
    embed.add_field(name="First Name", value=top_result[1])
    embed.add_field(name="Last Name", value=top_result[2])
    embed.add_field(name="Email", value=top_result[3])
    embed.add_field(name="Discord Username", value=top_result[4])
    embed.add_field(name="Discord Display Name", value=f"<@{top_result[0]}>")
    embed.add_field(name="Server Join Date", value=top_result[6])
    embed.add_field(name="School", value=top_result[7])
    embed.add_field(name="Graduation Year", value=top_result[8])
    return_val = return_val[1:]
    for data in return_val:
        if data[2] == "display_name":
            sqlPointer.execute(
                "SELECT * FROM whois WHERE discord_display_name = ? AND opt_in = 1", [data[1]])
        else:
            sqlPointer.execute(
                "SELECT * FROM whois WHERE discord_name = ? AND opt_in = 1", [data[1]])
        result = sqlPointer.fetchone()
        embed.add_field(name="Other Matches",
                        value=f"<@{result[0]}>, Levenshtein ratio: {data[0]}", inline=False)
    await ctx.send(embed=embed, allowed_mentions=False)


bot.run(bot.config_token)
