"""Server-side label rendering using Pillow and qrcode.

Replicates the CSS layout from the frontend's qrCodePrintingDialog.tsx:
- .print-qrcode-item:     display: flex; width: 100%; height: 100%
- .print-qrcode-container: max-width: 50%; display: flex
- .print-qrcode (SVG):     padding: 2mm; object-fit: contain; width/height: 100%
- .print-qrcode-title:     flex: 1 1 auto; font-size: Xmm
- .print-qrcode-title p:   padding: 1mm 1mm 1mm 0; margin: 0; white-space: pre-wrap
"""

import io
import logging
import re

import qrcode
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# DPI for rendering: 203 DPI is standard for thermal label printers
RENDER_DPI = 203

# Pixels per mm at render DPI
PX_PER_MM = RENDER_DPI / 25.4


def mm_to_px(mm: float) -> int:
    """Convert millimeters to pixels at render DPI."""
    return round(mm * PX_PER_MM)


def _substitute_template(template: str, spool_data: dict) -> str:  # noqa: C901
    """Apply the same template substitution logic as the frontend.

    Supports:
    - {tag} — simple substitution
    - {prefix {tag} suffix} — conditional wrapping (hidden if tag value is missing)
    - **bold** markers are stripped (no bold in Pillow simple rendering)
    """

    def _get_tag_value(tag: str, obj: dict) -> str | None:
        parts = tag.split(".")
        current = obj
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
            if current is None:
                return None
        # Treat boolean False and empty strings as missing values
        if current is False or current == "":
            return None
        return str(current)

    # First handle conditional tags: {prefix {tag} suffix}
    def replace_conditional(match: re.Match) -> str:
        full = match.group(0)
        inner = re.match(r"\{(.*?)\{(.*?)\}(.*?)\}", full, re.DOTALL)
        if inner:
            prefix = inner.group(1)
            tag = inner.group(2)
            suffix = inner.group(3)
            value = _get_tag_value(tag, spool_data)
            if value is None or value in {"?", "None"}:
                return ""
            return prefix + value + suffix
        return full

    # Handle double-brace conditionals
    result = re.sub(r"\{[^}{]*\{[^}{]*\}[^}{]*\}", replace_conditional, template)

    # Then handle simple tags: {tag}
    def replace_simple(match: re.Match) -> str:
        tag = match.group(1)
        value = _get_tag_value(tag, spool_data)
        if value is None:
            return "?"
        return str(value)

    return re.sub(r"\{([^{}]+)\}", replace_simple, result).replace("**", "")


def _spool_to_template_data(spool_pydantic) -> dict:  # noqa: ANN001
    """Convert a Spool pydantic model to a flat dict for template substitution."""
    data: dict = {
        "id": spool_pydantic.id,
        "registered": str(spool_pydantic.registered) if spool_pydantic.registered else None,
        "first_used": str(spool_pydantic.first_used) if spool_pydantic.first_used else None,
        "last_used": str(spool_pydantic.last_used) if spool_pydantic.last_used else None,
        "price": spool_pydantic.price,
        "initial_weight": spool_pydantic.initial_weight,
        "spool_weight": spool_pydantic.spool_weight,
        "remaining_weight": spool_pydantic.remaining_weight,
        "used_weight": spool_pydantic.used_weight,
        "remaining_length": spool_pydantic.remaining_length,
        "used_length": spool_pydantic.used_length,
        "location": spool_pydantic.location,
        "lot_nr": spool_pydantic.lot_nr,
        "comment": spool_pydantic.comment,
        "archived": spool_pydantic.archived,
        "extra": dict(spool_pydantic.extra) if spool_pydantic.extra else {},
    }

    # Filament fields
    filament_data: dict = {}
    if spool_pydantic.filament:
        f = spool_pydantic.filament
        filament_data = {
            "id": f.id,
            "registered": str(f.registered) if f.registered else None,
            "name": f.name,
            "material": f.material,
            "price": f.price,
            "density": f.density,
            "diameter": f.diameter,
            "weight": f.weight,
            "spool_weight": f.spool_weight,
            "article_number": f.article_number,
            "comment": f.comment,
            "settings_extruder_temp": f.settings_extruder_temp,
            "settings_bed_temp": f.settings_bed_temp,
            "color_hex": f.color_hex,
            "multi_color_hexes": f.multi_color_hexes,
            "external_id": f.external_id,
            "extra": dict(f.extra) if f.extra else {},
        }

        # Vendor fields
        vendor_data: dict = {}
        if f.vendor:
            v = f.vendor
            vendor_data = {
                "id": v.id,
                "registered": str(v.registered) if v.registered else None,
                "name": v.name,
                "comment": v.comment,
                "empty_spool_weight": v.empty_spool_weight,
                "external_id": v.external_id,
                "extra": dict(v.extra) if v.extra else {},
            }
        filament_data["vendor"] = vendor_data

    data["filament"] = filament_data
    return data


def _generate_qr_code(value: str, size_px: int) -> Image.Image:
    """Generate a QR code image."""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=1,
    )
    qr.add_data(value)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
    return img.resize((size_px, size_px), Image.LANCZOS)


