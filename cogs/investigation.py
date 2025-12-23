# cogs/investigation.py

import discord
from discord.ext import commands
import random

from config import INVESTIGATE_COOLDOWN_SECONDS
from db import (
    get_cooldown, set_cooldown, now_utc_ts,
    add_coins, award_xp,
    is_boost_active, consume_item,
    get_contracts_for_today, create_contracts_for_today, add_contract_progress,
)

# Item keys must match economy.py
LUCKY_CHARM = "lucky_charm_24h"
INSURANCE = "insurance_1"
XP_MULTIPLIER = "xp_multiplier_1h"


def generate_daily_contracts() -> list[dict]:
    """
    Generates 3 random daily contracts (phas-themed).
    contract_key values must be unique per day.
    """
    pool = [
        {"contract_key": "messages_25", "title": "📓 Record 25 EVP Messages", "target": 25, "reward_xp": 120, "reward_coins": 80},
        {"contract_key": "messages_40", "title": "🗒️ Log 40 Evidence Notes", "target": 40, "reward_xp": 180, "reward_coins": 120},
        {"contract_key": "voice_20", "title": "🎙️ 20 Minutes on Site (Voice)", "target": 20, "reward_xp": 160, "reward_coins": 110},
        {"contract_key": "voice_45", "title": "🎙️ 45 Minutes on Site (Voice)", "target": 45, "reward_xp": 260, "reward_coins": 180},
        {"contract_key": "investigate_1", "title": "🧪 Successful Investigation (x1)", "target": 1, "reward_xp": 200, "reward_coins": 150},
        {"contract_key": "investigate_2", "title": "🧪 Successful Investigations (x2)", "target": 2, "reward_xp": 320, "reward_coins": 240},
    ]
    return random.sample(pool, k=3)


class Investigation(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def ensure_contracts(self, guild_id: int, user_id: int) -> list[dict]:
        contracts = get_contracts_for_today(guild_id, user_id)
        if contracts:
            return contracts
        new_contracts = generate_daily_contracts()
        create_contracts_for_today(guild_id, user_id, new_contracts)
        return get_contracts_for_today(guild_id, user_id)

    @commands.command(name="contracts")
    async def contracts(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return

        contracts = self.ensure_contracts(ctx.guild.id, ctx.author.id)

        lines = ["📋 **Daily Contracts** (auto-random each day)\n"]
        for c in contracts:
            status = "✅" if c["completed"] else "🟡"
            lines.append(
                f"{status} **{c['title']}** — {c['progress']}/{c['target']}\n"
                f"└ Reward: **{c['reward_xp']} XP** + **{c['reward_coins']} coins**"
            )
        await ctx.send("\n".join(lines))

    @commands.command(name="investigate")
    async def investigate(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # cooldown
        next_ts = get_cooldown(guild_id, user_id, "investigate")
        now = now_utc_ts()
        if now < next_ts:
            left = next_ts - now
            mins = left // 60
            secs = left % 60
            await ctx.send(f"⏳ You need to rest. Try again in **{mins}m {secs}s**.")
            return

        set_cooldown(guild_id, user_id, "investigate", now + INVESTIGATE_COOLDOWN_SECONDS)

        # base success
        success_chance = 0.55
        if is_boost_active(guild_id, user_id, LUCKY_CHARM):
            success_chance += 0.10  # +10%

        success = random.random() < success_chance

        # rewards
        xp_reward = random.randint(20, 60)
        coins_reward = random.randint(25, 70)

        if success:
            # award XP + coins
            award_xp(guild_id, user_id, source="investigate", amount=xp_reward, daily_cap=999999)
            add_coins(guild_id, user_id, coins_reward)

            msg = (
                f"✅ **Investigation SUCCESS!**\n"
                f"You identified the ghost and secured evidence.\n"
                f"Rewards: **+{xp_reward} XP** and **+{coins_reward} coins**."
            )
            await ctx.send(msg)

            # contract progress (ONLY for contracts that exist today)
            todays = self.ensure_contracts(guild_id, user_id)
            today_keys = {c["contract_key"] for c in todays}

            completed: list[dict] = []

            if "investigate_1" in today_keys:
                completed += add_contract_progress(guild_id, user_id, "investigate_1", 1)

            if "investigate_2" in today_keys:
                completed += add_contract_progress(guild_id, user_id, "investigate_2", 1)

            # pay out any newly completed contracts
            await self.handle_completed_contracts(ctx, completed)

        else:
            # fail penalty (coins)
            penalty = random.randint(5, 15)

            # insurance prevents penalty (consumed)
            if consume_item(guild_id, user_id, INSURANCE, 1):
                penalty = 0

            if penalty > 0:
                add_coins(guild_id, user_id, -penalty)

            consolation_xp = random.randint(5, 15)
            award_xp(guild_id, user_id, source="investigate", amount=consolation_xp, daily_cap=999999)

            await ctx.send(
                f"❌ **Investigation FAILED.** The ghost played you.\n"
                f"You gained **+{consolation_xp} XP** but lost **-{penalty} coins**."
            )

    async def handle_completed_contracts(self, ctx: commands.Context, completed: list[dict]) -> None:
        """Grant rewards for newly completed contracts."""
        if not completed:
            return

        guild_id = ctx.guild.id
        user_id = ctx.author.id

        # de-dupe by contract_key just in case
        seen = set()
        unique = []
        for c in completed:
            ck = c.get("contract_key")
            if ck in seen:
                continue
            seen.add(ck)
            unique.append(c)

        for c in unique:
            award_xp(guild_id, user_id, source="contract", amount=c["reward_xp"], daily_cap=999999)
            add_coins(guild_id, user_id, c["reward_coins"])

            await ctx.send(
                f"🏁 **Contract Complete!** {c['title']}\n"
                f"Rewards: **+{c['reward_xp']} XP** and **+{c['reward_coins']} coins**."
            )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Investigation(bot))
