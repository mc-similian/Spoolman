"""Host printing utilities using CUPS command-line tools."""

import json
import logging
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


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


def print_image(
    image_data: bytes,
    printer_name: str | None = None,
    copies: int = 1,
    options: dict[str, str] | None = None,
) -> str:
    """Print an image file via CUPS.

    Args:
        image_data: Raw image bytes (PNG).
        printer_name: CUPS printer name. None = system default.
        copies: Number of copies.
        options: Dict of CUPS options (e.g. {"media": "Custom.62x29mm", "fit-to-page": ""}).

    Returns:
        The CUPS job ID string.

    Raises:
        RuntimeError: If CUPS is not available or the print command fails.
    """
    if not check_cups_available():
        raise RuntimeError("CUPS is not available on this system. Install cups-client.")

    # Write image to a temp file (lp needs a file path)
    tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)  # noqa: SIM115
    try:
        tmp.write(image_data)
        tmp.flush()
        tmp.close()

        cmd: list[str] = ["lp"]  # noqa: S607
        if printer_name:
            cmd.extend(["-d", printer_name])
        if copies > 1:
            cmd.extend(["-n", str(copies)])
        if options:
            for key, value in options.items():
                if value:
                    cmd.extend(["-o", f"{key}={value}"])
                else:
                    cmd.extend(["-o", key])
        cmd.append(tmp.name)

        logger.info("Sending print job: %s", " ".join(cmd))
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
        logger.info("Print job submitted: %s", job_id)
        return job_id

    finally:
        import os

        try:
            os.unlink(tmp.name)
        except OSError:
            pass
