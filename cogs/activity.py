# cogs/activity.py

from datetime import datetime, timezone
from discord.ext import commands, tasks
import discord

from db import update_last_active, get_last_active, get_inactive_users
from config import (
    UK_TZ,
    AFK_ROLE_NAME,
    AFK_NICK_PREFIX,
    AFK_INACTIVE_DAYS,
    PROTECTED_ROLE_IDS,
    TRACKED_GAMES,
    GUILD_ID,
    HELP_MESSAGE,        # 👈 add this
    format_timestamp,
)


class Activity(commands.Cog):
    """Activity tracking, AFK system, and basic commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Start AFK updater loop
        if not self.update_afk_roles_and_nicks.is_running():
            self.update_afk_roles_and_nicks.start()

    # ------------------------ DB helper ------------------------

    def mark_active(self, member: discord.Member) -> None:
        """Record that this member was active just now (in the DB)."""
        if member.bot:
            return  # ignore bots

        if member.guild is None:
            return  # only care about guilds

        update_last_active(
            member.guild.id,
            member.id,
            member.display_name
        )

    # ------------------------ AFK helpers ------------------------

    async def clear_afk_if_needed(self, member: discord.Member) -> None:
        """Remove AFK role + ghost nickname if the member was marked AFK."""
        if member.guild is None:
            return

        afk_role = discord.utils.get(member.guild.roles, name=AFK_ROLE_NAME)

        # Remove AFK role
        if afk_role and afk_role in member.roles:
            try:
                await member.remove_roles(
                    afk_role,
                    reason="User became active again",
                )
            except discord.Forbidden:
                # Bot can't manage this member's roles
                pass

        # Remove ghost prefix from nickname
        if member.nick and member.nick.startswith(AFK_NICK_PREFIX):
            new_nick = member.nick[len(AFK_NICK_PREFIX):].strip()
            try:
                await member.edit(
                    nick=new_nick or None,
                    reason="User became active again",
                )
            except discord.Forbidden:
                # Bot can't change this nickname
                pass

    # ------------------------ AFK role + nickname updater ------------------------

    @tasks.loop(hours=24)  # change to minutes=1 for testing if needed
    async def update_afk_roles_and_nicks(self) -> None:
        """
        Once a day:
        - Find users who have been inactive for AFK_INACTIVE_DAYS.
        - Give them the AFK role + ghosty nickname prefix.
        - Remove AFK role + prefix when they become active again.
        """
        await self.bot.wait_until_ready()

        now_ts = int(datetime.now(timezone.utc).timestamp())
        afk_cutoff_ts = now_ts - AFK_INACTIVE_DAYS * 86400

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            print("[AFK] Guild not found.")
            return

        afk_role = discord.utils.get(guild.roles, name=AFK_ROLE_NAME)
        if afk_role is None:
            print(f"[AFK] Role '{AFK_ROLE_NAME}' not found in guild.")
            return

        # Use existing DB helper
        rows = get_inactive_users(guild.id, afk_cutoff_ts)
        afk_ids = {user_id for (user_id, _last_ts) in rows}

        for member in guild.members:
            if member.bot:
                continue

            # Make protected roles immune to AFK tags
            if any(role.id in PROTECTED_ROLE_IDS for role in member.roles):
                continue

            is_afk = member.id in afk_ids
            has_afk_role = afk_role in member.roles
            current_nick = member.nick or member.name
            has_prefix = current_nick.startswith(AFK_NICK_PREFIX)

            # User should be AFK but isn't fully tagged yet
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

            # User is no longer AFK but still tagged
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

    # ------------------------ Events ------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Track message activity and clear AFK when someone talks."""
        if message.author.bot or message.guild is None:
            return

        # Mark them active in the DB
        self.mark_active(message.author)

        # If they were AFK, remove AFK role + ghost nickname
        await self.clear_afk_if_needed(message.author)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Track voice activity as 'active'."""
        if member.bot or member.guild is None:
            return

        # Joined or moved voice channel
        if before.channel != after.channel:
            if after.channel is not None:
                self.mark_active(member)
                await self.clear_afk_if_needed(member)
                print(f"[VOICE] Marked active from join/move: {member} in {after.channel}")
                return

        # Unmuted / undeafened / started streaming
        became_unmuted = before.self_mute and not after.self_mute
        became_undeaf = before.self_deaf and not after.self_deaf
        started_streaming = (not before.self_stream) and after.self_stream

        if became_unmuted or became_undeaf or started_streaming:
            self.mark_active(member)
            await self.clear_afk_if_needed(member)
            print(f"[VOICE] Marked active from voice action: {member}")

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Track activity when certain games are being played."""
        if after.bot or after.guild is None:
            return

        # Look through activities for tracked games
        for activity in after.activities:
            if isinstance(activity, discord.Game) and activity.name in TRACKED_GAMES:
                self.mark_active(after)
                await self.clear_afk_if_needed(after)
                print(f"[PRESENCE] Marked active from game: {after} playing {activity.name}")
                break

    # ------------------------ Commands ------------------------

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        """Show a list of bot commands."""
        await ctx.send(HELP_MESSAGE)


    @commands.command()
    async def ping(self, ctx: commands.Context) -> None:
        """Simple heartbeat command."""
        await ctx.send("Pong!")

    @commands.command(name="guildid")
    async def guildid(self, ctx: commands.Context) -> None:
        """Small helper to see which GUILD_ID this server has."""
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return
        await ctx.send(f"This server ID is: `{ctx.guild.id}`")

    @commands.command(name="lastseen")
    async def lastseen(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
        """
        Show when a user was last active.
        Usage:
          !lastseen        -> yourself
          !lastseen @user  -> specific user
        """
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return

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


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Activity(bot))
