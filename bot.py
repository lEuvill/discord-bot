import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import re
import json
import asyncio
from aiohttp import web

# Google Sheets authorization setup
scope = ['https://spreadsheets.google.com/feeds','https://www.googleapis.com/auth/drive']

# Load credentials from env var
creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
creds_dict = json.loads(creds_json)

creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
client = gspread.authorize(creds)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="r!", intents=intents)

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def send(ctx, sheet_url: str, date: str, until_row: int):
    try:
        # Extract the sheet ID from URL
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            await ctx.send("❌ Invalid Google Sheets URL.")
            return
        sheet_id = match.group(1)

        # Open the sheet
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.get_worksheet(0)  # you can adjust if needed

        # Get all values in the sheet
        all_values = worksheet.get_all_values()

        # Find the column index of the date
        header_row = all_values[0]  # assuming first row is header
        col_idx = None
        for i, cell in enumerate(header_row):
            if cell.strip() == date:
                col_idx = i
                break

        if col_idx is None:
            await ctx.send(f"❌ Date '{date}' not found in header row.")
            return

        # Collect values from col_idx, col_idx+1, col_idx+2 for rows 1 to until_row (1-based indexing)
        max_row = min(until_row, len(all_values) - 1)  # prevent index error

        response_lines = []
        for row in range(1, max_row + 1):
            row_values = all_values[row]
            vals = []
            for c in range(col_idx, col_idx + 3):
                vals.append(row_values[c] if c < len(row_values) else "")
            response_lines.append(" | ".join(vals))

        # Send the result in chunks to avoid Discord message limit (2000 chars)
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

# Minimal HTTP server for Render port binding
async def handle(request):
    return web.Response(text="Bot is running!")

async def run_webserver():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

async def main():
    await asyncio.gather(
        run_webserver(),
        bot.start(os.getenv("DISCORD_TOKEN"))
    )

asyncio.run(main())
