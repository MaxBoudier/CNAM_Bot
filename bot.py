import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import db_manager
import asyncio
import subprocess
import sys
import os
from dotenv import load_dotenv
import json
import ics_generator

load_dotenv()

# --- Discord Bot Setup ---

# Replace with your bot's token
TOKEN = os.getenv("DISCORD_TOKEN")

# Channel IDs from .env
DAILY_SCHEDULE_CHANNEL_ID = int(os.getenv("DAILY_SCHEDULE_CHANNEL_ID"))
ADDED_COURSES_CHANNEL_ID = int(os.getenv("ADDED_COURSES_CHANNEL_ID"))
REMOVED_COURSES_CHANNEL_ID = int(os.getenv("REMOVED_COURSES_CHANNEL_ID"))
BOT_LOGS_CHANNEL_ID = int(os.getenv("BOT_LOGS_CHANNEL_ID"))


# Define bot intents (permissions)
intents = discord.Intents.default()
intents.message_content = True  # Required to read message content

# Create a bot instance
bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), intents=intents)

# --- Helper function to split long messages ---
def split_message(message, max_len=1900):
    """Splits a message into chunks of max_len."""
    chunks = []
    while len(message) > max_len:
        split_point = message.rfind('\n\n', 0, max_len) # Try to split at a natural break
        if split_point == -1: # No natural break, just split at max_len
            split_point = max_len
        chunks.append(message[:split_point])
        message = message[split_point:].strip()
    chunks.append(message)
    return chunks

# --- Bot Events ---

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    await bot.tree.sync() # Sync slash commands
    print("Slash commands synced.")
    daily_schedule_task.start() # Start the daily schedule task
    print("Daily schedule task started.")
    update_database_task.start()
    print("Database update task started.")

# --- Scheduled Tasks ---

@tasks.loop(time=time(hour=18, minute=00, tzinfo=ZoneInfo("Europe/Paris"))) # Schedule to run daily at 18:00 (6 PM)
async def daily_schedule_task():
    print("Attempting to send daily schedule...")
    await bot.wait_until_ready()
    print(f"Daily Schedule Channel ID: {DAILY_SCHEDULE_CHANNEL_ID}")
    channel = bot.get_channel(DAILY_SCHEDULE_CHANNEL_ID)

    if channel:
        print(f"Channel found: {channel.name}")
        tomorrow = datetime.now() + timedelta(days=1)
        print(f"Fetching schedule for: {tomorrow.strftime('%d/%m/%Y')}")
        schedule = db_manager.get_day_schedule(tomorrow)

        if schedule:
            print(f"Schedule found for tomorrow. Number of events: {len(schedule)}")
            response_content = f"**Planning for Tomorrow ({tomorrow.strftime('%d/%m/%Y')}):**\n"
            for event in schedule:
                response_content += f"- **{event[0]}** ({event[1]} {event[2]} - {event[3]} {event[4]})\n"
                response_content += f"  Professor: {event[5]}\n"
                response_content += f"  Location: {event[6]}, Room: {event[7]}\n"
                response_content += f"  Description: {event[8]}\n\n"
        else:
            print("No events found for tomorrow.")
            response_content = f"No events found for tomorrow ({tomorrow.strftime('%d/%m/%Y')})."
        
        for chunk in split_message(response_content):
            await channel.send(chunk)
            print("Message chunk sent.")
    else:
        print(f"Error: Daily schedule channel with ID {DAILY_SCHEDULE_CHANNEL_ID} not found or bot does not have access.")

