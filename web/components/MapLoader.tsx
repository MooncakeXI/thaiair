"use client";

import dynamic from "next/dynamic";
import type {Station} from "@/lib/types";

const ClientMap = dynamic(() => import("./MapView").then((module) => module.MapView), {
  ssr: false,
  loading: () => <div className="map-loading">กำลังเตรียมแผนที่…</div>,
});

export function MapLoader(props: {
  stations: Station[];
  horizon: number;
  selectedId: string | null;
  onSelect: (stationId: string) => void;
}) {
  return <ClientMap {...props} />;
}
