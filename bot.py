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

# In-memory storage for variables
bot_variables = {
    'links': {},
    'sheet_names': {},
    'row_max': {}
}

@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")

@bot.command()
async def set(ctx, variable: str, *args):
    """
    Set variables for links, sheet names, and row max values.
    Usage: 
    - r!set [link] to [variable_name]
    - r!set [variable_name] [sheet_name] to [sheet_name_value]
    - r!set [variable_name] [row_max] to [row_max_value]
    """
    try:
        args_text = " ".join(args)
        
        # Check if it's setting a link
        if args_text.startswith("to "):
            # This is setting a link: r!set [link] to [variable_name]
            link = variable
            variable_name = args_text[3:].strip()  # Remove "to " and get variable name
            
            # Validate URL format
            if not re.search(r'/spreadsheets/d/([a-zA-Z0-9-_]+)', link):
                await ctx.send("❌ Invalid Google Sheets URL format.")
                return
            
            bot_variables['links'][variable_name] = link
            await ctx.send(f"✅ Link set: `{variable_name}` = `{link}`")
            return
        
        # Check if it's setting sheet name or row max
        if len(args) >= 3 and args[-2] == "to":
            property_type = args[0]  # Should be sheet name, row max, etc.
            property_value = args[-1]  # The value after "to"
            
            if property_type.lower() in ["sheet", "sheetname", "sheet_name"]:
                bot_variables['sheet_names'][variable] = property_value
                await ctx.send(f"✅ Sheet name set: `{variable}` sheet name = `{property_value}`")
                return
            
            elif property_type.lower() in ["row", "rowmax", "row_max", "max_row"]:
                try:
                    row_value = int(property_value)
                    if row_value < 1:
                        await ctx.send("❌ Row max must be at least 1.")
                        return
                    bot_variables['row_max'][variable] = row_value
                    await ctx.send(f"✅ Row max set: `{variable}` row max = `{row_value}`")
                    return
                except ValueError:
                    await ctx.send("❌ Row max must be a valid number.")
                    return
        
        # If we get here, the format wasn't recognized
        await ctx.send("""❌ Invalid format. Use one of these:
```
r!set [link] to [variable_name]
r!set [variable_name] [sheet_name] to [sheet_name_value]
r!set [variable_name] [row_max] to [row_max_value]
```

**Examples:**
```
r!set https://docs.google.com/.../edit to CA
r!set CA sheet_name to Daily-Audit-June
r!set CA row_max to 290
```""")
        
    except Exception as e:
        await ctx.send(f"❌ Error setting variable: {str(e)}")

