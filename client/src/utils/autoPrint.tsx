import { QRCode } from "antd";
import * as htmlToImage from "html-to-image";
import { createRoot } from "react-dom/client";
import { renderLabelContents, SpoolQRCodePrintSettings } from "../pages/printing/printing";
import { ISpool } from "../pages/spools/model";
import { getAPIURL } from "./url";
import { getBasePath } from "./url";

const DEFAULT_TEMPLATE = `**{filament.vendor.name} - {filament.name}
#{id} - {filament.material}**
Spool Weight: {filament.spool_weight} g
{ET: {filament.settings_extruder_temp} °C}
{BT: {filament.settings_bed_temp} °C}
{Lot Nr: {lot_nr}}
{{comment}}
{filament.comment}
{filament.vendor.comment}`;

interface AutoPrintLabelProps {
  spool: ISpool;
  preset: SpoolQRCodePrintSettings;
  baseUrlRoot: string;
  useHTTPUrl: boolean;
  onReady: () => void;
}

function AutoPrintLabel({ spool, preset, baseUrlRoot, useHTTPUrl, onReady }: AutoPrintLabelProps) {
  const template = preset.template ?? DEFAULT_TEMPLATE;
  const settings = preset.labelSettings;
  const showQRCodeMode = settings?.showQRCodeMode || "withIcon";
  const showContent = settings?.showContent === undefined ? true : settings?.showContent;
  const textSize = settings?.textSize || 3;

  const printSettings = settings.printSettings;
  const paperSize = printSettings?.paperSize || "custom";
  const customPaperSize = printSettings?.customPaperSize || { width: 62, height: 29 };
  const margin = printSettings?.margin || { top: 2, bottom: 2, left: 2, right: 2 };

  const paperDimensions: Record<string, { width: number; height: number }> = {
    A3: { width: 297, height: 420 },
    A4: { width: 210, height: 297 },
    A5: { width: 148, height: 210 },
    Letter: { width: 216, height: 279 },
    Legal: { width: 216, height: 356 },
    Tabloid: { width: 279, height: 432 },
  };

  const paperWidth = paperSize === "custom" ? customPaperSize.width : (paperDimensions[paperSize]?.width ?? 62);
  const paperHeight = paperSize === "custom" ? customPaperSize.height : (paperDimensions[paperSize]?.height ?? 29);

  const qrValue = useHTTPUrl
    ? `${baseUrlRoot}/spool/show/${spool.id}`
    : `WEB+SPOOLMAN:S-${spool.id}`;

  // Call onReady after a delay to allow QR code SVG to render
  setTimeout(onReady, 800);

  return (
    <div
      className="auto-print-page"
      style={{
        width: `${paperWidth}mm`,
        height: `${paperHeight}mm`,
        backgroundColor: "#FFF",
        overflow: "hidden",
        fontFamily:
          "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, 'Noto Sans', sans-serif",
        lineHeight: "1.2",
        boxSizing: "border-box",
      }}
    >
      <div
        style={{
          display: "flex",
          width: "100%",
          height: "100%",
          justifyContent: "center",
          padding: `${margin.top}mm ${margin.right}mm ${margin.bottom}mm ${margin.left}mm`,
        }}
      >
        {showQRCodeMode !== "no" && (
          <div style={{ maxWidth: showContent ? "50%" : "100%", display: "flex" }}>
            <QRCode
              icon={showQRCodeMode === "withIcon" ? getBasePath() + "/favicon.svg" : undefined}
              value={qrValue}
              errorLevel="H"
              type="svg"
              color="#000"
              style={{
                width: "auto",
                height: "auto",
                padding: "2mm",
                objectFit: "contain",
                maxHeight: "100%",
                maxWidth: "100%",
              }}
            />
          </div>
        )}
        {showContent && (
          <div
            style={{
              flex: "1 1 auto",
              fontSize: `${textSize}mm`,
              color: "#000",
              overflow: "hidden",
              paddingLeft: showQRCodeMode === "no" ? "1mm" : 0,
            }}
          >
            <p style={{ padding: "1mm 1mm 1mm 0", margin: 0, whiteSpace: "pre-wrap" }}>
              {renderLabelContents(template, spool)}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export async function autoPrintSpool(
  spool: ISpool,
  preset: SpoolQRCodePrintSettings,
  printerName: string,
  printerOptions: Record<string, string>,
  copies: number,
  baseUrlRoot: string,
  useHTTPUrl: boolean,
): Promise<void> {
  // Create an off-screen container
  const container = document.createElement("div");
  container.style.position = "fixed";
  container.style.left = "-10000px";
  container.style.top = "0";
  container.style.zIndex = "-9999";
  document.body.appendChild(container);

  try {
    // Render the label into the container
    const root = createRoot(container);
    await new Promise<void>((resolve) => {
      root.render(
        <AutoPrintLabel
          spool={spool}
          preset={preset}
          baseUrlRoot={baseUrlRoot}
          useHTTPUrl={useHTTPUrl}
          onReady={resolve}
        />,
      );
    });

    // Capture the rendered label as PNG
    const page = container.querySelector(".auto-print-page") as HTMLElement;
    if (!page) {
      throw new Error("Label element not found");
    }

    const dataUrl = await htmlToImage.toPng(page, {
      backgroundColor: "#FFF",
      cacheBust: true,
      pixelRatio: 2,
    });

    // Convert data URL to blob
    const response = await fetch(dataUrl);
    const blob = await response.blob();

    // Send to CUPS
    const formData = new FormData();
    formData.append("image", blob, "label.png");
    formData.append("printer_name", printerName ?? "");
    formData.append("copies", String(copies));
    formData.append("options", JSON.stringify(printerOptions));

    const printResponse = await fetch(`${getAPIURL()}/printer/print`, {
      method: "POST",
      body: formData,
    });

    if (!printResponse.ok) {
      const error = await printResponse.json();
      throw new Error(error.message || "Print job failed");
    }

    // Cleanup
    root.unmount();
  } finally {
    document.body.removeChild(container);
  }
}
