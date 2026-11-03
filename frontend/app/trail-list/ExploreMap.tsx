"use client";

import { useEffect, useRef, useState } from "react";
import * as maplibregl from "maplibre-gl";
import type { AddLayerObject, GeoJSONSource, LngLatBoundsLike, Map as MapLibreMap } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import type { Bounds, MapView } from "@/lib/exploreFilters";
import { TERRAIN_COLORS, TERRAIN_LABELS, type Terrain } from "@/lib/terrain";
import type { TrailSearchItem } from "@/lib/trailsApi";
import styles from "./page.module.css";

/**
 * OpenFreeMap: free OpenStreetMap vector tiles, no key or view limits, and
 * commercial use allowed with attribution, which MapLibre shows from the
 * tiles' own metadata. Everything (style, tiles, fonts, sprites) comes from
 * this one host, which next.config.ts allows in connect-src.
 */
const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";
/** Canada, for a first load with nothing to fit to yet. */
const CANADA: LngLatBoundsLike = [
  [-141, 41.7],
  [-52.6, 70],
];
const FIT_PADDING = 56;
const CLUSTER_MAX_ZOOM = 11;
/** Trails this close (about 300 m) share a trailhead: zooming won't part them. */
const SAME_SPOT_DEGREES = 0.003;
/** The list follows the map once it settles, not on every frame of a pan. */
const AREA_DEBOUNCE_MS = 300;
/**
 * MapLibre looks for its worker next to its own file at runtime, which the
 * bundler moves, so it ends up loading the page as the worker. This static
 * reference makes the build emit the worker and gives its real URL.
 */
const WORKER_URL = new URL("maplibre-gl/dist/maplibre-gl-worker.mjs", import.meta.url).href;

type Point = GeoJSON.Feature<GeoJSON.Point, { id: string; terrain: Terrain }>;

function toFeatures(trails: TrailSearchItem[]): GeoJSON.FeatureCollection<GeoJSON.Point, { id: string; terrain: Terrain }> {
  return {
    type: "FeatureCollection",
    features: trails.flatMap((trail): Point[] =>
      trail.latitude == null || trail.longitude == null
        ? []
        : [{
            type: "Feature",
            geometry: { type: "Point", coordinates: [trail.longitude, trail.latitude] },
            properties: { id: trail.id, terrain: trail.terrain },
          }],
    ),
  };
}

type CirclePaint = NonNullable<Extract<AddLayerObject, { type: "circle" }>["paint"]>;

/** Marker colour by difficulty (the legend and the cards' chips agree). */
const TERRAIN_COLOR: CirclePaint["circle-color"] = [
  "match",
  ["get", "terrain"],
  "easy",
  TERRAIN_COLORS.easy,
  "moderate",
  TERRAIN_COLORS.moderate,
  "difficult",
  TERRAIN_COLORS.difficult,
  TERRAIN_COLORS.extreme,
];

/** The marker popup, built from DOM nodes so trail data never becomes HTML. */
function popupContent(trail: TrailSearchItem, title: string, onOpen: (id: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = styles.popup;
  const href = `/trails?id=${encodeURIComponent(trail.id)}`;
  if (trail.photo) {
    const img = document.createElement("img");
    img.className = styles.popupPhoto;
    img.src = trail.photo.thumb_url;
    img.alt = "";
    img.width = 240;
    img.height = 135;
    img.decoding = "async";
    img.addEventListener("error", () => img.remove());
    root.append(img);
  }
  const body = document.createElement("div");
  body.className = styles.popupBody;
  const name = document.createElement("p");
  name.className = styles.popupName;
  name.textContent = title;
  const chip = document.createElement("span");
  chip.className = `${styles.terrainTag} ${styles[trail.terrain]}`;
  chip.textContent = TERRAIN_LABELS[trail.terrain];
  const link = document.createElement("a");
  link.className = styles.popupLink;
  link.href = href;
  link.textContent = "View trail →";
  link.addEventListener("click", (event) => {
    // A plain click stays in the app; new-tab clicks keep the browser's behaviour.
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    onOpen(trail.id);
  });
  body.append(name, chip, link);
  root.append(body);
  return root;
}

/** Several trails from one trailhead: a list to pick from. */
function groupContent(trails: TrailSearchItem[], titles: Map<string, string>, onPick: (id: string) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = `${styles.popup} ${styles.popupGroup}`;
  const heading = document.createElement("p");
  heading.className = styles.popupGroupHeading;
  heading.textContent = `${trails.length} trails from here`;
  const list = document.createElement("ul");
  for (const trail of trails) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = styles.popupGroupItem;
    const name = document.createElement("span");
    name.textContent = titles.get(trail.id) ?? trail.name;
    const chip = document.createElement("span");
    chip.className = `${styles.terrainTag} ${styles[trail.terrain]}`;
    chip.textContent = TERRAIN_LABELS[trail.terrain];
    button.append(name, chip);
    button.addEventListener("click", () => onPick(trail.id));
    item.append(button);
    list.append(item);
  }
  root.append(heading, list);
  return root;
}

