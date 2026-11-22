from django.urls import path

from . import views
from .form_views import room_edit


app_name = "rooms"

urlpatterns = [
    path("uninspected/", views.uninspected_rooms, name="uninspected"),
    path("", views.room_list, name="list"),
    path("<int:room_id>/", views.room_detail, name="detail"),
    path("<slug:slug>/edit/", room_edit, name="edit"),
    path("<slug:slug>/", views.room_detail_slug, name="detail-slug"),
]
