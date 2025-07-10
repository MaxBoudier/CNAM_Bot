import csv
import google_sheet_manager
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
import pandas as pd

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

def main():
    old_courses_df = google_sheet_manager.get_all_courses()

    url = "https://senesi.lecnam.net/Planning.aspx?uid=e8597f513995581b2f022d6dcc3e70bb&code_scolarite=BFC531211 - 397719"

    chrome_options = webdriver.ChromeOptions()
    chrome_options.add_argument("--headless")

    download_dir = os.path.join(os.getcwd(), "temp_downloads")
    os.makedirs(download_dir, exist_ok=True)

    prefs = {"download.default_directory": download_dir,
             "download.prompt_for_download": False,
             "download.directory_upgrade": True,
             "safebrowsing.enabled": True}
    chrome_options.add_experimental_option("prefs", prefs)

    service = Service()
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        driver.get(url)
        
        list_view_button = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "m_c_planning_btnChangerModeAffichage"))
        )
        list_view_button.click()
        time.sleep(2)

        future_events_switch = WebDriverWait(driver, 20).until(
            EC.element_to_be_clickable((By.ID, "m_c_planning_SwitchCheckEvtpasse"))
        )
        future_events_switch.click()
        time.sleep(2)

        csv_button = WebDriverWait(driver, 20).until(
            EC.presence_of_element_located((By.ID, "m_c_planning_lbExporterPlanningCSV"))
        )
        driver.execute_script("arguments[0].click();", csv_button)
        time.sleep(5)

        downloaded_files = [f for f in os.listdir(download_dir) if f.endswith('.csv')]
        if not downloaded_files:
            raise Exception("CSV file not downloaded.")

        downloaded_csv_path = os.path.join(download_dir, downloaded_files[0])

        courses_list = []
        with open(downloaded_csv_path, mode='r', encoding='latin-1') as csvfile:
            csv_reader = csv.reader(csvfile)
            header = next(csv_reader)
            for row in csv_reader:
                full_location = row[17]
                location, room = parse_location(full_location)
                courses_list.append({
                    "object": row[0],
                    "start_date": row[1],
                    "start_time": row[2],
                    "end_date": row[3],
                    "end_time": row[4],
                    "professor": row[9],
                    "location": location,
                    "room": room,
                    "description": row[16]
                })
        
        new_courses_df = pd.DataFrame(courses_list)
        google_sheet_manager.update_courses(new_courses_df)

        # Compare dataframes to find added and removed courses
        old_courses_set = set(map(tuple, old_courses_df.to_numpy()))
        new_courses_set = set(map(tuple, new_courses_df.to_numpy()))

        added_courses = [list(course) for course in new_courses_set - old_courses_set]
        removed_courses = [list(course) for course in old_courses_set - new_courses_set]

        output_data = {
            "added": added_courses,
            "removed": removed_courses
        }
        print(json.dumps(output_data))

    finally:
        driver.quit()
        for f in os.listdir(download_dir):
            os.remove(os.path.join(download_dir, f))
        os.rmdir(download_dir)

if __name__ == "__main__":
    main()
