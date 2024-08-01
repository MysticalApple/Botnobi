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

import aiohttp
import discord
import feedparser
import gspread
from PIL import Image, ImageColor
from discord.ext import commands, tasks
from fuzzywuzzy import fuzz
from num2words import num2words

from utils.util import (
    config_get,
    config_set,
    get_feeds_from_file,
    write_feeds_to_file,
    clean_code,
)

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
sql_pointer = sqlConnection.cursor()
sqlConnection.enable_load_extension(True)
sqlConnection.load_extension(os.path.abspath("spellfix-mirror/spellfix.so"))
sync_timer = None

# Check if config.json has the required values
if config_get("server_id") is None:
    raise ValueError("server_id is not set in config.json")
if config_get("verification_sheet_url") is None:
    raise ValueError("verification_sheet_url is not set in config.json")

# Check if a database exists, if not, create one
sql_pointer.execute(
    """
    CREATE TABLE IF NOT EXISTS whois (user_id INTEGER PRIMARY KEY,
    first_name TEXT, last_name TEXT, email TEXT,discord_name TEXT,
    discord_display_name TEXT, server_join_date TEXT, school TEXT,
    graduation_year INTEGER,present INTEGER DEFAULT 0 NOT NULL, opt_in
    INTEGER DEFAULT 0 NOT NULL );
    """
)
sqlConnection.commit()


# Are yah ready kids?
@bot.event
async def on_ready():
    print(
        f"Logged in as: {bot.user.name} : {bot.user.id}\n-----\nCurrent "
        f"prefix: '{command_prefix}'"
    )
    with open("us_words.csv") as f:
        reader = csv.reader(f)
        for row in reader:
            us_words.append(row[0])

    await bot.change_presence(
        activity=discord.Game(name="Undergoing Renovations")
    )
    update_commit_feed.start()
    sync_whois_data.start()
    await DEBUG()


async def fetch_remote():
    gc = gspread.service_account(filename=google_creds_file)
    gsheet = gc.open_by_url(config_get("verification_sheet_url"))
    sheet = gsheet.sheet1
    records = sheet.get_all_records()
    return records


async def fetch_local():
    sql_pointer.execute("SELECT * FROM whois")
    return [
        {
            "Timestamp": record[6],
            "Email Address": record[3],
            "First Name": record[1],
            "Last Name": record[2],
            "School": record[7],
            "Graduation Year": record[8],
            "UUID (do NOT change)": record[0],
        }
        for record in sql_pointer.fetchall()
    ]


async def get_diff():
    remote = await fetch_remote()
    local = await fetch_local()
    diff_add = [record for record in remote if record not in local]
    diff_del = [record for record in local if record not in remote]

    diff = {"add": diff_add, "del": diff_del}
    print(f"Additions: {len(diff['add'])}, Deletions: {len(diff['del'])}")
    return diff


@tasks.loop(minutes=60)
async def sync_whois_data():
    diff = await get_diff()
    for element in diff["del"]:
        sql_pointer.execute(
            "DELETE FROM whois WHERE user_id = ?;",
            [element["UUID (do NOT change)"]],
        )
    for element in diff["add"]:
        discord_user = bot.get_user(element["UUID (do NOT change)"])  # Cached
        if discord_user is None:  # Not cached
            try:
                discord_user = await bot.fetch_user(
                    int(element["UUID (do NOT change)"])
                )
            except discord.errors.NotFound:
                pass  # Happens when former users delete their accounts

        if discord_user is None:
            discord_name = "?"
            discord_display_name = "?"
        else:
            discord_name = discord_user.name
            discord_display_name = discord_user.display_name

        user_info = (
            element["UUID (do NOT change)"],
            element["First Name"],
            element["Last Name"],
            element["Email Address"],
            discord_name,
            discord_display_name,
            element["Timestamp"],
            element["School"],
            element["Graduation Year"],
        )
        sql_pointer.execute(  # IGNORE deals with duplicate entries
            """
            INSERT OR IGNORE INTO whois (
                user_id,
                first_name,
                last_name,
                email,
                discord_name,
                discord_display_name,
                server_join_date,
                school,
                graduation_year
            ) VALUES (?,?,?,?,?,?,?,?,?);
            """,
            user_info,
        )
        sqlConnection.commit()
    await set_user_status()
    print(f"All user data synced at {datetime.now()}")


