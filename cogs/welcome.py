# cogs/welcome.py
import io

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageOps

from config import (
    WELCOME_CHANNEL_ID,
    VERIFIED_ROLE_ID,
    WELCOME_BG_PATH,
    WELCOME_FONT_PATH,
)

# -------- CARD SIZE (SMALLER) --------
CARD_W, CARD_H = 900, 450
AVATAR_SIZE = 200


def _resample():
    # Pillow compatibility
    return getattr(Image, "Resampling", Image).LANCZOS


async def generate_welcome_card(member: discord.Member) -> discord.File:
    """Create a PNG welcome card with avatar + text and return it as a discord.File."""

    # Layout constants (define OUTSIDE try blocks so they always exist)
    avatar_x = 40
    avatar_y = (CARD_H - AVATAR_SIZE) // 2
    text_x = avatar_x + AVATAR_SIZE + 40

    # --- Background ---
    try:
        base_bg = Image.open(WELCOME_BG_PATH).convert("RGBA")
        print(f"[WELCOME] Loaded background image from {WELCOME_BG_PATH}")
    except Exception as e:
        print(f"[WELCOME] Could not open background {WELCOME_BG_PATH}: {e}")
        base_bg = Image.new("RGBA", (CARD_W, CARD_H), (5, 10, 16, 255))

    base = ImageOps.fit(base_bg, (CARD_W, CARD_H), method=_resample())

    overlay = Image.new("RGBA", (CARD_W, CARD_H), (0, 0, 0, 90))
    base = Image.alpha_composite(base, overlay)

    # --- Avatar ---
    try:
        # IMPORTANT: request a POWER-OF-2 size from Discord (256/512/1024)
        avatar_asset = member.display_avatar.replace(size=512, static_format="png")
        avatar_bytes = await avatar_asset.read()

        avatar_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
        avatar_img = ImageOps.fit(avatar_img, (AVATAR_SIZE, AVATAR_SIZE), method=_resample())

        # Circular mask
        mask = Image.new("L", (AVATAR_SIZE, AVATAR_SIZE), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.ellipse((0, 0, AVATAR_SIZE, AVATAR_SIZE), fill=255)

        # Ring behind avatar
        ring_size = AVATAR_SIZE + 12
        ring = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
        ring_draw = ImageDraw.Draw(ring)
        ring_draw.ellipse((0, 0, ring_size, ring_size), fill=(255, 255, 255, 60))

        base.paste(ring, (avatar_x - 6, avatar_y - 6), ring)
        base.paste(avatar_img, (avatar_x, avatar_y), mask)

    except Exception as e:
        print(f"[WELCOME] Failed to process avatar for {member}: {e}")
        # Continue without avatar (no crash)

    # --- Text ---
    draw = ImageDraw.Draw(base)

    try:
        font_big = ImageFont.truetype(WELCOME_FONT_PATH, 52)
        font_small = ImageFont.truetype(WELCOME_FONT_PATH, 28)
    except Exception as e:
        print(f"[WELCOME] Could not load font {WELCOME_FONT_PATH}: {e}")
        font_big = ImageFont.load_default()
        font_small = ImageFont.load_default()

    guild_name = member.guild.name
    username = member.display_name

    def shadow_text(x, y, text, font, fill):
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 160))
        draw.text((x, y), text, font=font, fill=fill)

    shadow_text(text_x, 130, "WELCOME TO THE HUNT", font_big, (255, 255, 255, 255))
    shadow_text(text_x, 215, username.upper(), font_small, (210, 230, 255, 255))
    shadow_text(text_x, 255, f"IN {guild_name.upper()}", font_small, (190, 210, 245, 255))

    buf = io.BytesIO()
    base.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    return discord.File(buf, filename="welcome.png")



class Welcome(commands.Cog):
    """Welcome cards when users get the Verified role."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("[WELCOME] Welcome cog loaded.")
        print(
            f"[WELCOME] VERIFIED_ROLE_ID={VERIFIED_ROLE_ID}, "
            f"WELCOME_CHANNEL_ID={WELCOME_CHANNEL_ID}"
        )

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if after.bot or after.guild is None:
            return

        if before.roles == after.roles:
            return

        verified_role = after.guild.get_role(VERIFIED_ROLE_ID)
        if verified_role is None:
            return

        if verified_role not in before.roles and verified_role in after.roles:
            channel = (
                after.guild.get_channel(WELCOME_CHANNEL_ID)
                or after.guild.system_channel
            )
            if channel is None:
                return

            try:
                card_file = await generate_welcome_card(after)
            except Exception:
                await channel.send(f"{after.mention} has joined the hunt 👻")
                return

            await channel.send(
                content=f"{after.mention} has joined the hunt 👻",
                file=card_file,
                allowed_mentions=discord.AllowedMentions(
                    users=True, roles=False, everyone=False
                ),
            )

    @commands.command(name="welcome_test")
    @commands.has_permissions(manage_guild=True)
    async def welcome_test(
        self, ctx: commands.Context, member: discord.Member | None = None
    ):
        target = member or ctx.author
        channel = ctx.channel

        card_file = await generate_welcome_card(target)
        await channel.send(
            content=f"{target.mention} has joined the hunt 👻",
            file=card_file,
            allowed_mentions=discord.AllowedMentions(
                users=True, roles=False, everyone=False
            ),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Welcome(bot))
