// Pure calculation helpers for the operations dashboard.
// No DOM access, no fetch — runs identically in the browser (via <script src>)
// and in Node (for tests).

function avgField(records, field) {
  const valid = records
    .map((r) => r[field])
    .filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (!valid.length) return null;
  return valid.reduce((a, b) => a + b, 0) / valid.length;
}

function windowAverage(records, dateField, valueField, referenceDateExclusive, days, offsetDays) {
  const refMs = new Date(referenceDateExclusive).getTime();
  const windowEndMs = refMs - offsetDays * 86400000;
  const windowStartMs = windowEndMs - days * 86400000;
  const inWindow = records.filter((r) => {
    const t = new Date(r[dateField]).getTime();
    return t >= windowStartMs && t < windowEndMs;
  });
  return avgField(inWindow, valueField);
}

function computeDeltaPct(currentAvg, priorAvg) {
  if (currentAvg === null || priorAvg === null || priorAvg === 0) return null;
  return ((currentAvg - priorAvg) / priorAvg) * 100;
}

// "up is good" metrics vs "down is good" metrics — everything else is neutral
// (e.g. strain and workout count are training-load inputs, not pass/fail signals).
const GOOD_UP = new Set(["recovery", "sleep_performance", "hrv", "spo2", "sleep_duration", "sleep_efficiency"]);
const GOOD_DOWN = new Set(["rhr", "sleep_debt"]);

function deltaDirection(metricKey, deltaPct) {
  if (deltaPct === null) return "neutral";
  if (GOOD_UP.has(metricKey)) return deltaPct >= 0 ? "good" : "bad";
  if (GOOD_DOWN.has(metricKey)) return deltaPct <= 0 ? "good" : "bad";
  return "neutral";
}

function computeKpiDeltas(records, dateField, valueField, metricKey, referenceDateExclusive) {
  const cur7 = windowAverage(records, dateField, valueField, referenceDateExclusive, 7, 0);
  const prior7 = windowAverage(records, dateField, valueField, referenceDateExclusive, 7, 7);
  const cur30 = windowAverage(records, dateField, valueField, referenceDateExclusive, 30, 0);
  const prior30 = windowAverage(records, dateField, valueField, referenceDateExclusive, 30, 30);

  const delta7Pct = computeDeltaPct(cur7, prior7);
  const delta30Pct = computeDeltaPct(cur30, prior30);

  return {
    current7: cur7,
    delta7: delta7Pct === null ? null : { pct: delta7Pct, direction: deltaDirection(metricKey, delta7Pct) },
    delta30: delta30Pct === null ? null : { pct: delta30Pct, direction: deltaDirection(metricKey, delta30Pct) },
  };
}

function nextDayIso(dateStr) {
  const d = new Date(dateStr);
  d.setUTCDate(d.getUTCDate() + 1);
  return d.toISOString().slice(0, 10);
}

function latestDateExclusive(records, dateField) {
  if (!records.length) return null;
  const maxMs = Math.max(...records.map((r) => new Date(r[dateField]).getTime()));
  return nextDayIso(new Date(maxMs).toISOString().slice(0, 10));
}

const STAGE_FIELDS = {
  light: "light_sleep_duration_minutes",
  deep: "deep_sleep_duration_minutes",
  rem: "rem_duration_minutes",
  awake: "awake_duration_minutes",
};

function weeklyStageAverages(sleepRecords, referenceDateExclusive) {
  const result = {};
  for (const [stage, field] of Object.entries(STAGE_FIELDS)) {
    result[stage] = {
      current: windowAverage(sleepRecords, "date_day", field, referenceDateExclusive, 7, 0),
      prior: windowAverage(sleepRecords, "date_day", field, referenceDateExclusive, 7, 7),
    };
  }
  return result;
}

// --- Calendar-bucket grouping (day / ISO week / month) ---------------------
// Unlike windowAverage (rolling 7d/30d windows anchored to "today"), these
// bucket records into fixed calendar periods for the granularity toggle.

function dayBucketStart(date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate()));
}

function isoWeekBucketStart(date) {
  const d = dayBucketStart(date);
  const weekday = d.getUTCDay(); // 0 = Sunday .. 6 = Saturday
  const daysSinceMonday = weekday === 0 ? 6 : weekday - 1;
  d.setUTCDate(d.getUTCDate() - daysSinceMonday);
  return d;
}

function monthBucketStart(date) {
  return new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1));
}

function toIsoDate(date) {
  return date.toISOString().slice(0, 10);
}

function groupByPeriod(records, dateField, valueFields, bucketStartFn) {
  const buckets = new Map();
  for (const record of records) {
    const bucketKey = toIsoDate(bucketStartFn(new Date(record[dateField])));
    if (!buckets.has(bucketKey)) buckets.set(bucketKey, []);
    buckets.get(bucketKey).push(record);
  }

  const result = [];
  for (const [bucketStart, bucketRecords] of buckets) {
    const bucket = { bucketStart };
    for (const field of valueFields) {
      bucket[field] = avgField(bucketRecords, field);
    }
    result.push(bucket);
  }
  result.sort((a, b) => a.bucketStart.localeCompare(b.bucketStart));
  return result;
}

function groupByDay(records, dateField, valueFields) {
  return groupByPeriod(records, dateField, valueFields, dayBucketStart);
}

function groupByISOWeek(records, dateField, valueFields) {
  return groupByPeriod(records, dateField, valueFields, isoWeekBucketStart);
}

function groupByMonth(records, dateField, valueFields) {
  return groupByPeriod(records, dateField, valueFields, monthBucketStart);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
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
  };
}