async def set_user_status():
    guild = bot.get_guild(config_get("server_id"))
    role = discord.utils.get(guild.roles, name="b:whois opted-in")
    sql_pointer.execute("UPDATE whois SET present = 0")
    for member in guild.members:
        sql_pointer.execute(
            "Update whois SET present = 1, opt_in = ? WHERE user_id = ?",
            [1 if role in member.roles else 0, member.id],
        )

    sqlConnection.commit()


@bot.command(name="sync_whois")
async def sync_whois(ctx):
    """
    Syncs the whois database with the Google sheet
    Limited to once every 10 minutes.
    """
    if ctx.author.guild_permissions.administrator:
        await sync_whois_data()
        await ctx.send("Synced! Rate limit bypassed.")
        return
    global sync_timer
    if sync_timer is None:
        await sync_whois_data()
        sync_timer = datetime.now()
        await ctx.send("Synced!")
    elif (datetime.now() - sync_timer).seconds > 600:
        await sync_whois_data()
        sync_timer = datetime.now()
        await ctx.send("Synced!")
    else:
        next_sync = 600 - (datetime.now() - sync_timer).seconds
        await ctx.send(f"Rate limited. Try again in {next_sync} seconds.")


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
    if (
        f"<@!{bot.user.id}>" in message.content
        or f"<@{bot.user.id}>" in message.content
    ):
        await message.reply(
            f"pingus pongus your mother is {random.choice(us_words)}"
        )

    # Says goodnight to henry
    henry = bot.get_user(289180942583463938)
    goodnight_message = "gn guys!"

    if (
        message.author == henry
        and message.content.lower() == goodnight_message
    ):
        sleep(1)
        await message.channel.send("gn Henry!")

    # Just because my knee hurts doesn't mean I have arthritis
    if "ow my knee" in message.content.lower():
        await message.reply(
            file=discord.File("owmyknee.png"), mention_author=False
        )

    await bot.process_commands(message)


