import test, { afterEach } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import {
  cacheKey,
  forecastPoints,
  forecastUrl,
  getTrailForecast,
  parseForecast,
  readCached,
  type ForecastTrail,
} from "./forecastApi.ts";

// A saved live response (Lake Agnes Tea House at 1735 m and 2135 m, fetched
// 2026-10-26) stands in for Open-Meteo; it is never called.
const FIXTURE = JSON.parse(readFileSync(join(import.meta.dirname, "fixtures", "open_meteo_forecast.json"), "utf8"));
const clone = () => structuredClone(FIXTURE);

const TRAILS: Record<string, ForecastTrail> = {
  both: { id: "agnes", latitude: 51.4159, longitude: -116.2112, max_elevation_m: 2135, elevation_gain_m: 400 },
  flat: { id: "marsh", latitude: 51.18, longitude: -115.57, max_elevation_m: 1400, elevation_gain_m: 20 },
  unknown: { id: "mystery", latitude: 50.1, longitude: -122.9, max_elevation_m: null, elevation_gain_m: null },
  nowhere: { id: "nowhere", latitude: null, longitude: null, max_elevation_m: 2000, elevation_gain_m: 500 },
};

const query = (url: string) => Object.fromEntries(new URL(url).searchParams);

/** Stubs fetch and sessionStorage; records each Open-Meteo URL. */
function stubBrowser(respond: (url: string) => Response | Promise<Response>) {
  const urls: string[] = [];
  const store = new Map<string, string>();
  const storage = {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => void store.set(key, value),
  };
  Object.assign(globalThis, {
    window: { sessionStorage: storage },
    fetch: async (url: string) => {
      urls.push(url);
      return respond(url);
    },
  });
  return { urls, store };
}

// Single-location requests get one location object back, like Open-Meteo.
const openMeteo = (url: string) => {
  const body = query(url).latitude.includes(",") ? clone() : clone()[0];
  return new Response(JSON.stringify(body), { status: 200 });
};

const realFetch = globalThis.fetch;
afterEach(() => {
  Object.assign(globalThis, { fetch: realFetch });
  delete (globalThis as { window?: unknown }).window;
});

test("forecast has trailhead and summit days", () => {
  const points = forecastPoints(TRAILS.both)!;
  const forecast = parseForecast(clone(), points, new Date("2026-10-26T12:00:00Z"));
  assert.equal(forecast.timezone, "America/Edmonton");
  assert.equal(forecast.trailhead.elevation_m, 1735);
  assert.equal(forecast.summit?.elevation_m, 2135);
  assert.equal(forecast.trailhead.days.length, 5);
  assert.equal(forecast.summit?.days.length, 5);
  const day = forecast.trailhead.days[0];
  assert.deepEqual(Object.keys(day).sort(), [
    "date", "precip_mm", "precip_probability_pct", "snowfall_cm", "sunrise", "sunset",
    "temp_max_c", "temp_min_c", "weather_code", "wind_max_kmh",
  ]);
  assert.equal(day.date, "2026-10-26");
  assert.ok(day.sunrise?.startsWith("2026-10-26T"));
  // The high point is colder than the trailhead.
  assert.ok(forecast.summit!.days[0].temp_max_c! < day.temp_max_c!);
  assert.equal(forecast.fetched_at, "2026-10-26T12:00:00.000Z");
});

test("one request asks for both elevations", () => {
  const params = query(forecastUrl(forecastPoints(TRAILS.both)!));
  assert.equal(params.latitude, "51.4159,51.4159");
  assert.equal(params.longitude, "-116.2112,-116.2112");
  // Trailhead = high point - elevation gain.
  assert.equal(params.elevation, "1735,2135");
  assert.equal(params.forecast_days, "5");
  assert.equal(params.timezone, "auto");
  assert.equal(params.wind_speed_unit, "kmh");
  assert.ok(forecastUrl(forecastPoints(TRAILS.both)!).startsWith("https://api.open-meteo.com/v1/forecast?"));
});

test("no summit when the high point is barely above the trailhead", () => {
  const points = forecastPoints(TRAILS.flat)!;
  assert.equal(points.summit_m, null);
  const params = query(forecastUrl(points));
  assert.equal(params.elevation, "1380");
  assert.ok(!params.latitude.includes(","));
});

