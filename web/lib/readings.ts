import type {Reading, Station} from "./types";

export function readingFor(station: Station, horizon: number): Reading {
  if (horizon === 0) return station.observed;
  return station.forecasts.find((item) => item.horizon_hours === horizon) ?? {
    pm25: null,
    level: "ข้อมูลไม่พอ",
    color: "#9aa7a5",
    method: "unavailable",
    horizon_hours: horizon,
  };
}

export function thaiTime(value?: string): string {
  if (!value) return "—";
  const normalized = /[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`;
  return new Intl.DateTimeFormat("th-TH", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Bangkok",
  }).format(new Date(normalized)) + " น.";
}

export function methodLabel(method?: string): string {
  if (method === "model") return "โมเดลพยากรณ์";
  if (method === "persistence") return "ใช้ค่าล่าสุด (baseline)";
  return "ข้อมูลไม่พอสำหรับพยากรณ์";
}