export interface ExploreMapProps {
  trails: TrailSearchItem[];
  titles: Map<string, string>;
  /** The card under the pointer or keyboard focus. */
  hoveredId: string | null;
  /** The trail picked on the map (its card is highlighted too). */
  selectedId: string | null;
  /**
   * Where to start, read when the map mounts (the URL's map=, so a shared
   * link or a trip to the list and back keeps its place); null fits the map
   * to the first results instead.
   */
  getInitialView: () => MapView | null;
  /**
   * Changes when the results are for a new search (not a new map area);
   * null while a search is loading. With `fitToResults` the map fits itself
   * to each new set; without, it only notes the key, so the set isn't fitted
   * later either.
   */
  fitKey: string | null;
  fitToResults: boolean;
  /** "Search as I move the map". */
  follow: boolean;
  onFollowChange: (follow: boolean) => void;
  onSelect: (id: string | null) => void;
  onOpen: (id: string) => void;
  onViewChange: (view: MapView) => void;
  /** The visible area: on load, then after each move settles. Null when there is no map. */
  onBoundsChange: (bounds: Bounds | null) => void;
}

function visibleBounds(map: MapLibreMap): Bounds {
  const b = map.getBounds();
  return { west: b.getWest(), south: b.getSouth(), east: b.getEast(), north: b.getNorth() };
}

