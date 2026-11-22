"""ПР11: настоящие HTTP-запросы, ошибки форм, права, CSRF и media."""

from datetime import timedelta
from io import BytesIO
import os

import django
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client, override_settings
from django.test.utils import (
    setup_databases, setup_test_environment,
    teardown_databases, teardown_test_environment,
)
from django.utils import timezone
from PIL import Image
import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "smartspace_web.settings")
django.setup()

from reports_web.forms import InspectionPlanForm  # noqa
from reports_web.models import InspectionPlan  # noqa
from rooms_web.models import Room  # noqa


@pytest.fixture(scope="module")
def forms_database():
    config = setup_databases(verbosity=0, interactive=False)
    setup_test_environment()
    yield
    teardown_test_environment()
    teardown_databases(config, verbosity=0)


@pytest.fixture
def site(forms_database, tmp_path):
    with transaction.atomic(), override_settings(
        ALLOWED_HOSTS=["testserver"], MEDIA_ROOT=tmp_path,
        PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"],
    ):
        room = Room.objects.create(name="Лаборатория", floor=2, area=40)
        other = Room.objects.create(name="Архив", floor=1, area=20)
        user = get_user_model().objects.create_superuser(
            "forms-admin", password="test-only-password",
        )
        client = Client()
        client.force_login(user)
        yield client, room, other, user
        transaction.set_rollback(True)


def payload(selected_room, **kwargs):
    return {"room": selected_room.pk,
            "inspection_date": str(timezone.localdate() + timedelta(days=1)),
            "note": "Проверить влажность", **kwargs}


def make_plan(room, user, **kwargs):
    return InspectionPlan.objects.create(
        room=room,
        inspection_date=timezone.localdate() + timedelta(days=1),
        created_by=user, **kwargs,
    )


def photo(name="room.png", color="blue"):
    stream = BytesIO()
    Image.new("RGB", (48, 32), color).save(stream, format="PNG")
    return SimpleUploadedFile(
        name, stream.getvalue(), content_type="image/png",
    )


def test_get_unbound_create_and_post_redirect_saved_author(site):
    client, room, _, user = site
    response = client.get("/inspections/create/")
    assert response.status_code == 200
    assert not response.context["form"].is_bound
    result = client.post("/inspections/create/", payload(
        room, status="cancelled", created_by=9999,
    ))
    assert result.status_code == 302
    plan = InspectionPlan.objects.get()
    assert plan.created_by == user
    assert plan.status == "planned"
    assert plan.note == "Проверить влажность"
    assert client.get(result.url).status_code == 200


@pytest.mark.parametrize("changes,field", [
    ({"inspection_date": "1999-01-01"}, "inspection_date"),
    ({"inspection_date": "invalid"}, "inspection_date"),
    ({"inspection_date": ""}, "inspection_date"),
    ({"room": "999999"}, "room"),
    ({"room": "invalid"}, "room"),
    ({"note": "x" * 1001}, "note"),
])
def test_invalid_create_is_bound_keeps_input_and_does_not_save(
        site, changes, field):
    client, room, _, _ = site
    response = client.post("/inspections/create/", payload(room, **changes))
    assert response.status_code == 200
    assert field in response.context["form"].errors
    assert response.context["form"].is_bound
    assert InspectionPlan.objects.count() == 0
    if field != "note":
        assert "Проверить влажность" in response.content.decode()


def test_duplicate_cancel_recreate_and_cancelled_not_editable(site):
    client, room, _, user = site
    plan = make_plan(room, user)
    response = client.post("/inspections/create/", payload(room))
    assert response.context["form"].non_field_errors()
    assert InspectionPlan.objects.count() == 1
    assert client.post(f"/inspections/{plan.pk}/cancel/").status_code == 302
    plan.refresh_from_db()
    assert plan.status == "cancelled"
    assert client.post(f"/inspections/{plan.pk}/cancel/").status_code == 302
    response = client.post("/inspections/create/", payload(room))
    assert response.status_code == 302
    assert InspectionPlan.objects.count() == 2
    assert client.post(f"/inspections/{plan.pk}/edit/", payload(
        room, note="Нельзя менять",
    )).status_code == 302
    plan.refresh_from_db()
    assert plan.note == ""


def test_edit_excludes_self_preserves_pk_author_and_refuses_conflict(site):
    client, room, other, user = site
    plan = make_plan(room, user)
    make_plan(other, user)
    url = f"/inspections/{plan.pk}/edit/"
    assert client.get(url).context["form"].initial["room"] == room.pk
    assert client.post(url, payload(room, note="Изменено")).status_code == 302
    assert InspectionPlan.objects.count() == 2
    plan.refresh_from_db()
    assert plan.note == "Изменено" and plan.created_by == user
    for data in (payload(other), payload(room, inspection_date="1999-01-01")):
        response = client.post(url, data)
        assert response.status_code == 200
        assert response.context["form"].errors
    plan.refresh_from_db()
    assert plan.room == room and plan.note == "Изменено"


def test_database_constraint_also_rejects_duplicate_without_form(site):
    _, room, _, user = site
    make_plan(room, user)
    with pytest.raises(IntegrityError), transaction.atomic():
        make_plan(room, user)


def test_direct_modelform_rejects_cancelled_and_accepts_today(site):
    _, room, _, user = site
    form = InspectionPlanForm(payload(
        room, inspection_date=str(timezone.localdate()),
    ))
    assert form.is_valid(), form.errors
    cancelled = make_plan(room, user, status="cancelled")
    assert not InspectionPlanForm(payload(room), instance=cancelled).is_valid()


