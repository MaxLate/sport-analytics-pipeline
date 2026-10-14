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
  calendarDate,
  filterByPeriod,
  mainSleepEpisodes,
  pairedValues,
  pearsonCorrelation,
  groupSleepPerformanceByMoonPhase,
  filterTrainingActivities,
  summarizeTraining,
  stackTrainingHours,
  compareSports,
  recentSessions,
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

// --- Period filtering and sleep-episode selection ---------------------------

test("calendarDate keeps the calendar day from an ISO timestamp", () => {
  assert.equal(calendarDate("2026-09-24T00:00:00"), "2026-09-24");
});

test("filterByPeriod 30d includes the boundary date and excludes the day before it", () => {
  const records = [
    { date_day: "2026-08-29" },
    { date_day: "2026-08-30T00:00:00" },
    { date_day: "2026-09-28" },
    { date_day: "2026-09-29" },
  ];
  const filtered = filterByPeriod(records, "date_day", "30d", "2026-09-28");
  assert.deepEqual(filtered.map((r) => calendarDate(r.date_day)), ["2026-08-30", "2026-09-28"]);
});

test("filterByPeriod 90d includes 2026-07-01 and excludes 2026-06-30", () => {
  const records = [{ date_day: "2026-06-30" }, { date_day: "2026-07-01" }, { date_day: "2026-09-28" }];
  const filtered = filterByPeriod(records, "date_day", "90d", "2026-09-28");
  assert.deepEqual(filtered.map((r) => calendarDate(r.date_day)), ["2026-07-01", "2026-09-28"]);
});

test("filterByPeriod 1y includes the same calendar date one year earlier", () => {
  const records = [
    { date_day: "2025-09-27" },
    { date_day: "2025-09-28" },
    { date_day: "2026-09-28" },
  ];
  const filtered = filterByPeriod(records, "date_day", "1y", "2026-09-28");
  assert.deepEqual(filtered.map((r) => calendarDate(r.date_day)), ["2025-09-28", "2026-09-28"]);
});

test("filterByPeriod all keeps every date through the reference date", () => {
  const records = [{ date_day: "2020-01-01" }, { date_day: "2026-09-29" }];
  const filtered = filterByPeriod(records, "date_day", "all", "2026-09-28");
  assert.deepEqual(filtered.map((r) => calendarDate(r.date_day)), ["2020-01-01"]);
});

test("mainSleepEpisodes keeps only nap === false", () => {
  const records = [{ nap: false, id: 1 }, { nap: true, id: 2 }, { nap: null, id: 3 }];
  assert.deepEqual(mainSleepEpisodes(records).map((r) => r.id), [1]);
});

// --- Correlation and moon-phase grouping -------------------------------------

test("pairedValues drops a null on either axis and keeps the other records", () => {
  const records = [
    { moon_illumination: 10, sleep_performance: 80, temperature_min_celsius: null },
    { moon_illumination: null, sleep_performance: 70, temperature_min_celsius: 5 },
    { moon_illumination: 90, sleep_performance: 60, temperature_min_celsius: 12 },
  ];
  assert.deepEqual(pairedValues(records, "moon_illumination", "sleep_performance"), [
    { x: 10, y: 80 },
    { x: 90, y: 60 },
  ]);
  assert.deepEqual(pairedValues(records, "temperature_min_celsius", "sleep_performance"), [
    { x: 5, y: 70 },
    { x: 12, y: 60 },
  ]);
});

test("pearsonCorrelation returns signed r and the association label", () => {
  const positive = pearsonCorrelation([
    { x: 1, y: 2 },
    { x: 2, y: 4 },
    { x: 3, y: 6 },
  ]);
  assert.equal(positive.n, 3);
  assert.equal(positive.r, 1);
  assert.equal(positive.label, "strong association");

  const weak = pearsonCorrelation([
    { x: 1, y: 1 },
    { x: 2, y: 1 },
    { x: 3, y: 2 },
    { x: 4, y: 1 },
  ]);
  assert.equal(Number(weak.r.toFixed(4)), 0.2582);
  assert.equal(weak.label, "weak association");

  const negative = pearsonCorrelation([
    { x: 1, y: 6 },
    { x: 2, y: 4 },
    { x: 3, y: 2 },
  ]);
  assert.equal(negative.r, -1);
  assert.equal(negative.label, "strong association");
});

