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
        # Roboto matches the browser's CSS font-family stack
        "/usr/share/fonts/truetype/roboto/unhinted/RobotoTTF/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/roboto/hinted/RobotoTTF/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/roboto/Roboto-Regular.ttf",
        # Fallbacks
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/TTF/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:  # noqa: PERF203
            continue
    logger.warning("No TrueType font found, using default bitmap font.")
    return ImageFont.load_default()


def _render_qr(img: Image.Image, spool_pydantic, base_url: str, content_x: int, content_y: int, content_w: int, content_h: int, *, use_http_url: bool = False) -> int:  # noqa: ANN001, E501
    """Render QR code onto the image matching the CSS layout.

    CSS layout replicated:
    - .print-qrcode-container: max-width: 50%; display: flex
    - .print-qrcode: padding: 2mm; object-fit: contain; width/height: 100%

    The QR code gets 2mm padding on all sides. The container is at most 50% of
    the content width. The QR is square and fits within the padded area.

    Returns the total width consumed by the QR container (QR + padding).
    """
    spool_id = spool_pydantic.id
    if use_http_url and base_url:
        qr_value = f"{base_url}/spool/show/{spool_id}"
    else:
        qr_value = f"WEB+SPOOLMAN:S-{spool_id}"

    qr_padding = mm_to_px(2)
    max_container_w = content_w // 2

    # Available space for QR inside padding
    available_w = max_container_w - 2 * qr_padding
    available_h = content_h - 2 * qr_padding

    # QR is square, constrained by the smaller dimension
    qr_size = min(available_w, available_h)
    if qr_size <= 0:
        return 0

    qr_img = _generate_qr_code(qr_value, qr_size)

    # Center QR vertically (matching CSS: object-fit: contain centers within full-height container)
    qr_y = content_y + (content_h - qr_size) // 2
    img.paste(qr_img, (content_x + qr_padding, qr_y))

    # Container width shrinks to fit: QR + 2*padding
    container_w = qr_size + 2 * qr_padding
    return container_w


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text_w: int) -> list[str]:  # noqa: E501
    """Word-wrap text to fit within the given width."""
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
    return wrapped_lines


def _calc_text_block_height(draw: ImageDraw.ImageDraw, wrapped_lines: list[str], font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text_size_px: int, line_spacing: int) -> int:  # noqa: E501
    """Calculate the total height of a wrapped text block."""
    total = 0
    for i, line in enumerate(wrapped_lines):
        if line:
            bbox = draw.textbbox((0, 0), line, font=font)
            total += bbox[3] - bbox[1]
        else:
            total += text_size_px
        if i < len(wrapped_lines) - 1:
            total += line_spacing
    return total


def _draw_wrapped_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont | ImageFont.ImageFont, text_x: int, text_y: int, text_w: int, text_h: int, text_size_px: int) -> None:  # noqa: E501
    """Draw word-wrapped, vertically centered text onto the image."""
    line_spacing = mm_to_px(0.5)
    wrapped_lines = _wrap_text(draw, text, font, text_w)

    # Calculate total text block height and center vertically
    block_h = _calc_text_block_height(draw, wrapped_lines, font, text_size_px, line_spacing)
    y = text_y + max(0, (text_h - block_h) // 2)

    max_y = text_y + text_h
    for i, wrapped_line in enumerate(wrapped_lines):
        if y >= max_y:
            break
        draw.text((text_x, y), wrapped_line, fill="black", font=font)
        if wrapped_line:
            bbox = draw.textbbox((0, 0), wrapped_line, font=font)
            line_h = bbox[3] - bbox[1]
        else:
            line_h = text_size_px
        y += line_h + line_spacing


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
    padding_top: float = 0,
    padding_bottom: float = 0,
    padding_left: float = 0,
    padding_right: float = 0,
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
        padding_top: Printer margin padding in mm (from printerMargin - margin).
        padding_bottom: Printer margin padding in mm.
        padding_left: Printer margin padding in mm.
        padding_right: Printer margin padding in mm.

    Returns:
        PNG image data as bytes.

    """
    width_px = mm_to_px(item_width_mm)
    height_px = mm_to_px(item_height_mm)
    text_size_px = max(mm_to_px(text_size_mm), 8)

    # Printer margin padding (matches printingDialog.tsx .print-page-item padding)
    pad_top = mm_to_px(padding_top)
    pad_bottom = mm_to_px(padding_bottom)
    pad_left = mm_to_px(padding_left)
    pad_right = mm_to_px(padding_right)

    # Content area after printer margin padding
    content_x = pad_left
    content_y = pad_top
    content_w = width_px - pad_left - pad_right
    content_h = height_px - pad_top - pad_bottom

    logger.info(
        "render_label: item=%.1fx%.1fmm (%dx%dpx), text_size=%.1fmm (%dpx), "
        "padding=%.1f/%.1f/%.1f/%.1f, content=%dx%dpx, qr=%s",
        item_width_mm, item_height_mm, width_px, height_px,
        text_size_mm, text_size_px,
        padding_top, padding_right, padding_bottom, padding_left,
        content_w, content_h, show_qr_code,
    )

    img = Image.new("RGB", (width_px, height_px), "white")
    draw = ImageDraw.Draw(img)

    spool_data = _spool_to_template_data(spool_pydantic)
    label_text = _substitute_template(template, spool_data)

    # QR code section (matches CSS: .print-qrcode-container + .print-qrcode)
    qr_container_w = 0
    if show_qr_code != "no":
        qr_container_w = _render_qr(
            img, spool_pydantic, base_url, content_x, content_y, content_w, content_h,
            use_http_url=use_http_url,
        )

    # Text section (matches CSS: .print-qrcode-title p { padding: 1mm 1mm 1mm 0 })
    if label_text.strip():
        text_pad_top = mm_to_px(1)
        text_pad_right = mm_to_px(1)
        text_pad_bottom = mm_to_px(1)
        text_pad_left = 0  # CSS: padding-left: 0

        text_x = content_x + qr_container_w + text_pad_left
        text_y = content_y + text_pad_top
        text_w = content_w - qr_container_w - text_pad_left - text_pad_right
        text_h = content_h - text_pad_top - text_pad_bottom

        font = _try_load_font(text_size_px)
        _draw_wrapped_text(
            draw, label_text, font,
            text_x, text_y, text_w, text_h, text_size_px,
        )

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(RENDER_DPI, RENDER_DPI))
    return buf.getvalue()
