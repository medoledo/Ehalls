import json
from datetime import datetime, timedelta

import pytz
from django.http import JsonResponse
from django.shortcuts import render
from django.db.models import Q

from .models import MeetingTime

CAIRO_TZ = pytz.timezone('Africa/Cairo')

WEEKDAY_FIELD = {
    0: 'monday',
    1: 'tuesday',
    2: 'wednesday',
    3: 'thursday',
    4: 'friday',
    5: 'saturday',
    6: 'sunday',
}

DAY_ABBR = [
    ('monday', 'Mon'),
    ('tuesday', 'Tue'),
    ('wednesday', 'Wed'),
    ('thursday', 'Thu'),
    ('friday', 'Fri'),
    ('saturday', 'Sat'),
    ('sunday', 'Sun'),
]

DAY_NAMES = [
    ('monday', 'Monday'),
    ('tuesday', 'Tuesday'),
    ('wednesday', 'Wednesday'),
    ('thursday', 'Thursday'),
    ('friday', 'Friday'),
    ('saturday', 'Saturday'),
    ('sunday', 'Sunday'),
]


def normalize_query(text):
    """Collapse repeated whitespace so searches survive messy input/DB values."""
    return " ".join((text or "").split())


def get_meeting_type(meeting):
    return meeting.schedule_type or meeting.course.schedule_type or "Lecture"


def serialize_meeting(meeting):
    days_active = [abbr for field, abbr in DAY_ABBR if getattr(meeting, field, False)]
    return {
        'building': meeting.building or 'TBA',
        'room': meeting.room or 'TBA',
        'course_title': meeting.course.title,
        'course_code': f"{meeting.course.subject} {meeting.course.course_number}".strip(),
        'days': ", ".join(days_active) if days_active else "TBA",
        'start_time': meeting.start_time.strftime('%I:%M %p').lstrip('0') if meeting.start_time else 'TBA',
        'end_time': meeting.end_time.strftime('%I:%M %p').lstrip('0') if meeting.end_time else 'TBA',
        'type': get_meeting_type(meeting),
        'raw_start': meeting.start_time,
        'raw_end': meeting.end_time,
    }

def get_egypt_now(request):
    at_param = request.GET.get('at', '')
    if at_param:
        try:
            naive = datetime.strptime(at_param, '%Y-%m-%dT%H:%M')
            return CAIRO_TZ.localize(naive)
        except ValueError:
            pass
    return datetime.now(CAIRO_TZ)

