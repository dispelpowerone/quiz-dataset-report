from io import BytesIO

from PIL import Image

from quiz_dataset_report.images import downscale


def _png(width: int, height: int, mode: str) -> bytes:
    img = Image.new(mode, (width, height), color=(10, 20, 30, 255)[: len(mode)])
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_opaque_image_becomes_smaller_jpeg():
    data = _png(1200, 800, "RGB")
    ct, out = downscale(data, max_width=600, jpeg_quality=80)
    assert ct == "image/jpeg"
    assert len(out) < len(data)
    assert Image.open(BytesIO(out)).width == 600


def test_transparent_image_stays_png():
    data = _png(1200, 800, "RGBA")
    ct, out = downscale(data, max_width=600, jpeg_quality=80)
    assert ct == "image/png"
    assert Image.open(BytesIO(out)).width == 600


def test_no_upscale_when_already_small():
    data = _png(400, 300, "RGB")
    ct, out = downscale(data, max_width=600, jpeg_quality=80)
    assert Image.open(BytesIO(out)).width == 400  # unchanged dimensions


def test_returns_none_on_garbage():
    assert downscale(b"not an image", max_width=600, jpeg_quality=80) is None
