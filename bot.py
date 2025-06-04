import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import re
import json
from aiohttp import web
import asyncio
from dotenv import load_dotenv

load_dotenv()

# Google Sheets authorization
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
creds_dict = json.loads(creds_json)
creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

# Discord setup
intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="r!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def send(ctx, sheet_url: str, date: str, until_row: int):
    try:
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            await ctx.send("❌ Invalid Google Sheets URL.")
            return
        sheet_id = match.group(1)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)
        all_values = worksheet.get_all_values()
        header_row = all_values[0]
        col_idx = None
        for i, cell in enumerate(header_row):
            if cell.strip() == date:
                col_idx = i
                break
        if col_idx is None:
            await ctx.send(f"❌ Date '{date}' not found.")
            return
        max_row = min(until_row, len(all_values) - 1)
        response_lines = []
        for row in range(1, max_row + 1):
            row_values = all_values[row]
            vals = [(row_values[c] if c < len(row_values) else "") for c in range(col_idx, col_idx + 3)]
            response_lines.append(" | ".join(vals))
        message = ""
        for line in response_lines:
            if len(message) + len(line) + 1 > 1900:
                await ctx.send(f"```\n{message}```")
                message = ""
            message += line + "\n"
        if message:
            await ctx.send(f"```\n{message}```")
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

# Web server to keep bot alive on Render
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
    await asyncio.gather(
        run_webserver(),
        bot.start(os.getenv("DISCORD_TOKEN"))
    )

asyncio.run(main())
