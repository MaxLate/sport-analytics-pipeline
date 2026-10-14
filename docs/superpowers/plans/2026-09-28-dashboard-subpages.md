# Dashboard Subpages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the operations dashboard into Overview, Sleep, and Training pages joined by a top tab strip, with sleep-performance associations and sport-load analysis.

**Architecture:** Keep FastAPI as a thin read-only DuckDB layer. Put period filtering, correlation, moon grouping, and training aggregation in `dashboard-utils.js` so Node tests cover them. Share visual rules in `dashboard.css`. Each HTML page owns only its markup and chart rendering.

**Tech Stack:** Static HTML, Chart.js, vanilla JavaScript tested with `node:test`, FastAPI, DuckDB.

**Spec:** `docs/superpowers/specs/2026-09-25-dashboard-subpages-design.md`

## Global Constraints

- Pages are `2_analytics/dashboard/index.html`, `sleep.html`, and `training.html`.
- Navigation is a persistent top tab strip under the title: Overview, Sleep, Training. The active tab is underlined with `#199e70`. There is no sidebar, redirect button, or back link. The strip stays horizontal on narrow screens.
- Shared CSS lives in `dashboard.css`. Shared calculations stay in `dashboard-utils.js`.
- Overview keeps the current title, subtitle, four KPI tiles, Recovery chart, Day/Week/Month control, and HRV, resting heart rate, SpO2, and skin-temperature tiles.
- Overview removes the detailed Sleep, Training, and Weather sections. Weather has no page.
- Sleep period presets are 30 days (default), 90 days, 1 year, and all time. Only `nap === false` episodes are included.
- Sleep performance is the lead metric. Scatters are performance versus moon illumination and versus daily minimum temperature. Each shows Pearson `r` and the valid count.
- Temperature joins weather on `wake_up_date` and is labeled as a daily-minimum proxy, not bedroom temperature.
- Association labels: absolute `r` below 0.2 is "little or no linear association"; 0.2 through below 0.4 is "weak association"; 0.4 through below 0.6 is "moderate association"; 0.6 or above is "strong association".
- Training defaults to `is_sport_exercise === true`, with a toggle for all activities. Presets match Sleep.
- Training buckets: 30 days by day, 90 days and 1 year by ISO week, all time by month. The eight activities with the most duration are individual series; the rest are `Other`.
- The recent-sessions table shows 20 rows.
- Correlation is unavailable below three paired observations or when either variable has zero variance.
- A failed API request shows a visible message. An empty period says that no observations exist. Navigation still works.
- Do not change Recovery calculations, add data sources, create a dbt model, or change Airflow.

## Review Focus

- A timestamp such as `2026-09-24T00:00:00` must stay on 2026-09-24. Task 1 tests `calendarDate`.
- A nap, or a row whose `nap` is not strictly `false`, must not enter sleep analysis. Task 1 tests `mainSleepEpisodes`.
- A night without temperature must remain in the moon scatter and disappear only from the temperature scatter. Task 2 tests `pairedValues`.
- A period of 30 days means 30 inclusive calendar dates ending on the latest date, not a rolling millisecond window. Task 1 tests the boundary.
- Nine sports must become eight named series plus `Other`, ranked by total duration. Task 3 tests `stackTrainingHours`.

---

### Task 1: Period filtering and sleep-episode selection

**Files:**
- Modify: `2_analytics/dashboard/dashboard-utils.js`
- Test: `2_analytics/dashboard/test-dashboard-utils.js`

**Interfaces:**
- Consumes: nothing new.
- Produces:
  - `calendarDate(value: string | Date): string` returns `YYYY-MM-DD`.
  - `filterByPeriod(records: object[], dateField: string, period: "30d" | "90d" | "1y" | "all", referenceDateInclusive: string): object[]`
  - `mainSleepEpisodes(records: object[]): object[]`

- [ ] **Step 1: Write the failing tests**

Append these tests to `test-dashboard-utils.js` and add the three names to its `require` destructure:

