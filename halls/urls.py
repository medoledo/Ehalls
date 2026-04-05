from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('timetable/', views.timetable, name='timetable'),
    path('api/free-rooms/', views.api_free_rooms, name='api_free_rooms'),
]
