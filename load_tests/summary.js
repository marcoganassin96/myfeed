import { textSummary } from "https://jslib.k6.io/k6-summary/0.0.2/index.js";
import { Counter } from "k6/metrics";

export const CACHE_HEADER = "X-Lambda-Cache";

// Counter sub-metrics have values.count in handleSummary; Trend sub-metrics only have values.avg.
// cacheCount (Counter) → counts; req_by_cache (Trend) → latency.
export const cacheCount = new Counter("cache_count");

export const cacheSubMetrics = {
  "cache_count{cache:HIT,ok:1}":  [],
  "cache_count{cache:HIT,ok:0}":  [],
  "cache_count{cache:MISS,ok:1}": [],
  "cache_count{cache:MISS,ok:0}": [],
  "cache_count{cache:NONE,ok:1}": [],
  "cache_count{cache:NONE,ok:0}": [],
  "req_by_cache{cache:HIT,ok:1}":  [],
  "req_by_cache{cache:HIT,ok:0}":  [],
  "req_by_cache{cache:MISS,ok:1}": [],
  "req_by_cache{cache:MISS,ok:0}": [],
  "req_by_cache{cache:NONE,ok:1}": [],
  "req_by_cache{cache:NONE,ok:0}": [],
};

function buildBreakdown(data) {
  const m = data.metrics;
  const label = { HIT: "Redis (HIT)", MISS: "Aurora (MISS)", NONE: "No header" };
  const col = (s, w) => String(s).padStart(w);

  const rows = [];
  for (const src of ["HIT", "MISS", "NONE"]) {
    const cntOk   = m[`cache_count{cache:${src},ok:1}`];
    const cntFail = m[`cache_count{cache:${src},ok:0}`];
    if (!cntOk && !cntFail) continue;
    const ok   = cntOk   ? (cntOk.values.count   || 0) : 0;
    const fail = cntFail ? (cntFail.values.count || 0) : 0;
    const total = ok + fail;
    if (total === 0) continue;

    const latOk   = m[`req_by_cache{cache:${src},ok:1}`];
    const latFail = m[`req_by_cache{cache:${src},ok:0}`];
    rows.push({ src, ok, fail, total,
      okAvg:   latOk   ? latOk.values.avg   : null,
      failAvg: latFail ? latFail.values.avg : null,
    });
  }

  if (rows.length === 0) return "";

  let out = "\n  Cache breakdown:\n";
  out += `  ${"Source".padEnd(14)} ${col("Reqs",6)} ${col("OK%",7)} ${col("Fail%",7)} ${col("OK avg",8)} ${col("Fail avg",9)}\n`;
  out += "  " + "─".repeat(58) + "\n";
  for (const r of rows) {
    const okPct   = `${(100 * r.ok   / r.total).toFixed(1)}%`;
    const failPct = `${(100 * r.fail / r.total).toFixed(1)}%`;
    const okAvg   = r.okAvg   !== null ? `${r.okAvg.toFixed(0)}ms`   : "—";
    const failAvg = r.failAvg !== null ? `${r.failAvg.toFixed(0)}ms` : "—";
    out += `  ${(label[r.src] || r.src).padEnd(14)} ${col(r.total,6)} ${col(okPct,7)} ${col(failPct,7)} ${col(okAvg,8)} ${col(failAvg,9)}\n`;
  }
  return out;
}

export function handleSummary(data) {
  return {
    stdout: buildBreakdown(data) + textSummary(data, { indent: "  ", enableColors: true }),
  };
}
