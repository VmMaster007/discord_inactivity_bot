import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone

from db import init_db, update_last_active, get_last_active


# Load environment variables from .env
load_dotenv()

# We'll expand these intents later when we start tracking activity
intents = discord.Intents.default()
intents.message_content = True   # so the bot can read command messages like !ping
intents.members = True           # for tracking users
intents.presences = True         # game activity (Phas/Marvel Rivals)

bot = commands.Bot(command_prefix="!", intents=intents)

def mark_active(member: discord.Member) -> None:
    """
    Record that this member was active just now (in the DB).
    """
    if member.bot:
        return  # ignore bots

    if member.guild is None:
        return  # just in case; we only care about guilds

    update_last_active(member.guild.id, member.id)

def format_timestamp(ts: int) -> str:
    """
    Convert a Unix timestamp (UTC) into a readable string.
    """
    dt = datetime.fromtimestamp(ts, tz=timezone.utc)
    # Example format: 2025-12-01 18:25:30 UTC
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    # Ignore DMs and bot messages
    if message.author.bot:
        return

    if message.guild is None:
        return

    # Mark the author as active
    mark_active(message.author)

    # Important: allow commands (like !ping) to still work
    await bot.process_commands(message)


# Everytime a command is made create a new bot.command with the function under it!
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")

@bot.command(name="lastseen")
async def lastseen(ctx: commands.Context, member: discord.Member | None = None):
    """
    Show when a user was last active (message/game/voice, once we hook all that up).
    Usage: !lastseen       -> shows info about yourself
           !lastseen @user -> shows info about that user
    """
    # Default to the author if no member is provided
    if member is None:
        member = ctx.author

    # Ignore bots (including our own)
    if member.bot:
        await ctx.send("I don't track activity for bots.")
        return

    ts = get_last_active(ctx.guild.id, member.id)
    if ts is None:
        await ctx.send(f"I have no activity record for {member.mention} yet.")
        return

    # When (absolute)
    when_str = format_timestamp(ts)

    # How long ago (relative)
    now_ts = int(datetime.now(timezone.utc).timestamp())
    diff = now_ts - ts

    # Calculate days/hours/minutes
    days = diff // 86400
    hours = (diff % 86400) // 3600
    minutes = (diff % 3600) // 60

    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")

    if not parts:
        parts.append("just now")

    ago_str = " ".join(parts)

    await ctx.send(
        f"{member.mention} was last active at **{when_str}** ({ago_str} ago)."
    )



def main():
    # Initialize the database (create tables if needed)
    init_db()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")
    
    bot.run(token)


if __name__ == "__main__":
    main()
