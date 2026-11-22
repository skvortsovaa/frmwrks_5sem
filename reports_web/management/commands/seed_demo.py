"""Дополнить единственную рабочую базу связанными примерами для защиты."""

from datetime import datetime, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from models.reports import get_room_status
from reports_web.models import Metric, Reading, Report, Status
from rooms_web.models import Room
from sensors_web.models import Sensor


class Command(BaseCommand):
    help = "Добавить демонстрационные записи, сохранив существующие данные."

    @transaction.atomic
    def handle(self, *args, **options):
        specs = (
            ("temperature", "Температура", "°C", 18, 24),
            ("humidity", "Влажность", "%", 40, 60),
            ("leak", "Протечка", "0/1", 0, 0),
        )
        metrics = {}
        for key, name, unit, low, high in specs:
            metric, _ = Metric.objects.get_or_create(
                pk=key, defaults=dict(name=name, unit=unit,
                                      minimum=low, maximum=high),
            )
            metric.full_clean()
            metrics[key] = metric

        rooms = (
            ("Переговорная", 2, 28, True, 94),
            ("Лаборатория", 3, 64, True, 78),
            ("Архив", 1, 42, True, 15),
            ("Учебная аудитория", 4, 86, True, 62),
            ("Техническое помещение", 0, 18, False, 0),
            ("Конференц-зал", 2, 120, True, 88),
        )
        start = timezone.make_aware(datetime(2026, 11, 20, 9))
        for index, (name, floor, area, active, battery) in enumerate(rooms):
            room, _ = Room.objects.get_or_create(
                slug=f"demo-pr10-room-{index + 1}",
                defaults=dict(name=name, floor=floor, area=area),
            )
            room.full_clean()
            sensor, _ = Sensor.objects.get_or_create(
                room=room, defaults=dict(id=f"DEMO-SENS-{index + 1:03}",
                                         active=active, battery=battery),
            )
            sensor.full_clean()
            for day in range(3):
                report_id = f"DEMO-PR10-{index + 1:02}-{day + 1:02}"
                if Report.objects.filter(pk=report_id).exists():
                    continue
                checked_at = start + timedelta(days=day, hours=index)
                available = sensor.is_available()
                values = {
                    key: (metric.minimum + metric.maximum) / 2
                    for key, metric in metrics.items()
                }
                scenario = (index + day) % 3
                if scenario == 1:
                    values["temperature"] = metrics["temperature"].maximum + 4
                values["leak"] = int(scenario == 2)
                normal = {
                    key: metric.minimum <= values[key] <= metric.maximum
                    for key, metric in metrics.items()
                }
                leak = bool(values["leak"]) if available else None
                status = get_room_status(
                    available, normal["temperature"], normal["humidity"], leak,
                )
                report = Report(
                    id=report_id, room=room, room_name=room.name,
                    checked_at=checked_at, sensor_active=sensor.active,
                    battery=sensor.battery, status=status,
                )
                report.full_clean()
                report.save()
                if not available:
                    continue
                for key, metric in metrics.items():
                    value = values[key]
                    reading_status = (
                        Status.ALARM if value else Status.NORMAL
                    ) if key == "leak" else (
                        Status.NORMAL
                        if metric.minimum <= value <= metric.maximum
                        else Status.WARNING
                    )
                    reading = Reading(
                        id=f"{report_id}-{key}", sensor=sensor, metric=metric,
                        report=report, measured_at=checked_at, value=value,
                        minimum=metric.minimum, maximum=metric.maximum,
                        status=reading_status,
                    )
                    reading.full_clean()
                    reading.save()
                report.validate_readings()
        for model in (Room, Sensor, Metric, Report, Reading):
            self.stdout.write(f"{model._meta.verbose_name_plural}: "
                              f"{model.objects.count()}")
