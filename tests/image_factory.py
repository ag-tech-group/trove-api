"""Real image bytes for tests: uploads are decoded now, so placeholder bytes are rejected."""

from io import BytesIO

from PIL import Image


def make_image(
    fmt: str = "JPEG",
    size: tuple[int, int] = (64, 48),
    mode: str = "RGB",
    color: float | tuple[int, ...] = 0,
    **save_args,
) -> bytes:
    buffer = BytesIO()
    Image.new(mode, size, color).save(buffer, fmt, **save_args)
    return buffer.getvalue()
