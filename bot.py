import os
import discord
from discord.ext import commands
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# We'll expand these intents later when we start tracking activity
intents = discord.Intents.default()

bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")


def main():
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in .env file")
    bot.run(token)


if __name__ == "__main__":
    main()