@tasks.loop(minutes=5)
async def update_database_task():
    """Runs the planning_parser.py script to update the database and notifies about changes."""
    print("Attempting to update database...")
    
    added_courses_channel = bot.get_channel(ADDED_COURSES_CHANNEL_ID)
    removed_courses_channel = bot.get_channel(REMOVED_COURSES_CHANNEL_ID)
    bot_logs_channel = bot.get_channel(BOT_LOGS_CHANNEL_ID)

    if not bot_logs_channel:
        print(f"Error: Bot logs channel with ID {BOT_LOGS_CHANNEL_ID} not found. Cannot send logs.")
        return

    try:
        parser_script_path = "planning_parser.py"
        result = subprocess.run([sys.executable, parser_script_path], capture_output=True, text=True, check=True)
        print("Database update script ran successfully.")
        await bot_logs_channel.send("Database update script ran successfully.")
        
        # Parse the JSON output
        try:
            changes = json.loads(result.stdout)
            added_courses = changes.get("added", [])
            removed_courses = changes.get("removed", [])

            if added_courses and added_courses_channel:
                message_content = "**Courses Added:**\n"
                for course in added_courses:
                    message_content += f"- **{course[0]}** ({course[1]} {course[2]} - {course[3]} {course[4]})\n"
                    message_content += f"  Professor: {course[5]}, Location: {course[6]}, Room: {course[7]}\n\n"
                for chunk in split_message(message_content):
                    await added_courses_channel.send(chunk)
                print("Added courses notification sent to Discord.")
            elif added_courses and not added_courses_channel:
                print(f"Warning: Added courses channel with ID {ADDED_COURSES_CHANNEL_ID} not found. Cannot send added courses notification.")

            if removed_courses and removed_courses_channel:
                message_content = "**Courses Removed:**\n"
                for course in removed_courses:
                    message_content += f"- **{course[0]}** ({course[1]} {course[2]} - {course[3]} {course[4]})\n"
                    message_content += f"  Professor: {course[5]}, Location: {course[6]}, Room: {course[7]}\n\n"
                for chunk in split_message(message_content):
                    await removed_courses_channel.send(chunk)
                print("Removed courses notification sent to Discord.")
            elif removed_courses and not removed_courses_channel:
                print(f"Warning: Removed courses channel with ID {REMOVED_COURSES_CHANNEL_ID} not found. Cannot send removed courses notification.")

            if not added_courses and not removed_courses:
                print("No course changes detected.")
                await bot_logs_channel.send("No course changes detected during update.")

        except json.JSONDecodeError:
            print("Error: Could not decode JSON from parser output.")
            await bot_logs_channel.send("Error: Could not process course updates. Check bot logs.")
        except Exception as e:
            print(f"An unexpected error occurred while processing changes: {e}")
            await bot_logs_channel.send(f"An unexpected error occurred while processing course updates: {e}")

        # Generate the .ics file
        try:
            ics_generator.create_ics_file()
            print("Generated planning.ics file.")
            await bot_logs_channel.send("Successfully generated `planning.ics` file.")
        except Exception as e:
            print(f"Error generating .ics file: {e}")
            await bot_logs_channel.send(f"Error generating .ics file: {e}")

    except subprocess.CalledProcessError as e:
        print(f"Error running database update script: {e}")
        print("stdout:", e.stdout)
        print("stderr:", e.stderr)
        await bot_logs_channel.send(f"Error updating database: {e.stderr}")
    except FileNotFoundError:
        print(f"Error: The script at {parser_script_path} was not found.")
        await bot_logs_channel.send(f"Error: Parser script not found at {parser_script_path}.")
    except Exception as e:
        print(f"An unexpected error occurred during database update: {e}")
        await bot_logs_channel.send(f"An unexpected error occurred during database update: {e}")

# --- Bot Commands (Slash Commands) ---

@bot.tree.command(name="current_week", description="Displays the schedule for the current week.")
async def current_week_schedule(interaction: discord.Interaction):
    today = datetime.now()
    # Get the Monday of the current week
    start_of_week = today - timedelta(days=today.weekday())
    schedule = db_manager.get_week_schedule(start_of_week)

    if schedule:
        response_content = "**Planning for the Current Week:**\n"
        for event in schedule:
            response_content += f"- **{event[0]}** ({event[1]} {event[2]} - {event[3]} {event[4]})\n"
            response_content += f"  Professor: {event[5]}\n"
            response_content += f"  Location: {event[6]}, Room: {event[7]}\n"
            response_content += f"  Description: {event[8]}\n\n"
    else:
        response_content = "No events found for the current week."
    
    for i, chunk in enumerate(split_message(response_content)):
        if i == 0:
            await interaction.response.send_message(chunk)
        else:
            await interaction.followup.send(chunk)

@bot.tree.command(name="next_week", description="Displays the schedule for the next week.")
async def next_week_schedule(interaction: discord.Interaction):
    next_week_start = datetime.now() + timedelta(weeks=1)
    # Get the Monday of the next week
    start_of_next_week = next_week_start - timedelta(days=next_week_start.weekday())
    schedule = db_manager.get_week_schedule(start_of_next_week)

    if schedule:
        response_content = "**Planning for the Next Week:**\n"
        for event in schedule:
            response_content += f"- **{event[0]}** ({event[1]} {event[2]} - {event[3]} {event[4]})\n"
            response_content += f"  Professor: {event[5]}\n"
            response_content += f"  Location: {event[6]}, Room: {event[7]}\n"
            response_content += f"  Description: {event[8]}\n\n"
    else:
        response_content = "No events found for the next week."
    
    for i, chunk in enumerate(split_message(response_content)):
        if i == 0:
            await interaction.response.send_message(chunk)
        else:
            await interaction.followup.send(chunk)

