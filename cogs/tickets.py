# cogs/tickets.py
# Hybrid ticket system (fixed):
# - Intake private thread (ticket-001)
# - Bug report forwards text + links + last 20 attachments from thread, then auto-closes thread
# - AFK/Holiday requires mod approval in AFK_APPROVAL_CHANNEL_ID
#   - Approve/Decline can only happen ONCE (buttons disable + embed color updates)
# - Talk to staff opens support channel under SUPPORT_CATEGORY_ID
# - Close from either side closes both

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import discord
from discord.ext import commands
from discord import app_commands

from config import STAFF_ROLE_ID, BUG_REPORTS_CHANNEL_ID, SUPPORT_CATEGORY_ID, AFK_APPROVAL_CHANNEL_ID
from db import (
    set_kick_exemption,
    next_ticket_number,
    upsert_ticket_link,
    get_ticket_link_by_thread,
    get_ticket_link_by_support_channel,
)

TICKET_PREFIX = "ticket-"
SUPPORT_PREFIX = "support-"


def ticket_name(n: int) -> str:
    return f"{TICKET_PREFIX}{n:03d}"


def support_name(n: int) -> str:
    return f"{SUPPORT_PREFIX}{n:03d}"


# ------------------ AFK: decline reason modal ------------------

class AfkDeclineReasonModal(discord.ui.Modal, title="Decline AFK Request"):
    reason = discord.ui.TextInput(
        label="Reason for declining",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=500,
    )

    def __init__(self, user_id: int, thread_id: int, message_id: int):
        super().__init__()
        self.user_id = user_id
        self.thread_id = thread_id
        self.message_id = message_id

    async def on_submit(self, interaction: discord.Interaction):
        # DM user
        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                await user.send(
                    "❌ Your AFK exemption was **declined**.\n\n"
                    f"Reason:\n{self.reason.value}"
                )
            except discord.Forbidden:
                pass

        # Update approval message embed -> RED and disable buttons
        try:
            msg = await interaction.channel.fetch_message(self.message_id)  # type: ignore
            embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🛂 AFK Exemption Request")
            embed.color = discord.Color.red()
            embed.add_field(name="Status", value=f"❌ Declined by {interaction.user.mention}", inline=False)
            view = AfkApprovalView(
                guild_id=0, user_id=0, until_ts=0, thread_id=0, message_id=self.message_id
            )
            view.locked = True
            for child in view.children:
                child.disabled = True
            await msg.edit(embed=embed, view=view)
        except Exception:
            pass

        await interaction.response.send_message("Declined. User notified.", ephemeral=True)

        # Close intake thread
        try:
            fetched = await interaction.client.fetch_channel(self.thread_id)
            if isinstance(fetched, discord.Thread):
                await fetched.edit(archived=True, locked=True)
        except Exception:
            pass


# ------------------ AFK: approval view ------------------
# Persisted buttons must have custom_id + view timeout=None

