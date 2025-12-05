# bot.py

import os
import asyncio

import discord
from discord.ext import commands
from dotenv import load_dotenv
from discord import app_commands

from db import init_db
from config import (
    GUILD_ID,
    HELP_MESSAGE,
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

load_dotenv()

# ------------------------ BOT SETUP ------------------------

intents = discord.Intents.default()
intents.message_content = True   # can read command messages like !ping
intents.members = True           # needed for member info / roles
intents.presences = True         # needed for game activity
intents.voice_states = True      # needed for voice tracking

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    help_command=None,  # we provide our own !help
)


# ------------------------ SLASH COMMANDS ------------------------

@bot.tree.command(name="help", description="Show Phasmocademy bot commands")
async def slash_help(interaction: discord.Interaction) -> None:
    """Slash version of help – shows all commands."""
    await interaction.response.send_message(HELP_MESSAGE, ephemeral=True)


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
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Sync slash commands once per session
    if not hasattr(bot, "synced"):
        await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        bot.synced = True
        print("Slash commands synced to guild.")

    # Make sure DB exists
    init_db()

    # Ensure every guild has a settings row
    for guild in bot.guilds:
        ensure_guild_settings(guild.id, guild.name)
        print(f"[SETTINGS] Ensured settings for guild: {guild.name} ({guild.id})")

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
    async with bot:
        await bot.load_extension("cogs.activity")
        await bot.load_extension("cogs.moderation")
        await bot.load_extension("cogs.housekeeping")
        await bot.load_extension("cogs.quiet_channels")
        await bot.start(token)


if __name__ == "__main__":
    asyncio.run(main())
