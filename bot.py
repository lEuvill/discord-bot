import discord
from discord.ext import commands
import re
from dotenv import load_dotenv
import os

load_dotenv()

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="r!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def send(ctx):
    full_text = ctx.message.content
    blocks = re.findall(r"```(.*?)```", full_text, re.DOTALL)

    if not blocks:
        await ctx.send("❌ No code blocks found.")
        return

    for block in blocks:
        await ctx.send(f"```{block.strip()}```")

bot.run(os.getenv("DISCORD_TOKEN"))