class AfkApprovalView(discord.ui.View):
    def __init__(self, guild_id: int, user_id: int, until_ts: int, thread_id: int, message_id: int = 0):
        super().__init__(timeout=None)
        self.guild_id = guild_id
        self.user_id = user_id
        self.until_ts = until_ts
        self.thread_id = thread_id
        self.message_id = message_id
        self.locked: bool = False

    async def _is_already_decided(self, interaction: discord.Interaction) -> bool:
        # If view locked in memory
        if self.locked:
            return True

        # If restarted, check message embed for Status field
        try:
            msg = interaction.message
            if msg and msg.embeds:
                for f in msg.embeds[0].fields:
                    if f.name.lower() == "status":
                        return True
        except Exception:
            pass
        return False

    async def _finalize_message(self, interaction: discord.Interaction, approved: bool, declined_reason: str | None = None):
        # Disable buttons + set embed color
        try:
            msg = interaction.message
            embed = msg.embeds[0] if msg.embeds else discord.Embed(title="🛂 AFK Exemption Request")
            if approved:
                embed.color = discord.Color.green()
                until_dt = datetime.fromtimestamp(self.until_ts, tz=timezone.utc)
                embed.add_field(
                    name="Status",
                    value=f"✅ Approved by {interaction.user.mention}\nUntil: **{until_dt.strftime('%d/%m/%Y %H:%M UTC')}**",
                    inline=False,
                )
            else:
                embed.color = discord.Color.red()
                embed.add_field(
                    name="Status",
                    value=f"❌ Declined by {interaction.user.mention}\nReason: {declined_reason or '*None*'}",
                    inline=False,
                )

            self.locked = True
            for child in self.children:
                child.disabled = True

            await msg.edit(embed=embed, view=self)
        except Exception:
            pass

    @discord.ui.button(
        label="Approve",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="afk:approve",
    )
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._is_already_decided(interaction):
            return await interaction.response.send_message("This AFK request is already decided.", ephemeral=True)

        # Apply exemption
        set_kick_exemption(
            guild_id=self.guild_id,
            user_id=self.user_id,
            exempt_until_ts=self.until_ts,
            created_by=interaction.user.id,
        )

        # DM user once
        user = interaction.client.get_user(self.user_id)
        if user:
            try:
                until_dt = datetime.fromtimestamp(self.until_ts, tz=timezone.utc)
                await user.send(
                    "✅ Your AFK exemption has been **approved**.\n"
                    f"Exempt until: **{until_dt.strftime('%d/%m/%Y %H:%M UTC')}**"
                )
            except discord.Forbidden:
                pass

        await interaction.response.send_message("Approved. User notified.", ephemeral=True)

        # Update message + disable buttons
        await self._finalize_message(interaction, approved=True)

        # Close intake thread
        try:
            fetched = await interaction.client.fetch_channel(self.thread_id)
            if isinstance(fetched, discord.Thread):
                await fetched.edit(archived=True, locked=True)
        except Exception:
            pass

    @discord.ui.button(
        label="Decline",
        style=discord.ButtonStyle.danger,
        emoji="❌",
        custom_id="afk:decline",
    )
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        if await self._is_already_decided(interaction):
            return await interaction.response.send_message("This AFK request is already decided.", ephemeral=True)

        # We need the modal to collect decline reason
        await interaction.response.send_modal(
            AfkDeclineReasonModal(
                user_id=self.user_id,
                thread_id=self.thread_id,
                message_id=interaction.message.id if interaction.message else 0,
            )
        )


# ------------------ AFK: request modal ------------------

