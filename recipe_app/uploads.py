import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

MAX_AVATAR_PIXELS = 20_000_000
Image.MAX_IMAGE_PIXELS = MAX_AVATAR_PIXELS


def save_avatar(upload: FileStorage) -> str:
    if not upload or not upload.filename:
        raise ValueError("Choisissez une image à envoyer.")
    try:
        image = Image.open(upload.stream)
        if image.format not in {"JPEG", "PNG", "WEBP"}:
            raise ValueError("Formats acceptés : JPEG, PNG ou WebP.")
        if image.width * image.height > MAX_AVATAR_PIXELS:
            raise ValueError("Cette image est trop grande.")
        image.load()
        image = image.convert("RGB")
        image.thumbnail((600, 600))
        filename = f"{secrets.token_hex(16)}.webp"
        destination = Path(current_app.config["UPLOAD_FOLDER"]) / filename
        image.save(destination, format="WEBP", quality=84, method=5)
        return filename
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise ValueError("Le fichier envoyé n'est pas une image valide.") from error
