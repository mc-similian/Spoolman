"""Auto-print labels when spools are created."""

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from spoolman.api.v1.models import Spool
from spoolman.database import setting as setting_db
from spoolman.exceptions import ItemNotFoundError
from spoolman.label_renderer import render_label
from spoolman.printing import check_printer_available, print_image
from spoolman.settings import parse_setting

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE = """**{filament.vendor.name} - {filament.name}
#{id} - {filament.material}**
Spool Weight: {filament.spool_weight} g
{ET: {filament.settings_extruder_temp} °C}
{BT: {filament.settings_bed_temp} °C}
{Lot Nr: {lot_nr}}
{{comment}}
{filament.comment}
{filament.vendor.comment}"""


async def _get_setting_value(db: AsyncSession, key: str) -> str:
    """Get a setting value, returning the default if not set."""
    definition = parse_setting(key)
    try:
        setting = await setting_db.get(db, definition)
    except ItemNotFoundError:
        return definition.default
    return setting.value


async def auto_print_spool_label(db: AsyncSession, spool_db_item) -> None:  # noqa: ANN001
    """Check auto-print settings and print a label if enabled.

    This is called after a spool is created. It reads the auto-print settings
    from the database and, if enabled, renders a label and sends it to CUPS.

    Args:
        db: Database session.
        spool_db_item: The database spool model object (with filament/vendor loaded).

    """
    try:
        # Check if auto-print is enabled
        enabled = json.loads(await _get_setting_value(db, "auto_print_enabled"))
        if not enabled:
            return

        # Check if print mode is "host"
        print_mode = json.loads(await _get_setting_value(db, "print_mode"))
        if print_mode != "host":
            logger.debug("Auto-print skipped: print mode is '%s', not 'host'.", print_mode)
            return

        # Check if CUPS is available
        if not check_printer_available():
            logger.warning("Auto-print skipped: no printer available.")
            return

        # Get auto-print settings
        preset_id = json.loads(await _get_setting_value(db, "auto_print_preset_id"))
        if not preset_id:
            logger.debug("Auto-print skipped: no preset selected.")
            return

        copies = int(json.loads(await _get_setting_value(db, "auto_print_copies")))
        printer_name = json.loads(await _get_setting_value(db, "host_printer_name"))
        printer_options = json.loads(await _get_setting_value(db, "host_printer_options"))
        base_url = json.loads(await _get_setting_value(db, "base_url"))

        # Get print presets and find the selected one
        presets_json = json.loads(await _get_setting_value(db, "print_presets"))
        preset = None
        for p in presets_json:
            pid = p.get("labelSettings", {}).get("printSettings", {}).get("id")
            if pid == preset_id:
                preset = p
                break

        if preset is None:
            logger.warning("Auto-print skipped: preset '%s' not found.", preset_id)
            return

        # Extract preset parameters
        template = preset.get("template", DEFAULT_TEMPLATE)
        # If useHTTPUrl is not in preset (legacy), default to True when base_url is configured
        use_http_url = preset.get("useHTTPUrl", bool(base_url))
        label_settings = preset.get("labelSettings", {})
        show_qr_code = label_settings.get("showQRCodeMode", "withIcon")
        text_size_mm = label_settings.get("textSize", 3.0)

        show_content = label_settings.get("showContent", True)

        print_settings = label_settings.get("printSettings", {})

        # Defaults must match the frontend (printingDialog.tsx lines 82-90)
        paper_size = print_settings.get("paperSize", "A4")
        custom_paper_size = print_settings.get("customPaperSize", {"width": 210, "height": 297})

        paper_dimensions = {
            "A3": (297, 420),
            "A4": (210, 297),
            "A5": (148, 210),
            "Letter": (216, 279),
            "Legal": (216, 356),
            "Tabloid": (279, 432),
        }

        if paper_size == "custom":
            paper_width = custom_paper_size.get("width", 210)
            paper_height = custom_paper_size.get("height", 297)
        elif paper_size in paper_dimensions:
            paper_width, paper_height = paper_dimensions[paper_size]
        else:
            paper_width = custom_paper_size.get("width", 210)
            paper_height = custom_paper_size.get("height", 297)

        margin = print_settings.get("margin", {"top": 10, "bottom": 10, "left": 10, "right": 10})
        printer_margin = print_settings.get("printerMargin", {"top": 5, "bottom": 5, "left": 5, "right": 5})
        spacing = print_settings.get("spacing", {"horizontal": 0, "vertical": 0})
        columns = print_settings.get("columns", 3)
        rows = print_settings.get("rows", 8)

        # Calculate item dimensions exactly like the frontend (printingDialog.tsx):
        # itemWidth = (paperWidth - margin.left - margin.right - spacing.horizontal) / columns - spacing.horizontal
        # itemHeight = (paperHeight - margin.top - margin.bottom - spacing.vertical) / rows - spacing.vertical
        spacing_h = spacing.get("horizontal", 0)
        spacing_v = spacing.get("vertical", 0)
        margin_top = margin.get("top", 10)
        margin_bottom = margin.get("bottom", 10)
        margin_left = margin.get("left", 10)
        margin_right = margin.get("right", 10)

        item_width = (paper_width - margin_left - margin_right - spacing_h) / columns - spacing_h
        item_height = (paper_height - margin_top - margin_bottom - spacing_v) / rows - spacing_v

        # Subtract printerMargin padding (matches printingDialog.tsx for first row/column items):
        # paddingLeft = Math.max(printerMargin.left - margin.left, 0)
        # paddingTop = Math.max(printerMargin.top - margin.top, 0)
        # etc.
        pm_left = max(printer_margin.get("left", 5) - margin_left, 0)
        pm_right = max(printer_margin.get("right", 5) - margin_right, 0)
        pm_top = max(printer_margin.get("top", 5) - margin_top, 0)
        pm_bottom = max(printer_margin.get("bottom", 5) - margin_bottom, 0)

        # Convert DB model to pydantic model for template rendering
        spool_pydantic = Spool.from_db(spool_db_item)

        # Render the label at item dimensions (no outer margins, matching UI capture)
        image_data = await asyncio.to_thread(
            render_label,
            spool_pydantic=spool_pydantic,
            template=template if show_content else "",
            show_qr_code=show_qr_code,
            text_size_mm=text_size_mm,
            item_width_mm=item_width,
            item_height_mm=item_height,
            base_url=base_url,
            use_http_url=use_http_url,
            padding_top=pm_top,
            padding_bottom=pm_bottom,
            padding_left=pm_left,
            padding_right=pm_right,
        )

        # Print the label (subprocess call, run in thread to avoid blocking event loop)
        job_id = await asyncio.to_thread(
            print_image,
            image_data=image_data,
            printer_name=printer_name or None,
            copies=copies,
            options=printer_options or None,
        )

        logger.info(
            "Auto-print: label for spool #%d sent to printer (job %s, %d copies).",
            spool_pydantic.id,
            job_id,
            copies,
        )

    except Exception:
        # Never let auto-print failures break spool creation
        logger.exception("Auto-print failed for spool.")