test("pearsonCorrelation is unavailable for too few points or zero variance", () => {
  assert.equal(pearsonCorrelation([{ x: 1, y: 2 }, { x: 2, y: 3 }]).r, null);
  assert.equal(pearsonCorrelation([{ x: 1, y: 2 }, { x: 1, y: 3 }, { x: 1, y: 4 }]).label, "unavailable");
});

test("groupSleepPerformanceByMoonPhase averages performance and omits empty phases", () => {
  const grouped = groupSleepPerformanceByMoonPhase([
    { moon_phase: "Full Moon", sleep_performance: 80 },
    { moon_phase: "Full Moon", sleep_performance: 60 },
    { moon_phase: null, sleep_performance: 50 },
    { moon_phase: "New Moon", sleep_performance: null },
  ]);
  assert.deepEqual(grouped, [{ moon_phase: "Full Moon", nights: 2, average_performance: 70 }]);
});

// --- Training aggregation ----------------------------------------------------

test("filterTrainingActivities defaults to sport and can include every activity", () => {
  const records = [
    { activity_name: "Run", is_sport_exercise: true },
    { activity_name: "Commuting", is_sport_exercise: false },
  ];
  assert.equal(filterTrainingActivities(records, false).length, 1);
  assert.equal(filterTrainingActivities(records, true).length, 2);
});

test("summarizeTraining totals hours and uses the highest heart rate", () => {
  const summary = summarizeTraining([
    { duration_minutes: 60, activity_strain: 10, max_heart_rate: 170 },
    { duration_minutes: 30, activity_strain: 4, max_heart_rate: 150 },
  ]);
  assert.equal(summary.hours, 1.5);
  assert.equal(summary.sessions, 2);
  assert.equal(summary.averageStrain, 7);
  assert.equal(summary.peakHeartRate, 170);
});

test("stackTrainingHours keeps eight activities and groups the rest as Other", () => {
  const records = [];
  for (let index = 1; index <= 9; index += 1) {
    records.push({
      date_day: "2026-09-01",
      activity_name: `Sport ${index}`,
      duration_minutes: (10 - index) * 60,
    });
  }
  const stacked = stackTrainingHours(records, "day");
  const names = stacked[0].series.map((series) => series.activity_name);
  assert.deepEqual(names, [
    "Sport 1", "Sport 2", "Sport 3", "Sport 4",
    "Sport 5", "Sport 6", "Sport 7", "Sport 8", "Other",
  ]);
  assert.equal(stacked[0].series.at(-1).hours, 1);
});

test("stackTrainingHours uses Monday as the ISO-week bucket", () => {
  const stacked = stackTrainingHours([
    { date_day: "2026-09-21", activity_name: "Run", duration_minutes: 30 },
    { date_day: "2026-09-27", activity_name: "Run", duration_minutes: 30 },
  ], "week");
  assert.equal(stacked.length, 1);
  assert.equal(stacked[0].bucketStart, "2026-09-21");
  assert.equal(stacked[0].series[0].hours, 1);
});

test("stackTrainingHours uses the first of the month as the month bucket", () => {
  const stacked = stackTrainingHours([
    { date_day: "2026-09-30T00:00:00", activity_name: "Run", duration_minutes: 60 },
    { date_day: "2026-10-01T00:00:00", activity_name: "Run", duration_minutes: 60 },
  ], "month");
  assert.deepEqual(stacked.map((bucket) => bucket.bucketStart), ["2026-09-01", "2026-10-01"]);
});

test("compareSports orders by total duration", () => {
  const compared = compareSports([
    { activity_name: "HIIT", duration_minutes: 30, average_heart_rate: 150, max_heart_rate: 180, activity_strain: 12 },
    { activity_name: "Run", duration_minutes: 120, average_heart_rate: 140, max_heart_rate: 175, activity_strain: 8 },
  ]);
  assert.equal(compared[0].activity_name, "Run");
  assert.equal(compared[0].hours, 2);
  assert.equal(compared[0].maxHeartRate, 175);
});

test("recentSessions returns the newest twenty sessions", () => {
  const records = Array.from({ length: 25 }, (_, index) => ({
    workout_start_time: `2026-09-${String(index + 1).padStart(2, "0")}T08:00:00`,
    activity_name: "Run",
  }));
  const recent = recentSessions(records);
  assert.equal(recent.length, 20);
  assert.equal(recent[0].workout_start_time, "2026-09-25T08:00:00");
});
