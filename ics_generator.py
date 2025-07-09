from ics import Calendar, Event
from datetime import datetime
from zoneinfo import ZoneInfo
import db_manager

def create_ics_file():
    """
    Fetches all courses from the database and generates an .ics file.
    """
    calendar = Calendar()
    courses = db_manager.get_all_courses()

    for course in courses:
        event = Event()
        event.name = course[0]
        
        # Combine date and time strings and parse them into datetime objects
        start_datetime_str = f"{course[1]} {course[2]}"
        end_datetime_str = f"{course[3]} {course[4]}"
        
        # Assuming the date format is DD/MM/YYYY and time is HH:MM
        start_datetime = datetime.strptime(start_datetime_str, "%d/%m/%Y %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Paris"))
        end_datetime = datetime.strptime(end_datetime_str, "%d/%m/%Y %H:%M:%S").replace(tzinfo=ZoneInfo("Europe/Paris"))

        event.begin = start_datetime
        event.end = end_datetime
        event.location = f"{course[6]}, {course[7]}" # Location, Room
        event.description = f"Professor: {course[5]}\nDescription: {course[8]}"
        
        calendar.events.add(event)

    with open("planning.ics", "w") as f:
        f.writelines(calendar)

if __name__ == '__main__':
    create_ics_file()
