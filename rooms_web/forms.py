from django import forms

from smartspace_web.forms import BootstrapFormMixin
from .models import Room


class RoomForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Room
        fields = ["name", "floor", "area", "photo"]
        widgets = {
            "photo": forms.ClearableFileInput(attrs={
                "accept": "image/jpeg,image/png,image/webp",
            }),
        }