```javascript
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: FAIL because `calendarDate` is not exported.

- [ ] **Step 3: Implement the functions**

Add this before the `module.exports` block in `dashboard-utils.js`, and export all three names:

```javascript
function calendarDate(value) {
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value).slice(0, 10);
}

function shiftUtcDate(isoDate, { days = 0, years = 0 }) {
  const date = new Date(`${calendarDate(isoDate)}T00:00:00Z`);
  if (years) date.setUTCFullYear(date.getUTCFullYear() + years);
  if (days) date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}

function filterByPeriod(records, dateField, period, referenceDateInclusive) {
  const reference = calendarDate(referenceDateInclusive);
  const starts = {
    "30d": shiftUtcDate(reference, { days: -29 }),
    "90d": shiftUtcDate(reference, { days: -89 }),
    "1y": shiftUtcDate(reference, { years: -1 }),
    all: null,
  };
  if (!Object.hasOwn(starts, period)) throw new Error(`Unknown period: ${period}`);
  const start = starts[period];
  return records.filter((record) => {
    const date = calendarDate(record[dateField]);
    return date <= reference && (start === null || date >= start);
  });
}

function mainSleepEpisodes(records) {
  return records.filter((record) => record.nap === false);
}
```

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 2_analytics/dashboard/dashboard-utils.js 2_analytics/dashboard/test-dashboard-utils.js
git commit -m "test: add dashboard period filtering"
```

### Task 2: Correlation and moon-phase grouping

**Files:**
- Modify: `2_analytics/dashboard/dashboard-utils.js`
- Test: `2_analytics/dashboard/test-dashboard-utils.js`

**Interfaces:**
- Consumes: `calendarDate` is not required here.
- Produces:
  - `pairedValues(records: object[], xField: string, yField: string): {x: number, y: number}[]`
  - `pearsonCorrelation(pairs: {x: number, y: number}[]): {r: number | null, n: number, label: string}`
  - `groupSleepPerformanceByMoonPhase(records: object[]): {moon_phase: string, nights: number, average_performance: number}[]`

- [ ] **Step 1: Write the failing tests**

```javascript
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: FAIL because `pairedValues` is not exported.

- [ ] **Step 3: Implement the functions**

```javascript
function pairedValues(records, xField, yField) {
  return records.flatMap((record) => {
    const x = record[xField];
    const y = record[yField];
    if (typeof x !== "number" || typeof y !== "number" || Number.isNaN(x) || Number.isNaN(y)) return [];
    return [{ x, y }];
  });
}

function associationLabel(r) {
  if (r === null) return "unavailable";
  const magnitude = Math.abs(r);
  if (magnitude < 0.2) return "little or no linear association";
  if (magnitude < 0.4) return "weak association";
  if (magnitude < 0.6) return "moderate association";
  return "strong association";
}

function pearsonCorrelation(pairs) {
  const n = pairs.length;
  if (n < 3) return { r: null, n, label: "unavailable" };
  const meanX = pairs.reduce((sum, pair) => sum + pair.x, 0) / n;
  const meanY = pairs.reduce((sum, pair) => sum + pair.y, 0) / n;
  let covariance = 0;
  let varianceX = 0;
  let varianceY = 0;
  for (const pair of pairs) {
    const dx = pair.x - meanX;
    const dy = pair.y - meanY;
    covariance += dx * dy;
    varianceX += dx * dx;
    varianceY += dy * dy;
  }
  if (varianceX === 0 || varianceY === 0) return { r: null, n, label: "unavailable" };
  const r = covariance / Math.sqrt(varianceX * varianceY);
  return { r, n, label: associationLabel(r) };
}

