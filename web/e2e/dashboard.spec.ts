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
  await page.route("**/map-data", (route) => route.fulfill({
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
  await page.route("https://api.open-meteo.com/v1/forecast?*", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({
      hourly: {
        time: ["2026-09-17T03:00", "2026-09-17T06:00"],
        temperature_2m: [30, 31],
        apparent_temperature: [34, 35],
        precipitation_probability: [20, 70],
        weather_code: [1, 80],
      },
    }),
  }));
  await page.route("https://tile.openstreetmap.org/**", (route) => route.abort());

  await page.goto("/");
  await expect(page.getByRole("heading", {name: /วันนี้ถึงพรุ่งนี้/})).toBeVisible();
  await expect(page.getByRole("heading", {name: station.name})).toBeVisible();
  await page.getByLabel("เลือกเวลาพยากรณ์").fill("1");
  await expect(page.locator(".time-control strong")).toContainText("13:00");
  await expect(page.getByText("21", {exact: true})).toBeVisible();
  await expect(page.locator(".weather-grid strong").nth(0)).toContainText("31");
  await expect(page.locator(".weather-grid strong").nth(2)).toContainText("70");
  await expect(page.getByText("ใช้ค่าล่าสุด (baseline)")).toBeVisible();
});
