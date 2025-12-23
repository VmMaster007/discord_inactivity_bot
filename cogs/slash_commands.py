# cogs/slash_commands.py
# Unified slash commands for Phasmocademy (boxed/embedded style):
# /balance /shop /buy /inventory /contracts /lastseen /investigate

import random
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone

from config import (
    format_timestamp,
    INVESTIGATE_COOLDOWN_SECONDS,
)

from db import (
    # activity
    get_last_active,

    # economy
    get_coins,
    add_coins,
    get_item,
    set_item,
    now_utc_ts,

    # cooldowns
    get_cooldown,
    set_cooldown,

    # xp
    award_xp,

    # contracts
    get_contracts_for_today,
    create_contracts_for_today,
    add_contract_progress,

    # boosts/consumables
    is_boost_active,
    consume_item,
)

# -------------------------
# Item keys (must match db/economy)
# -------------------------
LUCKY_CHARM = "lucky_charm_24h"
INSURANCE = "insurance_1"
XP_MULTIPLIER = "xp_multiplier_1h"
ROLE_VOUCHER = "role_voucher_1"

# -------------------------
# Shop config (source of truth for slash shop)
# -------------------------
SHOP = [
    {
        "id": 1,
        "key": LUCKY_CHARM,
        "name": "🍀 Lucky Charm (24h)",
        "price": 200,
        "desc": "+10% Investigate success for 24 hours",
        "duration": 24 * 3600,
        "stackable": False,
    },
    {
        "id": 2,
        "key": INSURANCE,
        "name": "🛡️ Insurance (1 use)",
        "price": 120,
        "desc": "Prevents coin loss on Investigate fail (consumed)",
        "duration": None,
        "stackable": True,
    },
    {
        "id": 3,
        "key": XP_MULTIPLIER,
        "name": "⚡ XP Multiplier (1h)",
        "price": 250,
        "desc": "2x XP from all sources for 1 hour",
        "duration": 3600,
        "stackable": False,
    },
    {
        "id": 4,
        "key": ROLE_VOUCHER,
        "name": "🎭 Role Voucher",
        "price": 500,
        "desc": "Claim 1 custom role (admin approval required)",
        "duration": None,
        "stackable": True,
    },
]

SHOP_BY_ID = {x["id"]: x for x in SHOP}


# -------------------------
# Contracts (same pool as your investigate/activity)
# -------------------------
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


def ensure_contracts(guild_id: int, user_id: int) -> list[dict]:
    existing = get_contracts_for_today(guild_id, user_id)
    if existing:
        return existing
    create_contracts_for_today(guild_id, user_id, generate_daily_contracts())
    return get_contracts_for_today(guild_id, user_id)


# -------------------------
# Response helper (content OR embed)
# -------------------------
async def respond(
    interaction: discord.Interaction,
    *,
    content: str | None = None,
    embed: discord.Embed | None = None,
    ephemeral: bool = False,
    view: discord.ui.View | None = None,
):
    # Always return after responding in callers
    if interaction.response.is_done():
        return await interaction.followup.send(content=content, embed=embed, ephemeral=ephemeral, view=view)
    return await interaction.response.send_message(content=content, embed=embed, ephemeral=ephemeral, view=view)


# -------------------------
# Embed builders (boxed style)
# -------------------------
def embed_box(title: str, subtitle: str | None = None) -> discord.Embed:
    e = discord.Embed(title=title)
    if subtitle:
        e.description = subtitle
    return e


def build_balance_embed(member: discord.Member, coins: int) -> discord.Embed:
    e = embed_box("🪙 Ghost Coins Balance")
    e.add_field(name="User", value=f"**{member.display_name}**", inline=True)
    e.add_field(name="Balance", value=f"**{coins}** Ghost Coins", inline=True)
    return e


def build_shop_embed() -> discord.Embed:
    e = embed_box("🛒 Ghost Shop", "Use **/buy** to purchase an item.")
    for item in SHOP:
        e.add_field(
            name=f"{item['id']}. {item['name']} — {item['price']} coins",
            value=f"└ {item['desc']}",
            inline=False,
        )
    e.set_footer(text="Tip: Start typing in /buy for autocomplete.")
    return e


def build_inventory_embed(member: discord.Member, guild_id: int, user_id: int) -> discord.Embed:
    e = embed_box("🎒 Your Inventory", f"**{member.display_name}**")

    any_items = False
    for item in SHOP:
        qty, exp = get_item(guild_id, user_id, item["key"])
        if qty <= 0:
            continue

        any_items = True
        if exp:
            remaining = max(0, exp - now_utc_ts())
            mins = remaining // 60
            value = f"Active — **{mins} min** left"
        else:
            value = f"Quantity — **x{qty}**"

        e.add_field(name=item["name"], value=value, inline=False)

    if not any_items:
        e.description = "Your inventory is empty. Use **/shop**."

    return e