export default function ExploreMap(props: ExploreMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const popupRef = useRef<maplibregl.Popup | null>(null);
  const groupRef = useRef<maplibregl.Popup | null>(null);
  // The latest props, for the map's own event handlers (bound once).
  const latest = useRef(props);
  useEffect(() => {
    latest.current = props;
  });
  const fittedKey = useRef<string | null>(null);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  // Read once, so the first fit knows whether a position was given.
  const initialViewRef = useRef<MapView | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const initial = latest.current.getInitialView();
    initialViewRef.current = initial;
    if (maplibregl.getWorkerUrl() !== WORKER_URL) maplibregl.setWorkerUrl(WORKER_URL);
    let map: MapLibreMap;
    try {
      map = new maplibregl.Map({
        container,
        style: STYLE_URL,
        ...(initial ? { center: [initial.lng, initial.lat], zoom: initial.zoom } : { bounds: CANADA }),
        attributionControl: { compact: false },
        dragRotate: false,
        pitchWithRotate: false,
        cooperativeGestures: false,
      });
    } catch {
      // No WebGL: the list still works on its own, unfiltered by area.
      queueMicrotask(() => {
        setFailed(true);
        latest.current.onBoundsChange(null);
      });
      return;
    }
    mapRef.current = map;
    map.touchZoomRotate.disableRotation();
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");

    map.on("load", () => {
      map.addSource("trails", {
        type: "geojson",
        data: toFeatures(latest.current.trails),
        cluster: true,
        clusterRadius: 44,
        clusterMaxZoom: CLUSTER_MAX_ZOOM,
      });
      // The hovered and picked trails, never clustered, drawn on top.
      map.addSource("focus", { type: "geojson", data: toFeatures([]) });
      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "trails",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#283618",
          "circle-opacity": 0.88,
          "circle-radius": ["step", ["get", "point_count"], 15, 10, 19, 30, 24],
          "circle-stroke-color": "#fefae0",
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "trails",
        filter: ["has", "point_count"],
        layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": ["Noto Sans Bold"], "text-size": 13 },
        paint: { "text-color": "#fefae0" },
      });
      map.addLayer({
        id: "points",
        type: "circle",
        source: "trails",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": TERRAIN_COLOR,
          "circle-radius": 7,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });
      map.addLayer({
        id: "focus",
        type: "circle",
        source: "focus",
        paint: {
          "circle-color": TERRAIN_COLOR,
          "circle-radius": 10,
          "circle-stroke-color": "#bc6c25",
          "circle-stroke-width": 3.5,
        },
      });

      const showGroup = (ids: string[], at: [number, number]) => {
        const group = latest.current.trails.filter((t) => ids.includes(t.id));
        groupRef.current?.remove();
        groupRef.current = new maplibregl.Popup({ offset: 16, maxWidth: "280px", className: styles.mapPopup })
          .setLngLat(at)
          .setDOMContent(
            groupContent(group, latest.current.titles, (id) => {
              groupRef.current?.remove();
              latest.current.onSelect(id);
            }),
          )
          .addTo(map);
      };

      map.on("click", "clusters", async (event) => {
        const feature = event.features?.[0];
        if (!feature) return;
        const center = (feature.geometry as GeoJSON.Point).coordinates as [number, number];
        const source = map.getSource<GeoJSONSource>("trails");
        const clusterId = feature.properties.cluster_id as number;
        const count = feature.properties.point_count as number;
        const leaves = (await source?.getClusterLeaves(clusterId, count, 0)) ?? [];
        const coords = leaves.map((leaf) => (leaf.geometry as GeoJSON.Point).coordinates);
        const span = Math.max(
          Math.max(...coords.map((c) => c[0])) - Math.min(...coords.map((c) => c[0])),
          Math.max(...coords.map((c) => c[1])) - Math.min(...coords.map((c) => c[1])),
        );
        if (coords.length && span < SAME_SPOT_DEGREES) {
          showGroup(leaves.map((leaf) => leaf.properties?.id as string), center);
          return;
        }
        const zoom = await source?.getClusterExpansionZoom(clusterId);
        if (zoom != null) map.easeTo({ center, zoom });
      });
      const pick = (event: maplibregl.MapLayerMouseEvent) => {
        // Trails sharing a trailhead stack under one dot: offer them all.
        const ids = [...new Set((event.features ?? []).map((f) => f.properties.id as string))];
        if (ids.length > 1) showGroup(ids, [event.lngLat.lng, event.lngLat.lat]);
        else if (ids[0]) latest.current.onSelect(ids[0]);
      };
      map.on("click", "points", pick);
      map.on("click", "focus", pick);
      for (const layer of ["clusters", "points", "focus"]) {
        map.on("mouseenter", layer, () => (map.getCanvas().style.cursor = "pointer"));
        map.on("mouseleave", layer, () => (map.getCanvas().style.cursor = ""));
      }
      setReady(true);
    });

    // The size and position are known already, before any tiles: the list
    // can search this area straight away.
    latest.current.onBoundsChange(visibleBounds(map));
    let areaTimer: number | undefined;
    map.on("moveend", () => {
      const center = map.getCenter();
      latest.current.onViewChange({ lat: center.lat, lng: center.lng, zoom: map.getZoom() });
      window.clearTimeout(areaTimer);
      areaTimer = window.setTimeout(() => latest.current.onBoundsChange(visibleBounds(map)), AREA_DEBOUNCE_MS);
    });
    map.on("error", (event) => {
      // A missing tile now and then is fine; a style that never loads is not.
      if (!map.isStyleLoaded() && !map.loaded()) console.warn("Map:", event.error?.message);
    });

    // The pane resizes with the layout (Map/List toggle, sidebar width).
    // A resize changes the visible area without a moveend.
    const observer = new ResizeObserver(() => {
      map.resize();
      window.clearTimeout(areaTimer);
      areaTimer = window.setTimeout(() => latest.current.onBoundsChange(visibleBounds(map)), AREA_DEBOUNCE_MS);
    });
    observer.observe(container);
    return () => {
      window.clearTimeout(areaTimer);
      observer.disconnect();
      popupRef.current?.remove();
      groupRef.current?.remove();
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // New results: update the markers, and fit to them when it's a new search.
  const { trails, fitKey, fitToResults } = props;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    map.getSource<GeoJSONSource>("trails")?.setData(toFeatures(trails));
    if (fitKey === null || fitKey === fittedKey.current) return;
    const first = fittedKey.current === null;
    fittedKey.current = fitKey;
    // A shared or reloaded link keeps its map position, and results from
    // the map's own area are on screen already.
    if ((first && initialViewRef.current) || !fitToResults) return;
    const located = trails.filter((t) => t.latitude != null && t.longitude != null);
    if (!located.length) return;
    const bounds = new maplibregl.LngLatBounds();
    for (const trail of located) bounds.extend([trail.longitude!, trail.latitude!]);
    map.fitBounds(bounds, { padding: FIT_PADDING, maxZoom: CLUSTER_MAX_ZOOM, duration: first ? 0 : 600 });
  }, [trails, fitKey, fitToResults, ready]);

  // Hover and selection: the focus layer, and the selected trail's popup.
  const { hoveredId, selectedId } = props;
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const ids = new Set([hoveredId, selectedId].filter(Boolean));
    map.getSource<GeoJSONSource>("focus")?.setData(toFeatures(trails.filter((t) => ids.has(t.id))));
  }, [hoveredId, selectedId, trails, ready]);

  useEffect(() => {
    const map = mapRef.current;
    // Cleared first, so the old popup's close doesn't read as "deselect".
    const previous = popupRef.current;
    popupRef.current = null;
    previous?.remove();
    groupRef.current?.remove();
    if (!map || !ready || !selectedId) return;
    const trail = latest.current.trails.find((t) => t.id === selectedId);
    if (!trail || trail.latitude == null || trail.longitude == null) return;
    const popup = new maplibregl.Popup({ offset: 14, maxWidth: "260px", focusAfterOpen: false, className: styles.mapPopup })
      .setLngLat([trail.longitude, trail.latitude])
      .setDOMContent(
        popupContent(trail, latest.current.titles.get(trail.id) ?? trail.name, (id) => latest.current.onOpen(id)),
      )
      .addTo(map);
    popup.on("close", () => {
      // Closed by its × or a click elsewhere on the map, not by a new pick.
      if (popupRef.current === popup) latest.current.onSelect(null);
    });
    popupRef.current = popup;
  }, [selectedId, ready]);

  if (failed) {
    return (
      <div className={styles.mapPlaceholder} role="status">
        <p>The map couldn&apos;t load in this browser. The list has every trail.</p>
      </div>
    );
  }

  return (
    <div className={styles.mapFrame}>
      <div ref={containerRef} className={styles.mapCanvas} role="region" aria-label="Map of the trails in the list" />
      {!ready && (
        <div className={`${styles.mapPlaceholder} ${styles.mapLoading}`} aria-hidden="true">
          <span>Loading map…</span>
        </div>
      )}
      {ready && (
        <label className={styles.followToggle}>
          <input
            type="checkbox"
            checked={props.follow}
            onChange={(event) => props.onFollowChange(event.target.checked)}
          />
          Search as I move the map
        </label>
      )}
      <ul className={styles.legend} aria-label="Marker colours">
        {(Object.keys(TERRAIN_LABELS) as Terrain[]).map((terrain) => (
          <li key={terrain}>
            <span className={styles.legendDot} style={{ background: TERRAIN_COLORS[terrain] }} aria-hidden="true" />
            {TERRAIN_LABELS[terrain]}
          </li>
        ))}
      </ul>
    </div>
  );
}
