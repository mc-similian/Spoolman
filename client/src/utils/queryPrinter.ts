import { useMutation, useQuery } from "@tanstack/react-query";
import { getAPIURL } from "./url";

interface PrinterInfo {
  name: string;
  description: string;
  is_default: boolean;
  status: string;
}

interface PrinterStatusResponse {
  cups_available: boolean;
}

interface PrinterListResponse {
  cups_available: boolean;
  printers: PrinterInfo[];
}

interface PrintJobResponse {
  job_id: string;
  status: string;
}

interface PrintToHostParams {
  imageBlob: Blob;
  printerName?: string;
  copies?: number;
  options?: Record<string, string>;
}

export function useGetPrinterStatus() {
  return useQuery<PrinterStatusResponse>({
    queryKey: ["printer", "status"],
    queryFn: async () => {
      const response = await fetch(`${getAPIURL()}/printer/status`);
      return response.json();
    },
  });
}

export function useGetPrinters() {
  return useQuery<PrinterListResponse>({
    queryKey: ["printer", "list"],
    queryFn: async () => {
      const response = await fetch(`${getAPIURL()}/printer/`);
      return response.json();
    },
  });
}

export function usePrintToHost() {
  return useMutation<PrintJobResponse, Error, PrintToHostParams>({
    mutationFn: async ({ imageBlob, printerName, copies, options }) => {
      const formData = new FormData();
      formData.append("image", imageBlob, "label.png");
      formData.append("printer_name", printerName ?? "");
      formData.append("copies", String(copies ?? 1));
      formData.append("options", JSON.stringify(options ?? {}));

      const response = await fetch(`${getAPIURL()}/printer/print`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        const error = await response.json();
        throw new Error(error.message || "Print job failed");
      }

      return response.json();
    },
  });
}
