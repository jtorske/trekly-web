import type { CSSProperties } from "react";
import { DEFAULT_TOPO_MAP, TOPO_MAPS, type TopoMapKey } from "@/lib/topoMaps";
import styles from "./TopoBackground.module.css";

/**
 * The fixed page background: warm paper, a faint grain, and real contour
 * lines. The contour SVG is used as a mask over a layer filled with the ink
 * token, so the lines always match the palette at low opacity.
 *
 * The root layout renders one with the default map. To swap the map for a
 * page, render another <TopoBackground map="..." /> inside that page (it
 * sits above the default one), or set `--topo-map: url(...)` on a wrapper
 * around it.
 */
export default function TopoBackground({ map = DEFAULT_TOPO_MAP }: { map?: TopoMapKey }) {
  const style = { "--topo-map": `url(${TOPO_MAPS[map].src})` } as CSSProperties;
  return (
    <div className={styles.layer} style={style} aria-hidden="true">
      <div className={styles.contours} />
    </div>
  );
}
