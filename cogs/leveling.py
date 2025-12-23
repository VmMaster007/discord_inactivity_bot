# cogs/leveling.py

import discord
from discord.ext import commands, tasks
from datetime import datetime
import random

from config import (
    UK_TZ,
    LEADERBOARD_CHANNEL_ID,
    ANNOUNCEMENTS_CHANNEL_ID,
    LEADERBOARD_UPDATE_MINUTES,
    WEEKLY_CHAMP_ROLE_NAME,
    DEFAULT_MSG_XP, DEFAULT_MSG_DAILY_CAP,
    DEFAULT_VOICE_XP_PER_MIN, DEFAULT_VOICE_DAILY_CAP,
)

from db import (
    award_xp,
    get_top_weekly,
    get_user_weekly_rank,
    reset_weekly,
    add_coins,
    is_boost_active,
)

# Item keys
XP_MULTIPLIER = "xp_multiplier_1h"


class Leveling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        if not self.leaderboard_updater.is_running():
            self.leaderboard_updater.start()

        if not self.weekly_winners_task.is_running():
            self.weekly_winners_task.start()

    # ---------- Public API for other cogs ----------
    def apply_xp_multiplier(self, guild_id: int, user_id: int, base_amount: int) -> int:
        if is_boost_active(guild_id, user_id, XP_MULTIPLIER):
            return base_amount * 2
        return base_amount

    def award_activity_xp(self, guild_id: int, user_id: int, source: str, amount: int, daily_cap: int) -> dict:
        amount = self.apply_xp_multiplier(guild_id, user_id, amount)
        return award_xp(guild_id=guild_id, user_id=user_id, source=source, amount=amount, daily_cap=daily_cap)

    # ---------- Leaderboard message ----------
    def rules_text(self) -> str:
        return (
            "**Earn XP**\n"
            f"• 💬 Messages: **+{DEFAULT_MSG_XP} XP** each (cap **{DEFAULT_MSG_DAILY_CAP}/day**)\n"
            f"• 🎙️ Voice: **+{DEFAULT_VOICE_XP_PER_MIN} XP/min** (cap **{DEFAULT_VOICE_DAILY_CAP}/day**)\n"
            "• 🧪 Investigate + Daily Contracts: bonus XP & Ghost Coins\n\n"
            "**Weekly Winners**\n"
            "• 🥇 #1 gets **Weekly Champ** role for 7 days + coin reward\n"
        )

    def leaderboard_text(self, guild: discord.Guild) -> str:
        top10 = get_top_weekly(guild.id, limit=10)
        if not top10:
            return "No activity yet this week."

        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        lines = []
        for i, (uid, points) in enumerate(top10, start=1):
            member = guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            prefix = medals.get(i, f"**{i}.**")
            lines.append(f"{prefix} {name} — **{points} XP**")
        return "\n".join(lines)

    async def upsert_leaderboard_message(self) -> None:
        if not LEADERBOARD_CHANNEL_ID:
            return
        channel = self.bot.get_channel(LEADERBOARD_CHANNEL_ID)
        if channel is None or not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild

        embed = discord.Embed(title="📊 Weekly Activity Leaderboard")
        embed.add_field(name="How to Earn XP", value=self.rules_text(), inline=False)
        embed.add_field(name="Top This Week", value=self.leaderboard_text(guild), inline=False)
        embed.set_footer(text=f"Auto-updates every {LEADERBOARD_UPDATE_MINUTES} mins • Resets Sundays 00:00 UK")

        async for msg in channel.history(limit=30):
            if msg.author == self.bot.user and msg.embeds:
                if msg.embeds[0].title == "📊 Weekly Activity Leaderboard":
                    await msg.edit(embed=embed)
                    return

        await channel.send(embed=embed)

    @tasks.loop(minutes=1)
    async def leaderboard_updater(self) -> None:
        await self.bot.wait_until_ready()
        if LEADERBOARD_UPDATE_MINUTES <= 0:
            return

        now = datetime.now(UK_TZ)
        if now.minute % LEADERBOARD_UPDATE_MINUTES != 0:
            return

        await self.upsert_leaderboard_message()

    # ---------- Weekly reset + winners ----------
    async def ensure_weekly_champ_role(self, guild: discord.Guild) -> discord.Role | None:
        role = discord.utils.get(guild.roles, name=WEEKLY_CHAMP_ROLE_NAME)
        if role:
            return role
        try:
            return await guild.create_role(name=WEEKLY_CHAMP_ROLE_NAME, reason="Weekly winners role")
        except discord.Forbidden:
            return None

    async def announce(self, text: str) -> None:
        if not ANNOUNCEMENTS_CHANNEL_ID:
            return
        ch = self.bot.get_channel(ANNOUNCEMENTS_CHANNEL_ID)
        if ch and isinstance(ch, discord.TextChannel):
            await ch.send(text)

    @tasks.loop(minutes=5)
    async def weekly_winners_task(self) -> None:
        """
        At Sunday 00:00 UK:
        - announce winners (top 3)
        - award coin prizes
        - assign Weekly Champ role to #1 (remove from others)
        - reset weekly XP + daily caps
        """
        await self.bot.wait_until_ready()

        now = datetime.now(UK_TZ)
        if not (now.weekday() == 6 and now.hour == 0 and now.minute < 5):
            return

        for guild in self.bot.guilds:
            top3 = get_top_weekly(guild.id, limit=3)

            if top3:
                # coin prizes
                prizes = {1: 250, 2: 150, 3: 100}

                lines = ["👻 **Weekly Investigation Results!**"]
                for i, (uid, pts) in enumerate(top3, start=1):
                    prize = prizes.get(i, 0)
                    add_coins(guild.id, uid, prize)
                    lines.append(f"{['🥇','🥈','🥉'][i-1]} <@{uid}> — **{pts} XP** (+{prize} Ghost Coins)")

                await self.announce("\n".join(lines))

                # Weekly champ role to #1
                champ_uid = top3[0][0]
                role = await self.ensure_weekly_champ_role(guild)
                if role:
                    for member in guild.members:
                        if member.bot:
                            continue
                        has_role = role in member.roles
                        if member.id == champ_uid and not has_role:
                            try:
                                await member.add_roles(role, reason="Weekly #1 winner")
                            except discord.Forbidden:
                                pass
                        elif member.id != champ_uid and has_role:
                            try:
                                await member.remove_roles(role, reason="Weekly champ rotated")
                            except discord.Forbidden:
                                pass

            # reset after handling winners
            reset_weekly(guild_id=guild.id)

        # refresh leaderboard message after reset
        await self.upsert_leaderboard_message()

    # ---------- Commands ----------
    @commands.command(name="rank")
    async def rank(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        # Weekly rank/points
        r, weekly_pts = get_user_weekly_rank(ctx.guild.id, ctx.author.id)
        await ctx.send(f"📟 **{ctx.author.display_name}** — Weekly Rank **#{r}**, Weekly XP **{weekly_pts}**")

    @commands.command(name="top")
    async def top(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        top5 = get_top_weekly(ctx.guild.id, limit=5)
        r, weekly_pts = get_user_weekly_rank(ctx.guild.id, ctx.author.id)

        lines = []
        for i, (uid, pts) in enumerate(top5, start=1):
            member = ctx.guild.get_member(uid)
            name = member.display_name if member else f"<@{uid}>"
            lines.append(f"**{i}.** {name} — **{pts} XP**")

        embed = discord.Embed(title="Weekly Activity Leaderboard", description="\n".join(lines) if lines else "No activity yet.")
        embed.add_field(name="Your weekly stats", value=f"Rank: **#{r}**\nPoints: **{weekly_pts} XP**", inline=False)
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Leveling(bot))
