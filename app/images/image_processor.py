"""Image import, thumbnails and cleanup (Pillow based)."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.paths import AppPaths
from app.utils.logger import get_logger

logger = get_logger("images")

SUPPORTED_FORMATS = ("PNG", "JPEG", "WEBP", "ICO", "GIF", "BMP", "TIFF")
SUPPORTED_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".ico", ".gif", ".bmp", ".tif", ".tiff")

THUMBNAIL_SIZE = (192, 192)
MAX_SOURCE_DIMENSION = 2048
#: Guard against decompression bombs / absurd files.
MAX_FILE_SIZE = 40 * 1024 * 1024
MAX_PIXELS = 60_000_000

Image.MAX_IMAGE_PIXELS = MAX_PIXELS


class ImageError(RuntimeError):
    """Raised when an image cannot be imported."""


def pick_icon(original: Image.Image) -> Image.Image:
    """Choose the best frame from multi-size sources (ICO/GIF)."""
    frames = getattr(original, "n_frames", 1) or 1
    if frames > 1:
        best = original
        best_area = 0
        for index in range(min(frames, 16)):
            try:
                original.seek(index)
                frame = original.copy()
            except (EOFError, OSError):
                break
            area = frame.width * frame.height
            if area > best_area:
                best, best_area = frame, area
        return best
    return original


def _open_image(path: Path) -> Image.Image:
    try:
        with Image.open(path) as raw:
            raw = pick_icon(raw)
            raw.load()
            return raw.copy()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise ImageError(f"Не удалось прочитать изображение: {exc}") from exc


class ImageProcessor:
    """Stores copies of user images inside the application data directory."""

    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    # -- importing -------------------------------------------------------
    def import_image(self, source: str | Path) -> str:
        """Copy ``source`` into the storage and return its relative path."""
        src = Path(source)
        if not src.is_file():
            raise ImageError("Файл изображения не найден")
        try:
            if src.stat().st_size > MAX_FILE_SIZE:
                raise ImageError("Файл изображения слишком большой")
        except OSError as exc:
            raise ImageError(f"Нет доступа к файлу изображения: {exc}") from exc

        image = _open_image(src)
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:  # noqa: BLE001 - EXIF issues must not block import
            logger.debug("EXIF orientation could not be applied for %s", src)

        return self._store(image)

    def import_bytes(self, data: bytes) -> str:
        """Store raw image bytes (a downloaded icon) and return its path."""
        if not data:
            raise ImageError("Пустое изображение")
        if len(data) > MAX_FILE_SIZE:
            raise ImageError("Изображение слишком большое")
        try:
            with Image.open(io.BytesIO(data)) as raw:
                raw = pick_icon(raw)
                raw.load()
                image = raw.copy()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
            raise ImageError("Полученный файл не является изображением") from exc
        try:
            image = ImageOps.exif_transpose(image)
        except Exception:  # noqa: BLE001 - EXIF issues must not block import
            logger.debug("EXIF orientation could not be applied to downloaded icon")
        return self._store(image)

    def _store(self, image: Image.Image) -> str:
        """Normalise, save and thumbnail an in-memory image."""
        has_alpha = image.mode in ("RGBA", "LA") or (
            image.mode == "P" and "transparency" in image.info
        )
        image = self._normalize(image, has_alpha)
        relative = f"entries/{uuid.uuid4().hex}.png"
        target = self.paths.image_file(relative)
        target.parent.mkdir(parents=True, exist_ok=True)

        tmp = target.with_suffix(".png.tmp")
        try:
            image.save(tmp, format="PNG", optimize=True)
            tmp.replace(target)
        except (OSError, ValueError) as exc:
            try:
                if tmp.exists():
                    tmp.unlink()
            except OSError:
                pass
            raise ImageError(f"Не удалось сохранить изображение: {exc}") from exc
        finally:
            image.close()

        try:
            self._write_thumbnail(target, relative)
        except (OSError, ValueError) as exc:
            logger.warning("Thumbnail creation failed for %s: %s", relative, exc)
        return relative

    @staticmethod
    def _normalize(image: Image.Image, has_alpha: bool) -> Image.Image:
        if image.mode not in ("RGB", "RGBA"):
            image = image.convert("RGBA" if has_alpha else "RGB")
        width, height = image.size
        if width <= 0 or height <= 0:
            raise ImageError("Некорректные размеры изображения")
        largest = max(width, height)
        if largest > MAX_SOURCE_DIMENSION:
            ratio = MAX_SOURCE_DIMENSION / float(largest)
            new_size = (max(1, int(width * ratio)), max(1, int(height * ratio)))
            image = image.resize(new_size, Image.Resampling.LANCZOS)
        return image

    def _write_thumbnail(self, source: Path, relative: str) -> None:
        target = self.paths.thumbnail_file(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as image:
            image = image.convert("RGBA")
            thumb = ImageOps.contain(image, THUMBNAIL_SIZE, Image.Resampling.LANCZOS)
            canvas = Image.new("RGBA", THUMBNAIL_SIZE, (0, 0, 0, 0))
            offset = (
                (THUMBNAIL_SIZE[0] - thumb.width) // 2,
                (THUMBNAIL_SIZE[1] - thumb.height) // 2,
            )
            canvas.paste(thumb, offset, thumb)
            canvas.save(target, format="PNG", optimize=True)
            canvas.close()

    # -- access ----------------------------------------------------------
    def resolve(self, relative: str | None, *, thumbnail: bool = False) -> Path | None:
        """Return an existing absolute path for ``relative`` or ``None``."""
        if not relative:
            return None
        try:
            path = (
                self.paths.thumbnail_file(relative)
                if thumbnail
                else self.paths.image_file(relative)
            )
        except ValueError as exc:
            logger.warning("Rejected image path %r: %s", relative, exc)
            return None
        return path if path.is_file() else None

    def load_bytes(self, relative: str | None, *, thumbnail: bool = True) -> bytes | None:
        """Image bytes for the UI.

        Falls back to the full-size file, and finally regenerates the
        thumbnail when it is missing.
        """
        path = self.resolve(relative, thumbnail=thumbnail)
        if path is None and thumbnail:
            path = self.resolve(relative, thumbnail=False)
            if path is not None:
                try:
                    self._write_thumbnail(path, relative or "")
                    path = self.resolve(relative, thumbnail=True) or path
                except (OSError, ValueError) as exc:
                    logger.warning("Cannot rebuild thumbnail: %s", exc)
        if path is None:
            return None
        try:
            return path.read_bytes()
        except OSError as exc:
            logger.error("Cannot read image %s: %s", path, exc)
            return None

    # -- deletion --------------------------------------------------------
    def delete(self, relative: str | None) -> None:
        """Delete stored image and its thumbnail (if present)."""
        if not relative:
            return
        for path in (
            self.resolve(relative, thumbnail=False),
            self.resolve(relative, thumbnail=True),
        ):
            if path is None:
                continue
            try:
                path.unlink()
            except OSError as exc:
                logger.warning("Cannot delete image %s: %s", path, exc)

    def to_pixmap_bytes(self, relative: str | None, size: int | None = None) -> bytes | None:
        """Return PNG bytes scaled to ``size`` (used for previews)."""
        data = self.load_bytes(relative, thumbnail=False)
        if data is None:
            return None
        if size is None:
            return data
        try:
            with Image.open(io.BytesIO(data)) as image:
                image = image.convert("RGBA")
                image.thumbnail((size, size), Image.Resampling.LANCZOS)
                buffer = io.BytesIO()
                image.save(buffer, format="PNG")
                return buffer.getvalue()
        except (OSError, ValueError) as exc:
            logger.warning("Cannot scale image %s: %s", relative, exc)
            return data
