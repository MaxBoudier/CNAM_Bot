import sqlite3
from datetime import datetime, timedelta

DATABASE_NAME = "courses.db"

def get_week_schedule(start_date):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    end_date = start_date + timedelta(days=6) # Get the end of the week

    cursor.execute("""
        SELECT object, start_date, start_time, end_date, end_time, professor, location, room, description
        FROM courses
        WHERE SUBSTR(start_date, 7, 4) || '-' || SUBSTR(start_date, 4, 2) || '-' || SUBSTR(start_date, 1, 2) BETWEEN ? AND ?
        ORDER BY start_date, start_time
    """, (start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")))

    schedule = cursor.fetchall()
    conn.close()
    return schedule

def get_day_schedule(target_date):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT object, start_date, start_time, end_date, end_time, professor, location, room, description
        FROM courses
        WHERE SUBSTR(start_date, 7, 4) || '-' || SUBSTR(start_date, 4, 2) || '-' || SUBSTR(start_date, 1, 2) = ?
        ORDER BY start_time
    """, (target_date.strftime("%Y-%m-%d"),))

    schedule = cursor.fetchall()
    conn.close()
    return schedule

def add_homework(course_name, due_date, description, professor_name):
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS homework (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            course_name TEXT,
            due_date TEXT,
            description TEXT,
            professor_name TEXT
        )
    """)
    cursor.execute("INSERT INTO homework (course_name, due_date, description, professor_name) VALUES (?, ?, ?, ?)",
                   (course_name, due_date, description, professor_name))
    conn.commit()
    conn.close()

def get_all_homework():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT course_name, due_date, description, professor_name FROM homework ORDER BY due_date")
    homework = cursor.fetchall()
    conn.close()
    return homework

def get_all_courses():
    conn = sqlite3.connect(DATABASE_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT object, start_date, start_time, end_date, end_time, professor, location, room, description FROM courses ORDER BY start_date, start_time")
    courses = cursor.fetchall()
    conn.close()
    return courses
