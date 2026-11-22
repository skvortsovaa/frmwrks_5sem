from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from PIL import Image, UnidentifiedImageError


def room_photo_path(instance, filename):
    return f"rooms/{uuid4().hex}{Path(filename).suffix.lower()}"


def validate_room_photo(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError("Размер изображения не должен превышать 5 МБ.")
    position = value.tell()
    try:
        image = Image.open(value)
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValidationError("Допустимы только JPEG, PNG и WebP.")
        if image.width * image.height > 20_000_000:
            raise ValidationError("Изображение должно быть не более 20 Мп.")
    except (UnidentifiedImageError, OSError,
            Image.DecompressionBombError) as e:
        raise ValidationError("Загрузите корректное изображение.") from e
    finally:
        value.seek(position)
