# bot.py

import os
import asyncio

import difflib
import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord import app_commands

from db import init_db
from config import (
    GUILD_ID,
    STAFF_CHANNEL_ID,
)
from db import (
    init_db,
    update_last_active,
    get_last_active,
    get_inactive_users,
    ensure_guild_settings,
    get_guild_settings,
)

from discord.ext import tasks
from zoneinfo import ZoneInfo
from datetime import datetime
from db import init_db, award_xp, get_top_weekly, get_user_weekly_rank, reset_weekly

LONDON = ZoneInfo("Europe/London")

load_dotenv()

# ------------------------ BOT SETUP ------------------------

intents = discord.Intents.default()
intents.message_content = False   # can read command messages like !ping
intents.members = True           # needed for member info / roles
intents.presences = True         # needed for game activity
intents.voice_states = True      # needed for voice tracking

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,  # we provide our own !help
    allowed_mentions=discord.AllowedMentions.none(),
)


# ------------------------ SLASH COMMANDS ------------------------

@bot.tree.command(name="clear", description="Delete recent messages in this channel")
@app_commands.checks.has_permissions(administrator=True)
async def slash_clear(
    interaction: discord.Interaction,
    amount: app_commands.Range[int, 1, 200],
) -> None:
    """Slash clear – amount has a numeric input, with validation."""
    channel = interaction.channel
    if not isinstance(channel, discord.TextChannel):
        await interaction.response.send_message(
            "This can only be used in a text channel.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    deleted = await channel.purge(
        limit=amount + 1,
        reason=f"Requested by {interaction.user} via /clear",
    )
    deleted_count = max(len(deleted) - 1, 0)

    await interaction.followup.send(
        f"🧹 Deleted **{deleted_count}** messages.",
        ephemeral=True,
    )


@bot.tree.command(name="kick", description="Kick a member from the server")
@app_commands.checks.has_permissions(kick_members=True)
async def slash_kick(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = None,
) -> None:
    """
    Slash kick.
    `member` shows as a user dropdown/picker when you run /kick.
    """
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    if member == interaction.user:
        await interaction.response.send_message(
            "You can't kick yourself.",
            ephemeral=True,
        )
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.kick_members:
        await interaction.response.send_message(
            "I don't have permission to kick members.",
            ephemeral=True,
        )
        return

    if member.top_role >= interaction.user.top_role and interaction.user != guild.owner:
        await interaction.response.send_message(
            "You can't kick someone with an equal or higher role than you.",
            ephemeral=True,
        )
        return

    if member.top_role >= bot_member.top_role:
        await interaction.response.send_message(
            "I can't kick that member because their top role is above mine.",
            ephemeral=True,
        )
        return

    await member.kick(
        reason=f"{reason or 'No reason provided.'} (kicked by {interaction.user})"
    )

    await interaction.response.send_message(
        f"👢 Kicked **{member}**. Reason: {reason or 'No reason provided.'}",
        ephemeral=True,
    )

    staff_channel = guild.get_channel(STAFF_CHANNEL_ID)
    if staff_channel is not None:
        await staff_channel.send(
            f"👢 **Kick** | {member} was kicked by {interaction.user}.\n"
            f"Reason: {reason or 'No reason provided.'}"
        )


@bot.tree.command(name="ban", description="Ban a member from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_ban(
    interaction: discord.Interaction,
    member: discord.Member,
    reason: str | None = None,
) -> None:
    """Slash ban – also uses a user picker."""
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    if member == interaction.user:
        await interaction.response.send_message(
            "You can't ban yourself.",
            ephemeral=True,
        )
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.ban_members:
        await interaction.response.send_message(
            "I don't have permission to ban members.",
            ephemeral=True,
        )
        return

    if member.top_role >= interaction.user.top_role and interaction.user != guild.owner:
        await interaction.response.send_message(
            "You can't ban someone with an equal or higher role than you.",
            ephemeral=True,
        )
        return

    if member.top_role >= bot_member.top_role:
        await interaction.response.send_message(
            "I can't ban that member because their top role is above mine.",
            ephemeral=True,
        )
        return

    await member.ban(
        reason=f"{reason or 'No reason provided.'} (banned by {interaction.user})",
        delete_message_days=0,
    )

    await interaction.response.send_message(
        f"🔨 Banned **{member}**. Reason: {reason or 'No reason provided.'}",
        ephemeral=True,
    )

    staff_channel = guild.get_channel(STAFF_CHANNEL_ID)
    if staff_channel is not None:
        await staff_channel.send(
            f"🔨 **Ban** | {member} was banned by {interaction.user}.\n"
            f"Reason: {reason or 'No reason provided.'}"
        )