function groupSleepPerformanceByMoonPhase(records) {
  const groups = new Map();
  for (const record of records) {
    if (typeof record.moon_phase !== "string" || typeof record.sleep_performance !== "number") continue;
    if (!groups.has(record.moon_phase)) groups.set(record.moon_phase, []);
    groups.get(record.moon_phase).push(record.sleep_performance);
  }
  return [...groups.entries()]
    .map(([moon_phase, values]) => ({
      moon_phase,
      nights: values.length,
      average_performance: values.reduce((sum, value) => sum + value, 0) / values.length,
    }))
    .sort((a, b) => b.nights - a.nights || a.moon_phase.localeCompare(b.moon_phase));
}
```

Export `pairedValues`, `pearsonCorrelation`, and `groupSleepPerformanceByMoonPhase`.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 2_analytics/dashboard/dashboard-utils.js 2_analytics/dashboard/test-dashboard-utils.js
git commit -m "test: add sleep correlation helpers"
```

### Task 3: Training aggregation

**Files:**
- Modify: `2_analytics/dashboard/dashboard-utils.js`
- Test: `2_analytics/dashboard/test-dashboard-utils.js`

**Interfaces:**
- Consumes: `calendarDate`, `filterByPeriod`, and the existing `isoWeekBucketStart` / `monthBucketStart` functions.
- Produces:
  - `filterTrainingActivities(records: object[], includeAllActivities: boolean): object[]`
  - `summarizeTraining(records: object[]): {hours: number, sessions: number, averageStrain: number | null, peakHeartRate: number | null}`
  - `stackTrainingHours(records: object[], bucket: "day" | "week" | "month"): {bucketStart: string, series: {activity_name: string, hours: number}[]}[]`
  - `compareSports(records: object[]): {activity_name: string, sessions: number, hours: number, averageHeartRate: number | null, maxHeartRate: number | null, averageStrain: number | null}[]`
  - `recentSessions(records: object[], limit?: number): object[]`

- [ ] **Step 1: Write the failing tests**

```javascript
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
```

- [ ] **Step 2: Run the tests and confirm they fail**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: FAIL because `filterTrainingActivities` is not exported.

- [ ] **Step 3: Implement the functions**

```javascript
function filterTrainingActivities(records, includeAllActivities) {
  if (includeAllActivities) return records;
  return records.filter((record) => record.is_sport_exercise === true);
}

function summarizeTraining(records) {
  const strains = records.map((record) => record.activity_strain).filter((value) => typeof value === "number");
  const heartRates = records.map((record) => record.max_heart_rate).filter((value) => typeof value === "number");
  const minutes = records.reduce((sum, record) => sum + (record.duration_minutes || 0), 0);
  return {
    hours: minutes / 60,
    sessions: records.length,
    averageStrain: strains.length ? strains.reduce((sum, value) => sum + value, 0) / strains.length : null,
    peakHeartRate: heartRates.length ? Math.max(...heartRates) : null,
  };
}

function bucketStartFor(dateValue, bucket) {
  const date = new Date(`${calendarDate(dateValue)}T00:00:00Z`);
  if (bucket === "day") return toIsoDate(dayBucketStart(date));
  if (bucket === "week") return toIsoDate(isoWeekBucketStart(date));
  if (bucket === "month") return toIsoDate(monthBucketStart(date));
  throw new Error(`Unknown bucket: ${bucket}`);
}

function stackTrainingHours(records, bucket) {
  const totals = new Map();
  for (const record of records) {
    totals.set(record.activity_name, (totals.get(record.activity_name) || 0) + (record.duration_minutes || 0));
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const named = new Set(ranked.slice(0, 8).map(([name]) => name));
  const buckets = new Map();
  for (const record of records) {
    const bucketStart = bucketStartFor(record.date_day, bucket);
    const activityName = named.has(record.activity_name) ? record.activity_name : "Other";
    if (!buckets.has(bucketStart)) buckets.set(bucketStart, new Map());
    const series = buckets.get(bucketStart);
    series.set(activityName, (series.get(activityName) || 0) + (record.duration_minutes || 0) / 60);
  }
  const names = [...ranked.slice(0, 8).map(([name]) => name), ...(ranked.length > 8 ? ["Other"] : [])];
  return [...buckets.keys()].sort().map((bucketStart) => ({
    bucketStart,
    series: names.map((activity_name) => ({
      activity_name,
      hours: buckets.get(bucketStart).get(activity_name) || 0,
    })),
  }));
}

function compareSports(records) {
  const groups = new Map();
  for (const record of records) {
    if (!groups.has(record.activity_name)) groups.set(record.activity_name, []);
    groups.get(record.activity_name).push(record);
  }
  return [...groups.entries()]
    .map(([activity_name, rows]) => {
      const average = (field) => {
        const values = rows.map((row) => row[field]).filter((value) => typeof value === "number");
        return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
      };
      const maxima = rows.map((row) => row.max_heart_rate).filter((value) => typeof value === "number");
      return {
        activity_name,
        sessions: rows.length,
        hours: rows.reduce((sum, row) => sum + (row.duration_minutes || 0), 0) / 60,
        averageHeartRate: average("average_heart_rate"),
        maxHeartRate: maxima.length ? Math.max(...maxima) : null,
        averageStrain: average("activity_strain"),
      };
    })
    .sort((a, b) => b.hours - a.hours || a.activity_name.localeCompare(b.activity_name));
}

function recentSessions(records, limit = 20) {
  return [...records]
    .sort((a, b) => String(b.workout_start_time).localeCompare(String(a.workout_start_time)))
    .slice(0, limit);
}
```

