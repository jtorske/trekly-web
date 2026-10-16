/**
 * Topographic page backgrounds. Each SVG is generated once from NRCan's CDEM
 * by backend/scripts/make_topo_background.py and committed under
 * public/topo/. Add a map here to make it available to <TopoBackground map>.
 */
export const TOPO_MAPS = {
  "mount-assiniboine": {
    src: "/topo/mount-assiniboine.svg",
    place: "Mount Assiniboine",
  },
} as const;

export type TopoMapKey = keyof typeof TOPO_MAPS;

export const DEFAULT_TOPO_MAP: TopoMapKey = "mount-assiniboine";

export const OGL_CANADA_URL = "https://open.canada.ca/en/open-government-licence-canada";
