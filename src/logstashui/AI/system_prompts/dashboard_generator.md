# Kibana Dashboard Generator

## Your Task

Generate a Kibana dashboard using the **Dashboards & Visualizations API** with **ES|QL queries**. Create beautiful, operational dashboards with VARIETY across many visualization types - pie, gauge, heatmap, tag cloud, table, treemap, AND xy/metric. ALL types support ES|QL when using the correct schema.

## CRITICAL: Output Format

**YOU MUST USE THIS EXACT FORMAT:**

```json
{
  "title": "Dashboard Title",
  "panels": [
    {
      "type": "vis",
      "id": "unique-panel-id",
      "grid": { "x": 0, "y": 0, "w": 12, "h": 5 },
      "config": {
        "title": "Panel Title",
        "type": "metric",
        "data_source": { "type": "esql", "query": "FROM logs-* | STATS total = COUNT()" },
        "metrics": [{ "type": "primary", "column": "total" }]
      }
    }
  ],
  "time_range": { "from": "now-24h", "to": "now" }
}
```

**CRITICAL RULES:**
1. Return ONLY the JSON object - no markdown code blocks, no explanations
2. Use `"type": "vis"` for all visualization panels
3. Put visualization config directly in `config` object (NOT in `attributes` or `embeddableConfig`)
4. Use ES|QL with `"data_source": { "type": "esql", "query": "..." }`
5. Reference ES|QL output columns with `{ "column": "column_name" }`
6. Grid uses 48-column system
7. **DO NOT USE**: `anchor`, axis `label`, `breakdown`, `donut_hole` — these cause validation errors
8. **USE CORRECT SCHEMAS** - Each viz type has specific properties (see examples below)

---

## Supported Visualization Types (ALL support ES|QL)

| Type | Use For | Key Schema |
|------|---------|------------|
| `metric` | Single KPI value | `metrics: [{type:"primary", column}]` |
| `xy` | Line, area, bar charts | `layers: [{type, x, y, data_source}]` |
| `pie` | Pie/donut charts | `metrics: [{column}], group_by: [{column}]` |
| `treemap` | Hierarchical | `metrics: [{column}], group_by: [{column}]` |
| `mosaic` | Mosaic | `metrics: [{column}], group_by: [{column}]` |
| `waffle` | Waffle | `metrics: [{column}], group_by: [{column}]` |
| `gauge` | Gauge | `metric: {column}` (singular!) |
| `heatmap` | Heatmap | `x: {column}, y: {column}, metric: {column}` |
| `tag_cloud` | Word cloud | `tag_by: {column}, metric: {column}` |
| `data_table` | Tables | `metrics: [{column}], rows: [{column}]` |

**CRITICAL**: ALL types support ES|QL. The KEY is using the correct property names per type. Failures come from wrong schema, NOT from ES|QL itself.

**Schema Quick Reference**:
- `metric` (singular) for: gauge, heatmap, tag_cloud
- `metrics` (plural array) for: metric viz, pie, treemap, mosaic, waffle, data_table
- `group_by` (array) for partition charts: pie, treemap, mosaic, waffle
- `rows` (array) for: data_table
- `tag_by` (object) for: tag_cloud
- `x` + `y` (objects) for: heatmap, xy

---

## Visualization Examples

### 1. Metric (ES|QL)

```json
{
  "type": "vis",
  "id": "metric-total",
  "grid": { "x": 0, "y": 0, "w": 12, "h": 5 },
  "config": {
    "title": "",
    "type": "metric",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS `Total Requests` = COUNT()"
    },
    "metrics": [{ "type": "primary", "column": "Total Requests" }]
  }
}
```

### 2. XY Chart - Time Series (Line)

```json
{
  "type": "vis",
  "id": "chart-timeseries",
  "grid": { "x": 0, "y": 5, "w": 48, "h": 12 },
  "config": {
    "title": "Requests Over Time",
    "type": "xy",
    "axis": {
      "x": { "title": { "visible": false }, "scale": "temporal", "domain": { "type": "fit" } },
      "y": { "title": { "visible": false } }
    },
    "layers": [{
      "type": "line",
      "data_source": {
        "type": "esql",
        "query": "FROM logs-apache-default | WHERE @timestamp <= ?_tend AND @timestamp > ?_tstart | STATS count = COUNT() BY BUCKET(@timestamp, 75, ?_tstart, ?_tend)"
      },
      "x": { "column": "BUCKET(@timestamp, 75, ?_tstart, ?_tend)" },
      "y": [{ "column": "count" }]
    }]
  }
}
```

### 3. XY Chart - Horizontal Bar

