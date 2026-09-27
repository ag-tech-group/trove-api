from io import BytesIO

import pytest
from fastapi import HTTPException
from PIL import ExifTags, Image, ImageCms

from app.image_utils import MAX_DIMENSION, ProcessedImage, process_image, stored_filename
from tests.image_factory import make_image


def _open(processed: ProcessedImage) -> Image.Image:
    return Image.open(BytesIO(processed.data))


async def test_stores_webp_and_describes_what_it_stored():
    processed = await process_image(make_image("PNG", size=(120, 80)))

    stored = _open(processed)
    assert stored.format == "WEBP"
    assert (processed.content_type, processed.extension) == ("image/webp", ".webp")
    assert (processed.width, processed.height) == stored.size == (120, 80)


async def test_caps_the_long_edge_and_keeps_the_aspect_ratio():
    processed = await process_image(make_image(size=(4000, 3000)))

    assert (processed.width, processed.height) == (MAX_DIMENSION, 1536)


async def test_never_upscales():
    processed = await process_image(make_image(size=(300, 200)))

    assert (processed.width, processed.height) == (300, 200)


async def test_applies_the_exif_orientation_then_drops_the_exif():
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = 6  # displayed rotated 90° clockwise
    exif[ExifTags.Base.Make] = "TestCam"

    stored = _open(await process_image(make_image(size=(60, 40), exif=exif.tobytes())))

    assert stored.size == (40, 60)
    assert "exif" not in stored.info
    assert not stored.getexif()


async def test_keeps_the_color_profile():
    icc = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()

    stored = _open(await process_image(make_image(icc_profile=icc)))

    assert stored.info.get("icc_profile") == icc


async def test_keeps_transparency():
    data = make_image("PNG", mode="RGBA", color=(255, 0, 0, 0))

    assert _open(await process_image(data)).mode == "RGBA"


async def test_scales_16_bit_greyscale_instead_of_clipping_it_to_white():
    stored = _open(await process_image(make_image("PNG", mode="I;16", color=32768)))

    assert stored.convert("L").getpixel((0, 0)) == pytest.approx(128, abs=2)


@pytest.mark.parametrize(
    "data",
    [b"not an image", make_image("GIF"), make_image("BMP")],
    ids=["garbage", "gif", "bmp"],
)
async def test_rejects_anything_but_jpeg_png_and_webp(data):
    with pytest.raises(HTTPException) as exc:
        await process_image(data)

    assert exc.value.status_code == 400
    assert "Not a valid" in exc.value.detail


async def test_rejects_truncated_images():
    data = make_image(size=(400, 300))

    with pytest.raises(HTTPException) as exc:
        await process_image(data[: len(data) // 2])

    assert exc.value.status_code == 400


async def test_rejects_pixel_bombs_before_decoding_them():
    # About 7 KB of PNG that declares 56 megapixels.
    bomb = make_image("PNG", size=(8000, 7000), mode="1")

    with pytest.raises(HTTPException) as exc:
        await process_image(bomb)

    assert exc.value.status_code == 400
    assert "too large" in exc.value.detail


def test_stored_filename_takes_the_stored_extension():
    processed = ProcessedImage(data=b"", width=1, height=1)

    assert stored_filename("IMG_0001.JPG", processed) == "IMG_0001.webp"
    assert stored_filename(None, processed) == "image.webp"
    assert stored_filename("x" * 300 + ".png", processed) == "x" * 250 + ".webp"
