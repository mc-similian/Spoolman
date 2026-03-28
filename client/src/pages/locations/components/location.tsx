import { Button, Input, Modal, Space, message, theme } from "antd";
import type { Identifier, XYCoord } from "dnd-core";
import { useRef, useState } from "react";
import { DragSourceMonitor, useDrag, useDrop } from "react-dnd";

import { CameraOutlined, DeleteOutlined } from "@ant-design/icons";
import { useTranslate, useUpdate } from "@refinedev/core";
import { IDetectedBarcode, Scanner } from "@yudiel/react-qr-scanner";
import { ISpool } from "../../spools/model";
import { DragItem, ItemTypes, SpoolDragItem } from "../dnd";
import { EMPTYLOC } from "../functions";
import { SpoolList } from "./spoolList";

const { useToken } = theme;

export function Location({
  index,
  title,
  spools,
  showDelete,
  onDelete,
  moveLocation,
  onEditTitle,
  locationSpoolOrder,
  setLocationSpoolOrder,
}: {
  index: number;
  title: string;
  spools: ISpool[];
  showDelete?: boolean;
  onDelete?: () => void;
  moveLocation: (dragIndex: number, hoverIndex: number) => void;
  onEditTitle: (newTitle: string) => void;
  locationSpoolOrder: number[];
  setLocationSpoolOrder: (spoolOrder: number[]) => void;
}) {
  const { token } = useToken();
  const t = useTranslate();
  const [editTitle, setEditTitle] = useState(false);
  const [newTitle, setNewTitle] = useState(title);
  const [scannerOpen, setScannerOpen] = useState(false);
  const [scannerError, setScannerError] = useState<string | null>(null);
  const [messageApi, contextHolder] = message.useMessage();
  const { mutate: updateSpool } = useUpdate({
    resource: "spool",
    mutationMode: "optimistic",
    successNotification: false,
  });

  const extractSpoolId = (raw: string): number | null => {
    const match = raw.match(/^web\+spoolman:s-(?<id>[0-9]+)$/i);
    if (match?.groups) return parseInt(match.groups.id, 10);
    const urlMatch = raw.match(/^https?:\/\/[^/]+\/spool\/show\/(?<id>[0-9]+)$/i);
    if (urlMatch?.groups) return parseInt(urlMatch.groups.id, 10);
    return null;
  };

  const onScanForLocation = (detectedCodes: IDetectedBarcode[]) => {
    if (detectedCodes.length === 0) return;
    const raw = detectedCodes[0].rawValue;
    const spoolId = extractSpoolId(raw);
    if (spoolId === null) return;

    const locationValue = title === EMPTYLOC ? "" : title;
    updateSpool(
      {
        id: spoolId,
        values: { location: locationValue },
      },
      {
        onSuccess: () => {
          messageApi.success(t("locations.scanner.success", { id: spoolId }));
        },
      }
    );
  };

  const moveSpoolLocation = (spool_id: number, location: string) => {
    updateSpool({
      id: spool_id,
      values: {
        location: location,
      },
    });
  };

  const dropTypes = title == EMPTYLOC ? [ItemTypes.SPOOL] : [ItemTypes.CONTAINER, ItemTypes.SPOOL];

  const ref = useRef<HTMLDivElement>(null);
  const [{ handlerId }, drop] = useDrop<DragItem, void, { handlerId: Identifier | null }>({
    accept: dropTypes,
    collect(monitor) {
      return {
        handlerId: monitor.getHandlerId(),
      };
    },
    hover(item, monitor) {
      if (!ref.current) {
        return null;
      }

      if ("spool" in item) {
        // Only allow dropping spools on the container if it's empty.
        if (spools.length > 0) {
          return null;
        }

        const spoolitem = item as SpoolDragItem;
        if (spoolitem.spool.location !== title) {
          moveSpoolLocation(spoolitem.spool.id, title);
          spoolitem.spool.location = title;
        }
        return null;
      }

      const dragIndex = item.index;
      const hoverIndex = index;

      // Don't replace items with themselves
      if (dragIndex === hoverIndex) {
        return;
      }

      // Determine rectangle on screen
      const hoverBoundingRect = ref.current?.getBoundingClientRect();

      // Get horizontal middle
      const hoverMiddleX = (hoverBoundingRect.right - hoverBoundingRect.left) / 2;

      // Determine mouse position
      const clientOffset = monitor.getClientOffset();

      // Get pixels to the left
      const hoverClientX = (clientOffset as XYCoord).x - hoverBoundingRect.left;

      // Dragging downwards
      if (dragIndex < hoverIndex && hoverClientX < hoverMiddleX) {
        return;
      }

      // Dragging upwards
      if (dragIndex > hoverIndex && hoverClientX > hoverMiddleX) {
        return;
      }

      // Time to actually perform the action
      moveLocation(dragIndex, hoverIndex);

      item.index = hoverIndex;
    },
  });

  const [{ isDragging }, drag] = useDrag({
    type: ItemTypes.CONTAINER,
    canDrag: !editTitle && title != EMPTYLOC,
    item: () => {
      return { title, index };
    },
    collect: (monitor: DragSourceMonitor<{ title: string; index: number }>) => ({
      isDragging: monitor.isDragging(),
    }),
  });

  const displayTitle = title == EMPTYLOC ? t("locations.no_location") : title;

  const opacity = isDragging ? 0 : 1;
  drag(drop(ref));

  const canEditTitle = title != EMPTYLOC;

  const titleStyle = {
    color: canEditTitle ? undefined : token.colorTextTertiary,
  };
  const spoolCountStyle = {
    color: token.colorTextQuaternary,
  };

  return (
    <div
      className={"loc-container " + (title != EMPTYLOC ? "grabable" : "")}
      ref={ref}
      style={{ opacity }}
      data-handler-id={handlerId}
    >
      <h3>
        {editTitle ? (
          <Input
            autoFocus
            variant="borderless"
            value={newTitle}
            onBlur={() => setEditTitle(false)}
            onChange={(e) => setNewTitle(e.target.value)}
            onPressEnter={() => {
              setEditTitle(false);
              return onEditTitle(newTitle);
            }}
          />
        ) : (
          <span
            className={canEditTitle ? "editable" : ""}
            onClick={() => {
              if (!canEditTitle) return;
              setNewTitle(title);
              setEditTitle(true);
            }}
            style={titleStyle}
          >
            {displayTitle}
            {<span style={spoolCountStyle}> ({spools.length})</span>}
          </span>
        )}
        <span>
          <Button icon={<CameraOutlined />} size="small" type="text" onClick={() => setScannerOpen(true)} />
          {showDelete && <Button icon={<DeleteOutlined />} size="small" type="text" onClick={onDelete} />}
        </span>
      </h3>
      {contextHolder}
      <Modal
        open={scannerOpen}
        destroyOnHidden
        onCancel={() => setScannerOpen(false)}
        footer={null}
        title={t("locations.scanner.title", { location: title === EMPTYLOC ? t("locations.no_location") : title })}
      >
        <Space direction="vertical" style={{ width: "100%" }}>
          <p>{t("locations.scanner.description")}</p>
          <Scanner
            constraints={{ facingMode: "environment" }}
            onScan={onScanForLocation}
            formats={["qr_code"]}
            onError={(err: unknown) => {
              const error = err as Error;
              console.error(error);
              if (error.name === "NotAllowedError") {
                setScannerError(t("scanner.error.notAllowed"));
              } else if (
                error.name === "InsecureContextError" ||
                (location.protocol !== "https:" && navigator.mediaDevices === undefined)
              ) {
                setScannerError(t("scanner.error.insecureContext"));
              } else if (error.name === "StreamApiNotSupportedError") {
                setScannerError(t("scanner.error.streamApiNotSupported"));
              } else if (error.name === "NotReadableError") {
                setScannerError(t("scanner.error.notReadable"));
              } else if (error.name === "NotFoundError") {
                setScannerError(t("scanner.error.notFound"));
              } else {
                setScannerError(t("scanner.error.unknown", { error: error.name }));
              }
            }}
          >
            {scannerError && (
              <div style={{ position: "absolute", textAlign: "center", width: "100%", top: "50%" }}>
                <p>{scannerError}</p>
              </div>
            )}
          </Scanner>
        </Space>
      </Modal>
      <SpoolList spools={spools} spoolOrder={locationSpoolOrder} setSpoolOrder={setLocationSpoolOrder} />
    </div>
  );
}
