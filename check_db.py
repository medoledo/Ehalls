import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Ehalls.settings')
django.setup()

from halls.models import Course, MeetingTime
from datetime import datetime, date, time
import pytz

print('--- DB STATS ---')
print('Courses:', Course.objects.count())
print('MeetingTimes:', MeetingTime.objects.count())
print()

# Unique buildings
buildings = MeetingTime.objects.exclude(building='').values_list('building', flat=True).distinct().order_by('building')
print('Unique buildings found:', list(buildings))
print()

CAIRO_TZ = pytz.timezone('Africa/Cairo')
now_dt = datetime.now(CAIRO_TZ)

print('--- Sample MeetingTimes with Building/Room ---')
for mt in MeetingTime.objects.exclude(building='').exclude(room='').select_related('course')[:5]:
    days = []
    for d in ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']:
        if getattr(mt, d): days.append(d[:3].capitalize())
    day_str = ','.join(days)
    print(f"{mt.course.subject}{mt.course.course_number} - {mt.course.title}")
    print(f"  Building: {mt.building}, Room: {mt.room}, Time: {mt.start_time}-{mt.end_time}, Days: {day_str}")