def _try_load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Try to load a system font, fall back to default."""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:  # noqa: PERF203
            continue
    logger.warning("No TrueType font found, using default bitmap font.")
    return ImageFont.load_default()


def _render_qr(img: Image.Image, spool_pydantic, base_url: str, width_px: int, height_px: int, *, use_http_url: bool = False) -> int:  # noqa: ANN001, E501
    """Render QR code onto the image matching the CSS layout.

    CSS layout replicated:
    - .print-qrcode-container: max-width: 50%; display: flex
    - .print-qrcode: padding: 2mm; object-fit: contain; width/height: 100%

    The QR code gets 2mm padding on all sides. The container is at most 50% of
    the total width. The QR is square and fits within the padded area.

    Returns the total width consumed by the QR container (QR + padding).
    """
    spool_id = spool_pydantic.id
    if use_http_url and base_url:
        qr_value = f"{base_url}/spool/show/{spool_id}"
    else:
        qr_value = f"WEB+SPOOLMAN:S-{spool_id}"

    qr_padding = mm_to_px(2)
    max_container_w = width_px // 2

    # Available space for QR inside padding
    available_w = max_container_w - 2 * qr_padding
    available_h = height_px - 2 * qr_padding

    # QR is square, constrained by the smaller dimension
    qr_size = min(available_w, available_h)
    if qr_size <= 0:
        return 0

    qr_img = _generate_qr_code(qr_value, qr_size)

    # Place QR at top-left with padding (matching CSS: aligned to top)
    img.paste(qr_img, (qr_padding, qr_padding))

    # Container width shrinks to fit: QR + 2*padding
    container_w = qr_size + 2 * qr_padding
    return container_w


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text_x: int, text_y: int, text_w: int, text_h: int, text_size_px: int) -> None:  # noqa: E501
    """Draw word-wrapped text onto the image."""
    lines = text.split("\n")
    wrapped_lines: list[str] = []
    for line in lines:
        if not line.strip():
            wrapped_lines.append("")
            continue
        words = line.split()
        current_line = ""
        for word in words:
            test_line = f"{current_line} {word}".strip() if current_line else word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            if bbox[2] - bbox[0] <= text_w:
                current_line = test_line
            else:
                if current_line:
                    wrapped_lines.append(current_line)
                current_line = word
        if current_line:
            wrapped_lines.append(current_line)

    y = text_y
    max_y = text_y + text_h
    for wrapped_line in wrapped_lines:
        if y >= max_y:
            break
        draw.text((text_x, y), wrapped_line, fill="black", font=font)
        if wrapped_line:
            bbox = draw.textbbox((0, 0), wrapped_line, font=font)
            line_h = bbox[3] - bbox[1]
        else:
            line_h = text_size_px
        y += line_h + mm_to_px(0.5)


def render_label(
    spool_pydantic,  # noqa: ANN001
    template: str,
    show_qr_code: str = "withIcon",
    text_size_mm: float = 3.0,
    item_width_mm: float = 58.0,
    item_height_mm: float = 25.0,
    base_url: str = "",
    *,
    use_http_url: bool = False,
    # Legacy parameters (ignored, kept for backwards compatibility)
    paper_width_mm: float = 62.0,  # noqa: ARG001
    paper_height_mm: float = 29.0,  # noqa: ARG001
    margin_mm: float = 2.0,  # noqa: ARG001
    margin_top_mm: float | None = None,  # noqa: ARG001
    margin_bottom_mm: float | None = None,  # noqa: ARG001
    margin_left_mm: float | None = None,  # noqa: ARG001
    margin_right_mm: float | None = None,  # noqa: ARG001
) -> bytes:
    """Render a label as a PNG image matching the frontend CSS layout.

    The image represents the content area of a single label item,
    exactly as captured by htmlToImage.toPng in the UI. No outer margins
    are included — those are handled by the page layout.

    Internal layout matches the CSS from qrCodePrintingDialog.tsx:
    - QR code: 2mm padding, container max 50% width, square QR
    - Text: padding 1mm top, 1mm right, 1mm bottom, 0 left

    Args:
        spool_pydantic: The Spool pydantic model object.
        template: Label template string with {tags}.
        show_qr_code: "no", "simple", or "withIcon".
        text_size_mm: Text size in mm.
        item_width_mm: Width of the label content area in mm.
        item_height_mm: Height of the label content area in mm.
        base_url: Base URL for QR codes.
        use_http_url: If True, use HTTP URL format; otherwise use WEB+SPOOLMAN protocol.

    Returns:
        PNG image data as bytes.

    """
    width_px = mm_to_px(item_width_mm)
    height_px = mm_to_px(item_height_mm)
    text_size_px = max(mm_to_px(text_size_mm), 8)

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    spool_data = _spool_to_template_data(spool_pydantic)
    label_text = _substitute_template(template, spool_data)

    # QR code section (matches CSS: .print-qrcode-container + .print-qrcode)
    qr_container_w = 0
    if show_qr_code != "no":
        qr_container_w = _render_qr(
            img, spool_pydantic, base_url, width_px, height_px,
            use_http_url=use_http_url,
        )

    # Text section (matches CSS: .print-qrcode-title p { padding: 1mm 1mm 1mm 0 })
    text_pad_top = mm_to_px(1)
    text_pad_right = mm_to_px(1)
    text_pad_bottom = mm_to_px(1)
    text_pad_left = 0  # CSS: padding-left: 0

    text_x = qr_container_w + text_pad_left
    text_y = text_pad_top
    text_w = width_px - qr_container_w - text_pad_left - text_pad_right
    text_h = height_px - text_pad_top - text_pad_bottom

    font = _try_load_font(text_size_px)
    _draw_wrapped_text(
        draw, label_text, font,
        text_x, text_y, text_w, text_h, text_size_px,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(RENDER_DPI, RENDER_DPI))
    return buf.getvalue()
