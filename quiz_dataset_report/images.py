"""Fetch report images and rewrite the HTML to embed them inline (cid:).

Email clients routinely block remote images, and the quiz images live on an
internal, self-signed host. Embedding them as ``multipart/related`` parts makes
them render in the email itself. The on-disk HTML keeps its real URLs; only the
emailed copy is rewritten.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from io import BytesIO
from typing import Callable

import httpx

logger = logging.getLogger(__name__)

# A fetch returns (content_type, data) or None to skip the image.
Fetch = Callable[[str], "tuple[str, bytes] | None"]

_IMG_SRC_RE = re.compile(r'<img[^>]*\bsrc="(?P<url>https?://[^"]+)"')


@dataclass(frozen=True)
class InlineImage:
    cid: str
    maintype: str
    subtype: str
    data: bytes


def embed_images(html: str, fetch: Fetch) -> tuple[str, list[InlineImage]]:
    """Replace remote <img> srcs with cid: references; return (html, images).

    ``fetch`` is injected so this stays unit-testable without network access.
    Images that fail to fetch keep their original URL.
    """
    seen: dict[str, None] = {}
    for m in _IMG_SRC_RE.finditer(html):
        seen.setdefault(m.group("url"), None)

    images: list[InlineImage] = []
    for i, url in enumerate(seen):
        result = fetch(url)
        if result is None:
            logger.warning("Could not embed image, leaving URL: %s", url)
            continue
        content_type, data = result
        maintype, _, subtype = content_type.partition("/")
        cid = f"img{i}@quiz-dataset-report"
        images.append(
            InlineImage(
                cid=cid,
                maintype=maintype or "image",
                subtype=subtype or "png",
                data=data,
            )
        )
        html = html.replace(url, f"cid:{cid}")

    logger.info("Embedded %d/%d images inline", len(images), len(seen))
    return html, images


def downscale(
    data: bytes, *, max_width: int, jpeg_quality: int
) -> "tuple[str, bytes] | None":
    """Resize (if wider than max_width) and re-encode to shrink the image.

    Opaque images are re-encoded as JPEG; images with transparency stay PNG.
    Returns (content_type, data), or None if the image can't be processed (the
    caller then keeps the original bytes).
    """
    from PIL import Image  # imported lazily so the rest works without Pillow

    try:
        img = Image.open(BytesIO(data))
        img.load()
    except Exception as exc:  # noqa: BLE001 - any decode failure -> keep original
        logger.warning("Could not decode image for downscaling: %s", exc)
        return None

    has_alpha = img.mode in ("RGBA", "LA") or (
        img.mode == "P" and "transparency" in img.info
    )

    if max_width and img.width > max_width:
        height = round(img.height * max_width / img.width)
        img = img.resize((max_width, height), Image.LANCZOS)

    out = BytesIO()
    if has_alpha:
        img.save(out, format="PNG", optimize=True)
        return "image/png", out.getvalue()
    img.convert("RGB").save(out, format="JPEG", quality=jpeg_quality, optimize=True)
    return "image/jpeg", out.getvalue()


def _make_http_fetch(
    verify_tls: bool, timeout: float, max_width: int, jpeg_quality: int
) -> Fetch:
    client = httpx.Client(verify=verify_tls, timeout=timeout)

    def fetch(url: str) -> "tuple[str, bytes] | None":
        try:
            resp = client.get(url)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            logger.warning("Failed to fetch image %s: %s", url, exc)
            return None
        content_type = (resp.headers.get("content-type") or "").split(";")[0].strip()
        if not content_type.startswith("image/"):
            logger.warning("Skipping non-image %s (%s)", url, content_type or "?")
            return None

        original = (content_type, resp.content)
        if max_width <= 0:
            return original
        reduced = downscale(
            resp.content, max_width=max_width, jpeg_quality=jpeg_quality
        )
        # Keep whichever is smaller; fall back to the original on failure.
        if reduced and len(reduced[1]) < len(resp.content):
            return reduced
        return original

    return fetch


def download_and_embed(
    html: str, *, verify_tls: bool, timeout: float, max_width: int, jpeg_quality: int
) -> tuple[str, list[InlineImage]]:
    """Convenience wrapper that downloads, downscales, and embeds images."""
    return embed_images(
        html, _make_http_fetch(verify_tls, timeout, max_width, jpeg_quality)
    )
