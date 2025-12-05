# cogs/quiet_channels.py

from datetime import datetime, timezone, timedelta
from discord.ext import commands, tasks
import discord

from config import QUIET_CHANNEL_IDS, QUIET_TIMEOUT_HOURS


class QuietChannels(commands.Cog):
    """Quiet channel monitor – pings if a channel has been silent too long."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.channel_last_message: dict[tuple[int, int], datetime] = {}
        self.last_quiet_ping: dict[tuple[int, int], datetime] = {}

        if not self.check_quiet_channels.is_running():
            self.check_quiet_channels.start()

    # ------------------------ Listeners ------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Remember when each monitored channel last saw a message."""
        if message.author.bot or message.guild is None:
            return

        now = datetime.now(timezone.utc)
        key = (message.guild.id, message.channel.id)
        self.channel_last_message[key] = now

    # ------------------------ Task ------------------------

    @tasks.loop(minutes=10)
    async def check_quiet_channels(self) -> None:
        """Periodically check if monitored channels have gone quiet."""
        await self.bot.wait_until_ready()

        now = datetime.now(timezone.utc)

        for guild in self.bot.guilds:
            for channel_id in QUIET_CHANNEL_IDS:
                channel = guild.get_channel(channel_id)
                if channel is None:
                    continue

                key = (guild.id, channel_id)
                last_msg = self.channel_last_message.get(key)

                # If we've never seen a message since the bot started, skip
                if last_msg is None:
                    continue

                # Has the channel been quiet long enough?
                if now - last_msg < timedelta(hours=QUIET_TIMEOUT_HOURS):
                    continue

                # Avoid spamming: only ping once per quiet window
                last_ping = self.last_quiet_ping.get(key)
                if last_ping is not None and now - last_ping < timedelta(hours=QUIET_TIMEOUT_HOURS):
                    continue

                # Try to send the ghost prompt
                try:
                    await channel.send(
                        "📻 *Static fills the radio… the ghost hasn’t been heard in hours.* "
                        "Who’s brave enough to talk?"
                    )
                    self.last_quiet_ping[key] = now
                except discord.Forbidden:
                    # No perms to send in that channel
                    continue


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(QuietChannels(bot))