Export all five functions.

- [ ] **Step 4: Run the tests and confirm they pass**

Run: `node --test 2_analytics/dashboard/test-dashboard-utils.js`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add 2_analytics/dashboard/dashboard-utils.js 2_analytics/dashboard/test-dashboard-utils.js
git commit -m "test: add training aggregation helpers"
```

### Task 4: Join overnight temperature into the sleep API

**Files:**
- Modify: `2_analytics/dashboard/api.py`
- Create: `2_analytics/dashboard/test_sleep_api.py`

**Interfaces:**
- Consumes: `whoop.fct_whoop_sleeps`, `whoop.fct_whoop_sleep_quality.wake_up_date`, and `weather.fct_weather_daily.temperature_min_celsius`.
- Produces: `/sleep` JSON records containing the existing fields plus `wake_up_date` and `temperature_min_celsius`.

- [ ] **Step 1: Write the failing smoke check**

Create `2_analytics/dashboard/test_sleep_api.py`:

```python
import duckdb
from pathlib import Path

from api import SLEEP_SQL, DUCKDB_PATH


def test_sleep_query_exposes_wake_up_date_and_temperature():
    con = duckdb.connect(DUCKDB_PATH, read_only=True)
    try:
        row = con.execute(f"SELECT * FROM ({SLEEP_SQL}) LIMIT 1").fetchdf()
    finally:
        con.close()
    assert "wake_up_date" in row.columns
    assert "temperature_min_celsius" in row.columns


if __name__ == "__main__":
    assert Path(DUCKDB_PATH).exists(), DUCKDB_PATH
    test_sleep_query_exposes_wake_up_date_and_temperature()
    print("sleep query smoke check passed")
