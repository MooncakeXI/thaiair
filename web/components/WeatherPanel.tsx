"use client";

import {useEffect, useState} from "react";
import type {Station} from "@/lib/types";
import {loadWeather, weatherAt, weatherCondition, type WeatherPayload} from "@/lib/weather";

export function WeatherPanel({station, targetTime}: {station: Station; targetTime?: string}) {
  const [result, setResult] = useState<{stationId: string; data?: WeatherPayload; error?: string}>({stationId: ""});

  useEffect(() => {
    let active = true;
    loadWeather(station)
      .then((data) => active && setResult({stationId: station.station_id, data}))
      .catch(() => active && setResult({stationId: station.station_id, error: "โหลดสภาพอากาศไม่สำเร็จ"}));
    return () => { active = false; };
  }, [station]);

  const weather = result.stationId === station.station_id && result.data
    ? weatherAt(result.data, targetTime)
    : null;
  const condition = weatherCondition(weather?.code ?? null);

  return (
    <section className="weather-panel" aria-label="สภาพอากาศ">
      <div className="section-heading">
        <div><span>สภาพอากาศ</span><strong>บริเวณสถานีนี้</strong></div>
        <small>Open-Meteo</small>
      </div>
      {result.stationId === station.station_id && result.error ? (
        <p className="weather-error">{result.error}</p>
      ) : (
        <div className={`weather-grid ${weather ? "" : "is-loading"}`}>
          <div><span>อุณหภูมิ</span><strong>{weather?.temperature ?? "—"}<small>°C</small></strong></div>
          <div><span>รู้สึกเหมือน</span><strong>{weather?.feelsLike ?? "—"}<small>°C</small></strong></div>
          <div><span>โอกาสฝน</span><strong>{weather?.rainChance ?? "—"}<small>%</small></strong></div>
          <div className="weather-condition"><b aria-hidden="true">{condition.icon}</b><span>{weather ? condition.label : "กำลังโหลด…"}</span></div>
        </div>
      )}
    </section>
  );
}
