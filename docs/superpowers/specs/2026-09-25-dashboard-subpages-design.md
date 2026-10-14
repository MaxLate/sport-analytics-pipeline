# Dashboard Subpages Design

## Purpose

Restructure the current one-page Sport Analytics dashboard into three focused pages:

- **Overview** remains the landing page and keeps the current KPI summary and Recovery analysis.
- **Sleep** explores associations between sleep performance, moon illumination/phase, and overnight temperature.
- **Training** shows how training time and load are distributed across sports.

The dashboard is for personal exploration. Sleep charts must describe associations and must not imply that moon phase or temperature causes changes in sleep.

## Navigation and Page Structure

All three pages use a persistent top tab strip, directly under the page title, with these links:

1. Overview
2. Sleep
3. Training

The active tab is underlined with the existing green accent. There is no sidebar, redirect button, or back link. The strip stays horizontal on narrow screens; the three labels do not collapse into another control.

The implementation uses three static pages in `2_analytics/dashboard/`:

- `index.html`
- `sleep.html`
- `training.html`

Shared visual rules move into `dashboard.css`, and common calculations remain in `dashboard-utils.js` instead of being copied among pages. Each page keeps only its page-specific rendering code. The existing dark palette and Chart.js dependency remain.

## Overview Page

The landing page preserves the current:

- title and subtitle
- four KPI tiles: Recovery, Sleep performance, Strain, and Resting heart rate
- Recovery chart and Day/Week/Month granularity selector
- Recovery detail tiles: HRV, resting heart rate, SpO2, and skin temperature

The current Sleep, Training, and Weather sections are removed from Overview. Weather has no standalone page or section.

Overview continues fetching sleep and workout data for its summary KPI tiles. Removing their detailed sections must not remove those KPI values.

## Sleep Page

### Controls

A single period selector filters every tile and chart:

- 30 days (default)
- 90 days
- 1 year
- all time

Only main sleep episodes (`nap = false`) are included. Rows without sleep performance are excluded from performance-based analysis. Each chart shows the number of valid nights used.

### Summary

Sleep performance is the primary measure. The top section contains:

- sleep performance trend over time
- average sleep performance
- average time asleep
- average sleep efficiency

Values are computed over the selected period.

### Moon Analysis

The first scatter plot uses:

- x-axis: moon illumination (%)
- y-axis: sleep performance (%)

It displays the Pearson correlation coefficient and valid night count. A separate bar chart groups average sleep performance by named moon phase and includes the number of nights in each phase. Groups with no observations are omitted.

### Temperature Analysis

The second scatter plot uses:

- x-axis: minimum overnight temperature proxy (°C)
- y-axis: sleep performance (%)

Daily weather is joined to sleep using `wake_up_date`, because the calendar day's minimum temperature around the wake-up morning is a better proxy for the preceding overnight conditions than weather on the sleep episode's assigned `date_day`. The UI labels this value as a daily-minimum proxy, not an indoor bedroom temperature measurement.

The plot displays the Pearson correlation coefficient and valid night count. Rows without weather coverage are omitted only from temperature analysis; they remain available to the sleep trend and moon analysis.

### Interpretation

Correlation labels use neutral language:

- absolute `r` below 0.2: little or no linear association
- 0.2 through below 0.4: weak association
- 0.4 through below 0.6: moderate association
- 0.6 or above: strong association

These labels describe linear association only and include no causal wording.

## Training Page

### Controls

A single period selector filters the complete page:

- 30 days (default)
- 90 days
- 1 year
- all time

The page defaults to activities where `is_sport_exercise = true`. A toggle can include all mapped activities such as commuting or sauna.

### Summary

The top tiles show, for the selected period:

- total workout hours
- session count
- average activity strain
- highest recorded workout heart rate

### Hours by Sport Over Time

A stacked chart shows workout duration in hours split by `activity_name`.

- 30 days uses daily buckets.
- 90 days and 1 year use ISO-week buckets.
- all time uses monthly buckets.

To keep the chart readable, the eight sports with the most duration in the selected period get individual series; remaining activities are grouped as `Other`.

### Sport Comparisons

Two side-by-side bar charts show:

1. average session heart rate and maximum recorded heart rate by sport
2. average activity strain by sport

Sports are ordered by total duration. Tooltips include sport name, session count, and total hours.

### Recent Sessions

A table under the charts lists the 20 most recent matching sessions with:

- date and start time
- activity name
- duration
- activity strain
- average heart rate
- maximum heart rate

The table follows the selected period and activity toggle.

## API and Data Flow

The FastAPI service remains a thin read-only layer over `analytics.duckdb`.

### Existing endpoints

- `/recovery` remains unchanged.
- `/workouts` continues returning session-level workout data and supplies Training.
- `/weather` remains available for compatibility but is not requested by any page in this change.

### Sleep endpoint

`/sleep` is extended to return:

- `wake_up_date`
- `temperature_min_celsius`

The query left-joins `weather.fct_weather_daily` using the sleep quality row's `wake_up_date`. Existing sleep and moon fields remain unchanged.

No new dbt model is required for this dashboard-only relationship. If the sleep-temperature relationship later becomes a reusable analytical dataset, it can move into dbt in a separate change.

### Client-side calculations

Pure calculations belong in `dashboard-utils.js`, including:

- period filtering
- Pearson correlation
- grouping by moon phase
- training aggregation by time bucket and activity
- top-eight activity selection plus `Other`

Keeping these functions independent of the DOM allows direct Node tests.

## Empty and Error States

- If an API request fails, the affected page shows a visible error message instead of leaving blank charts.
- If a selected period has no data, the page says that no observations exist for that period.
- Correlation is shown as unavailable when fewer than three paired observations exist or either variable has zero variance.
- Null metric values are excluded only from calculations that require them.
- Navigation remains usable when a page's data fails to load.

## Testing

### Automated

Extend `test-dashboard-utils.js` to cover:

- each period preset boundary
- Pearson correlation for positive, negative, zero-variance, and insufficient samples
- exclusion of null pairs
- moon-phase aggregation
- daily, ISO-week, and monthly training buckets
- top-eight activities plus `Other`
- sport-only versus all-activity filtering

Add API tests or direct query smoke checks for:

- `/sleep` returning temperature and wake-up date
- `/workouts` containing the fields required by Training

### Browser verification

Verify at desktop and narrow viewport widths:

- top tab navigation and active underline on all three pages
- the same horizontal tab strip on narrow screens
- Overview retains all four KPI tiles and Recovery details
- Overview contains no detailed Sleep, Training, or Weather sections
- every period preset updates every element on its page
- activity inclusion toggle updates all Training elements
- charts render tooltips, legends, labels, and correct units
- API failures and no-data periods render explicit messages

## Scope Boundaries

This change does not:

- alter Recovery calculations
- create a standalone Weather page
- claim causal effects from moon or temperature
- add new data sources
- estimate indoor bedroom temperature
- modify the ELT or Airflow schedule
