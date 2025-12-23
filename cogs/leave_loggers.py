import discord
from discord.ext import commands
from config import LEAVE_LOG_CHANNEL_ID

class LeaveLogger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        print("[LEAVE_LOG] LeaveLogger cog loaded.")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        if member.bot or member.guild is None:
            return

        channel = member.guild.get_channel(LEAVE_LOG_CHANNEL_ID) or member.guild.system_channel
        if channel is None:
            print("[LEAVE_LOG] No log channel found.")
            return

        # Basic info
        created = discord.utils.format_dt(member.created_at, style="R") if member.created_at else "Unknown"
        joined = discord.utils.format_dt(member.joined_at, style="R") if member.joined_at else "Unknown"

        embed = discord.Embed(
            title="Member Left",
            description=f"{member.mention} **{member}** left the server.",
        )
        embed.add_field(name="User ID", value=str(member.id), inline=True)
        embed.add_field(name="Account Created", value=str(created), inline=True)
        embed.add_field(name="Joined Server", value=str(joined), inline=True)
        if member.avatar:
            embed.set_thumbnail(url=member.display_avatar.url)

        await channel.send(embed=embed)
        print(f"[LEAVE_LOG] Logged leave: {member} ({member.id})")

async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LeaveLogger(bot))