# Reactions and stuff
@bot.event
async def on_raw_reaction_add(reaction):
    message = await bot.get_channel(reaction.channel_id).fetch_message(
        reaction.message_id
    )

    # Starboard
    star = "⭐"
    star_count = next(
        (r.count for r in message.reactions if r.emoji == star), 0
    )
    if (
        star_count >= config_get("minimum_starboard_stars")
        and message.guild.id == 710932856251351111
    ):
        starboard_messages = []
        with open("starboard.txt", "r") as file:
            starboard_messages = [
                int(message_id)
                for message_id in file.read().rstrip().split("\n")
            ]

        if message.id not in starboard_messages:
            starboard_messages.append(message.id)
            with open("starboard.txt", "w") as file:
                file.write(
                    "\n".join(
                        [str(message_id) for message_id in starboard_messages]
                    )
                )

            embed = discord.Embed(
                colour=message.author.colour,
                description=f"{message.content}\n\n"
                f"[Click for context]({message.jump_url})",
                timestamp=message.created_at,
            )

            embed.set_author(
                name=message.author.display_name,
                icon_url=message.author.avatar,
            )
            embed.set_footer(
                text=f"{message.guild.name} | {message.channel.name}"
            )

            if (
                message.attachments != []
                and "image" in message.attachments[0].content_type
            ):
                embed.set_image(url=message.attachments[0].url)

            await bot.get_channel(config_get("starboard_channel_id")).send(
                embed=embed
            )

    # Reaction Roles (adding)
    reaction_roles = []
    with open(rr_file, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            reaction_roles.append(row)

    for rr in reaction_roles:
        if (
            message.id == int(rr["message_id"])
            and str(reaction.emoji) == rr["emoji"]
        ):
            await reaction.member.add_roles(
                message.guild.get_role(int(rr["role_id"]))
            )


@bot.event
async def on_raw_reaction_remove(reaction):
    message = await bot.get_channel(reaction.channel_id).fetch_message(
        reaction.message_id
    )
    reaction.member = message.guild.get_member(reaction.user_id)

    # Reaction Roles (removing)
    reaction_roles = []
    with open(rr_file, "r") as csv_file:
        csv_reader = csv.DictReader(csv_file)
        for row in csv_reader:
            reaction_roles.append(row)

    for rr in reaction_roles:
        if (
            message.id == int(rr["message_id"])
            and str(reaction.emoji) == rr["emoji"]
        ):
            await reaction.member.remove_roles(
                message.guild.get_role(int(rr["role_id"]))
            )


# Runs code whenever someone leaves the server
@bot.event
async def on_member_remove(member):
    # Checks that the leaver left the correct server
    if member.guild.id == 710932856251351111 and config_get("leave_log"):
        # Sets the channel to the one specified in config.json
        channel = bot.get_channel(config_get("alerts_channel_id"))
        join_date = member.joined_at

        # Creates an embed with info about who left and when Format
        # shamelessly stolen (and slightly changed) from
        # https://github.com/ky28059
        embed = discord.Embed(
            description=f"{member.mention} {member}",
            color=member.color,
        )

        embed.set_author(name="Member left the server", icon_url=member.avatar)
        embed.set_footer(
            text=f"Joined: {join_date.month}/{join_date.day}/{join_date.year}"
        )

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
            commit for commit in d.entries if commit.id not in feed["commits"]
        ]
        feed["commits"].extend([commit.id for commit in new_commits])
        if not new_commits:
            continue

        # Prepare embed for sending (format stolen from
        # https://github.com/Obi-Wan3/OB13-Cogs/blob/main/github/github.py
        channel = bot.get_channel(config_get("commits_channel_id"))

        count = len(new_commits)

        repo = d.feed.id.split("/")[-3]
        branch = d.feed.id.split("/")[-1]

        desc = ""
        for commit in new_commits:
            desc += (
                f"[`{commit.link.split('/')[-1][:7]}`]({commit.link}) "
                f"{commit.title} -- {commit.author}\n"
            )

        embed = discord.Embed(
            title=f"[{repo}:{branch}] {count} new commit"
            f"{'s' if count > 1 else ''}",
            color=channel.guild.get_member(bot.user.id).color,
            description=desc,
            url=feed["link"][:-5] if count > 1 else commit.link,
        )

        embed.timestamp = datetime.strptime(
            new_commits[0].updated, "%Y-%m-%dT%H:%M:%SZ"
        ).replace(tzinfo=timezone.utc)

        embed.set_author(
            name=new_commits[0].author,
            url=f"https://github.com/{new_commits[0].author}",
            icon_url=new_commits[0].media_thumbnail[0]["url"],
        )

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

    embed = discord.Embed(
        title=":information_source: Botnobi",
        description="",
        color=ctx.guild.me.color,
        timestamp=ctx.message.created_at,
    )

    embed.add_field(
        name="<:github:842921746277203978>",
        value="[Repo](https://github.com/MysticalApple/Botnobi)",
    )
    embed.add_field(name="Python Version", value=python_version)
    embed.add_field(name="Discord.py Version", value=dpy_version)
    embed.add_field(name="Servers", value=server_count)
    embed.add_field(name="Users", value=user_count)
    embed.add_field(
        name="Contributors",
        value="\n".join(
            [
                "<@595719716560175149>",
                "<@1110811715169423381>",
                "<@376423367731052575>",
            ]
            # Ordered by commits, add yourself if you contribute
        ),
    )

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

    local_variables = {
        "discord": discord,
        "commands": commands,
        "bot": bot,
        "ctx": ctx,
    }

    stdout = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout):
            exec(
                f"async def func():\n{textwrap.indent(code, '    ')}",
                local_variables,
            )

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
    await ctx.send(
        "<a:seansheep:718186115294691482>```\n         ,ww\n   wWWWWWWW_)\n  "
        " `WWWWWW'\n    II  II```"
    )


@bot.command(name="moo")
async def cow(ctx):
    """
    Sends a cow, the apt cow
    """
    await ctx.send(
        "```               _     _\n"
        "              (_\\___( \\,\n"
        "                )___   _  \n"
        "               /( (_)-(_)    \n"
        "    ,---------'         \\_\n"
        "  //(  ',__,'      \\  (' ')\n"
        " //  )              '----'\n"
        " '' ; \\     .--.  ,/\n"
        "    | )',_,'----( ;\n"
        "    ||| '''     '||\n```The apt cow \n"
    )


@bot.command(name="emotize")
async def emotize(ctx, *, message=commands.parameter(description="")):
    """
    Converts text into discord emojis
    """
    output = ""

    for letter in message:
        if letter == " ":
            output += letter
        elif letter == "\n":
            output += letter
        elif letter.isdigit():
            numword = num2words(letter)
            output += f":{numword}:"
        elif letter.isalpha():
            letter = letter.lower()
            output += f":regional_indicator_{letter}:"

    await ctx.send(output)