```

- [ ] **Step 2: Run it and confirm it fails**

Run from `2_analytics/dashboard`: `uv run python test_sleep_api.py`

Expected: FAIL because `SLEEP_SQL` is not exported.

- [ ] **Step 3: Update the sleep query**

In `api.py`, define `SLEEP_SQL` and use it in `get_sleep()`:

```python
SLEEP_SQL = """
SELECT
    s.date_day,
    q.wake_up_date,
    s.asleep_duration_minutes,
    s.in_bed_duration_minutes,
    s.light_sleep_duration_minutes,
    s.deep_sleep_duration_minutes,
    s.rem_duration_minutes,
    s.awake_duration_minutes,
    q.sleep_performance,
    q.sleep_efficiency,
    q.sleep_consistency,
    q.sleep_debt_minutes,
    q.nap,
    q.moon_phase,
    q.moon_illumination,
    q.moon_phase_cycle,
    w.temperature_min_celsius
FROM whoop.fct_whoop_sleeps s
LEFT JOIN whoop.fct_whoop_sleep_quality q ON s.sleep_id = q.sleep_id
LEFT JOIN weather.fct_weather_daily w ON q.wake_up_date = w.date_day
WHERE s.asleep_duration_minutes IS NOT NULL
ORDER BY s.date_day
"""
```

`get_sleep()` executes `SLEEP_SQL` instead of its inline string. Leave `/weather` implemented but unused by the pages.

- [ ] **Step 4: Run the smoke check**

Run from `2_analytics/dashboard`: `uv run python test_sleep_api.py`

Expected: `sleep query smoke check passed`

- [ ] **Step 5: Commit**

```bash
git add 2_analytics/dashboard/api.py 2_analytics/dashboard/test_sleep_api.py
git commit -m "feat: attach overnight temperature to sleep"
```

### Task 5: Shared stylesheet, top navigation, and Overview

**Files:**
- Create: `2_analytics/dashboard/dashboard.css`
- Modify: `2_analytics/dashboard/index.html`
- Modify: `2_analytics/dashboard/how_to_run.txt`

**Interfaces:**
- Consumes: existing Overview recovery rendering in `index.html`.
- Produces: `.topNav` and `.topNav a.active` for all pages. Overview no longer contains `#sleepChart`, `#strainChart`, `#weatherChart`, or a weather fetch.

- [ ] **Step 1: Move the current style block into `dashboard.css`**

Move the contents of the second `<style>` block in `index.html` unchanged into `dashboard.css`. Add:

```css
.topNav {
    display: flex;
    gap: 22px;
    border-bottom: 1px solid var(--border-hairline);
    margin: 8px 0 28px;
}
.topNav a {
    color: var(--text-muted);
    text-decoration: none;
    padding: 8px 0;
    border-bottom: 2px solid transparent;
}
.topNav a.active {
    color: var(--text-primary);
    border-bottom-color: var(--color-recovery);
}
```

Replace the moved style block in `index.html` with `<link rel="stylesheet" href="dashboard.css">`. Keep the font-face style block.

- [ ] **Step 2: Add the tab strip and remove the three detail sections**

Immediately after the subtitle, add:

```html
<nav class="topNav" aria-label="Dashboard pages">
    <a class="active" href="index.html">Overview</a>
    <a href="sleep.html">Sleep</a>
    <a href="training.html">Training</a>
</nav>
```

Delete the `<!-- SLEEP -->`, `<!-- TRAINING -->`, and `<!-- WEATHER -->` panels. Delete `renderSleepSection`, `renderTrainingSection`, `renderWeatherSection`, `renderStageBars`, `renderMoonStrip`, and the weather chart config. Keep the recovery fetch and the sleep and workout fetches used by the four KPI tiles.

The load call becomes:

```javascript
Promise.all([
    fetch(`${API_BASE}/recovery`).then((response) => response.json()),
    fetch(`${API_BASE}/sleep`).then((response) => response.json()),
    fetch(`${API_BASE}/workouts`).then((response) => response.json()),
]).then(([recovery, sleep, workouts]) => {
    if (recovery.length) renderRecoverySection(recovery);
    if (sleep.length) renderHeroSleep(sleep);
    if (workouts.length) renderHeroStrain(workouts);
}).catch(() => {
    document.body.insertAdjacentHTML("beforeend", "<p class='error'>Dashboard data could not be loaded.</p>");
});
```

Extract the existing hero-tile calls for sleep performance and strain into `renderHeroSleep` and `renderHeroStrain` without changing their calculations. Add `.error { color: var(--delta-bad); }` to `dashboard.css`.

- [ ] **Step 3: Update the run note**

In `how_to_run.txt`, replace the endpoint sentence with: the pages fetch `/recovery`, `/sleep`, and `/workouts`; `/weather` remains available but no page requests it. State that `index.html`, `sleep.html`, and `training.html` are the three pages.

- [ ] **Step 4: Check the landing page**

