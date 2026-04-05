from django.db import models


class Course(models.Model):
    title = models.CharField(max_length=200)
    subject = models.CharField(max_length=20)
    course_number = models.CharField(max_length=20)
    section = models.CharField(max_length=10)
    crn = models.CharField(max_length=20, unique=True)
    term = models.CharField(max_length=20)
    instructor = models.CharField(max_length=200, blank=True)
    schedule_type = models.CharField(max_length=50, blank=True)
    campus = models.CharField(max_length=100, blank=True)
    seats_available = models.IntegerField(default=0)
    max_enrollment = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.subject}{self.course_number} - {self.title} (Section {self.section})"


class MeetingTime(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name='meeting_times')
    monday = models.BooleanField(default=False)
    tuesday = models.BooleanField(default=False)
    wednesday = models.BooleanField(default=False)
    thursday = models.BooleanField(default=False)
    friday = models.BooleanField(default=False)
    saturday = models.BooleanField(default=False)
    sunday = models.BooleanField(default=False)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    building = models.CharField(max_length=200, blank=True)
    room = models.CharField(max_length=100, blank=True)
    schedule_type = models.CharField(max_length=50, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.building} {self.room} - {self.start_time} to {self.end_time}"