def get_room_status(now_dt, building_filter=None, course_filter=None):
    weekday_field = WEEKDAY_FIELD[now_dt.weekday()]
    today = now_dt.date()
    now_time = now_dt.time()

    filter_kwargs = {
        weekday_field: True,
        'start_time__isnull': False,
        'end_time__isnull': False,
        'start_date__lte': today,
        'end_date__gte': today,
    }
    if building_filter:
        filter_kwargs['building__icontains'] = building_filter

    all_meetings = (
        MeetingTime.objects
        .filter(**filter_kwargs)
        .exclude(building='', room='')
        .exclude(schedule_type__icontains='Exam')
        .select_related('course')
    )

    room_meetings: dict = {}
    for mt in all_meetings:
        key = (mt.building, mt.room)
        room_meetings.setdefault(key, []).append(mt)

    occupied_rooms = []
    free_rooms = []

    for (building, room), meetings in sorted(room_meetings.items()):
        current = [m for m in meetings if m.start_time <= now_time <= m.end_time]
        if current:
            latest = max(current, key=lambda m: m.end_time)
            s_type = latest.schedule_type or latest.course.schedule_type or "Lecture"
            
            future_meetings = [m for m in meetings if m.start_time >= latest.end_time]
            if future_meetings:
                next_m = min(future_meetings, key=lambda m: m.start_time)
                next_free_till = next_m.start_time.strftime('%I:%M %p').lstrip('0')
            else:
                next_free_till = "EOD"
                
            occ_data = {
                'building': building,
                'room': room,
                'course_title': latest.course.title,
                'course_code': f"{latest.course.subject} {latest.course.course_number}".strip(),
                'end_time': latest.end_time.strftime('%I:%M %p').lstrip('0'),
                'raw_end_time': latest.end_time,
                'type': s_type,
                'next_free_till': next_free_till,
            }
            if course_filter:
                q = course_filter.lower()
                if q in occ_data['course_code'].lower() or q in occ_data['course_title'].lower():
                    occupied_rooms.append(occ_data)
            else:
                occupied_rooms.append(occ_data)
        else:
            if not course_filter:
                future = [m for m in meetings if m.start_time > now_time]
                is_soon_occupied = False
                if future:
                    next_meeting = min(future, key=lambda m: m.start_time)
                    free_till = next_meeting.start_time.strftime('%I:%M %p').lstrip('0')
                    raw_free_till = next_meeting.start_time
                    
                    from datetime import datetime, date
                    t1 = datetime.combine(date.min, next_meeting.start_time)
                    t2 = datetime.combine(date.min, now_time)
                    diff_minutes = (t1 - t2).total_seconds() / 60
                    soon_occupied_minutes = max(1, int(diff_minutes))
                    if diff_minutes <= 10:
                        is_soon_occupied = True
                else:
                    free_till = 'End of Day'
                    soon_occupied_minutes = 0
                    from datetime import time
                    raw_free_till = time(23, 59, 59)
                free_rooms.append({'building': building, 'room': room, 'free_till': free_till, 'is_soon_occupied': is_soon_occupied, 'raw_free_till': raw_free_till, 'soon_occupied_minutes': soon_occupied_minutes})

    occupied_rooms.sort(key=lambda x: x['raw_end_time'])
    free_rooms.sort(key=lambda x: x['raw_free_till'], reverse=True)
    return occupied_rooms, free_rooms

def get_all_buildings():
    return (
        MeetingTime.objects
        .exclude(building__in=['', '1'])
        .values_list('building', flat=True)
        .distinct()
        .order_by('building')
    )

def dashboard(request):
    now_dt = get_egypt_now(request)
    building_filter = request.GET.get('building', '').strip()
    course_filter = request.GET.get('course', '').strip()
    status_filter = request.GET.get('status', '').strip().lower()

    occupied_rooms, free_rooms = get_room_status(now_dt, building_filter or None, course_filter or None)
    
    if status_filter == 'free':
        occupied_rooms = []
    elif status_filter == 'occupied':
        free_rooms = []

    buildings = get_all_buildings()
    
    searched_meetings = []
    if course_filter:
        from django.db.models import Q
        q_meetings = MeetingTime.objects.exclude(building='', room='').exclude(schedule_type__icontains='Exam').select_related('course')
        
        if building_filter:
            q_meetings = q_meetings.filter(building__icontains=building_filter)
            
        from django.db.models.functions import Concat
        from django.db.models import Value
        
        q_clean = course_filter.replace(' ', '').lower()
        
        q_meetings = q_meetings.annotate(
            search_code=Concat('course__subject', Value(''), 'course__course_number')
        ).filter(
            Q(search_code__icontains=q_clean) |
            Q(course__title__icontains=course_filter)
        ).order_by('start_time')
        
        day_names = [('monday', 'Mon'), ('tuesday', 'Tue'), ('wednesday', 'Wed'), ('thursday', 'Thu'), ('friday', 'Fri'), ('saturday', 'Sat'), ('sunday', 'Sun')]
        today_field = day_names[now_dt.weekday()][0]
        
        searched_meetings_today = []
        searched_meetings_week = []
        for m in q_meetings:
            days_active = [abbr for field, abbr in day_names if getattr(m, field, False)]
            days_str = ", ".join(days_active) if days_active else "TBA"
            s_type = m.schedule_type or m.course.schedule_type or "Lecture"
            
            data = {
                'building': m.building,
                'room': m.room,
                'course_title': m.course.title,
                'course_code': f"{m.course.subject} {m.course.course_number}".strip(),
                'start_time': m.start_time.strftime('%I:%M %p').lstrip('0') if m.start_time else 'TBA',
                'end_time': m.end_time.strftime('%I:%M %p').lstrip('0') if m.end_time else 'TBA',
                'days': days_str,
                'type': s_type,
                'raw_start': m.start_time,
            }
            if getattr(m, today_field, False):
                searched_meetings_today.append(data)
            else:
                searched_meetings_week.append(data)
                
        searched_meetings_today.sort(key=lambda x: x['raw_start'])
        searched_meetings_week.sort(key=lambda x: x['raw_start'])

    context = {
        'occupied_rooms': occupied_rooms,
        'free_rooms': free_rooms,
        'total_rooms': len(occupied_rooms) + len(free_rooms),
        'searched_meetings_today': searched_meetings_today if course_filter else [],
        'searched_meetings_week': searched_meetings_week if course_filter else [],
        'current_time': now_dt,
        'buildings': buildings,
        'selected_building': building_filter,
        'selected_course': course_filter,
        'selected_status': status_filter,
    }
    return render(request, 'halls/dashboard.html', context)

