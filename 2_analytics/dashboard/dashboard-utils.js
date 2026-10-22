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

// --- Period presets (30d / 90d / 1y / all) ----------------------------------
// Periods are inclusive calendar dates ending on the reference date, not
// rolling millisecond windows, so "30d" is exactly 30 dates.

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

// First included date of the period, or null for "all".
function periodStart(period, referenceDateInclusive) {
  const reference = calendarDate(referenceDateInclusive);
  const starts = {
    "30d": () => shiftUtcDate(reference, { days: -29 }),
    "90d": () => shiftUtcDate(reference, { days: -89 }),
    "1y": () => shiftUtcDate(reference, { years: -1 }),
    all: () => null,
  };
  if (!Object.hasOwn(starts, period)) throw new Error(`Unknown period: ${period}`);
  return starts[period]();
}

function filterByPeriod(records, dateField, period, referenceDateInclusive) {
  const reference = calendarDate(referenceDateInclusive);
  const start = periodStart(period, reference);
  return records.filter((record) => {
    const date = calendarDate(record[dateField]);
    return date <= reference && (start === null || date >= start);
  });
}

function mainSleepEpisodes(records) {
  return records.filter((record) => record.nap === false);
}

// --- Association between two measures ----------------------------------------

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

// Lunar-cycle order, as named in the mooncalender seed.
const MOON_PHASES = [
  ["New Moon", "🌑"],
  ["Waxing Crescent", "🌒"],
  ["First Quarter", "🌓"],
  ["Waxing Gibbous", "🌔"],
  ["Full Moon", "🌕"],
  ["Waning Gibbous", "🌖"],
  ["Last Quarter", "🌗"],
  ["Waning Crescent", "🌘"],
];
const MOON_PHASE_EMOJI = new Map(MOON_PHASES);
const MOON_PHASE_ORDER = new Map(MOON_PHASES.map(([name], index) => [name, index]));

function moonPhaseEmoji(phase) {
  if (typeof phase !== "string") return "";
  return MOON_PHASE_EMOJI.get(phase) ?? "🌙";
}

function groupByMoonPhase(records, field) {
  const groups = new Map();
  for (const record of records) {
    if (typeof record.moon_phase !== "string" || typeof record[field] !== "number") continue;
    if (!groups.has(record.moon_phase)) groups.set(record.moon_phase, []);
    groups.get(record.moon_phase).push(record[field]);
  }
  const order = (phase) => MOON_PHASE_ORDER.get(phase) ?? MOON_PHASES.length;
  return [...groups.entries()]
    .map(([moon_phase, values]) => ({
      moon_phase,
      emoji: moonPhaseEmoji(moon_phase),
      nights: values.length,
      average: values.reduce((sum, value) => sum + value, 0) / values.length,
    }))
    .sort((a, b) => order(a.moon_phase) - order(b.moon_phase) || a.moon_phase.localeCompare(b.moon_phase));
}

// --- Training aggregation ------------------------------------------------------

const TRAINING_SERIES_LIMIT = 8;

function filterTrainingActivities(records, includeAllActivities) {
  if (includeAllActivities) return records;
  return records.filter((record) => record.is_sport_exercise === true);
}

function numbersIn(records, field) {
  return records.map((record) => record[field]).filter((value) => typeof value === "number");
}

function mean(values) {
  return values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;
}

function summarizeTraining(records) {
  const heartRates = numbersIn(records, "max_heart_rate");
  const minutes = records.reduce((sum, record) => sum + (record.duration_minutes || 0), 0);
  return {
    hours: minutes / 60,
    sessions: records.length,
    averageStrain: mean(numbersIn(records, "activity_strain")),
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

function nextBucketStart(bucketStart, bucket) {
  if (bucket === "day") return shiftUtcDate(bucketStart, { days: 1 });
  if (bucket === "week") return shiftUtcDate(bucketStart, { days: 7 });
  const date = new Date(`${bucketStart}T00:00:00Z`);
  date.setUTCMonth(date.getUTCMonth() + 1);
  return toIsoDate(date);
}

// With range {start, end}, every bucket in it is returned, including empty ones.
function stackTrainingHours(records, bucket, range = null) {
  const totals = new Map();
  for (const record of records) {
    totals.set(record.activity_name, (totals.get(record.activity_name) || 0) + (record.duration_minutes || 0));
  }
  const ranked = [...totals.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  const namedList = ranked.slice(0, TRAINING_SERIES_LIMIT).map(([name]) => name);
  const named = new Set(namedList);
  const buckets = new Map();
  for (const record of records) {
    const bucketStart = bucketStartFor(record.date_day, bucket);
    const activityName = named.has(record.activity_name) ? record.activity_name : "Other";
    if (!buckets.has(bucketStart)) buckets.set(bucketStart, new Map());
    const series = buckets.get(bucketStart);
    series.set(activityName, (series.get(activityName) || 0) + (record.duration_minutes || 0) / 60);
  }
  if (range) {
    const last = bucketStartFor(range.end, bucket);
    for (let start = bucketStartFor(range.start, bucket); start <= last; start = nextBucketStart(start, bucket)) {
      if (!buckets.has(start)) buckets.set(start, new Map());
    }
  }
  const names = [...namedList, ...(ranked.length > TRAINING_SERIES_LIMIT ? ["Other"] : [])];
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
      const maxima = numbersIn(rows, "max_heart_rate");
      return {
        activity_name,
        sessions: rows.length,
        hours: rows.reduce((sum, row) => sum + (row.duration_minutes || 0), 0) / 60,
        averageHeartRate: mean(numbersIn(rows, "average_heart_rate")),
        maxHeartRate: maxima.length ? Math.max(...maxima) : null,
        averageStrain: mean(numbersIn(rows, "activity_strain")),
      };
    })
    .sort((a, b) => b.hours - a.hours || a.activity_name.localeCompare(b.activity_name));
}

function recentSessions(records, limit = 20) {
  return [...records]
    .sort((a, b) => String(b.workout_start_time).localeCompare(String(a.workout_start_time)))
    .slice(0, limit);
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
    calendarDate,
    filterByPeriod,
    mainSleepEpisodes,
    pairedValues,
    pearsonCorrelation,
    groupByMoonPhase,
    moonPhaseEmoji,
    filterTrainingActivities,
    summarizeTraining,
    stackTrainingHours,
    periodStart,
    compareSports,
    recentSessions,
  };
}
