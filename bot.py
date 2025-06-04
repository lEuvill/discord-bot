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
        
        # Extract data from the found column and optionally next 2 columns
        response_lines = []
        
        # First, let's check what we're actually getting from the sheet
        for row_idx in range(1, min(6, len(all_values))):  # Check first 5 rows for debugging
            if row_idx >= len(all_values):
                break
            
            row_values = all_values[row_idx]
            
            # Check the date column content
            date_col_content = row_values[date_col_idx] if date_col_idx < len(row_values) else ""
            
            # Check if content spans multiple columns (maybe it's split across columns)
            next_col_1 = row_values[date_col_idx + 1] if (date_col_idx + 1) < len(row_values) else ""
            next_col_2 = row_values[date_col_idx + 2] if (date_col_idx + 2) < len(row_values) else ""
            
            # If the main column has content but looks incomplete, combine with next columns
            if date_col_content and (next_col_1 or next_col_2):
                # Content might be spread across columns, combine them
                combined_content = date_col_content
                if next_col_1:
                    combined_content += " " + next_col_1
                if next_col_2:
                    combined_content += " " + next_col_2
                response_lines.append(combined_content)
            elif date_col_content:
                response_lines.append(date_col_content)
        
        # Now extract all the data properly
        for row_idx in range(1, max_row + 1):
            if row_idx >= len(all_values):
                break
            
            row_values = all_values[row_idx]
            
            # Get content from the date column
            date_col_content = row_values[date_col_idx] if date_col_idx < len(row_values) else ""
            
            # Check if we need to combine with adjacent columns
            next_col_1 = row_values[date_col_idx + 1] if (date_col_idx + 1) < len(row_values) else ""
            next_col_2 = row_values[date_col_idx + 2] if (date_col_idx + 2) < len(row_values) else ""
            
            # Combine columns if there's content in adjacent columns
            if date_col_content and (next_col_1.strip() or next_col_2.strip()):
                combined_content = date_col_content
                if next_col_1.strip():
                    combined_content += " " + next_col_1
                if next_col_2.strip():
                    combined_content += " " + next_col_2
                if combined_content.strip():
                    response_lines.append(combined_content)
            elif date_col_content.strip():
                response_lines.append(date_col_content)
        
        # Combine all extracted data into one string
        full_data = "\n".join(response_lines)
        
        # Find all code blocks in the data (content between ``` markers)
        code_blocks = []
        parts = full_data.split('```')
        
        # Every odd-indexed part (1, 3, 5, etc.) is inside code blocks
        for i in range(1, len(parts), 2):
            if parts[i].strip():  # Only add non-empty blocks
                code_blocks.append(parts[i].strip())
        
        # Send header message
        await ctx.send(f"📊 **Data from '{sheet_name}' (Rows 1-{max_row})**")
        
        if code_blocks:
            # Send each code block as a separate message
            for i, code_block in enumerate(code_blocks, 1):
                # Ensure the message doesn't exceed Discord's limit
                if len(code_block) + 10 > 1900:  # Account for ``` formatting
                    # If a single code block is too long, split it
                    lines = code_block.split('\n')
                    current_chunk = ""
                    
                    for line in lines:
                        if len(current_chunk) + len(line) + 10 > 1900:
                            if current_chunk:
                                await ctx.send(f"```{current_chunk.strip()}```")
                                await asyncio.sleep(0.5)
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
                    
                    if current_chunk:
                        await ctx.send(f"```{current_chunk.strip()}```")
                else:
                    await ctx.send(f"```{code_block}```")
                
                # Small delay between messages to avoid rate limiting
                if i < len(code_blocks):
                    await asyncio.sleep(0.5)
            
            await ctx.send(f"✅ **Extraction complete!** Found {len(code_blocks)} code block(s) from {len(response_lines)} data rows.")
        else:
            # If no code blocks found, send as regular formatted data
            messages_to_send = []
            current_message = ""
            
            for line in response_lines:
                if len(current_message) + len(line) + 10 > 1900:
                    if current_message:
                        messages_to_send.append(current_message.strip())
                    current_message = line + "\n"
                else:
                    current_message += line + "\n"
            
            if current_message:
                messages_to_send.append(current_message.strip())
            
            for i, message_chunk in enumerate(messages_to_send, 1):
                await ctx.send(f"```{message_chunk}```")
                if i < len(messages_to_send):
                    await asyncio.sleep(0.5)
            
            await ctx.send(f"✅ **Extraction complete!** Found {len(response_lines)} data rows in {len(messages_to_send)} message(s). No code blocks detected.")
        
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