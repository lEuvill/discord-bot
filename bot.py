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
async def send(ctx, sheet_url: str, sheet_name: str, date: str, max_row: int):
    """
    Extract data from Google Sheets based on date column and row limit.
    Usage: r!send [sheet_url] [sheet_name] [date] [max_row]
    """
    try:
        # Extract sheet ID from URL
        match = re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', sheet_url)
        if not match:
            await ctx.send("❌ Invalid Google Sheets URL format.")
            return
        
        sheet_id = match.group(1)
        
        # Open the spreadsheet
        try:
            spreadsheet = client.open_by_key(sheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            await ctx.send("❌ Spreadsheet not found. Make sure the bot has access to the sheet.")
            return
        except gspread.exceptions.APIError as e:
            await ctx.send(f"❌ Google Sheets API error: {str(e)}")
            return
        
        # Get the specific worksheet by name
        try:
            worksheet = spreadsheet.worksheet(sheet_name)
        except gspread.exceptions.WorksheetNotFound:
            available_sheets = [ws.title for ws in spreadsheet.worksheets()]
            await ctx.send(f"❌ Sheet '{sheet_name}' not found. Available sheets: {', '.join(available_sheets)}")
            return
        
        # Get all values from the worksheet
        all_values = worksheet.get_all_values()
        
        if not all_values:
            await ctx.send("❌ The worksheet is empty.")
            return
        
        # Find the date column in the header row
        header_row = all_values[0]
        date_col_idx = None
        
        for i, cell in enumerate(header_row):
            if cell.strip() == date.strip():
                date_col_idx = i
                break
        
        if date_col_idx is None:
            await ctx.send(f"❌ Date '{date}' not found in header row. Available headers: {', '.join([h for h in header_row if h.strip()])}")
            return
        
        # Validate max_row
        total_rows = len(all_values) - 1  # Subtract 1 for header row
        if max_row < 1:
            await ctx.send("❌ max_row must be at least 1.")
            return
        
        if max_row > total_rows:
            await ctx.send(f"⚠️ Requested {max_row} rows but sheet only has {total_rows} data rows. Using {total_rows} rows.")
            max_row = total_rows
        
        # Extract data from the found column and next 2 columns
        response_lines = []
        
        # Add header for the 3 columns
        header_cols = []
        for c in range(date_col_idx, min(date_col_idx + 3, len(header_row))):
            header_cols.append(header_row[c] if c < len(header_row) else "")
        response_lines.append(" | ".join(header_cols))
        response_lines.append("-" * 50)  # Separator line
        
        # Extract data rows
        for row_idx in range(1, max_row + 1):
            if row_idx >= len(all_values):
                break
            
            row_values = all_values[row_idx]
            extracted_cols = []
            
            # Get the 3 columns starting from date_col_idx
            for c in range(date_col_idx, date_col_idx + 3):
                if c < len(row_values):
                    extracted_cols.append(row_values[c].strip())
                else:
                    extracted_cols.append("")
            
            response_lines.append(" | ".join(extracted_cols))
        
        # Send the response in separate code block messages to avoid Discord's message limit
        messages_to_send = []
        current_message = ""
        
        for line in response_lines:
            # Check if adding this line would exceed Discord's limit (2000 chars)
            # Account for code block formatting (``` at start and end = 6 chars + newlines)
            if len(current_message) + len(line) + 10 > 1900:
                if current_message:
                    messages_to_send.append(current_message.strip())
                current_message = line + "\n"
            else:
                current_message += line + "\n"
        
        # Add any remaining content
        if current_message:
            messages_to_send.append(current_message.strip())
        
        # Send header message
        await ctx.send(f"📊 **Data from '{sheet_name}' (Rows 1-{max_row})**")
        
        # Send each chunk as a separate code block message
        for i, message_chunk in enumerate(messages_to_send, 1):
            await ctx.send(f"```\n{message_chunk}\n```")
            
            # Small delay between messages to avoid rate limiting
            if i < len(messages_to_send):
                await asyncio.sleep(0.5)
        
        await ctx.send(f"✅ **Extraction complete!** Found {len(response_lines) - 2} data rows in {len(messages_to_send)} message(s).")
        
    except json.JSONDecodeError:
        await ctx.send("❌ Invalid Google credentials format in environment variables.")
    except Exception as e:
        await ctx.send(f"❌ Unexpected error: {str(e)}")
        print(f"Error in send command: {str(e)}")

@bot.command()
async def help_send(ctx):
    """Show help for the send command"""
    help_text = """
📋 **Send Command Help**

**Usage:** `r!send [sheet_url] [sheet_name] [date] [max_row]`

**Parameters:**
• `sheet_url` - Full Google Sheets URL
• `sheet_name` - Name of the specific sheet/tab
• `date` - Header value to search for (must match exactly)
• `max_row` - Maximum number of rows to extract (starting from row 1)

**Example:**
```
r!send https://docs.google.com/spreadsheets/d/10aUOWH2VDtiLIBUxBRdf1cRtLhT3KXaGBlp6MuNSxC4/edit sheet3 "June 4, 2025" 118
```

**Notes:**
• The bot will extract the found date column plus the next 2 columns
• Make sure the bot has access to your Google Sheet
• Sheet names are case-sensitive
• Date values must match the header exactly
    """
    await ctx.send(help_text)

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
    try:
        await asyncio.gather(
            run_webserver(),
            bot.start(os.getenv("DISCORD_TOKEN"))
        )
    except KeyboardInterrupt:
        print("Bot shutting down...")
    except Exception as e:
        print(f"Error running bot: {e}")

if __name__ == "__main__":
    asyncio.run(main())