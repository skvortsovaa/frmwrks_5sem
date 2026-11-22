"""Показатели, исторические отчёты и измерения Django ORM."""

from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.core.validators import MaxValueValidator
from django.db import models

from models.metrics import analyze_metric
from models.reports import get_room_status
from smartspace_web.validators import finite_number, nonblank_text
from .querysets import ReportQuerySet
from .plans import InspectionPlan  # noqa: F401


class Status(models.TextChoices):
    NORMAL = "НОРМА", "Норма"
    WARNING = "ПРЕДУПРЕЖДЕНИЕ", "Предупреждение"
    ALARM = "АВАРИЯ", "Авария"
    NO_DATA = "НЕТ ДАННЫХ", "Нет данных"


class Metric(models.Model):
    id = models.CharField(
        verbose_name='Идентификатор',
        primary_key=True,
        max_length=100,
        validators=[nonblank_text],
    )
    name = models.CharField(
        verbose_name='Название',
        max_length=200,
        validators=[nonblank_text])
    unit = models.CharField(
        verbose_name='Единица измерения',
        max_length=30,
        validators=[nonblank_text])
    minimum = models.FloatField(
        verbose_name='Нижняя граница',
        validators=[finite_number])
    maximum = models.FloatField(
        verbose_name='Верхняя граница',
        validators=[finite_number])

    class Meta:
        ordering = ["id"]
        verbose_name = "Показатель"
        verbose_name_plural = "Показатели"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(minimum__lte=models.F("maximum")),
                name="metric_ordered_limits",
            ),
            models.CheckConstraint(
                condition=(~models.Q(id="leak")
                           | models.Q(minimum=0, maximum=0)),
                name="metric_leak_limits",
            ),
        ]

    def __str__(self):
        return f"{self.name}, {self.unit}"


class Report(models.Model):
    objects = ReportQuerySet.as_manager()

    id = models.CharField(
        verbose_name='Идентификатор',
        primary_key=True,
        max_length=100,
        validators=[nonblank_text],
    )
    room = models.ForeignKey("rooms_web.Room", verbose_name="Помещение",
                             on_delete=models.PROTECT,
                             related_name="reports")
    room_name = models.CharField(
        verbose_name='Помещение при проверке',
        max_length=200,
        validators=[nonblank_text])
    checked_at = models.DateTimeField(verbose_name='Дата и время проверки')
    sensor_active = models.BooleanField(verbose_name='Датчик был включён')
    battery = models.PositiveSmallIntegerField(
        verbose_name='Заряд при проверке, %',
        validators=[MaxValueValidator(100)],
    )
    status = models.CharField(
        verbose_name='Статус',
        max_length=20,
        choices=Status.choices)

    class Meta:
        ordering = ["-checked_at", "id"]
        verbose_name = "Отчёт"
        verbose_name_plural = "Отчёты"
        indexes = [models.Index(fields=["room", "checked_at"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(battery__lte=100),
                                   name="report_battery_range"),
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values),
                name="report_valid_status",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(sensor_active=True, battery__gt=0)
                    & ~models.Q(status=Status.NO_DATA)
                ) | (
                    (models.Q(sensor_active=False) | models.Q(battery=0))
                    & models.Q(status=Status.NO_DATA)
                ), name="report_availability_status",
            ),
        ]

    def _reading(self, metric):
        # all() использует prefetch-кэш карточки, если он уже загружен.
        return next((row for row in self.readings.all()
                     if row.metric_id == metric), None)

    def _analysis(self, metric):
        row = self._reading(metric)
        if row is None:
            return None
        return {"value": row.value, "minimum": row.minimum,
                "maximum": row.maximum,
                "normal": row.status == Status.NORMAL}

    @property
    def temperature(self):
        return self._analysis("temperature")

    @property
    def humidity(self):
        return self._analysis("humidity")

    @property
    def leak_detected(self):
        row = self._reading("leak")
        return bool(row.value) if row is not None else None

    def clean(self):
        super().clean()
        available = self.sensor_active and (self.battery or 0) > 0
        if available == (self.status == Status.NO_DATA):
            raise ValidationError(
                "Статус не соответствует доступности датчика.")

    def validate_readings(self):
        """Проверить готовую проверку после записи всех её измерений."""
        rows = list(self.readings.all())
        available = self.sensor_active and self.battery > 0
        if not available:
            if rows or self.status != Status.NO_DATA:
                raise ValidationError("У недоступного датчика нет показаний.")
            return
        by_metric = {row.metric_id: row for row in rows}
        if (len(rows) != 3 or set(by_metric)
                != {"temperature", "humidity", "leak"}):
            raise ValidationError("Для проверки нужны три разных показателя.")
        if len({row.sensor_id for row in rows}) != 1:
            raise ValidationError(
                "Измерения проверки должны быть от одного датчика.")
        for row in rows:
            row.full_clean()
        expected = get_room_status(
            True, by_metric["temperature"].status == Status.NORMAL,
            by_metric["humidity"].status == Status.NORMAL,
            bool(by_metric["leak"].value),
        )
        if self.status != expected:
            raise ValidationError("Статус не соответствует показаниям.")

    def __str__(self):
        return f"{self.room_name}: {self.status} ({self.id})"


