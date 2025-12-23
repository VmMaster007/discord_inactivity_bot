# cogs/activity.py
# Activity tracking + AFK system + awarding XP for message/voice + contract progress hooks
# (Leaderboard/shop/investigate are handled by separate cogs.)

from datetime import datetime, timezone
from discord.ext import commands, tasks
import discord
import random

from db import (
    update_last_active,
    get_last_active,
    get_inactive_users,
    award_xp,
    get_contracts_for_today,
    create_contracts_for_today,
    add_contract_progress,
    add_coins,
    reset_all_progress,
)

from config import (
    UK_TZ,
    AFK_ROLE_NAME,
    AFK_NICK_PREFIX,
    AFK_INACTIVE_DAYS,
    PROTECTED_ROLE_IDS,
    TRACKED_GAMES,
    GUILD_ID,
    format_timestamp,
    DEFAULT_MSG_XP,
    DEFAULT_MSG_DAILY_CAP,
    DEFAULT_VOICE_XP_PER_MIN,
    DEFAULT_VOICE_DAILY_CAP,
)


# ------------------------ Daily Contracts (same pool as investigate cog) ------------------------

def generate_daily_contracts() -> list[dict]:
    pool = [
        {"contract_key": "messages_25", "title": "📓 Record 25 EVP Messages", "target": 25, "reward_xp": 120, "reward_coins": 80},
        {"contract_key": "messages_40", "title": "🗒️ Log 40 Evidence Notes", "target": 40, "reward_xp": 180, "reward_coins": 120},
        {"contract_key": "voice_20", "title": "🎙️ 20 Minutes on Site (Voice)", "target": 20, "reward_xp": 160, "reward_coins": 110},
        {"contract_key": "voice_45", "title": "🎙️ 45 Minutes on Site (Voice)", "target": 45, "reward_xp": 260, "reward_coins": 180},
        {"contract_key": "investigate_1", "title": "🧪 Successful Investigation (x1)", "target": 1, "reward_xp": 200, "reward_coins": 150},
        {"contract_key": "investigate_2", "title": "🧪 Successful Investigations (x2)", "target": 2, "reward_xp": 320, "reward_coins": 240},
    ]
    return random.sample(pool, k=3)


def ensure_contracts(guild_id: int, user_id: int) -> None:
    """Create today's contracts for this user if missing."""
    existing = get_contracts_for_today(guild_id, user_id)
    if existing:
        return
    create_contracts_for_today(guild_id, user_id, generate_daily_contracts())


