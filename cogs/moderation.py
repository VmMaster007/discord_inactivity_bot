# cogs/moderation.py

from discord.ext import commands
import discord

from config import STAFF_CHANNEL_ID


class Moderation(commands.Cog):
    """Basic moderation commands (clear, kick, ban, unban) and error handling."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------ Commands ------------------------

    @commands.command(name="clear", aliases=["purge"])
    @commands.has_permissions(administrator=True)
    async def clear_messages(self, ctx: commands.Context, amount: int) -> None:
        """
        Delete the last <amount> messages in the current channel.
        Usage: !clear 10  or  !purge 25
        """
        if amount <= 0:
            await ctx.send("Amount must be a positive number.", delete_after=5)
            return

        if amount > 200:
            await ctx.send(
                "I can only delete up to 200 messages at once (for safety).",
                delete_after=5,
            )
            return

        # +1 to include the command message itself
        deleted = await ctx.channel.purge(
            limit=amount + 1,
            reason=f"Requested by {ctx.author} via !clear",
        )
        deleted_count = max(len(deleted) - 1, 0)

        await ctx.send(f"🧹 Deleted **{deleted_count}** messages.", delete_after=5)

    @commands.command(name="kick")
    @commands.has_permissions(administrator=True)
    async def kick_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided.",
    ) -> None:
        """
        Kick a member from the server.
        Usage: !kick @user [reason]
        """
        if ctx.guild is None:
            return

        if member == ctx.author:
            await ctx.send("You can't kick yourself.")
            return

        bot_member = ctx.guild.me
        if bot_member is None or not bot_member.guild_permissions.kick_members:
            await ctx.send("I don't have permission to kick members.")
            return

        # Basic role hierarchy checks
        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("You can't kick someone with an equal or higher role than you.")
            return

        if member.top_role >= bot_member.top_role:
            await ctx.send("I can't kick that member because their top role is above mine.")
            return

        await member.kick(reason=f"{reason} (kicked by {ctx.author})")
        await ctx.send(f"👢 Kicked **{member}**. Reason: {reason}")

        staff_channel = ctx.guild.get_channel(STAFF_CHANNEL_ID)
        if staff_channel is not None:
            await staff_channel.send(
                f"👢 **Kick** | {member} was kicked by {ctx.author}.\n"
                f"Reason: {reason}"
            )

    @commands.command(name="ban")
    @commands.has_permissions(administrator=True)
    async def ban_member(
        self,
        ctx: commands.Context,
        member: discord.Member,
        *,
        reason: str = "No reason provided.",
    ) -> None:
        """
        Ban a member from the server.
        Usage: !ban @user [reason]
        """
        if ctx.guild is None:
            return

        if member == ctx.author:
            await ctx.send("You can't ban yourself.")
            return

        bot_member = ctx.guild.me
        if bot_member is None or not bot_member.guild_permissions.ban_members:
            await ctx.send("I don't have permission to ban members.")
            return

        if member.top_role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            await ctx.send("You can't ban someone with an equal or higher role than you.")
            return

        if member.top_role >= bot_member.top_role:
            await ctx.send("I can't ban that member because their top role is above mine.")
            return

        await member.ban(
            reason=f"{reason} (banned by {ctx.author})",
            delete_message_days=0,
        )
        await ctx.send(f"🔨 Banned **{member}**. Reason: {reason}")

        staff_channel = ctx.guild.get_channel(STAFF_CHANNEL_ID)
        if staff_channel is not None:
            await staff_channel.send(
                f"🔨 **Ban** | {member} was banned by {ctx.author}.\n"
                f"Reason: {reason}"
            )

    @commands.command(name="unban")
    @commands.has_permissions(administrator=True)
    async def unban_member(
        self,
        ctx: commands.Context,
        user: discord.User,
        *,
        reason: str = "No reason provided.",
    ) -> None:
        """
        Unban a user by mention or ID.
        Usage:
          !unban @user
          !unban 123456789012345678
        """
        if ctx.guild is None:
            return

        bot_member = ctx.guild.me
        if bot_member is None or not bot_member.guild_permissions.ban_members:
            await ctx.send("I don't have permission to unban members.")
            return

        bans = await ctx.guild.bans()
        banned_users = {ban_entry.user.id: ban_entry for ban_entry in bans}

        if user.id not in banned_users:
            await ctx.send("That user is not currently banned.")
            return

        await ctx.guild.unban(user, reason=f"{reason} (unbanned by {ctx.author})")
        await ctx.send(f"✅ Unbanned **{user}**. Reason: {reason}")

        staff_channel = ctx.guild.get_channel(STAFF_CHANNEL_ID)
        if staff_channel is not None:
            await staff_channel.send(
                f"✅ **Unban** | {user} was unbanned by {ctx.author}.\n"
                f"Reason: {reason}"
            )

    # ------------------------ Error handler ------------------------

    @commands.Cog.listener()
    async def on_command_error(
        self,
        ctx: commands.Context,
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("You need the **Administrator** permission to use that command.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("I couldn't understand that argument. Check your syntax and try again.")
        else:
            # Log anything unexpected so you can debug in console
            print(f"[COMMAND ERROR] {repr(error)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Moderation(bot))