@bot.command()
async def send(ctx, sheet_identifier: str, *args):
    """
    Extract data from Google Sheets. Can use variables or full parameters.
    Usage: 
    - r!send [variable_name] [date] (if variable has sheet_name and row_max set)
    - r!send [variable_name] [sheet_name] [date] [max_row] (if variable only has link)
    - r!send [sheet_url] [sheet_name] [date] [max_row] (original format)
    """
    try:
        # Check if sheet_identifier is a variable (stored link)
        if sheet_identifier in bot_variables['links']:
            sheet_url = bot_variables['links'][sheet_identifier]
            
            # Check if we have stored sheet_name and row_max for this variable
            if (sheet_identifier in bot_variables['sheet_names'] and 
                sheet_identifier in bot_variables['row_max']):
                
                # Format: r!send [variable] [date]
                if len(args) == 1:
                    sheet_name = bot_variables['sheet_names'][sheet_identifier]
                    date = args[0]
                    max_row = bot_variables['row_max'][sheet_identifier]
                else:
                    await ctx.send(f"❌ Expected format: `r!send {sheet_identifier} [date]`")
                    return
                    
            else:
                # Format: r!send [variable] [sheet_name] [date] [max_row]
                if len(args) == 3:
                    sheet_name = args[0]
                    date = args[1]
                    try:
                        max_row = int(args[2])
                    except ValueError:
                        await ctx.send("❌ max_row must be a valid number.")
                        return
                else:
                    await ctx.send(f"❌ Expected format: `r!send {sheet_identifier} [sheet_name] [date] [max_row]`")
                    return
        else:
            # Original format: r!send [sheet_url] [sheet_name] [date] [max_row]
            if len(args) == 3:
                sheet_url = sheet_identifier
                sheet_name = args[0]
                date = args[1]
                try:
                    max_row = int(args[2])
                except ValueError:
                    await ctx.send("❌ max_row must be a valid number.")
                    return
            else:
                await ctx.send("❌ Invalid format. Use `r!help_send` for usage instructions.")
                return
        
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
        header_row = all_values[2]
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
        
        # Extract data from the found column and next 2 columns (3 columns total)
        # Copy it like Windows copy-paste (tab-separated, then join naturally)
        response_lines = []
        
        # Extract data rows from the 3 columns starting from date column
        for row_idx in range(1, max_row + 1):
            if row_idx >= len(all_values):
                break
            
            row_values = all_values[row_idx]
            
            # Get the 3 columns starting from date_col_idx
            col1 = row_values[date_col_idx] if date_col_idx < len(row_values) else ""
            col2 = row_values[date_col_idx + 1] if (date_col_idx + 1) < len(row_values) else ""
            col3 = row_values[date_col_idx + 2] if (date_col_idx + 2) < len(row_values) else ""
            
            # Join them with tabs (like Windows copy-paste behavior)
            combined_row = f"{col1}\t{col2}\t{col3}".rstrip('\t')
            
            if combined_row.strip():  # Only add non-empty rows
                response_lines.append(combined_row)
        
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
async def vars(ctx):
    """Show all stored variables"""
    if not any([bot_variables['links'], bot_variables['sheet_names'], bot_variables['row_max']]):
        await ctx.send("📋 No variables set yet.")
        return
    
    embed = discord.Embed(title="📋 Stored Variables", color=0x00ff00)
    
    if bot_variables['links']:
        links_text = "\n".join([f"`{var}` = `{url[:50]}...`" if len(url) > 50 else f"`{var}` = `{url}`" 
                               for var, url in bot_variables['links'].items()])
        embed.add_field(name="🔗 Links", value=links_text, inline=False)
    
    if bot_variables['sheet_names']:
        sheets_text = "\n".join([f"`{var}` = `{sheet}`" 
                                for var, sheet in bot_variables['sheet_names'].items()])
        embed.add_field(name="📝 Sheet Names", value=sheets_text, inline=False)
    
    if bot_variables['row_max']:
        rows_text = "\n".join([f"`{var}` = `{rows}`" 
                              for var, rows in bot_variables['row_max'].items()])
        embed.add_field(name="📊 Row Max", value=rows_text, inline=False)
    
    await ctx.send(embed=embed)

@bot.command()
async def clear_vars(ctx, variable_name: str = None):
    """Clear variables. Usage: r!clear_vars [variable_name] or r!clear_vars all"""
    if variable_name is None:
        await ctx.send("❌ Specify a variable name or 'all' to clear everything.")
        return
    
    if variable_name.lower() == "all":
        bot_variables['links'].clear()
        bot_variables['sheet_names'].clear()
        bot_variables['row_max'].clear()
        await ctx.send("✅ All variables cleared.")
        return
    
    cleared = []
    if variable_name in bot_variables['links']:
        del bot_variables['links'][variable_name]
        cleared.append("link")
    
    if variable_name in bot_variables['sheet_names']:
        del bot_variables['sheet_names'][variable_name]
        cleared.append("sheet name")
    
    if variable_name in bot_variables['row_max']:
        del bot_variables['row_max'][variable_name]
        cleared.append("row max")
    
    if cleared:
        await ctx.send(f"✅ Cleared {variable_name}: {', '.join(cleared)}")
    else:
        await ctx.send(f"❌ Variable '{variable_name}' not found.")

@bot.command()
async def help_send(ctx):
    """Show help for the send command"""
    help_text = """
📋 **Send Command Help**

**Original Usage:** `r!send [sheet_url] [sheet_name] [date] [max_row]`

**With Variables:**
• `r!send [variable] [date]` - If variable has link, sheet name, and row max set
• `r!send [variable] [sheet_name] [date] [max_row]` - If variable only has link set

**Setting Variables:**
```
r!set [link] to [variable_name]
r!set [variable_name] sheet_name to [sheet_name_value]
r!set [variable_name] row_max to [row_max_value]
```

**Example Setup:**
```
r!set https://docs.google.com/.../edit to CA
r!set CA sheet_name to Daily-Audit-June
r!set CA row_max to 290
```

**Then use simply:**
```
r!send CA "June 5, 2025"
```

**Other Commands:**
• `r!vars` - Show all stored variables
• `r!clear_vars [variable_name]` - Clear specific variable
• `r!clear_vars all` - Clear all variables
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