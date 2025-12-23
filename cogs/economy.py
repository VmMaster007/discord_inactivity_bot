# cogs/economy.py

import discord
from discord.ext import commands
from datetime import timedelta

from db import get_coins, add_coins, set_item, get_item, now_utc_ts

# Item keys
LUCKY_CHARM = "lucky_charm_24h"
INSURANCE = "insurance_1"
XP_MULTIPLIER = "xp_multiplier_1h"
ROLE_VOUCHER = "role_voucher_1"

SHOP = {
    LUCKY_CHARM: {"name": "🍀 Lucky Charm (24h)", "price": 200, "desc": "+10% Investigate success for 24 hours", "duration": 24 * 3600},
    INSURANCE: {"name": "🛡️ Insurance (1 use)", "price": 120, "desc": "Prevents coin loss on Investigate fail (consumed)", "duration": None},
    XP_MULTIPLIER: {"name": "⚡ XP Multiplier (1h)", "price": 250, "desc": "2x XP from all sources for 1 hour", "duration": 3600},
    ROLE_VOUCHER: {"name": "🎭 Role Voucher", "price": 500, "desc": "Claim 1 custom role (admin approval required)", "duration": None},
}


class Economy(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.command(name="balance")
    async def balance(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return
        coins = get_coins(ctx.guild.id, ctx.author.id)
        await ctx.send(f"🪙 **{ctx.author.display_name}** has **{coins} Ghost Coins**.")

    @commands.command(name="shop")
    async def shop(self, ctx: commands.Context) -> None:
        lines = ["🛒 **Ghost Shop** (use `!buy <number>`)\n"]
        for i, (key, item) in enumerate(SHOP.items(), start=1):
            lines.append(f"**{i}.** {item['name']} — **{item['price']}** coins\n└ {item['desc']}")
        await ctx.send("\n".join(lines))

    @commands.command(name="buy")
    async def buy(self, ctx: commands.Context, number: int) -> None:
        if not ctx.guild:
            return

        items = list(SHOP.items())
        if number < 1 or number > len(items):
            await ctx.send("Pick a valid item number from `!shop`.")
            return

        key, item = items[number - 1]
        coins = get_coins(ctx.guild.id, ctx.author.id)

        if coins < item["price"]:
            await ctx.send(f"Not enough coins. You have **{coins}**, need **{item['price']}**.")
            return

        # pay
        add_coins(ctx.guild.id, ctx.author.id, -item["price"])

        # grant
        duration = item["duration"]
        if duration:
            expires = now_utc_ts() + duration
            set_item(ctx.guild.id, ctx.author.id, key, qty=1, expires_at_ts=expires)
        else:
            # stackable / consumable
            qty, exp = get_item(ctx.guild.id, ctx.author.id, key)
            set_item(ctx.guild.id, ctx.author.id, key, qty=qty + 1, expires_at_ts=exp)

        await ctx.send(f"✅ Purchased **{item['name']}**! (Coins left: **{get_coins(ctx.guild.id, ctx.author.id)}**)")

    @commands.command(name="inventory")
    async def inventory(self, ctx: commands.Context) -> None:
        if not ctx.guild:
            return

        # Basic inventory display for known items
        lines = ["🎒 **Your Inventory**"]
        for key, item in SHOP.items():
            qty, exp = get_item(ctx.guild.id, ctx.author.id, key)
            if qty <= 0:
                continue
            if exp:
                remaining = max(0, exp - now_utc_ts())
                mins = remaining // 60
                lines.append(f"• {item['name']} — active, **{mins} min** left")
            else:
                lines.append(f"• {item['name']} — **x{qty}**")
        if len(lines) == 1:
            lines.append("Empty. Visit `!shop`.")
        await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Economy(bot))
