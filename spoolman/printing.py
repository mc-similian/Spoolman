"""Host printing utilities with TSPL support via direct USB or CUPS."""

import io
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

logger = logging.getLogger(__name__)

# Default TSPL settings
DEFAULT_SPEED = 2
DEFAULT_DENSITY = 6
DEFAULT_GAP_MM = 2
DEFAULT_DIRECTION = 1

# Default USB device path for thermal label printers
DEFAULT_USB_DEVICE = "/dev/usb/lp0"


@dataclass
class PrinterInfo:
    """Information about a printer."""

    name: str
    description: str = ""
    is_default: bool = False
    status: str = "unknown"


def _find_usb_device() -> str | None:
    """Find the first available USB printer device."""
    for i in range(4):
        path = f"/dev/usb/lp{i}"
        if os.path.exists(path):
            return path
    return None


def check_cups_available() -> bool:
    """Check if CUPS client tools (lp, lpstat) are available."""
    return shutil.which("lp") is not None and shutil.which("lpstat") is not None


def check_printer_available() -> bool:
    """Check if any printing method is available (USB device or CUPS)."""
    return _find_usb_device() is not None or check_cups_available()


def list_printers() -> list[PrinterInfo]:
    """List available printers (USB devices and CUPS printers)."""
    printers: list[PrinterInfo] = []

    # Check for direct USB devices first
    usb_device = _find_usb_device()
    if usb_device:
        printers.append(
            PrinterInfo(
                name=usb_device,
                description=f"USB Thermal Printer ({usb_device})",
                is_default=True,
                status="ready",
            )
        )

    # Also list CUPS printers if available
    if check_cups_available():
        default_printer = _get_default_cups_printer()
        try:
            result = subprocess.run(
                ["lpstat", "-p"],  # noqa: S603, S607
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if not line.startswith("printer "):
                        continue
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
                            description=f"CUPS: {name}",
                            is_default=(not usb_device and name == default_printer),
                            status=status,
                        )
                    )
        except (subprocess.TimeoutExpired, Exception):
            logger.exception("Failed to list CUPS printers")

    return printers


def _get_default_cups_printer() -> str | None:
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
    """
    dots_per_mm = 8  # 203 DPI ≈ 8 dots/mm
    label_width_dots = int(label_width_mm * dots_per_mm)
    label_height_dots = int(label_height_mm * dots_per_mm)

    # Load and resize image to fit label
    img = Image.open(io.BytesIO(image_data))
    img = img.resize((label_width_dots, label_height_dots), Image.LANCZOS)

    # Convert to 1-bit monochrome (TSPL: 0=black, 1=white)
    img = img.convert("L")
    img = img.point(lambda x: 0 if x < 128 else 1, mode="1")  # noqa: PLR2004

    # Ensure width is byte-aligned (8 pixels per byte)
    width_bytes = (label_width_dots + 7) // 8
    actual_width = width_bytes * 8

    if actual_width != label_width_dots:
        padded = Image.new("1", (actual_width, label_height_dots), 1)
        padded.paste(img, (0, 0))
        img = padded

    raw_data = img.tobytes()

    header = (
        f"SIZE {label_width_mm} mm, {label_height_mm} mm\n"
        f"GAP {gap_mm} mm, 0 mm\n"
        f"SPEED {speed}\n"
        f"DENSITY {density}\n"
        f"DIRECTION {direction}\n"
        "SET TEAR ON\n"
        "OFFSET 0 mm\n"
        "CLS\n"
        f"BITMAP 0,0,{width_bytes},{label_height_dots},0,"
    )

    footer = b"\nPRINT 1,1\n"

    return header.encode("ascii") + raw_data + footer


def _print_via_usb(tspl_data: bytes, device_path: str, copies: int = 1) -> str:
    """Write TSPL data directly to a USB printer device."""
    device = Path(device_path)
    if not device.exists():
        raise RuntimeError(f"USB printer device not found: {device_path}")

    for i in range(copies):
        with open(device_path, "wb") as f:
            f.write(tspl_data)
            f.flush()
        logger.info("TSPL data written to %s (copy %d/%d, %d bytes)", device_path, i + 1, copies, len(tspl_data))

    return f"usb-{device_path}-direct"


def _print_via_cups(tspl_data: bytes, printer_name: str, copies: int = 1) -> str:
    """Send TSPL data via CUPS lp command as raw data."""
    import tempfile

    tmp = tempfile.NamedTemporaryFile(suffix=".tspl", delete=False)  # noqa: SIM115
    try:
        tmp.write(tspl_data)
        tmp.flush()
        tmp.close()

        cmd: list[str] = ["lp", "-d", printer_name]  # noqa: S607
        if copies > 1:
            cmd.extend(["-n", str(copies)])
        cmd.extend(["-o", "raw"])
        cmd.append(tmp.name)

        logger.info("Sending TSPL via CUPS: %s (%d bytes)", " ".join(cmd), len(tspl_data))
        result = subprocess.run(
            cmd,  # noqa: S603
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"lp command failed: {result.stderr.strip()}")

        match = re.search(r"request id is (\S+)", result.stdout)
        job_id = match.group(1) if match else "unknown"
        logger.info("CUPS print job submitted: %s", job_id)
        return job_id

    finally:
        try:
            Path(tmp.name).unlink()
        except OSError:
            pass


def print_image(
    image_data: bytes,
    printer_name: str | None = None,
    copies: int = 1,
    options: dict | None = None,
) -> str:
    """Print an image using TSPL format.

    Automatically selects the best method:
    1. If printer_name is a /dev/usb/lp* path or no printer specified and USB device exists: write directly
    2. Otherwise: send via CUPS

    Args:
        image_data: Raw image bytes (PNG).
        printer_name: Printer name or USB device path. None = auto-detect.
        copies: Number of copies.
        options: Dict of TSPL options (speed, density, gap_mm, direction, label_width_mm, label_height_mm).

    Returns:
        Job identifier string.

    """
    opts = options or {}

    # Extract TSPL settings
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

    # Determine print method
    use_usb = False
    usb_path = None

    if printer_name and printer_name.startswith("/dev/"):
        # Explicit USB device path
        use_usb = True
        usb_path = printer_name
    elif not printer_name or printer_name == "":
        # No printer specified — prefer USB if available
        usb_path = _find_usb_device()
        if usb_path:
            use_usb = True

    if use_usb and usb_path:
        return _print_via_usb(tspl_data, usb_path, copies)

    # Fall back to CUPS
    if not check_cups_available():
        raise RuntimeError("No USB printer device found and CUPS is not available.")

    cups_printer = printer_name or _get_default_cups_printer()
    if not cups_printer:
        raise RuntimeError("No printer specified and no default CUPS printer configured.")

    return _print_via_cups(tspl_data, cups_printer, copies)