With the API on port 8000 and `python3 -m http.server 5500` running inside `2_analytics/dashboard`, open `http://127.0.0.1:5500/`. Confirm the four KPI tiles and Recovery remain, the tab strip is present, and Sleep, Training, and Weather detail sections are absent. The Sleep and Training links may 404 until the next tasks.

- [ ] **Step 5: Commit**

```bash
git add 2_analytics/dashboard/dashboard.css 2_analytics/dashboard/index.html 2_analytics/dashboard/how_to_run.txt
git commit -m "feat: keep overview focused on recovery"
```

### Task 6: Sleep page

**Files:**
- Create: `2_analytics/dashboard/sleep.html`

**Interfaces:**
- Consumes: `avgField`, `mainSleepEpisodes`, `filterByPeriod`, `calendarDate`, `pairedValues`, `pearsonCorrelation`, `groupSleepPerformanceByMoonPhase`, and `/sleep`.
- Produces: `sleep.html`, whose active tab is Sleep.

- [ ] **Step 1: Create the page shell**

Use the same head, font, `dashboard.css`, and Chart.js script as Overview. The body starts with the title `Sleep`, the subtitle `Performance versus moon illumination and daily minimum temperature`, and this navigation:

```html
<nav class="topNav" aria-label="Dashboard pages">
    <a href="index.html">Overview</a>
    <a class="active" href="sleep.html">Sleep</a>
    <a href="training.html">Training</a>
</nav>
<div class="granularityToggle" id="periodToggle">
    <button class="toggleBtn active" data-period="30d">30d</button>
    <button class="toggleBtn" data-period="90d">90d</button>
    <button class="toggleBtn" data-period="1y">1y</button>
    <button class="toggleBtn" data-period="all">All</button>
</div>
<p id="pageStatus"></p>
```

Add canvases `sleepPerformanceChart`, `moonScatter`, `temperatureScatter`, and `moonPhaseChart`. Add captions `performanceCaption`, `moonCaption`, and `temperatureCaption`, plus tiles `sleepPerformanceValue`, `sleepDurationValue`, and `sleepEfficiencyValue`.

- [ ] **Step 2: Render from the tested helpers**

```javascript
function referenceDate(records) {
  const dates = records.map((record) => calendarDate(record.date_day)).sort();
  return dates.at(-1);
}

function renderSleep(records, period) {
  const episodes = mainSleepEpisodes(records);
  const selected = filterByPeriod(episodes, "date_day", period, referenceDate(episodes));
  if (!selected.length) {
    pageStatus.textContent = "No observations exist for this period.";
    return;
  }
  pageStatus.textContent = "";
  const performanceRows = selected.filter((record) => typeof record.sleep_performance === "number");
  sleepPerformanceValue.textContent = `${Math.round(avgField(performanceRows, "sleep_performance"))}%`;
  const duration = avgField(selected, "asleep_duration_minutes");
  sleepDurationValue.textContent = `${Math.floor(duration / 60)}h ${Math.round(duration % 60)}m`;
  sleepEfficiencyValue.textContent = `${Math.round(avgField(selected, "sleep_efficiency"))}%`;
  performanceCaption.textContent = `${performanceRows.length} nights`;
  const moon = pearsonCorrelation(pairedValues(performanceRows, "moon_illumination", "sleep_performance"));
  const temperature = pearsonCorrelation(pairedValues(performanceRows, "temperature_min_celsius", "sleep_performance"));
  moonCaption.textContent = `${moon.label} · r ${moon.r === null ? "unavailable" : moon.r.toFixed(2)} · ${moon.n} nights`;
  temperatureCaption.textContent = `Daily minimum temperature proxy · ${temperature.label} · r ${temperature.r === null ? "unavailable" : temperature.r.toFixed(2)} · ${temperature.n} nights`;
  const phases = groupSleepPerformanceByMoonPhase(selected.filter((record) => typeof record.sleep_performance === "number"));
  renderPhaseChart(phases);
}
```

