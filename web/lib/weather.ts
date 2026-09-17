import type {Station} from "./types";

export interface WeatherPayload {
  hourly: {
    time: string[];
    temperature_2m: Array<number | null>;
    apparent_temperature: Array<number | null>;
    precipitation_probability: Array<number | null>;
    weather_code: Array<number | null>;
  };
}

export interface WeatherReading {
  temperature: number | null;
  feelsLike: number | null;
  rainChance: number | null;
  code: number | null;
}

const requests = new Map<string, Promise<WeatherPayload>>();

export function loadWeather(station: Station): Promise<WeatherPayload> {
  const key = `${station.latitude.toFixed(3)},${station.longitude.toFixed(3)}`;
  const cached = requests.get(key);
  if (cached) return cached;

  const params = new URLSearchParams({
    latitude: String(station.latitude),
    longitude: String(station.longitude),
    hourly: "temperature_2m,apparent_temperature,precipitation_probability,weather_code",
    past_hours: "6",
    forecast_hours: "48",
    timezone: "GMT",
  });
  const request = fetch(`https://api.open-meteo.com/v1/forecast?${params}`)
    .then((response) => {
      if (!response.ok) throw new Error(`Open-Meteo ตอบ ${response.status}`);
      return response.json() as Promise<WeatherPayload>;
    })
    .catch((error) => {
      requests.delete(key);
      throw error;
    });
  requests.set(key, request);
  return request;
}

function utc(value: string): number {
  return Date.parse(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function weatherAt(payload: WeatherPayload, targetTime?: string): WeatherReading | null {
  if (!targetTime || !payload.hourly.time.length) return null;
  const target = utc(targetTime);
  let closest = 0;
  for (let index = 1; index < payload.hourly.time.length; index += 1) {
    if (Math.abs(utc(payload.hourly.time[index]) - target) < Math.abs(utc(payload.hourly.time[closest]) - target)) closest = index;
  }
  return {
    temperature: payload.hourly.temperature_2m[closest] ?? null,
    feelsLike: payload.hourly.apparent_temperature[closest] ?? null,
    rainChance: payload.hourly.precipitation_probability[closest] ?? null,
    code: payload.hourly.weather_code[closest] ?? null,
  };
}

export function weatherCondition(code: number | null): {icon: string; label: string} {
  if (code === null) return {icon: "·", label: "ไม่มีข้อมูล"};
  if (code === 0) return {icon: "☀", label: "ท้องฟ้าแจ่มใส"};
  if (code <= 2) return {icon: "⛅", label: "มีเมฆบางส่วน"};
  if (code === 3) return {icon: "☁", label: "เมฆมาก"};
  if (code <= 48) return {icon: "≋", label: "มีหมอก"};
  if (code <= 57 || (code >= 80 && code <= 82)) return {icon: "🌦", label: "ฝนโปรย"};
  if (code <= 67) return {icon: "🌧", label: "ฝนตก"};
  if (code <= 86) return {icon: "❄", label: "หิมะ"};
  return {icon: "⛈", label: "พายุฝนฟ้าคะนอง"};
}
