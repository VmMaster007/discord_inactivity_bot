# cogs/housekeeping.py

from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
import discord

from db import get_inactive_users
from config import (
    GUILD_ID,
    STAFF_CHANNEL_ID,
    INVITE_CHANNEL_ID,
    NOTIFY_CHANNEL_ID,
    INACTIVITY_DAYS,
    INACTIVITY_NOTIFY_DAYS,
    PROTECTED_ROLE_IDS,
    format_timestamp,
)


class Housekeeping(commands.Cog):
    """Inactivity cleanup + daily inactivity notifications."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Start background tasks
        if not self.inactivity_cleanup.is_running():
            self.inactivity_cleanup.start()
        if not self.notify_inactive_members.is_running():
            self.notify_inactive_members.start()

    # ------------------------ Core cleanup logic ------------------------

    async def run_inactivity_cleanup(self, real_run: bool) -> None:
        """
        Shared logic for inactivity cleanup.

        real_run = False -> DRY-RUN (no DM, no kick, just logs)
        real_run = True  -> REAL RUN (DM + invite + kick)
        """
        await self.bot.wait_until_ready()

        guild = self.bot.get_guild(GUILD_ID)
        if guild is None:
            print("[CLEANUP] Guild not found")
            return

        now_utc = datetime.now(timezone.utc)
        cutoff = now_utc - timedelta(days=INACTIVITY_DAYS)
        cutoff_ts = int(cutoff.timestamp())

        mode = "REAL" if real_run else "DRY-RUN"
        print(f"[CLEANUP {mode}] Running inactivity check, cutoff_ts={cutoff_ts}")

        # Fetch inactive users from DB
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

    # ------------------------ Tasks ------------------------

    @tasks.loop(hours=24)
    async def inactivity_cleanup(self) -> None:
        """Scheduled REAL cleanup (runs once per day)."""
        await self.run_inactivity_cleanup(real_run=True)

    @tasks.loop(hours=24)
    async def notify_inactive_members(self) -> None:
        """
        Once a day, post a message listing members
        who have been inactive longer than INACTIVITY_NOTIFY_DAYS.
        """
        await self.bot.wait_until_ready()

        now_ts = int(datetime.now(timezone.utc).timestamp())
        cutoff_ts = now_ts - INACTIVITY_NOTIFY_DAYS * 86400

        guild = self.bot.get_guild(GUILD_ID)
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

    # ------------------------ Command ------------------------

    @commands.command(name="cleanup_test")
    @commands.has_permissions(administrator=True)
    async def cleanup_test(self, ctx: commands.Context) -> None:
        """
        Run the inactivity cleanup in DRY-RUN mode:
        - No one is DM'd
        - No one is kicked
        - It just logs who *would* be kicked to the staff channel + console
        """
        await self.run_inactivity_cleanup(real_run=False)
        await ctx.send("Ran inactivity cleanup in DRY-RUN mode. Check staff channel + logs.")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Housekeeping(bot))