@bot.tree.command(name="schedule", description="Displays the schedule for a specific week or day.")
@app_commands.describe(
    type="Choose to view by week or day.",
    date="Enter the date in DD/MM/YYYY format."
)
@app_commands.choices(type=[
    app_commands.Choice(name="week", value="week"),
    app_commands.Choice(name="day", value="day"),
])
async def schedule_command(interaction: discord.Interaction, type: app_commands.Choice[str], date: str):
    try:
        parsed_date = datetime.strptime(date, "%d/%m/%Y")
    except ValueError:
        await interaction.response.send_message("Invalid date format. Please use DD/MM/YYYY.", ephemeral=True)
        return

    if type.value == "week":
        # Get the Monday of the specified week
        start_of_week = parsed_date - timedelta(days=parsed_date.weekday())
        schedule = db_manager.get_week_schedule(start_of_week)
        title = f"Planning for the week of {start_of_week.strftime('%d/%m/%Y')}:\n"
    else: # type.value == "day"
        schedule = db_manager.get_day_schedule(parsed_date)
        title = f"Planning for {parsed_date.strftime('%d/%m/%Y')}:\n"

    if schedule:
        response_content = title
        for event in schedule:
            response_content += f"- **{event[0]}** ({event[1]} {event[2]} - {event[3]} {event[4]})\n"
            response_content += f"  Professor: {event[5]}\n"
            response_content += f"  Location: {event[6]}, Room: {event[7]}\n"
            response_content += f"  Description: {event[8]}\n\n"
    else:
        response_content = f"No events found for {type.value} {date}."
    
    for i, chunk in enumerate(split_message(response_content)):
        if i == 0:
            await interaction.response.send_message(chunk)
        else:
            await interaction.followup.send(chunk)

@bot.tree.command(name="add_homework", description="Adds a new homework assignment.")
async def add_homework_command(interaction: discord.Interaction):
    await interaction.response.send_message("To add homework, please provide the following information separated by commas:\n`Course Name, Due Date (DD/MM/YYYY), Description, Professor Name`", ephemeral=True)

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        parts = [p.strip() for p in msg.content.split(',')]
        if len(parts) == 4: # Changed from 3 to 4
            course_name, due_date_str, description, professor_name = parts # Added professor_name
            try:
                # Validate date format
                datetime.strptime(due_date_str, "%d/%m/%Y")
                db_manager.add_homework(course_name, due_date_str, description, professor_name) # Added professor_name
                await interaction.followup.send(f"Homework for **{course_name}** (Professor: {professor_name}) due on **{due_date_str}** added successfully!") # Added professor_name
            except ValueError:
                await interaction.followup.send("Invalid date format. Please use DD/MM/YYYY.")
        else:
            await interaction.followup.send("Invalid format. Please provide Course Name, Due Date (DD/MM/YYYY), Description, and Professor Name.") # Updated message
    except asyncio.TimeoutError:
        await interaction.followup.send("You took too long to respond. Homework addition cancelled.")

@bot.tree.command(name="view_homework", description="Displays all homework assignments.")
async def view_homework_command(interaction: discord.Interaction):
    homework_list = db_manager.get_all_homework()

    if homework_list:
        response_content = "**All Homework Assignments:**\n"
        for hw in homework_list:
            response_content += f"- **{hw[0]}** (Professor: {hw[3]}, Due: {hw[1]}): {hw[2]}\n" # Added hw[3] for professor_name
    else:
        response_content = "No homework assignments found."
    
    for i, chunk in enumerate(split_message(response_content)):
        if i == 0:
            await interaction.response.send_message(chunk)
        else:
            await interaction.followup.send(chunk)

@bot.tree.command(name="generate_ics", description="Generates an .ics file of the schedule.")
async def generate_ics(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        ics_generator.create_ics_file()
        await interaction.followup.send("Generated `planning.ics` file.", file=discord.File("planning.ics"))
    except Exception as e:
        await interaction.followup.send(f"An error occurred while generating the .ics file: {e}")

# --- Run the bot ---

if __name__ == "__main__":
    # Ensure the database is initialized (e.g., homework table exists)
    # This call needs to be updated to include professor_name, or removed if not strictly necessary for table creation
    # For now, I'll update it with a dummy value.
    db_manager.add_homework("", "", "", "") # Updated to include professor_name
    bot.run(TOKEN)