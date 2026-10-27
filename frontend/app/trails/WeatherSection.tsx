"use client";

import { useEffect, useState } from "react";
import ui from "@/components/ui.module.css";
import { getTrailForecast, type ForecastDay, type TrailForecast } from "@/lib/forecastApi";
import {
  formatDegrees,
  formatElevation,
  formatPrecip,
  formatSnow,
  formatTemperature,
  formatWind,
  type UnitSystem,
} from "@/lib/units";
import {
  AVALANCHE_CANADA_URL,
  clockTime,
  dayName,
  describeWeather,
  environmentCanadaUrl,
  shortDate,
  showAvalancheLink,
  todayIn,
  type WeatherIcon,
} from "@/lib/weather";
import styles from "./WeatherSection.module.css";

export type ForecastState = { status: "loading" } | { status: "ready"; forecast: TrailForecast } | { status: "none" };

/**
 * The trail's forecast, fetched once the page has rendered. Any failure
 * (no coordinates, Open-Meteo down, offline) is "none": weather is a nicety
 * and must never break the page.
 */
export function useTrailForecast(trailId: string): ForecastState {
  const [state, setState] = useState<{ id: string; value: ForecastState } | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getTrailForecast(trailId, controller.signal)
      .then((forecast) =>
        setState({ id: trailId, value: forecast && forecast.trailhead.days.length ? { status: "ready", forecast } : { status: "none" } }),
      )
      .catch((error: unknown) => {
        if ((error as { name?: string }).name !== "AbortError") setState({ id: trailId, value: { status: "none" } });
      });
    return () => controller.abort();
  }, [trailId]);
  return state?.id === trailId ? state.value : { status: "loading" };
}

function Icon({ icon }: { icon: WeatherIcon }) {
  const sun = <circle cx="16" cy="16" r="6" className={styles.sun} />;
  const rays = (
    <g className={styles.rays}>
      {[0, 45, 90, 135, 180, 225, 270, 315].map((angle) => (
        <line key={angle} x1="16" y1="5" x2="16" y2="2" transform={`rotate(${angle} 16 16)`} />
      ))}
    </g>
  );
  const cloud = (x = 0, y = 0) => (
    <path
      d="M11 31h17a6 6 0 0 0 .6-12A8 8 0 0 0 13.3 17 6.5 6.5 0 0 0 11 31Z"
      transform={`translate(${x} ${y})`}
      className={styles.cloud}
    />
  );
  const drops = (count: number) => (
    <g className={styles.drops}>
      {Array.from({ length: count }, (_, i) => (
        <line key={i} x1={14 + i * 6} y1="35" x2={12 + i * 6} y2="40" />
      ))}
    </g>
  );
  const flakes = (
    <g className={styles.flakes}>
      {[14, 20, 26].map((x, i) => (
        <circle key={x} cx={x} cy={i % 2 ? 39 : 36} r="1.6" />
      ))}
    </g>
  );
  let body;
  switch (icon) {
    case "clear":
      body = (
        <g transform="translate(4 4)">
          {sun}
          {rays}
        </g>
      );
      break;
    case "partly":
      body = (
        <>
          <g transform="translate(-1 -2)">
            {sun}
            {rays}
          </g>
          {cloud(4, 0)}
        </>
      );
      break;
    case "fog":
      body = (
        <>
          {cloud(2, -4)}
          <g className={styles.fog}>
            <line x1="8" y1="32" x2="34" y2="32" />
            <line x1="12" y1="37" x2="38" y2="37" />
          </g>
        </>
      );
      break;
    case "drizzle":
      body = (
        <>
          {cloud(2, -2)}
          {drops(2)}
        </>
      );
      break;
    case "rain":
      body = (
        <>
          {cloud(2, -2)}
          {drops(3)}
        </>
      );
      break;
    case "freezing":
      body = (
        <>
          {cloud(2, -2)}
          {drops(2)}
          <circle cx="32" cy="38" r="1.6" className={styles.flakes} />
        </>
      );
      break;
    case "snow":
      body = (
        <>
          {cloud(2, -2)}
          {flakes}
        </>
      );
      break;
    case "storm":
      body = (
        <>
          {cloud(2, -2)}
          <path d="M22 31l-4 6h5l-3 6" className={styles.bolt} />
        </>
      );
      break;
    default:
      body = cloud(2, 2);
  }
  return (
    <svg viewBox="0 0 44 44" className={styles.icon} aria-hidden="true">
      {body}
    </svg>
  );
}

