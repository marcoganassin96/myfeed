import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";
import { cacheSubMetrics, handleSummary, cacheCount, CACHE_HEADER } from "./summary.js";

export { handleSummary };

const reqByCache = new Trend("req_by_cache", true);
const bypassHeaders = { ...headers, "X-Bypass-Cache": "1" };

export const options = {
  scenarios: {
    warmup: {
      executor: "ramping-vus",
      exec: "warmupFn",
      stages: [{ duration: "30s", target: 30 }],
      gracefulRampDown: "5s",
    },
    load: {
      executor: "ramping-vus",
      exec: "loadFn",
      startTime: "35s",
      stages: [
        { duration: "5s",  target: 200 },
        { duration: "60s", target: 200 },
      ],
      gracefulRampDown: "5s",
    },
  },
  thresholds: {
    // Aurora baseline — tighten once 3 stable bypass runs exist (EC2 single-sample estimate: ~590ms p99)
    "http_req_duration{scenario:load}": ["p(99)<2000"],
    "http_req_failed{scenario:load}":   ["rate<0.001"],
    ...cacheSubMetrics,
  },
};

export function warmupFn() {
  http.get(`${BASE_URL}/health`);
}

export function loadFn() {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers: bypassHeaders });
  const cacheTag = res.headers[CACHE_HEADER] || "NONE";
  const okTag = res.status > 0 && res.status < 400 ? "1" : "0";
  cacheCount.add(1, { cache: cacheTag, ok: okTag });
  reqByCache.add(res.timings.duration, { cache: cacheTag, ok: okTag });
  check(res, { "200": (r) => r.status === 200 });
}
