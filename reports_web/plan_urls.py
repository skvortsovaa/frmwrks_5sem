from django.urls import path

from . import plan_views


app_name = "inspections"
urlpatterns = [
    path("", plan_views.plan_list, name="list"),
    path("create/", plan_views.plan_create, name="create"),
    path("<int:pk>/edit/", plan_views.plan_edit, name="edit"),
    path("<int:pk>/cancel/", plan_views.plan_cancel, name="cancel"),
]