class Reading(models.Model):
    id = models.CharField(
        verbose_name='Идентификатор',
        primary_key=True,
        max_length=100,
        validators=[nonblank_text],
    )
    sensor = models.ForeignKey("sensors_web.Sensor", verbose_name="Датчик",
                               on_delete=models.PROTECT,
                               related_name="readings")
    metric = models.ForeignKey(Metric, verbose_name="Показатель",
                               on_delete=models.PROTECT,
                               related_name="readings")
    report = models.ForeignKey(Report, verbose_name="Отчёт",
                               on_delete=models.PROTECT,
                               related_name="readings")
    measured_at = models.DateTimeField(
        verbose_name='Время измерения', db_index=True)
    value = models.FloatField(
        verbose_name='Значение',
        validators=[finite_number])
    minimum = models.FloatField(
        verbose_name='Нижняя граница',
        validators=[finite_number])
    maximum = models.FloatField(
        verbose_name='Верхняя граница',
        validators=[finite_number])
    status = models.CharField(verbose_name='Статус', max_length=20, choices=[
        choice for choice in Status.choices if choice[0] != Status.NO_DATA
    ])

    class Meta:
        ordering = ["-measured_at", "id"]
        verbose_name = "Измерение"
        verbose_name_plural = "Измерения"
        constraints = [
            models.UniqueConstraint(fields=["report", "metric"],
                                    name="one_reading_per_report_metric"),
            models.CheckConstraint(
                condition=models.Q(minimum__lte=models.F("maximum")),
                name="reading_ordered_limits",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=Status.values[:3]),
                name="reading_valid_status",
            ),
        ]

    def clean(self):
        super().clean()
        try:
            result = analyze_metric(self.value, self.minimum, self.maximum)
            expected = Status.NORMAL if result.normal else Status.WARNING
            if self.metric_id == "leak":
                if (self.value not in (0, 1)
                        or (self.minimum, self.maximum) != (0, 0)):
                    raise ValueError("Протечка: значение 0/1, норма 0.")
                expected = Status.ALARM if self.value else Status.NORMAL
            if self.status != expected:
                raise ValueError("Неверный статус измерения.")
            if self.sensor.room_id != self.report.room_id:
                raise ValueError("Датчик и отчёт из разных помещений.")
            if self.measured_at != self.report.checked_at:
                raise ValueError("Время измерения не совпадает с отчётом.")
            if (not self.report.sensor_active or self.report.battery == 0
                    or self.report.status == Status.NO_DATA):
                raise ValueError("У недоступного датчика нет показаний.")
        except (ValueError, TypeError, ObjectDoesNotExist) as error:
            raise ValidationError(str(error)) from error

    def __str__(self):
        return f"{self.sensor_id}: {self.value} ({self.metric_id})"
