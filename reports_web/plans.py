"""Планы будущих проверок отделены от неизменяемых снимков Report."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def future_or_today(value):
    if value < timezone.localdate():
        raise ValidationError("Дата проверки не может быть в прошлом.")


class PlanQuerySet(models.QuerySet):
    def active(self):
        return self.filter(status=InspectionPlan.Status.PLANNED)


class InspectionPlan(models.Model):
    class Status(models.TextChoices):
        PLANNED = "planned", "Запланирована"
        CANCELLED = "cancelled", "Отменена"

    room = models.ForeignKey(
        "rooms_web.Room", on_delete=models.PROTECT,
        related_name="inspection_plans", verbose_name="Помещение",
    )
    inspection_date = models.DateField("Дата проверки")
    note = models.TextField("Задача проверки", max_length=1000, blank=True)
    status = models.CharField(
        "Статус", max_length=12, choices=Status.choices,
        default=Status.PLANNED, editable=False,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        verbose_name="Автор плана", related_name="inspection_plans",
        editable=False,
    )
    created_at = models.DateTimeField("Создана", auto_now_add=True)
    objects = PlanQuerySet.as_manager()

    class Meta:
        ordering = ["inspection_date", "pk"]
        verbose_name = "План проверки"
        verbose_name_plural = "Планы проверок"
        constraints = [
            models.UniqueConstraint(
                fields=["room", "inspection_date"],
                condition=models.Q(status="planned"),
                name="one_active_inspection_per_room_day",
                violation_error_message=(
                    "На эту дату для помещения уже запланирована проверка."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["planned", "cancelled"]),
                name="inspection_valid_status",
            ),
        ]

    def clean(self):
        super().clean()
        if self.status == self.Status.PLANNED and self.inspection_date:
            try:
                future_or_today(self.inspection_date)
            except ValidationError as error:
                raise ValidationError({"inspection_date": error}) from error

    def cancel(self):
        changed = type(self).objects.active().filter(pk=self.pk).update(
            status=self.Status.CANCELLED,
        )
        self.refresh_from_db(fields=["status"])
        return bool(changed)

    def __str__(self):
        return f"{self.room} — {self.inspection_date}"
