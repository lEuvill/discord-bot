import discord
from discord.ext import commands
import re
from dotenv import load_dotenv
import os
from aiohttp import web
import asyncio

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

# Simple webserver handler
async def handle(request):
    return web.Response(text="Bot is running!")

async def run_webserver():
    app = web.Application()
    app.add_routes([web.get('/', handle)])
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get('PORT', 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Webserver running on port {port}")

async def main():
    # Start both webserver and bot concurrently
    await asyncio.gather(
        run_webserver(),
        bot.start(os.getenv("DISCORD_TOKEN"))
    )

asyncio.run(main())
