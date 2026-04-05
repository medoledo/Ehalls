from django.contrib import admin
from .models import Course, MeetingTime


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ['title', 'subject', 'course_number', 'section', 'crn']
    search_fields = ['title', 'subject', 'crn']


@admin.register(MeetingTime)
class MeetingTimeAdmin(admin.ModelAdmin):
    list_display = ['course', 'building', 'room', 'start_time', 'end_time']
    list_filter = ['building', 'monday', 'tuesday', 'wednesday', 'thursday']