function DayCard({ day, today, units }: { day: ForecastDay; today: string; units: UnitSystem }) {
  const weather = describeWeather(day.weather_code);
  const snow = day.snowfall_cm != null && day.snowfall_cm > 0;
  return (
    <li className={styles.day}>
      <p className={styles.dayName}>
        {dayName(day.date, today)} <span className={styles.date}>{shortDate(day.date)}</span>
      </p>
      <Icon icon={weather.icon} />
      <p className={styles.condition}>{weather.label}</p>
      {day.temp_max_c != null && day.temp_min_c != null && (
        <p className={styles.temps}>
          <span className={styles.high}>{formatTemperature(day.temp_max_c, units)}</span>
          <span className={styles.low}>
            <span className={ui.srOnly}>low </span>
            {formatDegrees(day.temp_min_c, units)}
          </span>
        </p>
      )}
      <dl className={styles.facts}>
        {day.precip_probability_pct != null && (
          <div>
            <dt>Precip</dt>
            <dd>{day.precip_probability_pct}%</dd>
          </div>
        )}
        {day.precip_mm != null && (
          <div>
            <dt>Amount</dt>
            <dd>{formatPrecip(day.precip_mm, units)}</dd>
          </div>
        )}
        {snow && (
          <div>
            <dt>Snow</dt>
            <dd>{formatSnow(day.snowfall_cm!, units)}</dd>
          </div>
        )}
        {day.wind_max_kmh != null && (
          <div>
            <dt>Wind</dt>
            <dd>{formatWind(day.wind_max_kmh, units)}</dd>
          </div>
        )}
        {day.sunrise && (
          <div className={styles.sunTime}>
            <dt>Sunrise</dt>
            <dd>{clockTime(day.sunrise)}</dd>
          </div>
        )}
        {day.sunset && (
          <div className={styles.sunTime}>
            <dt>Sunset</dt>
            <dd>{clockTime(day.sunset)}</dd>
          </div>
        )}
      </dl>
    </li>
  );
}

export function WeatherSkeleton({ className }: { className?: string }) {
  return (
    <section className={className} aria-busy="true" aria-label="Loading the weather forecast">
      <h2 className={styles.title}>Weather</h2>
      <ul className={styles.days}>
        {Array.from({ length: 5 }, (_, i) => (
          <li key={i} className={`${ui.skeleton} ${styles.skeletonDay}`} />
        ))}
      </ul>
    </section>
  );
}

export default function WeatherSection({
  state,
  units,
  latitude,
  longitude,
  provinceCode,
  countryCode,
  className,
}: {
  state: ForecastState;
  units: UnitSystem;
  latitude: number | null;
  longitude: number | null;
  provinceCode: string | null;
  countryCode: string;
  className?: string;
}) {
  const [point, setPoint] = useState<"trailhead" | "summit">("trailhead");
  if (state.status === "loading") return <WeatherSkeleton className={className} />;
  if (state.status === "none") return null;

  const { forecast } = state;
  const shown = point === "summit" && forecast.summit ? forecast.summit : forecast.trailhead;
  const today = todayIn(forecast.timezone);
  const avalanche = showAvalancheLink(provinceCode, countryCode);

  return (
    <section className={className} aria-labelledby="weather-title">
      <div className={styles.header}>
        <h2 id="weather-title" className={styles.title}>
          Weather
        </h2>
        {forecast.summit && (
          <div className={ui.segmented} role="group" aria-label="Forecast location">
            <button type="button" aria-pressed={point === "trailhead"} onClick={() => setPoint("trailhead")}>
              Trailhead
            </button>
            <button type="button" aria-pressed={point === "summit"} onClick={() => setPoint("summit")}>
              Summit
            </button>
          </div>
        )}
      </div>
      <p className={styles.where}>
        {point === "summit" && forecast.summit ? "At the high point" : "At the trailhead"}
        {shown.elevation_m != null && `, ${formatElevation(shown.elevation_m, units)}`} · next 5 days
      </p>

      <ul className={styles.days} tabIndex={0} aria-label="Five-day forecast">
        {shown.days.map((day) => (
          <DayCard key={day.date} day={day} today={today} units={units} />
        ))}
      </ul>

      <p className={styles.note}>
        Mountain weather changes quickly. Check official forecasts before you go:{" "}
        {countryCode === "CA" && latitude != null && longitude != null && (
          <>
            <a href={environmentCanadaUrl(latitude, longitude)} target="_blank" rel="noopener noreferrer" className={styles.link}>
              Environment Canada
            </a>
            {avalanche ? " and " : "."}
          </>
        )}
        {avalanche && (
          <>
            <a href={AVALANCHE_CANADA_URL} target="_blank" rel="noopener noreferrer" className={styles.link}>
              Avalanche Canada
            </a>
            .
          </>
        )}
      </p>
      <p className={styles.credit}>
        Weather data by{" "}
        <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer" className={styles.link}>
          Open-Meteo.com
        </a>{" "}
        (
        <a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer" className={styles.link}>
          CC BY 4.0
        </a>
        ).
      </p>
    </section>
  );
}
