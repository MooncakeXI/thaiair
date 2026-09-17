import {describe, expect, it} from "vitest";
import {weatherAt, weatherCondition, type WeatherPayload} from "./weather";

const payload: WeatherPayload = {
  hourly: {
    time: ["2026-09-17T10:00", "2026-09-17T11:00"],
    temperature_2m: [30, 31],
    apparent_temperature: [34, 35],
    precipitation_probability: [20, 70],
    weather_code: [1, 80],
  },
};

describe("weatherAt", () => {
  it("เลือกชั่วโมงที่ใกล้เวลาเป้าหมายที่สุด", () => {
    expect(weatherAt(payload, "2026-09-17T10:45:00")).toEqual({
      temperature: 31,
      feelsLike: 35,
      rainChance: 70,
      code: 80,
    });
  });
});

it("แปล WMO code เป็นคำที่อ่านง่าย", () => {
  expect(weatherCondition(0).label).toBe("ท้องฟ้าแจ่มใส");
  expect(weatherCondition(95).label).toBe("พายุฝนฟ้าคะนอง");
});
