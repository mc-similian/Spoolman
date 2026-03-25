"""Auto-print labels when spools are created."""

import asyncio
import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from spoolman.api.v1.models import Spool
from spoolman.database import setting as setting_db
from spoolman.exceptions import ItemNotFoundError
from spoolman.label_renderer import render_label
from spoolman.printing import check_cups_available, print_image
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
        if not check_cups_available():
            logger.warning("Auto-print skipped: CUPS is not available.")
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
        label_settings = preset.get("labelSettings", {})
        show_qr_code = label_settings.get("showQRCodeMode", "withIcon")
        text_size_mm = label_settings.get("textSize", 3.0)

        print_settings = label_settings.get("printSettings", {})
        paper_size = print_settings.get("paperSize", "custom")
        custom_paper_size = print_settings.get("customPaperSize", {"width": 62, "height": 29})

        paper_dimensions = {
            "A3": (297, 420),
            "A4": (210, 297),
            "A5": (148, 210),
            "Letter": (216, 279),
            "Legal": (216, 356),
            "Tabloid": (279, 432),
        }

        if paper_size not in paper_dimensions:
            paper_width = custom_paper_size.get("width", 62)
            paper_height = custom_paper_size.get("height", 29)
        else:
            paper_width, paper_height = paper_dimensions[paper_size]

        margin = print_settings.get("margin", {"top": 2, "bottom": 2, "left": 2, "right": 2})
        margin_vals = [margin.get("top", 2), margin.get("bottom", 2), margin.get("left", 2), margin.get("right", 2)]
        avg_margin = sum(margin_vals) / len(margin_vals)

        # Convert DB model to pydantic model for template rendering
        spool_pydantic = Spool.from_db(spool_db_item)

        # Render the label (CPU-bound, run in thread to avoid blocking event loop)
        image_data = await asyncio.to_thread(
            render_label,
            spool_pydantic=spool_pydantic,
            template=template,
            show_qr_code=show_qr_code,
            text_size_mm=text_size_mm,
            paper_width_mm=paper_width,
            paper_height_mm=paper_height,
            margin_mm=avg_margin,
            base_url=base_url,
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
