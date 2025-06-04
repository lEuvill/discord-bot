import discord
from discord.ext import commands
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import re
import json
import asyncio
from aiohttp import web
import threading

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
async def ping(ctx):
    await ctx.send("🏓 Pong! Bot is working!")

@bot.command()
async def send(ctx, sheet_url: str, sheet_name: str, date: str, until_row: int):
    try:
        # Extract the sheet ID from URL
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            await ctx.send("❌ Invalid Google Sheets URL.")
            return
        
        sheet_id = match.group(1)
        
        # Open the spreadsheet
        spreadsheet = client.open_by_key(sheet_id)
        
        # Try to open the specific worksheet by name
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            # List available sheets for user reference
            available_sheets = [ws.title for ws in spreadsheet.worksheets()]
            await ctx.send(f"❌ Sheet '{sheet_name}' not found. Available sheets: {', '.join(available_sheets)}")
            return
        
        # Get all values in the sheet
        all_values = worksheet.get_all_values()
        
        if not all_values:
            await ctx.send("❌ The sheet appears to be empty.")
            return
        
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
        # Adjust row indexes because all_values is zero indexed
        max_row = min(until_row, len(all_values) - 1)  # prevent index error
        
        response_lines = []
        for row in range(1, max_row + 1):
            if row >= len(all_values):
                break
            
            row_values = all_values[row]
            # Some rows might be shorter, fill with empty string if missing
            vals = []
            for c in range(col_idx, col_idx + 3):
                if c < len(row_values):
                    vals.append(row_values[c])
                else:
                    vals.append("")
            response_lines.append(" | ".join(vals))
        
        if not response_lines:
            await ctx.send("❌ No data found in the specified range.")
            return
        
        # Send the result in chunks to avoid Discord message limit (2000 chars)
        message = f"**Data from sheet '{sheet_name}' for date '{date}':**\n"
        for line in response_lines:
            if len(message) + len(line) + 10 > 1900:  # Leave some buffer for code block formatting
                await ctx.send(f"```\n{message}```")
                message = ""
            message += line + "\n"
        
        if message:
            await ctx.send(f"```\n{message}```")
            
    except Exception as e:
        await ctx.send(f"❌ Error: {str(e)}")

async def health_check(request):
    return web.Response(text="Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', health_check)
    app.router.add_get('/health', health_check)
    
    port = int(os.environ.get('PORT', 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"🌐 Web server started on port {port}")

async def main():
    # Start web server in background
    await start_web_server()
    
    # Start Discord bot
    await bot.start(os.getenv("DISCORD_TOKEN"))

if __name__ == "__main__":
    asyncio.run(main())