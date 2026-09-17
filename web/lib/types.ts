export type ForecastMethod = "model" | "persistence" | "unavailable";

export interface Reading {
  timestamp?: string;
  predicted_for?: string;
  pm25: number | null;
  level: string;
  color: string;
  method?: ForecastMethod;
  horizon_hours?: number;
}

export interface Station {
  station_id: string;
  location_id: number;
  sensor_id: number;
  name: string;
  latitude: number;
  longitude: number;
  provider: string;
  freshness: "fresh" | "stale" | "unavailable";
  feature_coverage: number;
  observed: Reading;
  forecasts: Reading[];
}

export interface MapData {
  generated_at: string;
  source_status: "live" | "snapshot";
  refreshed_at: string;
  refreshing: boolean;
  available_horizons: number[];
  stations: Station[];
}
