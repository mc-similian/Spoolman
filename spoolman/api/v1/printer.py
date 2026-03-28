"""Printer-related endpoints for host-based printing via USB or CUPS."""

import json
import logging

from fastapi import APIRouter, File, Form, UploadFile
from fastapi.responses import JSONResponse

from spoolman.api.v1.models import PrinterInfo, PrinterListResponse, PrinterStatusResponse, PrintJobResponse
from spoolman.printing import check_printer_available, list_printers, print_image

router = APIRouter(
    prefix="/printer",
    tags=["printer"],
)

logger = logging.getLogger(__name__)


@router.get(
    "/status",
    name="Get printer status",
    description="Check whether printing is available (USB device or CUPS).",
    response_model=PrinterStatusResponse,
)
async def get_printer_status() -> PrinterStatusResponse:
    """Return whether a printer is available."""
    return PrinterStatusResponse(cups_available=check_printer_available())


@router.get(
    "/",
    name="List printers",
    description="List all available printers (USB devices and CUPS printers).",
    response_model=PrinterListResponse,
)
async def get_printers() -> PrinterListResponse:
    """List available printers."""
    printers = list_printers()
    return PrinterListResponse(
        cups_available=len(printers) > 0,
        printers=[
            PrinterInfo(
                name=p.name,
                description=p.description,
                is_default=p.is_default,
                status=p.status,
            )
            for p in printers
        ],
    )


@router.post(
    "/print",
    name="Print label",
    description="Send a label image to a printer (USB direct or CUPS).",
    response_model=PrintJobResponse,
    responses={
        503: {"description": "No printer available."},
        404: {"description": "The specified printer was not found."},
    },
)
async def print_label(
    image: UploadFile = File(..., description="The label image (PNG) to print."),
    printer_name: str = Form(default="", description="Printer name or USB device path. Empty = auto-detect."),
    copies: int = Form(default=1, description="Number of copies to print."),
    options: str = Form(default="{}", description="JSON-encoded dict of TSPL print options."),
) -> PrintJobResponse | JSONResponse:
    """Submit a print job."""
    if not check_printer_available():
        return JSONResponse(
            status_code=503,
            content={"message": "No printer available. Ensure a USB printer device is accessible or CUPS is configured."},
        )

    # Validate printer exists if specified
    if printer_name:
        available = list_printers()
        printer_names = [p.name for p in available]
        if printer_name not in printer_names:
            return JSONResponse(
                status_code=404,
                content={"message": f"Printer '{printer_name}' not found. Available: {', '.join(printer_names)}"},
            )

    # Parse options
    try:
        opts = json.loads(options) if options else {}
    except json.JSONDecodeError:
        return JSONResponse(
            status_code=400,
            content={"message": "Invalid JSON in 'options' field."},
        )

    # Read image data
    image_data = await image.read()

    try:
        job_id = print_image(
            image_data=image_data,
            printer_name=printer_name or None,
            copies=copies,
            options=opts,
        )
        return PrintJobResponse(job_id=job_id, status="submitted")
    except RuntimeError as e:
        logger.exception("Print job failed")
        return JSONResponse(
            status_code=500,
            content={"message": str(e)},
        )
