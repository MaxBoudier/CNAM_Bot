import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import google_sheet_manager
import asyncio
import subprocess
import sys
import os
from dotenv import load_dotenv
import json
from selenium import webdriver

load_dotenv()

# --- Discord Bot Setup ---

TOKEN = os.getenv("DISCORD_TOKEN")

DAILY_SCHEDULE_CHANNEL_ID = int(os.getenv("DAILY_SCHEDULE_CHANNEL_ID"))
ADDED_COURSES_CHANNEL_ID = int(os.getenv("ADDED_COURSES_CHANNEL_ID"))
REMOVED_COURSES_CHANNEL_ID = int(os.getenv("REMOVED_COURSES_CHANNEL_ID"))
BOT_LOGS_CHANNEL_ID = int(os.getenv("BOT_LOGS_CHANNEL_ID"))
WEBSITE_URL = os.getenv("WEBSITE_URL") # Add your website URL to the .env file

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix=commands.when_mentioned_or('!'), intents=intents)

def split_message(message, max_len=1900):
    chunks = []
    while len(message) > max_len:
        split_point = message.rfind('\n\n', 0, max_len)
        if split_point == -1:
            split_point = max_len
        chunks.append(message[:split_point])
        message = message[split_point:].strip()
    chunks.append(message)
    return chunks

@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    await bot.tree.sync()
    print("Slash commands synced.")
    update_database_task.start()
    print("Database update task started.")

@tasks.loop(seconds=10)
async def update_database_task():
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

            if removed_courses and removed_courses_channel:
                message_content = "**Courses Removed:**\n"
                for course in removed_courses:
                    message_content += f"- **{course[0]}** ({course[1]} {course[2]} - {course[3]} {course[4]})\n"
                    message_content += f"  Professor: {course[5]}, Location: {course[6]}, Room: {course[7]}\n\n"
                for chunk in split_message(message_content):
                    await removed_courses_channel.send(chunk)
                print("Removed courses notification sent to Discord.")

            if not added_courses and not removed_courses:
                print("No course changes detected.")
                await bot_logs_channel.send("No course changes detected during update.")

        except json.JSONDecodeError:
            print("Error: Could not decode JSON from parser output.")
            await bot_logs_channel.send("Error: Could not process course updates. Check bot logs.")
        except Exception as e:
            print(f"An unexpected error occurred while processing changes: {e}")
            await bot_logs_channel.send(f"An unexpected error occurred while processing course updates: {e}")

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

@bot.tree.command(name="add_homework", description="Adds a new homework assignment.")
async def add_homework_command(interaction: discord.Interaction):
    await interaction.response.send_message("To add homework, please provide the following information separated by commas:\n`Course Name, Due Date (DD/MM/YYYY), Description, Professor Name`", ephemeral=True)

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', check=check, timeout=60.0)
        parts = [p.strip() for p in msg.content.split(',')]
        if len(parts) == 4:
            course_name, due_date_str, description, professor_name = parts
            try:
                datetime.strptime(due_date_str, "%d/%m/%Y")
                google_sheet_manager.add_homework(course_name, due_date_str, description, professor_name)
                await interaction.followup.send(f"Homework for **{course_name}** (Professor: {professor_name}) due on **{due_date_str}** added successfully!")
            except ValueError:
                await interaction.followup.send("Invalid date format. Please use DD/MM/YYYY.")
        else:
            await interaction.followup.send("Invalid format. Please provide Course Name, Due Date (DD/MM/YYYY), Description, and Professor Name.")
    except asyncio.TimeoutError:
        await interaction.followup.send("You took too long to respond. Homework addition cancelled.")

@bot.tree.command(name="view_homework", description="Displays all homework assignments.")
async def view_homework_command(interaction: discord.Interaction):
    homework_df = google_sheet_manager.get_all_homework()

    if not homework_df.empty:
        response_content = "**All Homework Assignments:**\n"
        for index, hw in homework_df.iterrows():
            response_content += f"- **{hw['course_name']}** (Professor: {hw['professor_name']}, Due: {hw['due_date']}): {hw['description']}\n"
    else:
        response_content = "No homework assignments found."
    
    for i, chunk in enumerate(split_message(response_content)):
        if i == 0:
            await interaction.response.send_message(chunk)
        else:
            await interaction.followup.send(chunk)

@bot.tree.command(name="planning", description="Displays the planning from the website.")
async def planning(interaction: discord.Interaction):
    await interaction.response.defer()
    try:
        chrome_options = webdriver.ChromeOptions()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--window-size=1920,1080")
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(WEBSITE_URL)
        await asyncio.sleep(5) # Wait for the page to load
        screenshot = driver.get_screenshot_as_png()
        driver.quit()
        await interaction.followup.send(file=discord.File(io.BytesIO(screenshot), "planning.png"))
    except Exception as e:
        await interaction.followup.send(f"An error occurred while generating the planning: {e}")

if __name__ == "__main__":
    bot.run(TOKEN)