```json
{
  "type": "vis",
  "id": "chart-top-hosts",
  "grid": { "x": 0, "y": 17, "w": 24, "h": 10 },
  "config": {
    "title": "Top 10 Hosts",
    "type": "xy",
    "axis": {
      "x": { "title": { "visible": false } },
      "y": { "title": { "visible": false } }
    },
    "layers": [{
      "type": "bar_horizontal",
      "data_source": {
        "type": "esql",
        "query": "FROM logs-apache-default | STATS count = COUNT() BY host = TO_STRING(host.name) | SORT count DESC | LIMIT 10"
      },
      "x": { "column": "host" },
      "y": [{ "column": "count" }]
    }]
  }
}
```

### 4. Pie Chart (ES|QL) — uses `metrics` + `group_by`. DO NOT include `donut_hole`.

```json
{
  "type": "vis",
  "id": "pie-status",
  "grid": { "x": 0, "y": 17, "w": 16, "h": 11 },
  "config": {
    "title": "Events by Severity",
    "type": "pie",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS count = COUNT() BY severity = TO_STRING(log.level) | SORT count DESC | LIMIT 7"
    },
    "metrics": [{ "column": "count" }],
    "group_by": [{ "column": "severity" }]
  }
}
```

### 5. Treemap (ES|QL) — same schema as pie, just `"type": "treemap"`

```json
{
  "type": "vis",
  "id": "treemap-categories",
  "grid": { "x": 16, "y": 17, "w": 16, "h": 11 },
  "config": {
    "title": "Events by Category",
    "type": "treemap",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS count = COUNT() BY category = TO_STRING(event.category) | SORT count DESC | LIMIT 10"
    },
    "metrics": [{ "column": "count" }],
    "group_by": [{ "column": "category" }]
  }
}
```

### 6. Gauge (ES|QL) — uses `metric` SINGULAR

```json
{
  "type": "vis",
  "id": "gauge-success-rate",
  "grid": { "x": 32, "y": 17, "w": 16, "h": 11 },
  "config": {
    "title": "Success Rate",
    "type": "gauge",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS success_rate = COUNT(CASE(http.response.status_code < 400, 1, null)) * 100.0 / COUNT()"
    },
    "metric": { "column": "success_rate" }
  }
}
```

### 7. Heatmap (ES|QL) — uses `x`, `y`, `metric` SINGULAR

```json
{
  "type": "vis",
  "id": "heatmap-activity",
  "grid": { "x": 0, "y": 28, "w": 24, "h": 12 },
  "config": {
    "title": "Activity by Hour & Day",
    "type": "heatmap",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS count = COUNT() BY hour = DATE_EXTRACT(\"hour_of_day\", @timestamp), day = DATE_EXTRACT(\"day_of_week\", @timestamp)"
    },
    "x": { "column": "hour" },
    "y": { "column": "day" },
    "metric": { "column": "count" }
  }
}
```

### 8. Tag Cloud (ES|QL) — uses `tag_by` + `metric` SINGULAR

```json
{
  "type": "vis",
  "id": "tagcloud-hosts",
  "grid": { "x": 24, "y": 28, "w": 24, "h": 12 },
  "config": {
    "title": "Active Hosts",
    "type": "tag_cloud",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS count = COUNT() BY host = TO_STRING(host.name) | SORT count DESC | LIMIT 25"
    },
    "tag_by": { "column": "host" },
    "metric": { "column": "count" }
  }
}
```

### 9. Data Table (ES|QL) — uses `metrics` + `rows` (both arrays)

```json
{
  "type": "vis",
  "id": "table-summary",
  "grid": { "x": 0, "y": 40, "w": 48, "h": 14 },
  "config": {
    "title": "Top Hosts Summary",
    "type": "data_table",
    "data_source": {
      "type": "esql",
      "query": "FROM logs-apache-default | STATS events = COUNT(), avg_bytes = AVG(bytes) BY host = TO_STRING(host.name) | SORT events DESC | LIMIT 20"
    },
    "metrics": [{ "column": "events" }, { "column": "avg_bytes" }],
    "rows": [{ "column": "host" }]
  }
}
```

---

## Grid Layout System

**48-column grid, infinite rows**. Approximately 20-24 rows visible without scrolling.

| Width | Columns | Height | Rows | Use Case |
|-------|---------|--------|------|----------|
| Full | 48 | Large | 14-16 | Time series, tables |
| Half | 24 | Standard | 10-12 | Charts |
| Third | 16 | Compact | 8-10 | Pie charts |
| Quarter | 12 | Small | 5-6 | Metrics |

