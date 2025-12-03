# bot.py
# -------------------------------------------------
# Discord inactivity bot
# - Tracks message + voice activity
# - Stores last_active in SQLite via db.py helpers
# - Daily cleanup: DM + invite + kick inactive users
# - Daily notify: post list of inactive members
# -------------------------------------------------

import os
import sqlite3
from datetime import datetime, timezone, timedelta

import discord
from discord.ext import commands, tasks
from dotenv import load_dotenv
from zoneinfo import ZoneInfo

from db import init_db, update_last_active, get_last_active, get_inactive_users


# ------------------------ CONFIG ------------------------

# How many days of inactivity before a user is eligible for kick
INACTIVITY_DAYS = 14

# How many days of inactivity before they show in the daily "notify" message
INACTIVITY_NOTIFY_DAYS = 7

# IDs specific to your server
GUILD_ID = 1442989805666308158          # your main server ID
STAFF_CHANNEL_ID = 1445137949871182150  # where cleanup logs + dry-runs go
INVITE_CHANNEL_ID = 1445176511614418955 # channel the bot will create invites from
NOTIFY_CHANNEL_ID = 1445137949871182150 # channel for daily inactivity summaries

# Roles that should NEVER be kicked
# NOTE: If you're testing and YOU have one of these roles,
# you will NOT appear in cleanup/dry-run results.
PROTECTED_ROLE_IDS = [
    1445172088963993610,  # Bots
    1444715664110649394,  # Moderator
]

# --- Quiet server pings config ---

# How long a channel can be silent before the bot pokes it
QUIET_TIMEOUT_HOURS = 9  # change to whatever you want

# Channels to monitor for silence
# Replace these with real channel IDs from Discord (right-click channel → Copy ID)
QUIET_CHANNEL_IDS = [
    1442989806517747724,  #lounge
]

# AFK settings
AFK_ROLE_NAME = "👻 AFK Spirit"  # must match the role name in Discord
AFK_INACTIVE_DAYS = 7           # how many days of inactivity before AFK
AFK_NICK_PREFIX = "👻 "          # what to add in front of nicknames

# In-memory tracking: last message & last quiet ping per (guild_id, channel_id)
channel_last_message: dict[tuple[int, int], datetime] = {}
last_quiet_ping: dict[tuple[int, int], datetime] = {}

# Games that count as "activity" when played (presence-based)
TRACKED_GAMES = {"Phasmophobia"}

# Timezone for display
UK_TZ = ZoneInfo("Europe/London")

# Load environment variables from .env
load_dotenv()


# ------------------------ TIME / FORMAT HELPERS ------------------------

def format_timestamp(ts: int) -> str:
    """Turn a UNIX timestamp into a UK time string."""
    dt = datetime.fromtimestamp(ts, tz=UK_TZ)
    # Example: 03/12/2025 21:47 GMT
    return dt.strftime("%d/%m/%Y %H:%M:%S %Z")


# ------------------------ DB HELPERS (wrappers around db.py) ------------------------

def mark_active(member: discord.Member) -> None:
    """
    Record that this member was active just now (in the DB).
    Uses db.update_last_active.
    """
    if member.bot:
        return  # ignore bots

    if member.guild is None:
        return  # only care about guilds

    update_last_active(member.guild.id, member.id)

# ------------------------ BOT SETUP ------------------------

intents = discord.Intents.default()
intents.message_content = True   # can read command messages like !ping
intents.members = True           # needed for member info / roles
intents.presences = True         # needed for game activity
intents.voice_states = True      # needed for voice tracking

bot = commands.Bot(command_prefix="!", intents=intents)


# ------------------------ INACTIVITY CLEANUP CORE ------------------------