class AfkModal(discord.ui.Modal, title="AFK / Holiday"):
    days = discord.ui.TextInput(
        label="Days away (1–365)",
        placeholder="Example: 14",
        required=True,
        max_length=3,
    )
    reason = discord.ui.TextInput(
        label="Reason (optional)",
        placeholder="Holiday / exams / work trip / etc. You can paste links here.",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=800,
    )

    def __init__(self, thread: discord.Thread, requester: discord.Member):
        super().__init__()
        self.thread = thread
        self.requester = requester

    async def on_submit(self, interaction: discord.Interaction):
        raw = str(self.days.value).strip()
        try:
            d = int(raw)
            if d < 1 or d > 365:
                raise ValueError
        except ValueError:
            return await interaction.response.send_message("Please enter days between 1 and 365.", ephemeral=True)

        until_dt = datetime.now(timezone.utc) + timedelta(days=d)
        until_ts = int(until_dt.timestamp())
        reason_txt = (self.reason.value or "").strip()

        # Approval channel
        try:
            approval_ch = await interaction.client.fetch_channel(AFK_APPROVAL_CHANNEL_ID)
        except Exception:
            approval_ch = None

        if not isinstance(approval_ch, discord.TextChannel):
            return await interaction.response.send_message(
                "AFK approval channel is not configured. Tell an admin.",
                ephemeral=True,
            )

        embed = discord.Embed(title="🛂 AFK Exemption Request", timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{self.requester.mention} (`{self.requester.id}`)", inline=False)
        embed.add_field(name="Until", value=until_dt.strftime("%d/%m/%Y %H:%M UTC"), inline=False)
        embed.add_field(name="Reason/Links", value=reason_txt or "*None*", inline=False)
        embed.add_field(name="Intake Thread", value=self.thread.mention, inline=False)

        msg = await approval_ch.send(
            embed=embed,
            view=AfkApprovalView(
                guild_id=interaction.guild_id,
                user_id=self.requester.id,
                until_ts=until_ts,
                thread_id=self.thread.id,
            ),
        )

        # Store message id into the view instance (nice-to-have)
        try:
            await msg.edit(view=AfkApprovalView(
                guild_id=interaction.guild_id,
                user_id=self.requester.id,
                until_ts=until_ts,
                thread_id=self.thread.id,
                message_id=msg.id,
            ))
        except Exception:
            pass

        await interaction.response.send_message(
            "🕒 AFK request sent to staff for approval. This thread will close after a decision.",
            ephemeral=True,
        )
        await self.thread.send("🕒 AFK request sent to staff for approval.")


# ------------------ BUG REPORT ------------------

class BugReportModal(discord.ui.Modal, title="Bug Report"):
    details = discord.ui.TextInput(
        label="Describe the bug",
        placeholder="Type Your Message Here, And Paste Links If Needed",
        style=discord.TextStyle.paragraph,
        required=True,
        max_length=1500,
    )

    def __init__(self, thread: discord.Thread, requester: discord.Member):
        super().__init__()
        self.thread = thread
        self.requester = requester

    async def on_submit(self, interaction: discord.Interaction):
        # Mods-only bug channel
        try:
            bug_ch = await interaction.client.fetch_channel(BUG_REPORTS_CHANNEL_ID)
        except Exception:
            bug_ch = None

        if not isinstance(bug_ch, discord.TextChannel):
            return await interaction.response.send_message(
                "Bug reports channel is not configured. Tell an admin.",
                ephemeral=True,
            )

        embed = discord.Embed(title="🐛 Bug Report", timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{self.requester.mention} (`{self.requester.id}`)", inline=False)
        embed.add_field(name="Details / Links", value=self.details.value[:1024], inline=False)
        embed.add_field(name="Intake Thread", value=self.thread.mention, inline=False)

        await bug_ch.send(embed=embed)

        # Forward last 20 attachments (images/videos)
        try:
            async for msg in self.thread.history(limit=20):
                for att in msg.attachments:
                    try:
                        await bug_ch.send(
                            content=f"📎 Attachment from {self.requester.mention}",
                            file=await att.to_file(),
                        )
                    except Exception:
                        pass
        except Exception:
            pass

        await interaction.response.send_message("✅ Bug submitted. Closing ticket thread…", ephemeral=True)

        # Auto-close intake thread
        try:
            await self.thread.send("🔒 Bug report submitted. Closing…")
            await self.thread.edit(archived=True, locked=True)
        except Exception:
            pass


# ------------------ SUPPORT CHANNEL HELPERS ------------------

async def create_support_channel(guild: discord.Guild, requester: discord.Member, n: int) -> discord.TextChannel:
    category = guild.get_channel(SUPPORT_CATEGORY_ID)
    if category is None:
        category = await guild.fetch_channel(SUPPORT_CATEGORY_ID)
    if not isinstance(category, discord.CategoryChannel):
        raise RuntimeError("SUPPORT_CATEGORY_ID is not a category channel.")

    staff_role = guild.get_role(STAFF_ROLE_ID)
    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        requester: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
    }
    if staff_role:
        overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

    ch = await guild.create_text_channel(
        support_name(n),
        category=category,
        overwrites=overwrites,
        topic="Support ticket",
        reason="Support ticket created",
    )
    return ch


# ------------------ CLOSE BOTH (THREAD <-> SUPPORT) ------------------

class ThreadCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close_thread")
    async def close_thread(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Guild not found.", ephemeral=True)
        if not interaction.channel or not isinstance(interaction.channel, discord.Thread):
            return await interaction.response.send_message("This must be used inside an intake thread.", ephemeral=True)

        guild = interaction.guild
        thread: discord.Thread = interaction.channel
        link = get_ticket_link_by_thread(guild.id, thread.id)

        await interaction.response.send_message("Closing ticket…", ephemeral=True)

        support_channel_id = link[2] if link else None
        if support_channel_id:
            support_ch = guild.get_channel(support_channel_id)
            if support_ch is None:
                try:
                    support_ch = await interaction.client.fetch_channel(support_channel_id)
                except Exception:
                    support_ch = None
            if isinstance(support_ch, discord.TextChannel):
                try:
                    await support_ch.send("🔒 Ticket closed from intake thread. Closing this channel…")
                    await support_ch.delete(reason=f"Ticket closed by {interaction.user} (from thread)")
                except Exception:
                    pass

        try:
            await thread.edit(archived=True, locked=True, reason=f"Closed by {interaction.user}")
        except Exception:
            pass


class SupportCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="ticket:close_support")
    async def close_support(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild:
            return await interaction.response.send_message("Guild not found.", ephemeral=True)
        if not interaction.channel or not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("This must be used inside a support channel.", ephemeral=True)

        guild = interaction.guild
        channel: discord.TextChannel = interaction.channel

        member = interaction.user if isinstance(interaction.user, discord.Member) else None
        if not member:
            return await interaction.response.send_message("Invalid user.", ephemeral=True)

        is_staff = False
        if STAFF_ROLE_ID:
            is_staff = any(r.id == STAFF_ROLE_ID for r in member.roles)
        if not (is_staff or member.guild_permissions.manage_channels):
            return await interaction.response.send_message("Only staff can close this ticket.", ephemeral=True)

        link = get_ticket_link_by_support_channel(guild.id, channel.id)

        await interaction.response.send_message("Closing ticket…", ephemeral=True)

        intake_thread_id = link[1] if link else None
        if intake_thread_id:
            th = guild.get_thread(intake_thread_id)
            if th is None:
                try:
                    fetched = await interaction.client.fetch_channel(intake_thread_id)
                    th = fetched if isinstance(fetched, discord.Thread) else None
                except Exception:
                    th = None
            if isinstance(th, discord.Thread):
                try:
                    await th.send("🔒 Ticket closed by staff. Closing this thread…")
                    await th.edit(archived=True, locked=True, reason=f"Closed by {interaction.user} (from support)")
                except Exception:
                    pass

        try:
            await channel.delete(reason=f"Ticket closed by {interaction.user}")
        except Exception:
            pass


# ------------------ INTAKE MENU ------------------

class IntakeSelect(discord.ui.Select):
    def __init__(self, thread: discord.Thread, requester: discord.Member, n: int):
        self.thread = thread
        self.requester = requester
        self.n = n

        super().__init__(
            placeholder="Choose an option…",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label="AFK/Holiday → requires staff approval", value="afk", emoji="🏖️"),
                discord.SelectOption(label="Bug report → sends to mods + closes", value="bug", emoji="🐛"),
                discord.SelectOption(label="Talk to staff → opens support ticket", value="staff", emoji="🧑‍⚖️"),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        # Always respond safely (prevents "interaction failed")
        try:
            if interaction.user.id != self.requester.id:
                return await interaction.response.send_message("Only the ticket creator can use this.", ephemeral=True)

            choice = self.values[0]

            if choice == "afk":
                return await interaction.response.send_modal(AfkModal(self.thread, self.requester))

            if choice == "bug":
                return await interaction.response.send_modal(BugReportModal(self.thread, self.requester))

            if choice == "staff":
                guild = interaction.guild
                if guild is None:
                    return await interaction.response.send_message("Guild not found.", ephemeral=True)

                support_ch = await create_support_channel(guild, self.requester, self.n)

                upsert_ticket_link(
                    guild_id=guild.id,
                    ticket_number=self.n,
                    intake_thread_id=self.thread.id,
                    support_channel_id=support_ch.id,
                )

                staff_role = guild.get_role(STAFF_ROLE_ID) if STAFF_ROLE_ID else None
                mention = staff_role.mention if staff_role else "@staff"

                embed = discord.Embed(title="🧑‍⚖️ Support Ticket", description="A user requested staff help.")
                embed.add_field(name="User", value=self.requester.mention, inline=False)
                embed.add_field(name="Intake Thread", value=self.thread.mention, inline=False)

                await support_ch.send(content=mention, embed=embed, view=SupportCloseView())
                await support_ch.send(f"{self.requester.mention} Please explain your issue here.")

                return await interaction.response.send_message(f"✅ Support ticket opened: {support_ch.mention}", ephemeral=True)

        except Exception as e:
            # This prevents the red "interaction failed" bar
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(f"Something went wrong: `{e}`", ephemeral=True)
                else:
                    await interaction.response.send_message(f"Something went wrong: `{e}`", ephemeral=True)
            except Exception:
                pass


class IntakeView(discord.ui.View):
    def __init__(self, thread: discord.Thread, requester: discord.Member, n: int):
        super().__init__(timeout=900)  # 15 min, not persistent
        self.add_item(IntakeSelect(thread, requester, n))


# ------------------ PANEL BUTTON (persistent) ------------------

class CreateTicketView(discord.ui.View):
    def __init__(self, bot: commands.Bot):
        super().__init__(timeout=None)
        self.bot = bot

    @discord.ui.button(
        label="Create ticket",
        style=discord.ButtonStyle.secondary,
        emoji="📩",
        custom_id="ticket:panel_create",
    )
    async def create(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            return await interaction.response.send_message("This can only be used in a server.", ephemeral=True)

        guild = interaction.guild
        requester = interaction.user

        if not isinstance(interaction.channel, discord.TextChannel):
            return await interaction.response.send_message("Click this in a normal text channel.", ephemeral=True)

        intake: discord.TextChannel = interaction.channel

        me = guild.me or guild.get_member(self.bot.user.id)
        if me is None:
            return await interaction.response.send_message("Bot member not found.", ephemeral=True)

        perms = intake.permissions_for(me)
        if not perms.create_private_threads:
            return await interaction.response.send_message(
                "I can’t create **private threads** here.\nGive me **Create Private Threads**.",
                ephemeral=True,
            )
        if not perms.send_messages_in_threads:
            return await interaction.response.send_message(
                "I can’t send messages in threads here.\nGive me **Send Messages in Threads**.",
                ephemeral=True,
            )

        n = next_ticket_number(guild.id)
        name = ticket_name(n)

        try:
            thread = await intake.create_thread(
                name=name,
                type=discord.ChannelType.private_thread,
                auto_archive_duration=1440,
                invitable=False,
                reason="Ticket intake thread created",
            )
            await thread.add_user(requester)
        except discord.Forbidden:
            return await interaction.response.send_message(
                "Discord blocked private thread creation. Check perms + enable Threads.",
                ephemeral=True,
            )
        except discord.HTTPException as e:
            return await interaction.response.send_message(f"Failed to create thread: `{e}`", ephemeral=True)

        upsert_ticket_link(guild.id, n, thread.id, None)

        await interaction.response.send_message(f"✅ Opened intake: {thread.mention}", ephemeral=True)

        embed = discord.Embed(
            title="Ticket Intake",
            description=(
                "Choose an option:\n\n"
                "🏖️ AFK/Holiday → requires staff approval\n"
                "🐛 Bug report → sends to mods + closes\n"
                "🧑‍⚖️ Talk to staff → opens a support ticket channel"
            ),
        )
        await thread.send(content=requester.mention, embed=embed, view=IntakeView(thread, requester, n))
        await thread.send(view=ThreadCloseView())


class TicketsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Persistent views
        self.bot.add_view(CreateTicketView(bot))
        self.bot.add_view(ThreadCloseView())
        self.bot.add_view(SupportCloseView())
        self.bot.add_view(AfkApprovalView(guild_id=0, user_id=0, until_ts=0, thread_id=0))

    @app_commands.command(name="ticketpanel", description="Post the ticket panel (Create Ticket button).")
    @app_commands.checks.has_permissions(administrator=True)
    async def ticketpanel(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Ticket", description="To create a ticket click 📩 below.")
        await interaction.channel.send(embed=embed, view=CreateTicketView(self.bot))
        await interaction.response.send_message("✅ Ticket panel posted.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(TicketsCog(bot))
