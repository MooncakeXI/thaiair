import {describe, expect, it} from "vitest";
import {methodLabel, readingFor} from "./readings";
import type {Station} from "./types";

const station = {
  observed: {pm25: 12, level: "ดีมาก", color: "blue"},
  forecasts: [{horizon_hours: 3, pm25: 18, level: "ดี", color: "green", method: "model"}],
} as Station;

describe("readingFor", () => {
  it("returns observed data for now and the matching forecast for the future", () => {
    expect(readingFor(station, 0).pm25).toBe(12);
    expect(readingFor(station, 3).pm25).toBe(18);
    expect(readingFor(station, 6).pm25).toBeNull();
  });

  it("labels baseline forecasts honestly", () => {
    expect(methodLabel("persistence")).toContain("baseline");
  });
});
