# cogs/help_menu.py
import discord
from discord.ext import commands
from discord import app_commands

# ---- EDIT THIS LIST WHEN YOU ADD COMMANDS ----
# name: what user types (without / or !)
# perms: short who-can-use
# desc: short description
COMMAND_CATEGORIES: dict[str, list[dict]] = {
    "Activity / Inactivity": [
        {"name": "lastseen", "perms": "Everyone", "desc": "See when someone was last active"},
        {"name": "guildid", "perms": "Everyone", "desc": "Show this server's Guild ID"},
    ],
    "Economy": [
        {"name": "balance", "perms": "Everyone", "desc": "Check your Ghost Coins"},
        {"name": "shop", "perms": "Everyone", "desc": "View the Ghost Shop"},
        {"name": "buy", "perms": "Everyone", "desc": "Buy an item from the shop"},
        {"name": "inventory", "perms": "Everyone", "desc": "View your inventory"},
    ],
    "Game Modes": [
        {"name": "contracts", "perms": "Everyone", "desc": "View today’s rotating game modes/tasks"},
        {"name": "investigate", "perms": "Everyone", "desc": "Investigate a ghost for rewards (cooldown)"},
    ],
    "Moderation": [
        {"name": "clear", "perms": "Admin", "desc": "Delete recent messages in a channel"},
        {"name": "kick", "perms": "Kick", "desc": "Kick a member"},
        {"name": "ban", "perms": "Ban", "desc": "Ban a member"},
        {"name": "unban", "perms": "Ban", "desc": "Unban a user"},
    ],
}


def build_page_text(category: str, page: int, page_size: int = 8) -> tuple[str, int]:
    items = COMMAND_CATEGORIES.get(category, [])
    total_pages = max(1, (len(items) + page_size - 1) // page_size)
    page = max(0, min(page, total_pages - 1))

    start = page * page_size
    end = start + page_size
    chunk = items[start:end]

    # 1 per line (as requested)
    lines = [f"`/{cmd['name']}` — *{cmd['perms']}* — {cmd['desc']}" for cmd in chunk]
    body = "\n".join(lines) if lines else "_No commands in this category yet._"
    return body, total_pages


class CategorySelect(discord.ui.Select):
    def __init__(self, parent_view: "HelpMenuView"):
        self.parent_view = parent_view
        options = [discord.SelectOption(label=k, value=k) for k in COMMAND_CATEGORIES.keys()]
        super().__init__(
            placeholder="Select a category...",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.parent_view.category = self.values[0]
        self.parent_view.page = 0
        await self.parent_view.render(interaction)


class HelpMenuView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.category = list(COMMAND_CATEGORIES.keys())[0]
        self.page = 0
        self.add_item(CategorySelect(self))

    def _make_embed(self) -> discord.Embed:
        body, total_pages = build_page_text(self.category, self.page)
        return discord.Embed(
            title="📜 Phasmocademy Command Menu",
            description=(
                f"**Category:** `{self.category}`\n\n"
                f"{body}\n\n"
                f"**Page {self.page + 1}/{total_pages}** • Use dropdown + buttons"
            ),
        )

    async def render(self, interaction: discord.Interaction):
        # Component interactions should always be edited via response.edit_message
        embed = self._make_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.page = 0
        await self.render(interaction)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.secondary)
    async def prev(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.page -= 1
        await self.render(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, _button: discord.ui.Button):
        self.page += 1
        await self.render(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, _button: discord.ui.Button):
        items = COMMAND_CATEGORIES.get(self.category, [])
        total_pages = max(1, (len(items) + 8 - 1) // 8)
        self.page = total_pages - 1
        await self.render(interaction)


class HelpMenu(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ✅ /help (the nice menu)
    @app_commands.command(name="help", description="Show Phasmocademy bot commands")
    async def slash_help(self, interaction: discord.Interaction):
        view = HelpMenuView()
        embed = view._make_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    # ✅ Prefix version (NOT named help, avoids conflicts)
    @commands.command(name="commands")
    async def prefix_commands(self, ctx: commands.Context):
        await ctx.send("✅ Use **/help** to open the command menu.")


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpMenu(bot))