@bot.command(name="inspire")
async def inspire(ctx):
    """
    Uses InspiroBot to generate an inspirational quote"
    """
    async with ctx.typing():
        async with aiohttp.ClientSession() as session:
            async with session.get(
                "https://inspirobot.me/api?generate=true"
            ) as resp:
                r = await resp.text()
    await ctx.send(r)


@bot.command(name="color")
async def color(
    ctx,
    *,
    description=commands.parameter(
        description="See help color for valid color codes"
    ),
):
    """
    Sends a square of color based on description given.
    Valid color codes are:
    - Hexadecimal (e.g. #000000)
    - Hexadecimal with Alpha (e.g. #00000000)
    - RGB (e.g. rgb(0, 0, 0))
    - HSL (e.g. hsl(0, 0%, 0%))
    - HSB (e.g. hsb((hue, saturation%, brightness%))
    - Common color names (e.g. red)
    - And X windows color names (e.g. X11 color names)
    """
    try:
        stylelor = ImageColor.getrgb(description)

    except Exception:
        await ctx.reply(
            f" Valid color codes are can be found at {command_prefix}help "
            f"color",
            mention_author=False,
        )
        return

    img = Image.new("RGBA", (480, 480), color=stylelor)
    img.save("color.png")
    await ctx.send(file=discord.File("color.png"))


@bot.command(name="stackify")
async def stackify(ctx, count: int = commands.parameter(description="")):
    """
    Converts an item count into Minecraft stacks
    """
    stacks = math.floor(count / 64)
    items = count % 64
    await ctx.send(
        f"{count} items can fit into {stacks} stacks and {items} items."
    )


@bot.command(name="shulkify")
async def shulkify(ctx, count: int = commands.parameter(description="")):
    """
    Converts an item count into Minecraft shulkers (and stacks)
    """
    shulkers = math.floor(count / 64 / 27)
    stacks = math.floor(count / 64) % 27
    items = count % 64
    await ctx.send(
        f"{count} items can fit into {shulkers} shulkers, {stacks} stacks, "
        f"and {items} items."
    )


@bot.command(name="toggle")
# Checks that user is Harvite
@commands.has_role(999078830973136977)
async def toggle(ctx, feature=commands.parameter(description="")):
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
async def configset(
    ctx,
    feature=commands.parameter(description="The feature to set"),
    value=commands.parameter(description="The value to set"),
):
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
async def delete(
    ctx,
    channel_id: int = commands.parameter(description=""),
    message_id: int = commands.parameter(description=""),
):
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
async def inrole(
    ctx,
    *,
    given_role=commands.parameter(
        description="The role either the name or the id"
    ),
):
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
async def reactionrole(
    ctx,
    message_id: int = commands.parameter(description=""),
    emoji=commands.parameter(description=""),
    role_id: int = commands.parameter(description=""),
):
    """
    Adds a reaction role
    """
    with open(rr_file, "a") as csv_file:
        csv.writer(csv_file).writerow([message_id, emoji, role_id])

    await ctx.reply("Successfully added reaction role.", mention_author=False)


@bot.command(name="addrepo")
async def addrepo(
    ctx,
    link: str = commands.parameter(description=""),
):
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
async def whois(
    ctx,
    *,
    search: str = commands.parameter(
        description="Mention, id, username, or display name to be searched"
    ),
):
    """
    Looks up a person by username/display name or mention.
    """
    if ctx.guild.id != config_get("server_id"):
        return

    user = whois_search_exact(search)
    if user:
        await ctx.send(
            embed=await get_whois_embed(search, [user]), allowed_mentions=None
        )
        return

    users = whois_search_fuzzy(search)
    if len(users) == 0:
        await ctx.send("failed")
        return

    for user in users:
        user[11] = max(
            fuzz.token_sort_ratio(search, user[4]),
            fuzz.token_sort_ratio(search, user[5]),
        )
    users.sort(key=lambda x: x[11], reverse=True)
    await ctx.send(
        embed=await get_whois_embed(search, users), allowed_mentions=None
    )


