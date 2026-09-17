import {expect, test} from "@playwright/test";

const station = {
  station_id: "oa:42:4202",
  location_id: 42,
  sensor_id: 4202,
  name: "สถานีบางกอกน้อย",
  latitude: 13.7563,
  longitude: 100.5018,
  provider: "OpenAQ",
  freshness: "fresh",
  feature_coverage: 1,
  observed: {timestamp: "2026-09-17T03:00:00", pm25: 18, level: "ดี", color: "#67c6a3"},
  forecasts: [{horizon_hours: 3, predicted_for: "2026-09-17T06:00:00", pm25: 21, method: "persistence", level: "ดี", color: "#67c6a3"}],
};

test("เลือกเวลาพยากรณ์และเห็นค่าของสถานี", async ({page}) => {
  await page.route("http://localhost:8000/map-data", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      generated_at: "2026-09-17T03:05:00Z",
      source_status: "live",
      refreshed_at: "2026-09-17T03:00:00Z",
      refreshing: false,
      available_horizons: [0, 3],
      stations: [station],
    }),
  }));
  await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());

  await page.goto("/");
  await expect(page.getByRole("heading", {name: /วันนี้ถึงพรุ่งนี้/})).toBeVisible();
  await expect(page.getByRole("heading", {name: station.name})).toBeVisible();
  await page.getByLabel("เลือกช่วงเวลาพยากรณ์").fill("1");
  await expect(page.getByText("อีก 3 ชั่วโมง")).toBeVisible();
  await expect(page.getByText("21", {exact: true})).toBeVisible();
  await expect(page.getByText("ใช้ค่าล่าสุด (baseline)")).toBeVisible();
});