def timetable(request):
    try:
        day = int(request.GET.get('day', 0))
    except ValueError:
        day = 0
    day = max(0, min(day, 5))

    building_filter = request.GET.get('building', '').strip()
    course_filter = request.GET.get('course', '').strip()

    weekday_field = WEEKDAY_FIELD[day]
    filter_kwargs = {weekday_field: True, 'start_time__isnull': False}
    if building_filter:
        filter_kwargs['building__icontains'] = building_filter
        
    query = MeetingTime.objects.filter(**filter_kwargs)
    if course_filter:
        query = query.filter(
            Q(course__subject__icontains=course_filter) | 
            Q(course__course_number__icontains=course_filter) |
            Q(course__title__icontains=course_filter)
        )

    meetings = (
        query
        .exclude(building='', room='')
        .exclude(schedule_type__icontains='Exam')
        .select_related('course')
        .order_by('building', 'room', 'start_time')
    )

    time_slots = []
    base = datetime(2000, 1, 1, 8, 0)
    while base.hour < 20:
        time_slots.append(base.time())
        base += timedelta(minutes=30)

    buildings_data: dict = {}
    for mt in meetings:
        b = mt.building
        r = mt.room
        buildings_data.setdefault(b, {}).setdefault(r, []).append(mt)

    grid_data = {}
    for b, rooms in buildings_data.items():
        grid_data[b] = {}
        for r, mts in rooms.items():
            row = []
            for slot in time_slots:
                occupied_by = None
                for mt in mts:
                    if mt.start_time <= slot < mt.end_time:
                        occupied_by = mt
                        break
                row.append(occupied_by)
            grid_data[b][r] = row

    day_names = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']

    context = {
        'selected_day': day,
        'day_names': day_names,
        'time_slots': [t.strftime('%I:%M %p').lstrip('0') for t in time_slots],
        'grid_data': grid_data,
        'buildings': get_all_buildings(),
        'selected_building': building_filter,
        'selected_course': course_filter,
    }
    return render(request, 'halls/timetable.html', context)

def api_free_rooms(request):
    now_dt = get_egypt_now(request)
    building_filter = request.GET.get('building', '').strip()
    course_filter = request.GET.get('course', '').strip()
    occupied_rooms, free_rooms = get_room_status(now_dt, building_filter or None, course_filter or None)

    return JsonResponse({
        'as_of': now_dt.isoformat(),
        'free': [{'building': r['building'], 'room': r['room'], 'free_till': r['free_till']} for r in free_rooms],
        'occupied': [
            {
                'building': r['building'],
                'room': r['room'],
                'course': r['course_title'],
                'course_code': r.get('course_code', ''),
                'until': r['end_time'],
            }
            for r in occupied_rooms
        ],
    })