@bot.command(name="iswhom")
async def iswhom(
    ctx,
    *,
    search: str = commands.parameter(
        description="Real name, first last, to be searched"
    ),
):
    """
    Looks up a person by real name.
    """
    if ctx.guild.id != config_get("server_id"):
        return

    sql_pointer.execute(
        """
        WITH Results AS (
            SELECT
                *,
                MIN(
                    editdist3(?, first_name),
                    editdist3(?, last_name),
                    editdist3(?, first_name || ' ' || last_name)
                ) AS distance
            FROM
                whois
            WHERE
                opt_in = 1
        )
        SELECT
            *
        FROM
            Results
        ORDER BY
            distance
        ASC;
        """,
        (search, search, search),
    )
    results = [list(entry) for entry in sql_pointer.fetchmany(6)]
    if len(results) == 0:
        await ctx.send("failed")
        return

    for user in results:
        user[11] = fuzz.partial_token_sort_ratio(search, " ".join(user[1:3]))
    results.sort(key=lambda x: x[11], reverse=True)

    await ctx.send(
        embed=await get_whois_embed(search, results), allowed_mentions=None
    )


@bot.command(name="whoami")
async def whoami(ctx):
    """
    Who are you really?
    """
    if ctx.guild.id != config_get("server_id"):
        return

    sql_pointer.execute(
        "SELECT * FROM whois WHERE user_id = ?", (ctx.author.id,)
    )
    result = sql_pointer.fetchone()
    if result is None:
        await ctx.reply("Don't ask me...", mention_author=False)

    await ctx.reply(
        embed=await get_whois_embed("", [result], whoami=True),
        mention_author=False,
        allowed_mentions=False,
    )


def whois_search_exact(search: str):
    # Only mentions and numeric user ids are treated as exact searches.
    match = re.match(r"<@(\d+)>", search)
    if match:
        user_id = match.group(1)
    elif search.isdigit():
        user_id = int(search)
    else:
        return None

    # fetchone returns None if the user can't be found, so the behavior
    # should be the same as if it were not an exact search (i.e. it
    # falls through to fuzzy search). This ensures compatibility with
    # purely numeric usernames/display names.
    return sql_pointer.execute(
        "SELECT * FROM whois WHERE user_id = ? AND opt_in = 1;", (user_id,)
    ).fetchone()


def whois_search_fuzzy(search: str):
    sql_pointer.execute(
        """
        WITH Results AS (
            SELECT
                *,
                MIN(
                    editdist3(?, discord_display_name),
                    editdist3(?, discord_name)
                ) AS distance
            FROM
                whois
            WHERE
                discord_name NOT LIKE 'deleted_user_%'
                AND opt_in = 1
        )
        SELECT
            *
        FROM
            Results
        ORDER BY
            distance
        ASC;
        """,
        (search, search),
    )
    results = sql_pointer.fetchmany(6)
    return [list(entry) for entry in results]  # Convert into list of lists


async def get_whois_embed(search: str, results, whoami=False) -> discord.Embed:
    exact = len(results) == 1

    person = results[0]
    user = await bot.fetch_user(person[0])

    embed = discord.Embed(
        colour=discord.Colour.brand_red(),
        title=f"{config_get('school_name')} Server User Info",
        description=(
            f"Information about {user.mention}"
            if not whoami
            else "Having an identity crisis? Here's whom you told me you were:"
        ),
    )
    embed.set_footer(
        text="Keep in mind b:whois searches usernames, while b:iswhom "
        "searches real names."
    )

    embed.add_field(inline=True, name="Year", value=person[8])
    embed.add_field(
        inline=True, name="Name", value=person[1] + " " + person[2]
    )
    embed.add_field(inline=True, name="School", value=person[7])
    embed.add_field(inline=True, name="Discord", value=user.name)
    parsed_time = datetime.strptime(person[6], "%m/%d/%Y %H:%M:%S")
    timestamp = parsed_time.replace(tzinfo=timezone.utc).timestamp()
    embed.add_field(
        inline=True,
        name="Joined",
        value=f"<t:{int(timestamp)}:D>",
    )
    embed.add_field(
        inline=True,
        name="Status",
        value="Present" if person[9] == 1 else "Absent",
    )

    if not exact:
        # Display shortened versions of next five matches' info
        shortened_results = [
            (
                f"{person[11]}%: {person[8]} {person[1]} {person[2]} "
                f"<@{person[0]}>"
            )
            for person in results
        ]
        other_results = "\n".join(shortened_results[1:6])
        embed.add_field(
            inline=False,
            name=f"Fuzzy Search Results for: `{search}`",
            value=f"The top result was {person[11]}% similar. Other results:\n"
            f"{other_results}",
        )

    return embed


async def debug():
    # Here for debugging purposes
    return


bot.run(bot.config_token)