async def run_inactivity_cleanup(real_run: bool) -> None:
    """
    Shared logic for inactivity cleanup.

    real_run = False -> DRY-RUN (no DM, no kick, just logs)
    real_run = True  -> REAL RUN (DM + invite + kick)
    """
    await bot.wait_until_ready()

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("[CLEANUP] Guild not found")
        return

    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=INACTIVITY_DAYS)
    cutoff_ts = int(cutoff.timestamp())

    mode = "REAL" if real_run else "DRY-RUN"
    print(f"[CLEANUP {mode}] Running inactivity check, cutoff_ts={cutoff_ts}")

    # Fetch inactive users from DB (function provided by db.py)
    rows = get_inactive_users(guild.id, cutoff_ts)

    if not rows:
        print(f"[CLEANUP {mode}] No inactive users found at DB level.")
        return

    staff_channel = guild.get_channel(STAFF_CHANNEL_ID)
    invite_channel = guild.get_channel(INVITE_CHANNEL_ID)

    if invite_channel is None:
        print(f"[CLEANUP {mode}] Invite channel missing!")
        return

    any_candidates = False

    for user_id, last_active_ts in rows:
        member = guild.get_member(user_id)
        if member is None:
            continue

        # Skip bots
        if member.bot:
            continue

        # Skip protected roles
        if any(role.id in PROTECTED_ROLE_IDS for role in member.roles):
            continue

        any_candidates = True
        last_seen_str = format_timestamp(last_active_ts)

        if not real_run:
            # DRY RUN: just log who *would* be kicked
            preview_msg = (
                f"[DRY RUN] Would kick **{member}** for inactivity "
                f"({INACTIVITY_DAYS}+ days, last seen {last_seen_str})."
            )
            if staff_channel is not None:
                await staff_channel.send(preview_msg)
            print(preview_msg)
            continue

        # REAL RUN: DM + invite + kick
        try:
            invite = await invite_channel.create_invite(
                max_uses=1,
                max_age=7 * 24 * 60 * 60,
                unique=True,
                reason="Inactivity cleanup auto-invite",
            )
        except Exception as e:
            print(f"[CLEANUP REAL] Failed to create invite: {e}")
            continue

        dm_text = (
            f"Hey {member.display_name},\n\n"
            f"You’ve been inactive on **{guild.name}** for over {INACTIVITY_DAYS} days "
            f"(last seen: **{last_seen_str}**).\n\n"
            f"We’re doing a small cleanup of inactive members, so I’ve removed you from the server.\n"
            f"If you’d like to come back, here’s a fresh invite:\n{invite.url}\n\n"
            f"Hope to see you again!"
        )

        try:
            await member.send(dm_text)
        except discord.Forbidden:
            print(f"[CLEANUP REAL] Could not DM {member} (forbidden).")
        except Exception as e:
            print(f"[CLEANUP REAL] Error DMing {member}: {e}")

        try:
            await guild.kick(
                member,
                reason=f"Inactivity {INACTIVITY_DAYS}+ days (auto cleanup)",
            )
        except discord.Forbidden:
            print(f"[CLEANUP REAL] No permission to kick {member}.")
            continue
        except Exception as e:
            print(f"[CLEANUP REAL] Error kicking {member}: {e}")
            continue

        log_msg = (
            f"👢 Kicked **{member}** for inactivity ({INACTIVITY_DAYS}+ days).\n"
            f"Last seen: **{last_seen_str}**\n"
            f"Rejoin invite: {invite.url}"
        )

        if staff_channel is not None:
            await staff_channel.send(log_msg)

        print(f"[CLEANUP REAL] Kicked inactive member: {member} (last_seen={last_seen_str})")

    if not any_candidates:
        # This means DB had rows, but all were bots / protected roles
        print(f"[CLEANUP {mode}] No non-protected inactive members found.")


@tasks.loop(hours=24)
async def inactivity_cleanup() -> None:
    """Scheduled REAL cleanup (runs once per day)."""
    await run_inactivity_cleanup(real_run=True)


# ------------------------ DAILY INACTIVITY NOTIFIER ------------------------

@tasks.loop(hours=24)
async def notify_inactive_members() -> None:
    """
    Once a day, post a message listing members
    who have been inactive longer than INACTIVITY_NOTIFY_DAYS.
    """
    await bot.wait_until_ready()

    now_ts = int(datetime.now(timezone.utc).timestamp())
    cutoff_ts = now_ts - INACTIVITY_NOTIFY_DAYS * 86400

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print(f"[NOTIFY] Guild {GUILD_ID} not found.")
        return

    channel = guild.get_channel(NOTIFY_CHANNEL_ID)
    if channel is None:
        print(f"[NOTIFY] Channel {NOTIFY_CHANNEL_ID} not found.")
        return

    rows = get_inactive_users(guild.id, cutoff_ts)
    if not rows:
        await channel.send(
            f"No members are currently over {INACTIVITY_NOTIFY_DAYS} days inactive."
        )
        print("[NOTIFY] No inactive members found.")
        return

    lines: list[str] = []

    for user_id, last_ts in rows:
        member = guild.get_member(user_id)
        if member is None:
            continue

        # Skip bots
        if member.bot:
            continue

        # Skip protected roles
        if any(role.id in PROTECTED_ROLE_IDS for role in member.roles):
            continue

        display_name = member.display_name
        when_str = format_timestamp(last_ts)
        lines.append(f"- **{display_name}** (last active: {when_str})")

    if not lines:
        print("[NOTIFY] Only bots/protected members were inactive.")
        return

    msg = (
        f"⏰ Members inactive for more than {INACTIVITY_NOTIFY_DAYS} days:\n"
        + "\n".join(lines)
    )
    await channel.send(msg)
    print("[NOTIFY] Posted inactive member list.")


