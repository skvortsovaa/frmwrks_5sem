"""Фильтры GET и проверенные пользовательские данные плана проверки."""

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from rooms_web.models import Room
from smartspace_web.forms import BootstrapFormMixin
from .models import InspectionPlan
from .plans import future_or_today


class InspectionFilterForm(BootstrapFormMixin, forms.Form):
    date = forms.DateField(
        label="Дата", required=False,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    room = forms.ModelChoiceField(
        label="Помещение", queryset=Room.objects.all(), required=False,
        empty_label="Все помещения",
    )
    author = forms.ModelChoiceField(
        label="Автор плана", queryset=get_user_model().objects.none(),
        required=False, empty_label="Все авторы",
    )
    status = forms.ChoiceField(
        label="Статус", required=False, initial="planned",
        choices=[("", "Все статусы"), *InspectionPlan.Status.choices],
    )
    sort = forms.ChoiceField(
        label="Сортировка", required=False,
        choices=[("date", "Ближайшие сначала"),
                 ("-date", "Поздние сначала"), ("room", "По помещению")],
    )
    per_page = forms.TypedChoiceField(
        label="На странице", required=False, coerce=int,
        choices=[(5, "5"), (10, "10"), (20, "20")],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["author"].queryset = get_user_model().objects.filter(
            inspection_plans__isnull=False,
        ).distinct().order_by("username")


class InspectionPlanForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = InspectionPlan
        fields = ["room", "inspection_date", "note"]
        labels = {"note": "Что проверить"}
        help_texts = {
            "inspection_date": "Сегодня или позднее, по московскому времени.",
            "note": "До 1000 символов. Например, проверить датчик влажности.",
        }
        widgets = {
            "inspection_date": forms.DateInput(
                format="%Y-%m-%d", attrs={"type": "date"},
            ),
            "note": forms.Textarea(attrs={
                "rows": 3, "placeholder": "Цель и особенности проверки",
            }),
        }

    def clean_inspection_date(self):
        day = self.cleaned_data["inspection_date"]
        future_or_today(day)
        return day

    def clean(self):
        data = super().clean()
        if self.instance.pk and (
                self.instance.status != InspectionPlan.Status.PLANNED):
            raise ValidationError("Отменённый план нельзя редактировать.")
        room, day = data.get("room"), data.get("inspection_date")
        if room and day and InspectionPlan.objects.active().filter(
            room=room, inspection_date=day,
        ).exclude(pk=self.instance.pk).exists():
            raise ValidationError(
                "На эту дату для помещения уже запланирована проверка. "
                "Выберите другую дату или отмените существующий план.",
            )
        return data
