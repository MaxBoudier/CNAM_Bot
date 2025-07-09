import csv
import sqlite3
import re
import io
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import os
import time
import json

def parse_location(location_str):
    """Parses the location string to extract the room and general location."""
    room_match = re.search(r'Salle\s+([A-Za-z0-9\s-]+)', location_str)
    general_location_match = re.search(r'([^\-]+)\s+-\s+Salle', location_str)

    room = room_match.group(1).strip() if room_match else "N/A"
    general_location = general_location_match.group(1).strip() if general_location_match else location_str.strip()

    # Refine general_location if it still contains "Salle" or similar patterns
    if "Salle" in general_location:
        general_location = general_location.split("Salle")[0].strip()
    if "-" in general_location and "CHALON SUR SAONE" in general_location:
        general_location = general_location.split("-")[0].strip()

    return general_location, room

# csv_file_path is no longer needed as we are downloading directly
# csv_file_path = 'input_files/Planning_11062025171823_56794.csv'
script_dir = os.path.dirname(os.path.abspath(__file__))
db_file_path = os.path.join(script_dir, 'courses.db')

def get_all_courses_from_db(cursor):
    # Check if the 'courses' table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='courses'")
    if cursor.fetchone():
        cursor.execute("SELECT object, start_date, start_time, end_date, end_time, professor, location, room, description FROM courses")
        return set(cursor.fetchall())
    else:
        return set() # Return an empty set if the table doesn't exist

def main():

    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()

    # Get existing courses before dropping the table
    old_courses = get_all_courses_from_db(cursor)

    cursor.execute("DROP TABLE IF EXISTS courses")
    cursor.execute("""
        CREATE TABLE courses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            object TEXT,
            start_date TEXT,
            start_time TEXT,
            end_date TEXT,
            end_time TEXT,
            professor TEXT,
            location TEXT,
            room TEXT,
            description TEXT
        )
    """)
    conn.commit()

    url = "https://senesi.lecnam.net/Planning.aspx?uid=e8597f513995581b2f022d6dcc3e70bb&code_scolarite=BFC531211 - 397719"

    # Set up Chrome options for headless mode and download directory
    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless") # Run Chrome in headless mode (without a UI)

    # Set download directory
    download_dir = os.path.join(os.getcwd(), "temp_downloads")
    os.makedirs(download_dir, exist_ok=True) # Create the directory if it doesn't exist

    prefs = {"download.default_directory": download_dir,
             "download.prompt_for_download": False, # To auto download the file
             "download.directory_upgrade": True,
             "safebrowsing.enabled": True}
    chrome_options.add_experimental_option("prefs", prefs)

    # Initialize WebDriver
    # Assuming chromedriver.exe is in PATH or in the same directory as the script
    service = Service() # Use default service, assumes chromedriver is in PATH
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        # print("Initial page source:", driver.page_source)

        # Click the "Voir le planning sous forme de liste" button
        list_view_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "m_c_planning_btnChangerModeAffichage"))
        )
        list_view_button.click()

        # Wait for the page to update after clicking the list view button
        time.sleep(2) # A short sleep to allow the page to render
        # print("Page source after list view click:", driver.page_source)

        # Click the "Afficher uniquement les événements à venir" switch
        future_events_switch = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "m_c_planning_SwitchCheckEvtpasse"))
        )
        future_events_switch.click()

        # Wait for the page to update after clicking the switch
        time.sleep(2) # A short sleep to allow the page to render
        # print("Page source after future events switch:", driver.page_source)

        # Click the "Planning au format CSV" button using JavaScript
        csv_button = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "m_c_planning_lbExporterPlanningCSV"))
        )
        driver.execute_script("arguments[0].click();", csv_button)

        # Wait for the file to download
        # This is a simple wait, a more robust solution would check for file existence/completion
        time.sleep(5) # Give some time for the download to complete

        # Find the downloaded CSV file
        downloaded_files = [f for f in os.listdir(download_dir) if f.endswith('.csv')]
        if not downloaded_files:
            raise Exception("CSV file not downloaded.")

        downloaded_csv_path = os.path.join(download_dir, downloaded_files[0])

        # Read the downloaded CSV file
        with open(downloaded_csv_path, mode='r', encoding='latin-1') as csvfile:
            csv_reader = csv.reader(csvfile)
            header = next(csv_reader) # Skip header row
            for row in csv_reader:
                obj = row[0]
                start_date = row[1]
                start_time = row[2]
                end_date = row[3]
                end_time = row[4]
                professor = row[9]
                description = row[16]
                full_location = row[17]
                location, room = parse_location(full_location)

                cursor.execute("""
                    INSERT INTO courses (object, start_date, start_time, end_date, end_time, professor, location, room, description)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (obj, start_date, start_time, end_date, end_time, professor, location, room, description))

        conn.commit()

        # After data insertion
        new_courses = get_all_courses_from_db(cursor)

        added_courses = new_courses - old_courses
        removed_courses = old_courses - new_courses

        # Prepare output for stdout
        output_data = {
            "added": [list(course) for course in added_courses],
            "removed": [list(course) for course in removed_courses]
        }
        print(json.dumps(output_data))

        conn.close()

    finally:
        driver.quit() # Always close the browser
        # Clean up downloaded files
        for f in os.listdir(download_dir):
            os.remove(os.path.join(download_dir, f))
        os.rmdir(download_dir)

def verify_data(db_file_path):
    conn = sqlite3.connect(db_file_path)
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM courses LIMIT 5")
    rows = cursor.fetchall()
    for row in rows:
        print(row)
    conn.close()

if __name__ == "__main__":
    main()
    # The verification print statements should be removed or modified
    # as the main output is now JSON for the bot.
    # print("\nVerifying data in the database:")
    # verify_data(db_file_path)
