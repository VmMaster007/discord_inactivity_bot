import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import init_db, update_last_active


# Load environment variables from .env
load_dotenv()

# We'll expand these intents later when we start tracking activity
intents = discord.Intents.default()
intents.message_content = True   # so the bot can read command messages like !ping
intents.members = True           # for tracking users
intents.presences = True         # game activity (Phas/Marvel Rivals)

bot = commands.Bot(command_prefix="!", intents=intents)

def mark_active(member: discord.Member) -> None:
    """
    Record that this member was active just now (in the DB).
    """
    if member.bot:
        return  # ignore bots

    if member.guild is None:
        return  # just in case; we only care about guilds

    update_last_active(member.guild.id, member.id)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

@bot.event
async def on_message(message: discord.Message):
    # Ignore DMs and bot messages
    if message.author.bot:
        return

    if message.guild is None:
        return

    # Mark the author as active
    mark_active(message.author)

    # Important: allow commands (like !ping) to still work
    await bot.process_commands(message)


# Everytime a command is made create a new bot.command with the function under it!
@bot.command()
async def ping(ctx):
    await ctx.send("Pong!")


def main():
    # Initialize the database (create tables if needed)
    init_db()

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")
    
    bot.run(token)


if __name__ == "__main__":
    main()
