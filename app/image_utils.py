import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePath

from fastapi import HTTPException, UploadFile, status
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
MAX_ITEM_IMAGES = 10
MAX_MARK_IMAGES = 3

# Every upload is stored as WebP with its long edge capped here: sharp enough for
# detail shots, and a fraction of a phone original's size.
MAX_DIMENSION = 2048
WEBP_QUALITY = 85

# Checked against the header before any pixel data is decoded, since a few KB of
# PNG can declare an image that fills memory. Admits 48 MP phone photos.
MAX_PIXELS = 50_000_000
_TOO_MANY_PIXELS = f"Image dimensions too large. Maximum is {MAX_PIXELS // 1_000_000} megapixels"

# Pillow can parse dozens of formats; untrusted bytes only ever reach these three.
_DECODERS = ("JPEG", "PNG", "WEBP")

# The service has one vCPU, so parallel decodes gain nothing and each holds a full
# image in memory. Its own pool also keeps queued images off the default executor
# that storage calls run on.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="image")


@dataclass(frozen=True)
class ProcessedImage:
    """An upload after re-encoding: what gets stored, not what was sent."""

    data: bytes
    width: int
    height: int
    content_type: str = "image/webp"
    extension: str = ".webp"


class _RejectedImage(ValueError):
    pass


async def validate_image_file(file: UploadFile) -> bytes:
    """Validate an uploaded image file and return its contents.

    Raises HTTPException if the file is invalid.
    """
    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '{file.content_type}' not allowed. Allowed types: JPEG, PNG, WebP",
        )

    data = await file.read()

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size is {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    if len(data) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File is empty",
        )

    return data


async def process_image(data: bytes) -> ProcessedImage:
    """Decode, orient, downscale and re-encode an image as WebP, dropping its metadata.

    Raises HTTPException if the bytes are not a JPEG, PNG or WebP image we can decode.
    """
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_executor, _process, data)
    except _RejectedImage as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def stored_filename(original: str | None, processed: ProcessedImage) -> str:
    """The uploaded name with the stored format's extension: IMG_1.jpg -> IMG_1.webp."""
    stem = PurePath(original).stem if original else "image"
    return f"{stem[: 255 - len(processed.extension)]}{processed.extension}"


def _process(data: bytes) -> ProcessedImage:
    try:
        with Image.open(BytesIO(data), formats=_DECODERS) as source:
            if source.width * source.height > MAX_PIXELS:
                raise _RejectedImage(_TOO_MANY_PIXELS)
            icc_profile = source.info.get("icc_profile")
            if source.format == "JPEG" and max(source.size) > MAX_DIMENSION:
                # Decode at the smallest DCT scale that still covers the target,
                # rather than at full resolution only to throw most of it away.
                source.draft("RGB", _fit(source.size))
            # Applies the EXIF rotation before the EXIF (GPS included) is dropped;
            # otherwise phone photos would be stored sideways.
            image = _to_rgb(ImageOps.exif_transpose(source))
    except UnidentifiedImageError as exc:
        raise _RejectedImage("Not a valid JPEG, PNG or WebP image") from exc
    except Image.DecompressionBombError as exc:
        raise _RejectedImage(_TOO_MANY_PIXELS) from exc
    except (OSError, SyntaxError) as exc:
        raise _RejectedImage("Image data is corrupt or could not be decoded") from exc

    image.thumbnail((MAX_DIMENSION, MAX_DIMENSION), Image.Resampling.LANCZOS)
    out = BytesIO()
    # The ICC profile is kept: phones shoot in wide-gamut color, which renders
    # dull without it.
    image.save(out, "WEBP", quality=WEBP_QUALITY, icc_profile=icc_profile)
    return ProcessedImage(data=out.getvalue(), width=image.width, height=image.height)


def _fit(size: tuple[int, int]) -> tuple[int, int]:
    width, height = size
    scale = MAX_DIMENSION / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def _to_rgb(image: Image.Image) -> Image.Image:
    if image.mode in ("I", "I;16", "I;16B", "I;16L", "I;16N"):
        # 16-bit greyscale scans: a plain convert() clips every value above 255 to white.
        image = image.convert("I").point(lambda value: value * (1 / 256)).convert("L")
    return image.convert("RGBA" if image.has_transparency_data else "RGB")