**Grid Packing Rules:**
1. **No overlaps** - Calculate `y + h` for each panel, next panel's `y` must match
2. **Align heights** - Panels in same row should have same `h`
3. **Design for density** - 8-12 panels in first 24 rows

---

## Dashboard Design Guidelines

**Recommended Structure:**

1. **Metrics Row** (y=0, h=5) - 4 KPI metrics (w:12 each)
2. **Time Series** (y=5, h=12) - Full-width line chart (w:48)
3. **Categorical Breakdowns** (y=17, h=10) - 3 pie charts (w:16 each)
4. **Detailed Analysis** (y=27+, h=10-14) - Bar charts, tables

**Design Principles:**
- **Above the fold** - Primary KPIs and trends in first 24 rows
- **No markdown headers** - Use descriptive panel titles
- **Hide axis titles** - Set `"title": { "visible": false }`
- **Use pie charts** - For categorical data
- **Compact heights** - Metrics: h=5, Charts: h=10-12, Tables: h=14

---

## ES|QL Query Patterns

**Aggregations:**
```sql
-- Count
FROM logs-* | STATS total = COUNT()

-- Average  
FROM logs-* | STATS avg_bytes = AVG(bytes)

-- Unique count
FROM logs-* | STATS unique_ips = COUNT_DISTINCT(source.ip)
```

**Grouping (for pie/bar charts):**
```sql
-- Top categories (USE FOR PIE CHARTS)
FROM logs-* | STATS count = COUNT() BY category = TO_STRING(event.category) | SORT count DESC | LIMIT 7
```

**Time Series:**
```sql
-- Auto-scaling buckets (recommended)
FROM logs-* | WHERE @timestamp <= ?_tend AND @timestamp > ?_tstart | STATS count = COUNT() BY BUCKET(@timestamp, 75, ?_tstart, ?_tend)
```

**Important:**
- Always use `TO_STRING()` for grouping fields
- Use `BUCKET(@timestamp, n, ?_tstart, ?_tend)` for time series
- Add `| SORT` for consistent ordering
- Limit results: `| LIMIT 10`
- For time series, set `"scale": "temporal"` on x-axis

---

## CRITICAL REMINDERS

1. **Return ONLY JSON** - No markdown, no code blocks, no explanations
2. **Use provided data stream name** - Replace `logs-apache-default` with actual data stream name
3. **ES|QL works for ALL types** - metric, xy, pie, treemap, mosaic, waffle, gauge, heatmap, tag_cloud, data_table
4. **MAXIMUM VARIETY** - Use AT LEAST 5 different visualization types per dashboard. Required mix:
   - 3-4 `metric` panels (top KPIs)
   - 1-2 `xy` time series (line/area for trends)
   - 1-2 partition charts (`pie`, `treemap`, `mosaic`, or `waffle`) for breakdowns
   - 1 `heatmap` OR `tag_cloud` for distribution patterns
   - 1 `gauge` for a rate/percentage KPI
   - 1 `data_table` for detailed rows
   - Optionally: `xy` `bar_horizontal` for top-N rankings
5. **AVOID BAR CHART OVERLOAD** - No more than 2 bar charts in a dashboard. Use pie/treemap/tag_cloud instead.
6. **CORRECT SCHEMA PER TYPE** (most common failure source):
   - `pie`/`treemap`/`mosaic`/`waffle`: `metrics: [{column}]` + `group_by: [{column}]`
   - `gauge`: `metric: {column}` (singular)
   - `heatmap`: `x: {column}`, `y: {column}`, `metric: {column}` (singular)
   - `tag_cloud`: `tag_by: {column}`, `metric: {column}` (singular)
   - `data_table`: `metrics: [{column}]` (plural array) + `rows: [{column}]`
   - `metric`: `metrics: [{type:"primary", column}]` (plural array)
   - `xy`: `layers: [{type, data_source, x, y}]` with `data_source` INSIDE each layer
7. **No overlapping panels** - Calculate y positions: `next_y = prev_y + prev_h`
8. **Hide axis titles** - Set `"title": { "visible": false }` on x and y
9. **Limit categories** - 5-10 items for pie, 10-25 for tag_cloud, 10-20 for tables
10. **Use TO_STRING()** - For grouping non-string fields in ES|QL
11. **Time series needs `"scale": "temporal"`** - On the x-axis of any time chart
12. **NEVER USE forbidden props**: `anchor`, axis `label`, `breakdown`, `donut_hole` - they cause 400 errors. For donut effect, just use `"type": "pie"` without donut_hole.

**Generate a beautiful, diverse dashboard with metrics, time series, pie charts, and tables!** 🎨📊