test("without elevation data the trailhead uses Open-Meteo's terrain", () => {
  const points = forecastPoints(TRAILS.unknown)!;
  assert.equal(points.summit_m, null);
  assert.equal(query(forecastUrl(points)).elevation, undefined);
});

test("only the high point known: the trailhead asks for the terrain model", () => {
  const points = forecastPoints({ id: "x", latitude: 50.1, longitude: -122.9, max_elevation_m: 2100, elevation_gain_m: null })!;
  assert.deepEqual([points.trailhead_m, points.summit_m], [null, 2100]);
  assert.equal(query(forecastUrl(points)).elevation, "nan,2100");
});

test("summit is dropped when Open-Meteo's trailhead is nearly as high", () => {
  const points = { latitude: 51.4, longitude: -116.2, trailhead_m: null, summit_m: 2135 };
  const body = clone();
  body[0].elevation = 2066.0;
  assert.equal(parseForecast(body, points, new Date()).summit, null);
  body[0].elevation = 1900.0;
  assert.equal(parseForecast(body, points, new Date()).summit?.elevation_m, 2135);
});

test("a trail without coordinates has no forecast and never calls Open-Meteo", async () => {
  const { urls } = stubBrowser(openMeteo);
  assert.equal(forecastPoints(TRAILS.nowhere), null);
  assert.equal(await getTrailForecast(TRAILS.nowhere), null);
  assert.deepEqual(urls, []);
});

test("malformed responses throw", () => {
  const points = forecastPoints(TRAILS.both)!;
  const bad = [
    { error: true, reason: "Cannot initialize WeatherCode from invalid String value" },
    [FIXTURE[0]], // one location when two were asked for
    "<html>Bad gateway</html>",
    [{ ...FIXTURE[0], daily: { ...FIXTURE[0].daily, sunset: [] } }, FIXTURE[1]],
  ];
  for (const body of bad) assert.throws(() => parseForecast(body, points, new Date()));
});

test("forecasts are cached per trail in sessionStorage", async () => {
  const { urls, store } = stubBrowser(openMeteo);
  for (let i = 0; i < 3; i++) {
    await getTrailForecast(TRAILS.both);
    await getTrailForecast(TRAILS.flat);
  }
  assert.equal(urls.length, 2);
  assert.ok(store.has(cacheKey("agnes", forecastPoints(TRAILS.both)!)));
});

test("the cache lasts an hour", () => {
  const key = "k";
  const forecast = parseForecast(clone(), forecastPoints(TRAILS.both)!, new Date("2026-10-26T12:00:00Z"));
  const storage = { getItem: () => JSON.stringify(forecast) };
  const start = Date.parse("2026-10-26T12:00:00Z");
  assert.ok(readCached(storage, key, start + 59 * 60 * 1000));
  assert.equal(readCached(storage, key, start + 61 * 60 * 1000), null);
  assert.equal(readCached({ getItem: () => "not json" }, key), null);
  assert.equal(readCached(null, key), null);
});

test("the cache key changes when the catalogue changes", async () => {
  const { urls } = stubBrowser(openMeteo);
  await getTrailForecast(TRAILS.both);
  await getTrailForecast({ ...TRAILS.both, max_elevation_m: 2200 });
  assert.equal(urls.length, 2);
  assert.equal(query(urls[1]).elevation, "1800,2200");
});

test("Open-Meteo failures throw and are never cached", async () => {
  const { urls, store } = stubBrowser(() => new Response(JSON.stringify({ error: true, reason: "Too many requests" }), { status: 429 }));
  await assert.rejects(getTrailForecast(TRAILS.both));
  const malformed = stubBrowser(() => new Response(JSON.stringify([FIXTURE[0]]), { status: 200 }));
  await assert.rejects(getTrailForecast(TRAILS.both));
  assert.equal(urls.length, 1);
  assert.equal(store.size + malformed.store.size, 0);
});

test("works without sessionStorage (blocked storage)", async () => {
  const { urls } = stubBrowser(openMeteo);
  Object.assign(globalThis, { window: {} });
  assert.ok(await getTrailForecast(TRAILS.both));
  assert.equal(urls.length, 1);
});
