// Run: node 2_analytics/dashboard/test-dashboard-utils.js
const test = require("node:test");
const assert = require("node:assert/strict");
const {
  avgField,
  windowAverage,
  computeDeltaPct,
  deltaDirection,
  computeKpiDeltas,
  latestDateExclusive,
  weeklyStageAverages,
  groupByDay,
  groupByISOWeek,
  groupByMonth,
} = require("./dashboard-utils.js");

test("avgField ignores null and undefined", () => {
  const records = [{ v: 10 }, { v: null }, { v: 20 }, { v: undefined }];
  assert.equal(avgField(records, "v"), 15);
});

test("avgField returns null for empty input", () => {
  assert.equal(avgField([], "v"), null);
});

test("windowAverage buckets records into the correct 7-day window", () => {
  const records = [
    { date_day: "2026-07-28", v: 10 }, // prior week
    { date_day: "2026-08-02", v: 20 }, // current week
    { date_day: "2026-08-05", v: 30 }, // current week
  ];
  const cur = windowAverage(records, "date_day", "v", "2026-08-08", 7, 0);
  assert.equal(cur, 25);
});

test("windowAverage prior window excludes current window", () => {
  const records = [
    { date_day: "2026-07-20", v: 5 }, // outside both windows
    { date_day: "2026-07-28", v: 10 }, // prior window
    { date_day: "2026-08-05", v: 40 }, // current window
  ];
  const prior = windowAverage(records, "date_day", "v", "2026-08-08", 7, 7);
  assert.equal(prior, 10);
});

test("windowAverage returns null when the window has no data", () => {
  const records = [{ date_day: "2026-01-01", v: 1 }];
  assert.equal(windowAverage(records, "date_day", "v", "2026-08-08", 7, 0), null);
});

test("computeDeltaPct computes signed percent change", () => {
  assert.equal(computeDeltaPct(110, 100), 10);
  assert.equal(computeDeltaPct(90, 100), -10);
});

test("computeDeltaPct returns null when prior average missing or zero", () => {
  assert.equal(computeDeltaPct(50, null), null);
  assert.equal(computeDeltaPct(50, 0), null);
});

test("deltaDirection: recovery up is good, down is bad", () => {
  assert.equal(deltaDirection("recovery", 5), "good");
  assert.equal(deltaDirection("recovery", -5), "bad");
});

test("deltaDirection: rhr down is good, up is bad", () => {
  assert.equal(deltaDirection("rhr", -3), "good");
  assert.equal(deltaDirection("rhr", 3), "bad");
});

test("deltaDirection: strain is always neutral", () => {
  assert.equal(deltaDirection("strain", 20), "neutral");
  assert.equal(deltaDirection("strain", -20), "neutral");
});

test("deltaDirection: null delta is neutral regardless of metric", () => {
  assert.equal(deltaDirection("recovery", null), "neutral");
});

test("computeKpiDeltas returns null delta blocks when a window has no data", () => {
  const records = [{ date_day: "2026-08-05", v: 70 }];
  const out = computeKpiDeltas(records, "date_day", "v", "recovery", "2026-08-08");
  assert.equal(out.current7, 70);
  assert.equal(out.delta7, null);
});

test("computeKpiDeltas returns a direction-tagged delta7 when both windows have data", () => {
  const records = [
    { date_day: "2026-07-28", v: 60 }, // prior week
    { date_day: "2026-08-05", v: 70 }, // current week
  ];
  const out = computeKpiDeltas(records, "date_day", "v", "recovery", "2026-08-08");
  assert.equal(out.current7, 70);
  assert.ok(out.delta7.pct > 0);
  assert.equal(out.delta7.direction, "good");
});

test("latestDateExclusive returns the day after the max date_day", () => {
  const records = [{ date_day: "2026-08-01" }, { date_day: "2026-08-05" }];
  assert.equal(latestDateExclusive(records, "date_day"), "2026-08-06");
});

test("latestDateExclusive returns null for empty input", () => {
  assert.equal(latestDateExclusive([], "date_day"), null);
});

test("weeklyStageAverages splits sleep stage minutes into this-week vs last-week", () => {
  const sleeps = [
    { date_day: "2026-07-28", light_sleep_duration_minutes: 100, deep_sleep_duration_minutes: 60, rem_duration_minutes: 80, awake_duration_minutes: 10 },
    { date_day: "2026-08-05", light_sleep_duration_minutes: 120, deep_sleep_duration_minutes: 70, rem_duration_minutes: 90, awake_duration_minutes: 15 },
  ];
  const out = weeklyStageAverages(sleeps, "2026-08-08");
  assert.equal(out.light.current, 120);
  assert.equal(out.light.prior, 100);
  assert.equal(out.deep.current, 70);
  assert.equal(out.deep.prior, 60);
  assert.equal(out.rem.current, 90);
  assert.equal(out.rem.prior, 80);
  assert.equal(out.awake.current, 15);
  assert.equal(out.awake.prior, 10);
});

test("groupByDay returns one bucket per calendar day (identity grouping)", () => {
  const records = [
    { date_day: "2026-08-01", v: 10 },
    { date_day: "2026-08-02", v: 20 },
  ];
  const out = groupByDay(records, "date_day", ["v"]);
  assert.equal(out.length, 2);
  assert.equal(out[0].bucketStart, "2026-08-01");
  assert.equal(out[0].v, 10);
  assert.equal(out[1].bucketStart, "2026-08-02");
  assert.equal(out[1].v, 20);
});

test("groupByDay averages multiple records on the same day", () => {
  const records = [
    { date_day: "2026-08-01", v: 10 },
    { date_day: "2026-08-01", v: 30 },
  ];
  const out = groupByDay(records, "date_day", ["v"]);
  assert.equal(out.length, 1);
  assert.equal(out[0].v, 20);
});

test("groupByISOWeek buckets Mon-Sun into the same week starting on Monday", () => {
  const records = [
    { date_day: "2026-08-03", v: 10 }, // Monday
    { date_day: "2026-08-09", v: 30 }, // Sunday, same ISO week
    { date_day: "2026-08-10", v: 100 }, // Monday, next week
  ];
  const out = groupByISOWeek(records, "date_day", ["v"]);
  assert.equal(out.length, 2);
  assert.equal(out[0].bucketStart, "2026-08-03");
  assert.equal(out[0].v, 20);
  assert.equal(out[1].bucketStart, "2026-08-10");
  assert.equal(out[1].v, 100);
});

test("groupByMonth buckets by calendar month", () => {
  const records = [
    { date_day: "2026-08-01", v: 10 },
    { date_day: "2026-08-31", v: 30 },
    { date_day: "2026-09-01", v: 100 },
  ];
  const out = groupByMonth(records, "date_day", ["v"]);
  assert.equal(out.length, 2);
  assert.equal(out[0].bucketStart, "2026-08-01");
  assert.equal(out[0].v, 20);
  assert.equal(out[1].bucketStart, "2026-09-01");
  assert.equal(out[1].v, 100);
});

test("groupByPeriod functions sort buckets ascending regardless of input order", () => {
  const records = [
    { date_day: "2026-08-10", v: 1 },
    { date_day: "2026-08-01", v: 2 },
  ];
  const out = groupByDay(records, "date_day", ["v"]);
  assert.equal(out[0].bucketStart, "2026-08-01");
  assert.equal(out[1].bucketStart, "2026-08-10");
});