def api_instructors(request):
    """Autocomplete endpoint: distinct instructor names matching the query."""
    q = normalize_query(request.GET.get('q', ''))
    if len(q) < 2:
        return JsonResponse({'results': [], 'count': 0})

    names = set()
    joined_names = (
        MeetingTime.objects
        .exclude(course__instructor='')
        .values_list('course__instructor', flat=True)
        .distinct()
    )
    for joined in joined_names:
        for part in joined.split(','):
            part = normalize_query(part)
            if part:
                names.add(part)

    q_lower = q.lower()
    matches = sorted(name for name in names if q_lower in name.lower())
    return JsonResponse({'results': matches[:10], 'count': len(matches)})


def instructor_locator(request):
    now_dt = get_egypt_now(request)
    name = normalize_query(request.GET.get('name', ''))
    weekday_field = WEEKDAY_FIELD[now_dt.weekday()]
    today = now_dt.date()
    now_time = now_dt.time()

    current_class = None
    next_class = None
    today_meetings = []
    weekly_schedule = []
    matched_instructors = []

    if name:
        base = (
            MeetingTime.objects
            .filter(course__instructor__icontains=name)
            .filter(
                start_time__isnull=False,
                end_time__isnull=False,
                start_date__lte=today,
                end_date__gte=today,
            )
            .exclude(schedule_type__icontains='Exam')
            .select_related('course')
        )

        # Disambiguate people who share part of the same name
        name_lower = name.lower()
        matched_counts: dict = {}
        for joined in base.values_list('course__instructor', flat=True).distinct():
            for part in joined.split(','):
                part = normalize_query(part)
                if part and name_lower in part.lower():
                    matched_counts[part] = matched_counts.get(part, 0) + 1
        matched_instructors = [
            {'name': person, 'count': count}
            for person, count in sorted(matched_counts.items(), key=lambda kv: (-kv[1], kv[0]))
        ]

        # Today's classes
        meetings_today = list(base.filter(**{weekday_field: True}).order_by('start_time'))
        today_meetings = [serialize_meeting(m) for m in meetings_today]

        ongoing = [m for m in meetings_today if m.start_time <= now_time <= m.end_time]
        if ongoing:
            current_class = serialize_meeting(max(ongoing, key=lambda m: m.end_time))

        upcoming = [m for m in meetings_today if m.start_time > now_time]
        if upcoming:
            next_class = serialize_meeting(min(upcoming, key=lambda m: m.start_time))
        elif not current_class:
            # Look ahead through the rest of the week
            for offset in range(1, 7):
                wd = (now_dt.weekday() + offset) % 7
                field = WEEKDAY_FIELD[wd]
                candidate = base.filter(**{field: True}).order_by('start_time').first()
                if candidate:
                    next_class = serialize_meeting(candidate)
                    next_class['day_label'] = DAY_NAMES[wd][1]
                    break

        # Full week grouped by day
        week_map: dict = {field: [] for field, _ in DAY_NAMES}
        for m in base.order_by('start_time'):
            data = serialize_meeting(m)
            for field, _ in DAY_NAMES:
                if getattr(m, field, False):
                    week_map[field].append(data)
        weekly_schedule = [
            {'day': label, 'day_field': field, 'is_today': field == weekday_field, 'meetings': week_map[field]}
            for field, label in DAY_NAMES
            if week_map[field]
        ]

    context = {
        'current_time': now_dt,
        'selected_name': name,
        'searched': bool(name),
        'current_class': current_class,
        'next_class': next_class,
        'today_meetings': today_meetings,
        'weekly_schedule': weekly_schedule,
        'matched_instructors': matched_instructors,
        'today_label': DAY_NAMES[now_dt.weekday()][1],
    }
    return render(request, 'halls/instructor.html', context)