def build_contracts_embed(rows: list[dict]) -> discord.Embed:
    e = embed_box("📋 Daily Contracts", "Auto-random each day • Complete them for XP + Ghost Coins")

    for c in rows:
        status = "✅" if int(c["completed"]) == 1 else "🟡"
        title = f"{status} {c['title']}"
        progress = f"{c['progress']}/{c['target']}"
        reward = f"Reward: **{c['reward_xp']} XP** + **{c['reward_coins']} coins**"
        e.add_field(name=title, value=f"Progress: **{progress}**\n{reward}", inline=False)

    return e


def build_lastseen_embed(member: discord.Member, ts: int) -> discord.Embed:
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

    e = embed_box("🕒 Last Seen")
    e.add_field(name="Member", value=f"**{member.display_name}**", inline=False)
    e.add_field(name="Last Active", value=f"**{when_str}** ({ago_str} ago)", inline=False)
    return e


# -------------------------
# Cog
# -------------------------
class SlashCommands(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------- /contracts ----------
    @app_commands.command(name="contracts", description="View your daily contracts (XP + Ghost Coins)")
    async def contracts(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        rows = ensure_contracts(interaction.guild.id, interaction.user.id)
        if not rows:
            return await respond(interaction, content="No contracts found yet. Try again after doing some activity.")

        return await respond(interaction, embed=build_contracts_embed(rows))

    # ---------- /balance ----------
    @app_commands.command(name="balance", description="Check your Ghost Coins balance")
    async def balance(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        bal = get_coins(interaction.guild.id, interaction.user.id)
        return await respond(interaction, embed=build_balance_embed(interaction.user, bal))

    # ---------- /inventory ----------
    @app_commands.command(name="inventory", description="See your items and active boosts")
    async def inventory(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        e = build_inventory_embed(interaction.user, interaction.guild.id, interaction.user.id)
        return await respond(interaction, embed=e)

    # ---------- /lastseen ----------
    @app_commands.command(name="lastseen", description="See when a user was last active")
    @app_commands.describe(member="Pick a member (defaults to you)")
    async def lastseen(self, interaction: discord.Interaction, member: discord.Member | None = None):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        member = member or interaction.user
        ts = get_last_active(interaction.guild.id, member.id)
        if ts is None:
            e = embed_box("🕒 Last Seen", f"No activity record for **{member.display_name}** yet.")
            return await respond(interaction, embed=e)

        return await respond(interaction, embed=build_lastseen_embed(member, ts))

    # ---------- /shop ----------
    @app_commands.command(name="shop", description="View the Ghost Shop")
    async def shop(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")
        return await respond(interaction, embed=build_shop_embed())

    # ---------- /buy (AUTOCOMPLETE) ----------
    async def buy_autocomplete(self, interaction: discord.Interaction, current: str):
        cur = (current or "").lower().strip()
        choices: list[app_commands.Choice[str]] = []

        for item in SHOP:
            label = f"{item['id']}. {item['name']}"
            if cur in label.lower() or cur in str(item["id"]):
                choices.append(app_commands.Choice(name=label, value=str(item["id"])))

        return choices[:25]

    @app_commands.command(name="buy", description="Buy an item from the Ghost Shop")
    @app_commands.describe(item="Start typing: Lucky Charm / Insurance / XP Multiplier / Role Voucher")
    @app_commands.autocomplete(item=buy_autocomplete)
    async def buy(self, interaction: discord.Interaction, item: str):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        try:
            item_id = int(item)
        except ValueError:
            e = embed_box("❌ Purchase Failed", "Pick an item from the autocomplete list.")
            return await respond(interaction, embed=e, ephemeral=True)

        shop_item = SHOP_BY_ID.get(item_id)
        if not shop_item:
            e = embed_box("❌ Purchase Failed", "That item doesn’t exist.")
            return await respond(interaction, embed=e, ephemeral=True)

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        bal = get_coins(guild_id, user_id)
        price = shop_item["price"]

        if bal < price:
            e = embed_box("❌ Not enough Ghost Coins")
            e.add_field(name="You have", value=f"**{bal}** coins", inline=True)
            e.add_field(name="You need", value=f"**{price}** coins", inline=True)
            return await respond(interaction, embed=e, ephemeral=True)

        # pay
        add_coins(guild_id, user_id, -price)

        # grant item
        duration = shop_item["duration"]
        key = shop_item["key"]

        if duration:
            expires = now_utc_ts() + duration
            # timed boosts overwrite to 1 active boost (simple/clean)
            set_item(guild_id, user_id, key, qty=1, expires_at_ts=expires)
        else:
            qty, exp = get_item(guild_id, user_id, key)
            set_item(guild_id, user_id, key, qty=qty + 1, expires_at_ts=exp)

        new_bal = get_coins(guild_id, user_id)

        e = embed_box("✅ Purchase Complete!")
        e.add_field(name="Item", value=f"**{shop_item['name']}**", inline=False)
        e.add_field(name="Coins Left", value=f"**{new_bal}**", inline=False)
        return await respond(interaction, embed=e)

    # ---------- /investigate ----------
    @app_commands.command(name="investigate", description="Investigate a ghost (chance-based rewards, cooldown)")
    async def investigate(self, interaction: discord.Interaction):
        if not interaction.guild:
            return await respond(interaction, content="Use this in a server.")

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # cooldown
        next_ts = get_cooldown(guild_id, user_id, "investigate")
        now = now_utc_ts()
        if now < next_ts:
            left = next_ts - now
            mins = left // 60
            secs = left % 60
            e = embed_box("⏳ Cooldown", f"Try again in **{mins}m {secs}s**.")
            return await respond(interaction, embed=e, ephemeral=True)

        set_cooldown(guild_id, user_id, "investigate", now + INVESTIGATE_COOLDOWN_SECONDS)

        # success chance (+ lucky charm)
        success_chance = 0.55
        if is_boost_active(guild_id, user_id, LUCKY_CHARM):
            success_chance += 0.10

        success = random.random() < success_chance

        # rewards
        xp_reward = random.randint(20, 60)
        coins_reward = random.randint(25, 70)

        # XP multiplier doubles XP rewards (simple rule)
        if is_boost_active(guild_id, user_id, XP_MULTIPLIER):
            xp_reward *= 2

        if success:
            award_xp(guild_id, user_id, source="investigate", amount=xp_reward, daily_cap=999999)
            add_coins(guild_id, user_id, coins_reward)

            e = embed_box("✅ Investigation SUCCESS!", "You identified the ghost and secured evidence.")
            e.add_field(name="Rewards", value=f"**+{xp_reward} XP** and **+{coins_reward} coins**", inline=False)

            # contracts: ONLY progress keys that exist today
            todays = ensure_contracts(guild_id, user_id)
            today_keys = {c["contract_key"] for c in todays}

            completed: list[dict] = []
            if "investigate_1" in today_keys:
                completed += add_contract_progress(guild_id, user_id, "investigate_1", 1)
            if "investigate_2" in today_keys:
                completed += add_contract_progress(guild_id, user_id, "investigate_2", 1)

            await respond(interaction, embed=e)

            # payouts for newly completed contracts (one-time)
            await self._payout_completed_contracts(interaction, completed)
            return

        # fail penalty (coins) + insurance
        penalty = random.randint(5, 15)
        if consume_item(guild_id, user_id, INSURANCE, 1):
            penalty = 0

        if penalty > 0:
            add_coins(guild_id, user_id, -penalty)

        consolation_xp = random.randint(5, 15)
        if is_boost_active(guild_id, user_id, XP_MULTIPLIER):
            consolation_xp *= 2

        award_xp(guild_id, user_id, source="investigate", amount=consolation_xp, daily_cap=999999)

        e = embed_box("❌ Investigation FAILED", "The ghost played you.")
        e.add_field(name="Result", value=f"**+{consolation_xp} XP** and **-{penalty} coins**", inline=False)
        return await respond(interaction, embed=e)

    async def _payout_completed_contracts(self, interaction: discord.Interaction, completed: list[dict]) -> None:
        if not completed or not interaction.guild:
            return

        guild_id = interaction.guild.id
        user_id = interaction.user.id

        # de-dupe by contract_key (extra safety)
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

            e = embed_box("🏁 Contract Complete!")
            e.add_field(name="Contract", value=f"**{c['title']}**", inline=False)
            e.add_field(name="Rewards", value=f"**+{c['reward_xp']} XP** and **+{c['reward_coins']} coins**", inline=False)

            # send as a follow-up so it doesn’t clash with the main investigate response
            await interaction.followup.send(embed=e)


async def setup(bot: commands.Bot):
    await bot.add_cog(SlashCommands(bot))
