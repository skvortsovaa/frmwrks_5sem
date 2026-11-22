from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from reports_web.models import InspectionPlan
from rooms_web.models import Room


class Command(BaseCommand):
    help = "Добавить учебные планы ПР11 без изменения существующих записей."

    def add_arguments(self, parser):
        parser.add_argument("--author", help="Логин автора учебных планов")

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(is_active=True)
        author = (users.filter(username=options["author"]).first()
                  if options["author"] else users.filter(
                      is_superuser=True).order_by("pk").first())
        if author is None:
            raise CommandError("Создайте администратора или укажите --author.")
        rooms = list(Room.objects.order_by("pk")[:2])
        if not rooms:
            raise CommandError("Сначала выполните seed_demo.")
        created = 0
        for offset in range(1, 7):
            for room in rooms:
                day = timezone.localdate() + timedelta(days=offset)
                if InspectionPlan.objects.active().filter(
                    room=room, inspection_date=day,
                ).exists():
                    continue
                _, added = InspectionPlan.objects.get_or_create(
                    room=room, inspection_date=day,
                    note="ПР11: плановая проверка микроклимата",
                    defaults={"created_by": author},
                )
                created += added
        self.stdout.write(self.style.SUCCESS(
            f"Добавлено планов: {created}. "
            f"Всего: {InspectionPlan.objects.count()}. "
            f"Начальная дата: {timezone.localdate() + timedelta(days=1)}.",
        ))
