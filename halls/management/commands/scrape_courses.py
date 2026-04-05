"""
Management command: scrape_courses
Fetches all courses and meeting times from register.must.edu.eg and saves them to the DB.
"""
import time
import warnings
import requests
import urllib3
from datetime import datetime, time as dt_time, date
from django.core.management.base import BaseCommand
from halls.models import Course, MeetingTime

# MUST's server uses a self-signed / local-issuer SSL cert; suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


BASE_URL = "https://register.must.edu.eg/StudentRegistrationSsb/ssb"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://register.must.edu.eg/StudentRegistrationSsb/ssb/classSearch/classSearch",
}


def parse_time(t_str):
    """Convert 'HHMM' string to Python time object. Returns None if invalid."""
    if not t_str or len(t_str) < 4:
        return None
    try:
        hour = int(t_str[:2])
        minute = int(t_str[2:])
        return dt_time(hour, minute)
    except (ValueError, IndexError):
        return None


def parse_date(d_str):
    """Convert 'MM/DD/YYYY' or 'YYYY-MM-DD' string to Python date object."""
    if not d_str:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d'):
        try:
            return datetime.strptime(d_str, fmt).date()
        except ValueError:
            continue
    return None


def get_session_and_term():
    """Create a requests Session, discover the Spring/2026 term code, and initialize the session."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Phase 2: Get term code
    print("Fetching term list...")
    resp = session.get(
        f"{BASE_URL}/classSearch/getTerms",
        params={"offset": 1, "max": 10},
        timeout=30,
        verify=False,
    )
    resp.raise_for_status()
    terms = resp.json()
    term_code = None
    for t in terms:
        desc = t.get("description", "")
        if "Spring" in desc and "2026" in desc:
            term_code = t["code"]
            print(f"Found term: {desc} => code={term_code}")
            break
    if not term_code:
        # Fall back to first term
        term_code = terms[0]["code"]
        print(f"Spring/2026 not found, using first term: {terms[0].get('description')} => {term_code}")

    # Phase 3: Initialize session
    print(f"Initializing session for term {term_code}...")
    session.post(
        f"{BASE_URL}/term/search",
        params={"mode": "search"},
        data={"term": term_code},
        timeout=30,
        verify=False,
    )
    session.get(f"{BASE_URL}/classSearch/classSearch", timeout=30, verify=False)
    print("Session initialized.")
    return session, term_code


def fetch_subjects(session, term_code):
    """Fetch all subject codes."""
    print("Fetching subject codes...")
    resp = session.get(
        f"{BASE_URL}/classSearch/get_subject",
        params={"term": term_code, "offset": 1, "max": 5000, "searchTerm": ""},
        timeout=30,
        verify=False,
    )
    resp.raise_for_status()
    data = resp.json()
    subjects = [s["code"] for s in data]
    print(f"Total subjects: {len(subjects)}")
    return subjects


def fetch_sections_for_subject(session, term_code, subject_code):
    """Paginate through all sections for a given subject."""
    # Reset banner server-side search cache
    session.post(f"{BASE_URL}/classSearch/resetDataForm", verify=False)
    
    sections = []
    page_offset = 0
    page_size = 500
    while True:
        resp = session.get(
            f"{BASE_URL}/searchResults/searchResults",
            params={
                "txt_term": term_code,
                "txt_subject": subject_code,
                "startDatepicker": "",
                "endDatepicker": "",
                "uniqueSessionId": "hall1",
                "pageOffset": page_offset,
                "pageMaxSize": page_size,
                "sortColumn": "subjectDescription",
                "sortDirection": "asc",
            },
            timeout=60,
            verify=False,
        )
        resp.raise_for_status()
        payload = resp.json()
        data = payload.get("data") or []
        if not data:
            break
        sections.extend(data)
        page_offset += page_size
        if len(data) < page_size:
            break
    return sections


class Command(BaseCommand):
    help = "Scrape all courses and meeting times from register.must.edu.eg"

    def handle(self, *args, **options):
        session, term_code = get_session_and_term()
        subjects = fetch_subjects(session, term_code)

        total_courses = 0
        total_meetings = 0

        for subject_code in subjects:
            try:
                sections = fetch_sections_for_subject(session, term_code, subject_code)
            except Exception as exc:
                self.stderr.write(f"  ERROR fetching {subject_code}: {exc}")
                continue

            subject_courses = 0
            subject_meetings = 0

            for sec in sections:
                # Extract course-level fields
                crn = str(sec.get("courseReferenceNumber") or "")
                if not crn:
                    continue

                title = sec.get("courseTitle") or ""
                subject = sec.get("subject") or subject_code
                course_number = str(sec.get("courseNumber") or "")
                section_num = str(sec.get("sequenceNumber") or "")
                schedule_type = sec.get("scheduleTypeDescription") or ""
                campus = sec.get("campusDescription") or ""
                seats_available = int(sec.get("seatsAvailable") or 0)
                max_enrollment = int(sec.get("maximumEnrollment") or 0)

                # Instructor (may be nested)
                instructor = ""
                faculty_list = sec.get("faculty") or []
                if faculty_list:
                    name = faculty_list[0].get("displayName") or ""
                    instructor = name

                course_obj, _ = Course.objects.update_or_create(
                    crn=crn,
                    defaults={
                        "title": title,
                        "subject": subject,
                        "course_number": course_number,
                        "section": section_num,
                        "term": term_code,
                        "instructor": instructor,
                        "schedule_type": schedule_type,
                        "campus": campus,
                        "seats_available": seats_available,
                        "max_enrollment": max_enrollment,
                    },
                )
                subject_courses += 1

                # Delete old meeting times and re-create
                course_obj.meeting_times.all().delete()

                meetings_faculty = sec.get("meetingsFaculty") or []
                for mf in meetings_faculty:
                    mt = mf.get("meetingTime") or {}
                    if not mt:
                        continue

                    building = mt.get("buildingDescription") or mt.get("building") or ""
                    room = mt.get("room") or ""
                    start_time = parse_time(mt.get("beginTime"))
                    end_time = parse_time(mt.get("endTime"))
                    start_date = parse_date(mt.get("startDate"))
                    end_date = parse_date(mt.get("endDate"))
                    mt_schedule_type = mt.get("meetingScheduleType") or ""

                    MeetingTime.objects.create(
                        course=course_obj,
                        monday=bool(mt.get("monday")),
                        tuesday=bool(mt.get("tuesday")),
                        wednesday=bool(mt.get("wednesday")),
                        thursday=bool(mt.get("thursday")),
                        friday=bool(mt.get("friday")),
                        saturday=bool(mt.get("saturday")),
                        sunday=bool(mt.get("sunday")),
                        start_time=start_time,
                        end_time=end_time,
                        building=building,
                        room=room,
                        schedule_type=mt_schedule_type,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    subject_meetings += 1

            total_courses += subject_courses
            total_meetings += subject_meetings
            print(f"  Subject {subject_code}: {subject_courses} sections, {subject_meetings} meetings")

        self.stdout.write(self.style.SUCCESS(
            f"\n=== DONE ===\nTotal courses saved: {total_courses}\nTotal meeting times saved: {total_meetings}"
        ))