@bot.tree.command(name="unban", description="Unban a user from the server")
@app_commands.checks.has_permissions(ban_members=True)
async def slash_unban(
    interaction: discord.Interaction,
    user: discord.User,
    reason: str | None = None,
) -> None:
    """
    Slash unban.
    `user` is picked via a user search/selector.
    """
    guild = interaction.guild
    if guild is None:
        await interaction.response.send_message(
            "This command can only be used in a server.",
            ephemeral=True,
        )
        return

    bot_member = guild.me
    if bot_member is None or not bot_member.guild_permissions.ban_members:
        await interaction.response.send_message(
            "I don't have permission to unban members.",
            ephemeral=True,
        )
        return

    bans = await guild.bans()
    banned_users = {ban_entry.user.id: ban_entry for ban_entry in bans}

    if user.id not in banned_users:
        await interaction.response.send_message(
            "That user is not currently banned.",
            ephemeral=True,
        )
        return

    await guild.unban(
        user,
        reason=f"{reason or 'No reason provided.'} (unbanned by {interaction.user})",
    )

    await interaction.response.send_message(
        f"✅ Unbanned **{user}**. Reason: {reason or 'No reason provided.'}",
        ephemeral=True,
    )

    staff_channel = guild.get_channel(STAFF_CHANNEL_ID)
    if staff_channel is not None:
        await staff_channel.send(
            f"✅ **Unban** | {user} was unbanned by {interaction.user}.\n"
            f"Reason: {reason or 'No reason provided.'}"
        )


# ------------------------ EVENTS ------------------------

@bot.event
async def on_message(message: discord.Message):
    # ✅ allow normal chat + your activity tracking listeners in cogs
    # but DO NOT let discord.py treat messages as prefix commands
    return

@bot.event
async def on_ready():
    print(f"[READY] Logged in as {bot.user} (ID: {bot.user.id})")

    guild = discord.Object(id=GUILD_ID)

    # IMPORTANT: copy global commands into the guild then sync
    bot.tree.copy_global_to(guild=guild)
    synced = await bot.tree.sync(guild=guild)

    print(f"[SYNC] Synced to guild {GUILD_ID}. Commands synced: {len(synced)}")
    for c in synced:
        print(f" - /{c.name}")

    print(f"[TREE] Local tree commands: {len(bot.tree.get_commands())}")

@bot.event
async def on_guild_join(guild: discord.Guild) -> None:
    """When the bot joins a new server, create default settings for it."""
    ensure_guild_settings(guild.id, guild.name)
    print(f"[SETTINGS] Created default settings for new guild: {guild.name} ({guild.id})")

# ------------------------ ENTRY POINT ------------------------

async def main() -> None:
    """Main entry point to initialise DB, load cogs and start the bot."""
    init_db()
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")

    # Load cogs as extensions, then start the bot
    bot.remove_command("help")
    async with bot:
        await bot.load_extension("cogs.activity")
        await bot.load_extension("cogs.moderation")
        await bot.load_extension("cogs.housekeeping")
        await bot.load_extension("cogs.quiet_channels")
        await bot.load_extension("cogs.welcome")
        await bot.load_extension("cogs.leave_loggers")
        await bot.load_extension("cogs.leveling")
        await bot.load_extension("cogs.economy")
        await bot.load_extension("cogs.investigation")
        await bot.load_extension("cogs.help_menu")
        await bot.load_extension("cogs.slash_commands")
        await bot.load_extension("cogs.tickets")
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())