@notify_inactive_members.before_loop
async def before_notify_inactive_members() -> None:
    await bot.wait_until_ready()


# ------------------------ AFK ROLE + NICKNAME UPDATER ------------------------

@tasks.loop(hours=24)  # change to minutes=1 for testing
async def update_afk_roles_and_nicks() -> None:
    """
    Once a day:
    - Find users who have been inactive for AFK_INACTIVE_DAYS.
    - Give them the AFK role + ghosty nickname prefix.
    - Remove AFK role + prefix when they become active again.
    """
    await bot.wait_until_ready()

    now_ts = int(datetime.now(timezone.utc).timestamp())
    afk_cutoff_ts = now_ts - AFK_INACTIVE_DAYS * 86400

    guild = bot.get_guild(GUILD_ID)
    if guild is None:
        print("[AFK] Guild not found.")
        return

    afk_role = discord.utils.get(guild.roles, name=AFK_ROLE_NAME)
    if afk_role is None:
        print(f"[AFK] Role '{AFK_ROLE_NAME}' not found in guild.")
        return

    # Use your existing DB helper – this already matches whatever db.py does
    rows = get_inactive_users(guild.id, afk_cutoff_ts)
    afk_ids = {user_id for (user_id, _last_ts) in rows}

    for member in guild.members:
        if member.bot:
            continue

        # If you want protected roles to be immune to AFK tags:
        if any(role.id in PROTECTED_ROLE_IDS for role in member.roles):
            continue

        is_afk = member.id in afk_ids
        has_afk_role = afk_role in member.roles
        current_nick = member.nick or member.name
        has_prefix = current_nick.startswith(AFK_NICK_PREFIX)

        # --- User should be AFK but isn't fully tagged yet ---
        if is_afk and not has_afk_role:
            # Add AFK role
            try:
                await member.add_roles(
                    afk_role,
                    reason=f"Inactive for {AFK_INACTIVE_DAYS}+ days (AFK tagging)",
                )
                print(f"[AFK] Added role to {member} in {guild.name}")
            except discord.Forbidden:
                print(f"[AFK] Missing permission to add role for {member}")
            except discord.HTTPException as e:
                print(f"[AFK] HTTP error adding role: {e}")

            # Add ghost prefix to nickname (if not already present)
            if not has_prefix:
                base = member.nick if member.nick else member.name
                new_nick = (AFK_NICK_PREFIX + base)[:32]  # Discord nick limit

                try:
                    await member.edit(nick=new_nick, reason="Marked AFK")
                    print(f"[AFK] Set nickname for {member} to '{new_nick}'")
                except discord.Forbidden:
                    print(f"[AFK] Missing permission to edit nickname for {member}")
                except discord.HTTPException as e:
                    print(f"[AFK] HTTP error editing nickname: {e}")

        # --- User is no longer AFK but still tagged ---
        elif (not is_afk) and has_afk_role:
            # Remove AFK role
            try:
                await member.remove_roles(
                    afk_role,
                    reason="User became active again (AFK cleared)",
                )
                print(f"[AFK] Removed role from {member} in {guild.name}")
            except discord.Forbidden:
                print(f"[AFK] Missing permission to remove role for {member}")
            except discord.HTTPException as e:
                print(f"[AFK] HTTP error removing role: {e}")

            # Strip ghost prefix from nickname if it’s there
            if has_prefix:
                stripped = current_nick[len(AFK_NICK_PREFIX):] or None

                try:
                    await member.edit(nick=stripped, reason="Cleared AFK status")
                    print(f"[AFK] Restored nickname for {member} to '{stripped}'")
                except discord.Forbidden:
                    print(f"[AFK] Missing permission to restore nickname for {member}")
                except discord.HTTPException as e:
                    print(f"[AFK] HTTP error restoring nickname: {e}")

# ------------------------ EVENTS ------------------------

@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if not inactivity_cleanup.is_running():
        inactivity_cleanup.start()
        print("Inactivity cleanup task started.")

    if not notify_inactive_members.is_running():
        notify_inactive_members.start()
        print("Notify inactive members task started.")

    # Start quiet-channel checker if not already running
    if not check_quiet_channels.is_running():
        check_quiet_channels.start()
        print("Quiet channel checker started.")

    # Start AFK role + nickname updater
    if not update_afk_roles_and_nicks.is_running():
        update_afk_roles_and_nicks.start()
        print("AFK role + nickname updater started.")


