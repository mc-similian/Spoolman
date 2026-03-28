"""Host printing utilities using CUPS command-line tools with TSPL support."""

import io
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass

from PIL import Image

logger = logging.getLogger(__name__)

# Default TSPL settings
DEFAULT_SPEED = 2
DEFAULT_DENSITY = 6
DEFAULT_GAP_MM = 2
DEFAULT_DIRECTION = 1


@dataclass
class PrinterInfo:
    """Information about a CUPS printer."""

    name: str
    description: str = ""
    is_default: bool = False
    status: str = "unknown"


def check_cups_available() -> bool:
    """Check if CUPS client tools (lp, lpstat) are available."""
    return shutil.which("lp") is not None and shutil.which("lpstat") is not None


def list_printers() -> list[PrinterInfo]:
    """List available CUPS printers by parsing lpstat output."""
    if not check_cups_available():
        return []

    printers: list[PrinterInfo] = []
    default_printer = get_default_printer()

    try:
        result = subprocess.run(
            ["lpstat", "-p"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            logger.warning("lpstat -p failed: %s", result.stderr.strip())
            return []

        for line in result.stdout.strip().split("\n"):
            if not line.startswith("printer "):
                continue
            # Format: "printer NAME is idle." or "printer NAME disabled since ..."
            parts = line.split()
            if len(parts) < 3:
                continue
            name = parts[1]
            status = "idle"
            if "disabled" in line.lower():
                status = "disabled"
            elif "printing" in line.lower():
                status = "printing"

            printers.append(
                PrinterInfo(
                    name=name,
                    description=name,
                    is_default=(name == default_printer),
                    status=status,
                )
            )
    except subprocess.TimeoutExpired:
        logger.warning("lpstat timed out — is CUPS reachable?")
    except Exception:
        logger.exception("Failed to list printers")

    return printers


def get_default_printer() -> str | None:
    """Get the system default CUPS printer name."""
    if not check_cups_available():
        return None

    try:
        result = subprocess.run(
            ["lpstat", "-d"],  # noqa: S603, S607
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        # Format: "system default destination: PRINTER_NAME"
        match = re.search(r"system default destination:\s*(\S+)", result.stdout)
        if match:
            return match.group(1)
    except Exception:
        logger.exception("Failed to get default printer")

    return None


def _png_to_tspl(
    image_data: bytes,
    label_width_mm: float,
    label_height_mm: float,
    speed: int = DEFAULT_SPEED,
    density: int = DEFAULT_DENSITY,
    gap_mm: float = DEFAULT_GAP_MM,
    direction: int = DEFAULT_DIRECTION,
) -> bytes:
    """Convert a PNG image to TSPL commands with BITMAP data.

    The image is resized to fit the label dimensions at 203 DPI,
    converted to 1-bit monochrome, and encoded as a TSPL BITMAP command.

    Args:
        image_data: Raw PNG image bytes.
        label_width_mm: Label width in millimeters.
        label_height_mm: Label height in millimeters.
        speed: Print speed (1-6, 1=slowest).
        density: Print density (0-15).
        gap_mm: Gap between labels in mm.
        direction: Print direction (0 or 1).

    Returns:
        TSPL command bytes ready to send to printer.

    """
    dots_per_mm = 8  # 203 DPI ≈ 8 dots/mm
    label_width_dots = int(label_width_mm * dots_per_mm)
    label_height_dots = int(label_height_mm * dots_per_mm)

    # Load and resize image to fit label
    img = Image.open(io.BytesIO(image_data))
    img = img.resize((label_width_dots, label_height_dots), Image.LANCZOS)

    # Convert to 1-bit monochrome (TSPL: 0=black, 1=white)
    img = img.convert("L")  # grayscale first
    img = img.point(lambda x: 0 if x < 128 else 1, mode="1")  # noqa: PLR2004

    # Ensure width is byte-aligned (8 pixels per byte)
    width_bytes = (label_width_dots + 7) // 8
    actual_width = width_bytes * 8

    # Pad image if needed
    if actual_width != label_width_dots:
        padded = Image.new("1", (actual_width, label_height_dots), 1)
        padded.paste(img, (0, 0))
        img = padded

    # Convert to raw bitmap bytes
    # PIL "1" mode: each pixel is 0 or 1, packed 8 per byte, MSB first
    # TSPL BITMAP expects: 0=black dot, 1=white (no dot) — same as PIL "1" mode
    raw_data = img.tobytes()

    # Build TSPL command sequence
    header = (
        f"SIZE {label_width_mm} mm, {label_height_mm} mm\n"
        f"GAP {gap_mm} mm, 0 mm\n"
        f"SPEED {speed}\n"
        f"DENSITY {density}\n"
        f"DIRECTION {direction}\n"
        "CLS\n"
        f"BITMAP 0,0,{width_bytes},{label_height_dots},0,"
    )

    footer = b"\nPRINT 1,1\n"

    return header.encode("ascii") + raw_data + footer


def print_image(
    image_data: bytes,
    printer_name: str | None = None,
    copies: int = 1,
    options: dict | None = None,
) -> str:
    """Print an image via CUPS using TSPL format.

    The PNG image is converted to TSPL BITMAP commands and sent to the printer.
    TSPL settings (speed, density, label size, gap) are read from the options dict.

    Args:
        image_data: Raw image bytes (PNG).
        printer_name: CUPS printer name. None = system default.
        copies: Number of copies.
        options: Dict of print options. Supports TSPL settings:
            - speed (int, 1-6): Print speed, default 2
            - density (int, 0-15): Print density, default 6
            - label_width_mm (float): Label width, default from rendered image
            - label_height_mm (float): Label height, default from rendered image
            - gap_mm (float): Gap between labels, default 2

    Returns:
        The CUPS job ID string.

    Raises:
        RuntimeError: If CUPS is not available or the print command fails.

    """
    if not check_cups_available():
        raise RuntimeError("CUPS is not available on this system. Install cups-client.")

    opts = options or {}

    # Extract TSPL settings from options
    speed = int(opts.get("speed", DEFAULT_SPEED))
    density = int(opts.get("density", DEFAULT_DENSITY))
    gap_mm = float(opts.get("gap_mm", DEFAULT_GAP_MM))
    direction = int(opts.get("direction", DEFAULT_DIRECTION))

    # Get label dimensions from options or from the image itself
    img = Image.open(io.BytesIO(image_data))
    img_width, img_height = img.size
    dots_per_mm = 8
    default_width = img_width / dots_per_mm
    default_height = img_height / dots_per_mm

    label_width_mm = float(opts.get("label_width_mm", default_width))
    label_height_mm = float(opts.get("label_height_mm", default_height))

    # Convert PNG to TSPL
    tspl_data = _png_to_tspl(
        image_data,
        label_width_mm=label_width_mm,
        label_height_mm=label_height_mm,
        speed=speed,
        density=density,
        gap_mm=gap_mm,
        direction=direction,
    )

    # Write TSPL data to temp file and send via lp with raw option
    tmp = tempfile.NamedTemporaryFile(suffix=".tspl", delete=False)  # noqa: SIM115
    try:
        tmp.write(tspl_data)
        tmp.flush()
        tmp.close()

        cmd: list[str] = ["lp"]  # noqa: S607
        if printer_name:
            cmd.extend(["-d", printer_name])
        if copies > 1:
            cmd.extend(["-n", str(copies)])
        # Send as raw data — TSPL commands go directly to printer
        cmd.extend(["-o", "raw"])
        cmd.append(tmp.name)

        logger.info("Sending TSPL print job: %s (%d bytes)", " ".join(cmd), len(tspl_data))
        result = subprocess.run(
            cmd,  # noqa: S603
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"lp command failed: {result.stderr.strip()}")

        # Parse job ID from output like "request id is PRINTER-123 (1 file(s))"
        match = re.search(r"request id is (\S+)", result.stdout)
        job_id = match.group(1) if match else "unknown"
        logger.info("TSPL print job submitted: %s", job_id)
        return job_id

    finally:
        import os

        try:
            os.unlink(tmp.name)
        except OSError:
            pass
