"use client";

import {Fragment, useEffect} from "react";
import {CircleMarker, MapContainer, TileLayer, Tooltip, useMap} from "react-leaflet";
import type {Station} from "@/lib/types";
import {readingFor} from "@/lib/readings";

const BANGKOK: [number, number] = [13.7563, 100.5018];

function Focus({station}: {station?: Station}) {
  const map = useMap();
  useEffect(() => {
    if (station) map.flyTo([station.latitude, station.longitude], Math.max(map.getZoom(), 13));
  }, [map, station]);
  return null;
}

export function MapView({stations, horizon, selectedId, onSelect}: {
  stations: Station[];
  horizon: number;
  selectedId: string | null;
  onSelect: (stationId: string) => void;
}) {
  const selected = stations.find((station) => station.station_id === selectedId);
  return (
    <MapContainer center={BANGKOK} zoom={11} minZoom={9} maxZoom={16} preferCanvas>
      <TileLayer
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
      />
      {stations.map((station) => {
        const reading = readingFor(station, horizon);
        const selectedMarker = station.station_id === selectedId;
        return (
          <Fragment key={station.station_id}>
            <CircleMarker
              center={[station.latitude, station.longitude]}
              radius={selectedMarker ? 14 : 10}
              pathOptions={{color: "#fffdf8", fillOpacity: 0, opacity: .96, weight: selectedMarker ? 6 : 4}}
              interactive={false}
            />
            <CircleMarker
              center={[station.latitude, station.longitude]}
              radius={selectedMarker ? 9 : 6}
              pathOptions={{
                color: selectedMarker ? "#102b2a" : "#284744",
                fillColor: reading.color,
                fillOpacity: 1,
                opacity: 1,
                weight: selectedMarker ? 3 : 2,
              }}
              eventHandlers={{click: () => onSelect(station.station_id)}}
            >
              <Tooltip direction="top" offset={[0, -10]}>
                <strong>{station.name}</strong><br />
                {reading.pm25 === null ? "ข้อมูลไม่พอ" : `${reading.pm25} µg/m³ · ${reading.level}`}
              </Tooltip>
            </CircleMarker>
          </Fragment>
        );
      })}
      <Focus station={selected} />
    </MapContainer>
  );
}