@bot.event
async def on_message(message: discord.Message) -> None:
    """Track message activity, then let commands run."""
    if message.author.bot:
        return

    if message.guild is None:
        return  # ignore DMs
    
    # Track last message per channel for quiet-ping feature
    if message.guild is not None:  # ignore DMs
        now = datetime.now(timezone.utc)
        key = (message.guild.id, message.channel.id)
        channel_last_message[key] = now

    mark_active(message.author)

    await bot.process_commands(message)


@bot.event
async def on_voice_state_update(
    member: discord.Member,
    before: discord.VoiceState,
    after: discord.VoiceState,
) -> None:
    """Track voice activity as 'active'."""
    if member.bot:
        return

    if member.guild is None:
        return

    # Joined or moved voice channel
    if before.channel != after.channel:
        if after.channel is not None:
            mark_active(member)
            print(f"[VOICE] Marked active from join/move: {member} in {after.channel}")
            return

    # Unmuted / undeafened / started streaming
    became_unmuted = before.self_mute and not after.self_mute
    became_undeaf = before.self_deaf and not after.self_deaf
    started_streaming = (not before.self_stream) and after.self_stream

    if became_unmuted or became_undeaf or started_streaming:
        mark_active(member)
        print(f"[VOICE] Marked active from voice action: {member}")


@bot.event
async def on_presence_update(before: discord.Member, after: discord.Member) -> None:
    """Track activity when certain games are being played."""
    if after.bot:
        return

    if after.guild is None:
        return

    # Look through activities for tracked games
    for activity in after.activities:
        if isinstance(activity, discord.Game) and activity.name in TRACKED_GAMES:
            mark_active(after)
            print(f"[PRESENCE] Marked active from game: {after} playing {activity.name}")
            break


# ------------------------ COMMANDS ------------------------

@bot.command()
async def ping(ctx: commands.Context) -> None:
    await ctx.send("Pong!")


@bot.command(name="guildid")
async def guildid(ctx: commands.Context) -> None:
    """Small helper to see which GUILD_ID this server has."""
    await ctx.send(f"This server ID is: `{ctx.guild.id}`")


@bot.command(name="cleanup_test")
@commands.has_permissions(administrator=True)
async def cleanup_test(ctx: commands.Context) -> None:
    """
    Run the inactivity cleanup in DRY-RUN mode:
    - No one is DM'd
    - No one is kicked
    - It just logs who *would* be kicked to the staff channel + console
    """
    await run_inactivity_cleanup(real_run=False)
    await ctx.send("Ran inactivity cleanup in DRY-RUN mode. Check staff channel + logs.")


@bot.command(name="lastseen")
async def lastseen(ctx: commands.Context, member: discord.Member | None = None) -> None:
    """
    Show when a user was last active.
    Usage:
      !lastseen        -> yourself
      !lastseen @user  -> specific user
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

    parts: list[str] = []
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

@tasks.loop(minutes=10)
async def check_quiet_channels():
    """Periodically check if monitored channels have gone quiet."""
    if not bot.is_ready():
        return

    now = datetime.now(timezone.utc)

    for guild in bot.guilds:
        for channel_id in QUIET_CHANNEL_IDS:
            channel = guild.get_channel(channel_id)
            if channel is None:
                continue

            key = (guild.id, channel_id)
            last_msg = channel_last_message.get(key)

            # If we've never seen a message since the bot started, skip
            if last_msg is None:
                continue

            # Has the channel been quiet long enough?
            if now - last_msg < timedelta(hours=QUIET_TIMEOUT_HOURS):
                continue

            # Avoid spamming: only ping once per quiet window
            last_ping = last_quiet_ping.get(key)
            if last_ping is not None and now - last_ping < timedelta(hours=QUIET_TIMEOUT_HOURS):
                continue

            # Try to send the ghost prompt
            try:
                await channel.send("📻 *Static fills the radio… the ghost hasn’t been heard in hours.* Who’s brave enough to talk?")
                last_quiet_ping[key] = now
            except discord.Forbidden:
                # No perms to send in that channel
                continue

# ------------------------ ENTRY POINT ------------------------

def main() -> None:
    # Initialize the database (create tables if needed)
    init_db()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")

    bot.run(token)


if __name__ == "__main__":
    main()
