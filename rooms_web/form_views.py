from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods

from smartspace_web.query_params import database_page
from .forms import RoomForm
from .models import Room


@database_page
@login_required
@permission_required("rooms_web.change_room", raise_exception=True)
@require_http_methods(["GET", "POST"])
def room_edit(request, slug):
    room = get_object_or_404(Room, slug=slug)
    form = RoomForm(
        request.POST if request.method == "POST" else None,
        request.FILES if request.method == "POST" else None, instance=room,
    )
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Помещение сохранено.")
        return redirect(room)
    return render(request, "rooms_web/room_form.html", {
        "form": form, "room": room,
    })