The performance chart plots one point per selected episode, not an average that hides multiple episodes. Scatter captions must include the exact association label and must not say "causes", "improves", or "worsens".

- [ ] **Step 3: Verify the page**

Reload `http://127.0.0.1:5500/sleep.html`. Switch all four periods. Confirm naps do not add points, both captions show a count, and the temperature caption says "Daily minimum temperature proxy".

- [ ] **Step 4: Commit**

```bash
git add 2_analytics/dashboard/sleep.html
git commit -m "feat: add sleep association page"
```

### Task 7: Training page

**Files:**
- Create: `2_analytics/dashboard/training.html`

**Interfaces:**
- Consumes: `filterByPeriod`, `calendarDate`, `filterTrainingActivities`, `summarizeTraining`, `stackTrainingHours`, `compareSports`, and `recentSessions`.
- Produces: `training.html`, whose active tab is Training.

- [ ] **Step 1: Create the page shell**

Match the Sleep page head and navigation, with Training marked active and the title `Training`. Add the same period buttons plus:

```html
<label><input id="includeAllActivities" type="checkbox"> Include all activities</label>
```

Add tiles for hours, sessions, average strain, and peak heart rate. Add canvases `hoursChart`, `heartRateChart`, and `strainBySportChart`, plus `#recentSessions`.

- [ ] **Step 2: Render from the tested helpers**

```javascript
function trainingBucket(period) {
  if (period === "30d") return "day";
  if (period === "all") return "month";
  return "week";
}

function renderTraining(records, period, includeAllActivities) {
  const reference = records.map((record) => calendarDate(record.date_day)).sort().at(-1);
  const selected = filterTrainingActivities(
    filterByPeriod(records, "date_day", period, reference),
    includeAllActivities,
  );
  if (!selected.length) {
    pageStatus.textContent = "No observations exist for this period.";
    return;
  }
  const summary = summarizeTraining(selected);
  const stacked = stackTrainingHours(selected, trainingBucket(period));
  const sports = compareSports(selected);
  const recent = recentSessions(selected, 20);
  renderStackedHours(stacked);
  renderSportCharts(sports);
  renderRecentRows(recent);
}
```

`renderStackedHours` creates one Chart.js dataset per series. `renderSportCharts` orders bars exactly as `compareSports` returns them. Tooltips include activity name, session count, and total hours. The checkbox reruns `renderTraining` against the already fetched records.

- [ ] **Step 3: Verify the page**

Open `http://127.0.0.1:5500/training.html`. Confirm the default excludes commuting and sauna, the checkbox adds them, 30 days is daily, 90 days and 1 year are weekly, all time is monthly, and the table has at most 20 rows.

- [ ] **Step 4: Commit**

```bash
git add 2_analytics/dashboard/training.html
git commit -m "feat: add training load page"
```

### Task 8: Browser verification

**Files:**
- Modify none unless verification reveals a defect. Fix that defect in the owning file and add a regression test when the behavior is in `dashboard-utils.js`.

- [ ] **Step 1: Run the automated checks**

Run:

```bash
node --test 2_analytics/dashboard/test-dashboard-utils.js
cd 2_analytics/dashboard && uv run python test_sleep_api.py
```

Expected: all Node tests pass and the smoke check prints `sleep query smoke check passed`.

- [ ] **Step 2: Exercise both viewports**

At desktop width and at 390px width, on all three pages, confirm:

- the same horizontal Overview / Sleep / Training strip is visible
- the active tab is underlined in green
- Overview has all four KPI tiles and Recovery details, and has no sleep, training, or weather detail section
- every Sleep and Training period changes every tile, chart, caption, and table on that page
- the Training activity checkbox changes every Training element
- chart axes and tooltips include their units
- stopping the API and reloading shows `Dashboard data could not be loaded.` while the tab links still navigate

- [ ] **Step 3: Commit any verification fixes**

```bash
git add 2_analytics/dashboard
git commit -m "fix: correct dashboard subpage verification issues"
```

Skip this commit when Step 2 finds no defect.
