"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type PointerEvent } from "react";
import ui from "@/components/ui.module.css";
import { MAX_ZOOM, clampOffset, clampZoom, displayScale, type Offset, type Size } from "@/lib/avatarImage";
import { processAvatar, type ProcessedAvatar } from "@/lib/processAvatar";
import styles from "./AvatarCropper.module.css";

const FRAME = 240;
const STEP = 8;

/** Square crop/position step for a newly chosen avatar. */
export default function AvatarCropper({
  file,
  onCancel,
  onDone,
}: {
  file: File;
  onCancel: () => void;
  onDone: (image: ProcessedAvatar) => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [natural, setNatural] = useState<Size | null>(null);
  const [zoom, setZoom] = useState(1);
  const [offset, setOffset] = useState<Offset>({ x: 0, y: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const drag = useRef<{ pointer: number; x: number; y: number; start: Offset } | null>(null);

  useEffect(() => {
    const url = URL.createObjectURL(file);
    queueMicrotask(() => setSrc(url));
    return () => URL.revokeObjectURL(url);
  }, [file]);

  useEffect(() => {
    frameRef.current?.focus();
  }, []);

  const move = (next: Offset, nextZoom = zoom) => {
    if (natural) setOffset(clampOffset(natural, FRAME, nextZoom, next));
  };
  const zoomTo = (value: number) => {
    const next = clampZoom(value);
    setZoom(next);
    move(offset, next);
  };

  const onKeyDown = (event: KeyboardEvent) => {
    const step = event.shiftKey ? STEP * 4 : STEP;
    const moves: Record<string, Offset> = {
      ArrowLeft: { x: offset.x - step, y: offset.y },
      ArrowRight: { x: offset.x + step, y: offset.y },
      ArrowUp: { x: offset.x, y: offset.y - step },
      ArrowDown: { x: offset.x, y: offset.y + step },
    };
    if (moves[event.key]) move(moves[event.key]);
    else if (event.key === "+" || event.key === "=") zoomTo(zoom + 0.1);
    else if (event.key === "-" || event.key === "_") zoomTo(zoom - 0.1);
    else return;
    event.preventDefault();
  };

  const onPointerDown = (event: PointerEvent<HTMLDivElement>) => {
    event.currentTarget.setPointerCapture(event.pointerId);
    drag.current = { pointer: event.pointerId, x: event.clientX, y: event.clientY, start: offset };
  };
  const onPointerMove = (event: PointerEvent<HTMLDivElement>) => {
    const current = drag.current;
    if (!current || current.pointer !== event.pointerId) return;
    move({ x: current.start.x + event.clientX - current.x, y: current.start.y + event.clientY - current.y });
  };
  const endDrag = () => {
    drag.current = null;
  };

  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      onDone(await processAvatar(file, { frame: FRAME, zoom, offset }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "We couldn't process that photo. Try another one.");
      setBusy(false);
    }
  };

  const scale = natural ? displayScale(natural, FRAME, zoom) : 0;

  return (
    <div className={styles.cropper}>
      <p id="crop-help" className={ui.hint}>
        Drag the photo, or use the arrow keys, to position it. Zoom with the slider or the + and − keys.
      </p>
      <div
        ref={frameRef}
        className={styles.frame}
        style={{ width: FRAME, height: FRAME }}
        tabIndex={0}
        role="group"
        aria-roledescription="photo crop area"
        aria-label="Position your photo"
        aria-describedby="crop-help"
        onKeyDown={onKeyDown}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={endDrag}
        onPointerCancel={endDrag}
      >
        {src && (
          // A local object URL; next/image can't optimise it.
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={src}
            alt=""
            draggable={false}
            className={styles.image}
            onLoad={(event) => setNatural({ width: event.currentTarget.naturalWidth, height: event.currentTarget.naturalHeight })}
            style={
              natural
                ? {
                    width: natural.width * scale,
                    height: natural.height * scale,
                    transform: `translate(calc(-50% + ${offset.x}px), calc(-50% + ${offset.y}px))`,
                  }
                : { visibility: "hidden" }
            }
          />
        )}
        <span className={styles.guide} aria-hidden="true" />
      </div>
      <label className={styles.zoom}>
        <span className={ui.label}>Zoom</span>
        <input
          type="range"
          min={1}
          max={MAX_ZOOM}
          step={0.01}
          value={zoom}
          onChange={(event) => zoomTo(Number(event.target.value))}
          aria-valuetext={`${Math.round(zoom * 100)}%`}
        />
      </label>
      {error && (
        <p className={ui.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.actions}>
        <button type="button" className={ui.ghost} onClick={onCancel} disabled={busy}>
          Choose a different photo
        </button>
        <button type="button" className={ui.secondary} onClick={apply} disabled={busy || !natural}>
          {busy ? "Processing…" : "Use this photo"}
        </button>
      </div>
    </div>
  );
}