class Activity(commands.Cog):
    """Activity tracking, AFK system, and the hooks that award XP for message/voice + contract progress."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Start AFK updater loop
        if not self.update_afk_roles_and_nicks.is_running():
            self.update_afk_roles_and_nicks.start()

        # Start voice XP ticker (awards XP/min + voice contract progress)
        if not self.voice_xp_tick.is_running():
            self.voice_xp_tick.start()
            

    # ------------------------ DB helper ------------------------

    def mark_active(self, member: discord.Member) -> None:
        """Record that this member was active just now (in the DB)."""
        if member.bot:
            return
        if member.guild is None:
            return

        update_last_active(member.guild.id, member.id, member.display_name)

    # ------------------------ AFK helpers ------------------------

    async def clear_afk_if_needed(self, member: discord.Member) -> None:
        """Remove AFK role + ghost nickname if the member was marked AFK."""
        if member.guild is None:
            return

        afk_role = discord.utils.get(member.guild.roles, name=AFK_ROLE_NAME)

        # Remove AFK role
        if afk_role and afk_role in member.roles:
            try:
                await member.remove_roles(afk_role, reason="User became active again")
            except discord.Forbidden:
                pass

        # Remove ghost prefix from nickname
        if member.nick and member.nick.startswith(AFK_NICK_PREFIX):
            new_nick = member.nick[len(AFK_NICK_PREFIX):].strip()
            try:
                await member.edit(nick=new_nick or None, reason="User became active again")
            except discord.Forbidden:
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

        rows = get_inactive_users(guild.id, afk_cutoff_ts)
        afk_ids = {user_id for (user_id, _last_ts) in rows}

        for member in guild.members:
            if member.bot:
                continue

            if any(role.id in PROTECTED_ROLE_IDS for role in member.roles):
                continue

            is_afk = member.id in afk_ids
            has_afk_role = afk_role in member.roles
            current_nick = member.nick or member.name
            has_prefix = current_nick.startswith(AFK_NICK_PREFIX)

            if is_afk and not has_afk_role:
                # Add AFK role
                try:
                    await member.add_roles(
                        afk_role,
                        reason=f"Inactive for {AFK_INACTIVE_DAYS}+ days (AFK tagging)",
                    )
                except discord.Forbidden:
                    pass
                except discord.HTTPException as e:
                    print(f"[AFK] HTTP error adding role: {e}")

                # Add nickname prefix
                if not has_prefix:
                    base = member.nick if member.nick else member.name
                    new_nick = (AFK_NICK_PREFIX + base)[:32]
                    try:
                        await member.edit(nick=new_nick, reason="Marked AFK")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException as e:
                        print(f"[AFK] HTTP error editing nickname: {e}")

            elif (not is_afk) and has_afk_role:
                # Remove AFK role
                try:
                    await member.remove_roles(afk_role, reason="User became active again (AFK cleared)")
                except discord.Forbidden:
                    pass
                except discord.HTTPException as e:
                    print(f"[AFK] HTTP error removing role: {e}")

                # Strip nickname prefix
                if has_prefix:
                    stripped = current_nick[len(AFK_NICK_PREFIX):] or None
                    try:
                        await member.edit(nick=stripped, reason="Cleared AFK status")
                    except discord.Forbidden:
                        pass
                    except discord.HTTPException as e:
                        print(f"[AFK] HTTP error restoring nickname: {e}")

    # ------------------------ Voice XP ticker (XP/min + contracts) ------------------------

    @tasks.loop(minutes=1)
    async def voice_xp_tick(self) -> None:
        """Every minute, award voice XP to members currently in voice channels + progress voice contracts."""
        await self.bot.wait_until_ready()

        for guild in self.bot.guilds:
            for vc in guild.voice_channels:
                for member in vc.members:
                    if member.bot:
                        continue

                    # Award XP (cap enforced in DB)
                    award_xp(
                        guild_id=guild.id,
                        user_id=member.id,
                        source="voice",
                        amount=DEFAULT_VOICE_XP_PER_MIN,
                        daily_cap=DEFAULT_VOICE_DAILY_CAP,
                    )

                    # Ensure + progress voice contracts (minutes)
                    ensure_contracts(guild.id, member.id)

                    completed = []
                    completed += add_contract_progress(guild.id, member.id, "voice_20", 1)
                    completed += add_contract_progress(guild.id, member.id, "voice_45", 1)

                    await self.payout_completed_contracts(member, completed)




    # ------------------------ Events ------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Track message activity, award XP, progress contracts, and clear AFK."""
        if message.author.bot or message.guild is None:
            return

        # Mark activity for inactivity/AFK system
        self.mark_active(message.author)

        # Award message XP (cap enforced in DB)
        award_xp(
            guild_id=message.guild.id,
            user_id=message.author.id,
            source="message",
            amount=DEFAULT_MSG_XP,
            daily_cap=DEFAULT_MSG_DAILY_CAP,
        )

        # Ensure + progress message contracts
        ensure_contracts(message.guild.id, message.author.id)

        completed = []
        completed += add_contract_progress(message.guild.id, message.author.id, "messages_25", 1)
        completed += add_contract_progress(message.guild.id, message.author.id, "messages_40", 1)
        await self.payout_completed_contracts(message.author, completed)

        # Clear AFK if needed
        await self.clear_afk_if_needed(message.author)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        """Track voice activity as 'active' for inactivity/AFK clearing."""
        if member.bot or member.guild is None:
            return

        if before.channel != after.channel:
            if after.channel is not None:
                self.mark_active(member)
                await self.clear_afk_if_needed(member)
                return

        became_unmuted = before.self_mute and not after.self_mute
        became_undeaf = before.self_deaf and not after.self_deaf
        started_streaming = (not before.self_stream) and after.self_stream

        if became_unmuted or became_undeaf or started_streaming:
            self.mark_active(member)
            await self.clear_afk_if_needed(member)

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        """Track activity when certain games are being played (AFK/inactivity only)."""
        if after.bot or after.guild is None:
            return

        for activity in after.activities:
            if isinstance(activity, discord.Game) and activity.name in TRACKED_GAMES:
                self.mark_active(after)
                await self.clear_afk_if_needed(after)
                break
    
    async def payout_completed_contracts(self, member: discord.Member, completed: list[dict]) -> None:
        if not completed:
            return

        # De-dupe by contract_key
        seen = set()
        unique = []
        for c in completed:
            ck = c.get("contract_key")
            if ck in seen:
                continue
            seen.add(ck)
            unique.append(c)

        for c in unique:
            award_xp(
                guild_id=member.guild.id,
                user_id=member.id,
                source="contract",
                amount=c["reward_xp"],
                daily_cap=999999,
            )
            add_coins(member.guild.id, member.id, c["reward_coins"])

            try:
                await member.send(
                    f"🏁 **Contract Complete!**\n"
                    f"{c['title']}\n"
                    f"Rewards: **+{c['reward_xp']} XP** and **+{c['reward_coins']} Ghost Coins**."
                )
            except discord.Forbidden:
                pass

    @commands.command(name="resetall")
    @commands.has_permissions(administrator=True)
    async def resetall(self, ctx: commands.Context) -> None:
        """
        ADMIN ONLY: wipes today's contracts + all XP/coins/inventory/cooldowns for this server.
        """
        if not ctx.guild:
            return

        reset_all_progress(ctx.guild.id)
        await ctx.send("✅ **RESET COMPLETE**: XP, coins, inventory, cooldowns, and **today's** contracts were wiped for this server.")


    # ------------------------ Commands ------------------------

    @commands.command(name="help")
    async def help_command(self, ctx: commands.Context) -> None:
        await ctx.send(HELP_MESSAGE)

    @commands.command(name="guildid")
    async def guildid(self, ctx: commands.Context) -> None:
        if ctx.guild is None:
            await ctx.send("This command can only be used in a server.")
            return
        await ctx.send(f"This server ID is: `{ctx.guild.id}`")

    @commands.command(name="lastseen")
    async def lastseen(self, ctx: commands.Context, member: discord.Member | None = None) -> None:
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

        await ctx.send(f"**{display_name}** was last active at **{when_str}** ({ago_str} ago).")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Activity(bot))
