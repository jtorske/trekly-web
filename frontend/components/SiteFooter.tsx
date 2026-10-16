import { DEFAULT_TOPO_MAP, OGL_CANADA_URL, TOPO_MAPS, type TopoMapKey } from "@/lib/topoMaps";
import styles from "./SiteFooter.module.css";

/** Small site footer carrying the credit for the contour background's data. */
export default function SiteFooter({ map = DEFAULT_TOPO_MAP }: { map?: TopoMapKey }) {
  return (
    <footer className={styles.footer}>
      <p>
        Contours: {TOPO_MAPS[map].place} ·{" "}
        <a href={OGL_CANADA_URL} target="_blank" rel="noopener noreferrer">
          Contains information licensed under the Open Government Licence – Canada
        </a>
      </p>
    </footer>
  );
}
