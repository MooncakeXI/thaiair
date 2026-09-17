"use client";

import {useCallback, useEffect, useMemo, useState} from "react";
import type {CSSProperties} from "react";
import {MapLoader} from "./MapLoader";
import {methodLabel, readingFor, thaiTime} from "@/lib/readings";
import type {MapData} from "@/lib/types";

const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/$/, "");

export function Dashboard() {
  const [data, setData] = useState<MapData | null>(null);
  const [error, setError] = useState("");
  const [slow, setSlow] = useState(false);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [horizonIndex, setHorizonIndex] = useState(0);
  const [query, setQuery] = useState("");

  const load = useCallback(async () => {
    const slowTimer = window.setTimeout(() => setSlow(true), 3500);
    try {
      const response = await fetch(`${API_URL}/map-data`);
      if (!response.ok) throw new Error(`API ตอบ ${response.status}`);
      const payload: MapData = await response.json();
      setError("");
      setData(payload);
      setSelectedId((current) => current && payload.stations.some((s) => s.station_id === current)
        ? current
        : payload.stations.find((s) => s.freshness === "fresh")?.station_id ?? payload.stations[0]?.station_id ?? null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "โหลดข้อมูลไม่สำเร็จ");
    } finally {
      window.clearTimeout(slowTimer);
      setSlow(false);
    }
  }, []);

  useEffect(() => {
    const initial = window.setTimeout(load, 0);
    const timer = window.setInterval(load, 5 * 60 * 1000);
    return () => {
      window.clearTimeout(initial);
      window.clearInterval(timer);
    };
  }, [load]);

  const horizons = data?.available_horizons ?? [0, 3, 6, 9, 12, 15, 18, 21, 24];
  const safeIndex = Math.min(horizonIndex, horizons.length - 1);
  const horizon = horizons[safeIndex];
  const selected = data?.stations.find((station) => station.station_id === selectedId);
  const reading = selected ? readingFor(selected, horizon) : null;
  const filtered = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("th");
    if (!needle) return data?.stations ?? [];
    return (data?.stations ?? []).filter((station) =>
      `${station.name} ${station.station_id}`.toLocaleLowerCase("th").includes(needle));
  }, [data, query]);

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="#top" aria-label="ThaiAir หน้าแรก">
          <span className="brand-mark" aria-hidden="true">อ</span><span>ThaiAir</span>
        </a>
        <div className={`live-badge ${data?.source_status === "live" ? "is-live" : "is-snapshot"}`}>
          {data?.source_status === "live" ? "ข้อมูลสด" : "ข้อมูลสำรอง"}
        </div>
      </header>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">Bangkok · PM2.5 forecast map</p>
          <h1>วันนี้ถึงพรุ่งนี้<br />อากาศเป็นไง?</h1>
        </div>
        <p>ข้อมูลตรวจวัดล่าสุดและพยากรณ์ล่วงหน้าทุก 3 ชั่วโมง รอบกรุงเทพฯ 25 กิโลเมตร</p>
      </section>

      <section className="workspace" aria-busy={!data && !error}>
        <div className="map-panel">
          {!data && !error && <div className="map-loading">{slow ? "กำลังปลุกเซิร์ฟเวอร์ฟรี อาจใช้เวลาประมาณหนึ่งนาที…" : "กำลังโหลดข้อมูลล่าสุด…"}</div>}
          {error && <div className="map-loading error-state"><strong>เชื่อมต่อข้อมูลไม่ได้</strong><span>{error}</span><button onClick={load}>ลองอีกครั้ง</button></div>}
          {data && <MapLoader stations={data.stations} horizon={horizon} selectedId={selectedId} onSelect={setSelectedId} />}
          <div className="map-legend" aria-label="ระดับ PM2.5">
            {[['#58bcd5','ดีมาก'],['#67c6a3','ดี'],['#f3d451','ปานกลาง'],['#f39b4a','เริ่มมีผลกระทบ'],['#e46666','มีผลกระทบ']].map(([color,label]) =>
              <span key={label}><i style={{backgroundColor: color}} />{label}</span>)}
          </div>
        </div>

        <aside className="detail-panel">
          <div className="time-control">
            <div><span>ช่วงเวลา</span><strong>{horizon === 0 ? "ตอนนี้" : `อีก ${horizon} ชั่วโมง`}</strong></div>
            <input
              aria-label="เลือกช่วงเวลาพยากรณ์"
              type="range"
              min="0"
              max={Math.max(horizons.length - 1, 0)}
              step="1"
              value={safeIndex}
              onChange={(event) => setHorizonIndex(Number(event.target.value))}
            />
            <div className="time-ticks"><span>ตอนนี้</span><span>+12 ชม.</span><span>+24 ชม.</span></div>
          </div>

          {selected && reading ? (
            <article className="reading-card" style={{"--tone": reading.color} as CSSProperties}>
              <div className="station-heading"><div><span>สถานีที่เลือก</span><h2>{selected.name}</h2></div><i /></div>
              <div className="reading"><strong>{reading.pm25 ?? "—"}</strong><span>µg/m³<br />PM2.5</span></div>
              <div className="level-pill">{reading.level || "ข้อมูลไม่พอ"}</div>
              <dl>
                <div><dt>{horizon === 0 ? "เวลาตรวจวัด" : "เวลาที่พยากรณ์"}</dt><dd>{thaiTime(horizon === 0 ? reading.timestamp : reading.predicted_for)}</dd></div>
                <div><dt>แหล่งข้อมูล</dt><dd>{selected.provider}</dd></div>
                <div><dt>วิธีคาดการณ์</dt><dd>{horizon === 0 ? "ค่าตรวจวัด" : methodLabel(reading.method)}</dd></div>
                <div><dt>ความสดของข้อมูล</dt><dd>{selected.freshness === "fresh" ? "ไม่เกิน 3 ชั่วโมง" : selected.freshness === "stale" ? "เก่ากว่า 3 ชั่วโมง" : "ข้อมูลเก่าเกินไป"}</dd></div>
              </dl>
              <p className="disclaimer">ค่าพยากรณ์จากแบบจำลองเพื่อการศึกษา ไม่ใช่คำแนะนำทางการแพทย์</p>
            </article>
          ) : <div className="empty-card">เลือกสถานีบนแผนที่เพื่อดูรายละเอียด</div>}

          <div className="station-browser">
            <label htmlFor="station-search">ค้นหาสถานี</label>
            <input id="station-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ชื่อหรือรหัสสถานี" />
            <div className="station-list">
              {filtered.map((station) => {
                const stationReading = readingFor(station, horizon);
                return <button className={station.station_id === selectedId ? "selected" : ""} key={station.station_id} onClick={() => setSelectedId(station.station_id)}>
                  <i style={{backgroundColor: stationReading.color}} /><span><strong>{station.name}</strong><small>{stationReading.pm25 === null ? "ข้อมูลไม่พอ" : `${stationReading.pm25} µg/m³`}</small></span>
                </button>;
              })}
            </div>
          </div>
        </aside>
      </section>

      <footer>
        <span>อัปเดตล่าสุด {thaiTime(data?.refreshed_at)}</span>
        <span>ข้อมูลจาก OpenAQ · แผนที่ © OpenStreetMap contributors</span>
      </footer>
    </main>
  );
}
