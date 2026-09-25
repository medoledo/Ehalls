from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('timetable/', views.timetable, name='timetable'),
    path('instructor/', views.instructor_locator, name='instructor'),
    path('api/free-rooms/', views.api_free_rooms, name='api_free_rooms'),
    path('api/instructors/', views.api_instructors, name='api_instructors'),
]