def test_filter_sort_pagination_keeps_parameters(site):
    client, room, other, user = site
    for offset in range(1, 14):
        InspectionPlan.objects.create(
            room=room, inspection_date=timezone.localdate() + timedelta(
                days=offset), created_by=user,
        )
    cancelled = make_plan(other, user, status="cancelled")
    response = client.get("/inspections/", {
        "room": room.pk, "author": user.pk, "sort": "-date",
        "per_page": 5, "status": "planned", "page": 2,
    })
    page = response.context["page_obj"]
    assert page.number == 2 and page.paginator.count == 13
    assert len(page.object_list) == 5
    assert "sort=-date" in response.content.decode()
    assert f"room={room.pk}" in response.content.decode()
    dates = [p.inspection_date for p in page]
    assert dates == sorted(dates, reverse=True)
    default = client.get("/inspections/").context["page_obj"]
    assert default.paginator.count == 13
    result = client.get("/inspections/", {"status": "cancelled"})
    assert [p.pk for p in result.context["page_obj"]] == [cancelled.pk]


@pytest.mark.parametrize("params", [
    {"date": "2026-99-99"}, {"room": "missing"}, {"author": "999999"},
    {"status": "unknown"}, {"sort": "__raw_sql"}, {"per_page": "9999"},
])
def test_bad_get_filters_show_errors_and_empty_page(site, params):
    response = site[0].get("/inspections/", params)
    assert response.status_code == 200
    assert response.context["form"].errors
    assert response.context["page_obj"].paginator.count == 0


def test_missing_edit_and_cancel_are_404_and_get_cancel_is_405(site):
    client, room, _, user = site
    plan = make_plan(room, user)
    assert client.get(f"/inspections/{plan.pk}/cancel/").status_code == 405
    plan.refresh_from_db()
    assert plan.status == "planned"
    assert client.get("/inspections/999999/edit/").status_code == 404
    assert client.post("/inspections/999999/cancel/").status_code == 404


def test_csrf_required_for_create_edit_cancel_and_photo(site):
    _, room, _, user = site
    plan = make_plan(room, user)
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    urls = ["/inspections/create/", f"/inspections/{plan.pk}/edit/",
            f"/inspections/{plan.pk}/cancel/", f"/rooms/{room.slug}/edit/"]
    for url in urls:
        assert client.post(url, payload(room)).status_code == 403
    client.get("/inspections/create/")
    token = client.cookies["csrftoken"].value
    assert client.post(f"/inspections/{plan.pk}/cancel/", {
        "csrfmiddlewaretoken": token,
    }).status_code == 302


def test_anonymous_login_redirect_and_user_without_permissions(site):
    _, room, _, _ = site
    client = Client()
    assert client.get("/inspections/").status_code == 200
    assert client.get("/inspections/create/").status_code == 302
    assert client.get("/accounts/login/").status_code == 200
    user = get_user_model().objects.create_user("reader")
    client.force_login(user)
    response = client.post("/inspections/create/", payload(room))
    assert response.status_code == 403
    assert client.get(f"/rooms/{room.slug}/edit/").status_code == 403


def test_photo_upload_replace_clear_and_detail(site):
    client, room, _, _ = site
    data = {"name": room.name, "floor": 2, "area": 40}
    url = f"/rooms/{room.slug}/edit/"
    for color in ("blue", "red"):
        response = client.post(url, {**data, "photo": photo(color=color)})
        assert response.status_code == 302
        room.refresh_from_db()
        assert room.photo.storage.exists(room.photo.name)
        with room.photo.open() as stream:
            assert Image.open(stream).getpixel((0, 0)) == (
                (0, 0, 255) if color == "blue" else (255, 0, 0)
            )
        assert room.photo.url in client.get(
            room.get_absolute_url()).content.decode()
    assert client.post(url, {**data, "photo-clear": "on"}).status_code == 302
    room.refresh_from_db()
    assert not room.photo


def test_fake_and_oversized_photo_not_saved(site):
    client, room, _, _ = site
    fake = SimpleUploadedFile("fake.png", b"not an image", "image/png")
    big = photo()
    big.size = 6 * 1024 * 1024
    from rooms_web.forms import RoomForm
    for upload in (fake, big):
        form = RoomForm({"name": room.name, "floor": 2, "area": 40},
                        {"photo": upload}, instance=room)
        assert not form.is_valid()
        assert "photo" in form.errors


def test_admin_photo_upload_and_plan_creation_use_same_forms(site):
    client, room, _, user = site
    response = client.post(f"/admin/rooms_web/room/{room.pk}/change/", {
        "name": room.name, "floor": 2, "area": 40, "photo": photo(),
        "sensor-TOTAL_FORMS": 0, "sensor-INITIAL_FORMS": 0,
        "reports-TOTAL_FORMS": 0, "reports-INITIAL_FORMS": 0,
        "_save": "Сохранить",
    })
    assert response.status_code == 302, response.context["adminform"].errors
    room.refresh_from_db()
    assert room.photo.storage.exists(room.photo.name)
    result = client.post("/admin/reports_web/inspectionplan/add/", {
        **payload(room), "_save": "Сохранить",
    })
    assert result.status_code == 302
    plan = InspectionPlan.objects.get()
    assert plan.created_by == user
