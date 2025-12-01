import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
from datetime import datetime, timezone
from discord.ext import commands, tasks


from db import init_db, update_last_active, get_last_active, get_inactive_users

INACTIVITY_NOTIFY_DAYS = 14  # change this to whatever "X days" you want
GUILD_ID = 1442989805666308158      # replace with your server ID
NOTIFY_CHANNEL_ID = 1445137949871182150  # replace with your channel ID



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

from zoneinfo import ZoneInfo

UK_TZ = ZoneInfo("Europe/London")

def format_timestamp(ts: int) -> str:
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")



@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if not notify_inactive_members.is_running():
        notify_inactive_members.start()
        print("Started notify_inactive_members loop.")

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
    Show when a user was last active.
    Usage: !lastseen       -> yourself
           !lastseen @user -> specific user
    """
    if member is None:
        member = ctx.author

    if member.bot:
        await ctx.send("I don't track activity for bots.")
        return

    ts = get_last_active(ctx.guild.id, member.id)
    display_name = member.display_name

    if ts is None:
        await ctx.send(f"I have no activity record for **{display_name}** yet.")
        return

    when_str = format_timestamp(ts)

    now_ts = int(datetime.now(timezone.utc).timestamp())
    diff = now_ts - ts
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
        f"**{display_name}** was last active at **{when_str}** ({ago_str} ago)."
    )

@tasks.loop(hours=24)
async def notify_inactive_members():
    """
    Once a day, post a message in NOTIFY_CHANNEL_ID listing members
    who have been inactive longer than INACTIVITY_NOTIFY_DAYS.
    """
    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff_ts = now_ts - INACTIVITY_NOTIFY_DAYS * 86400

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print(f"notify_inactive_members: Guild {GUILD_ID} not found.")
        return

    channel = guild.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        print(f"notify_inactive_members: Channel {NOTIFY_CHANNEL_ID} not found.")
        return

    # Fetch inactive users from DB
    rows = get_inactive_users(GUILD_ID, cutoff_ts)
    if not rows:
        # Optional: you can comment this out if you only want messages when someone *is* inactive
        await channel.send(
            f"No members are currently over {INACTIVITY_NOTIFY_DAYS} days inactive."
        )
        return

    lines = []
    for user_id_str, last_ts in rows:
        member = guild.get_member(int(user_id_str))
        if member is None:
            # user might have left the server already
            continue

        display_name = member.display_name
        when_str = format_timestamp(last_ts)
        lines.append(f"- **{display_name}** (last active: {when_str})")

    if not lines:
        return

    msg = (
        f"⏰ Members inactive for more than {INACTIVITY_NOTIFY_DAYS} days:\n"
        + "\n".join(lines)
    )
    await channel.send(msg)


@notify_inactive_members.before_loop
async def before_notify_inactive_members():
    await bot.wait_until_ready()




def main():
    # Initialize the database (create tables if needed)
    init_db()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")
    
    bot.run(token)


if __name__ == "__main__":
    main()
