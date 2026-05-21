import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";
import { cacheSubMetrics, handleSummary, cacheCount, CACHE_HEADER } from "./summary.js";

export { handleSummary };

const reqByCache = new Trend("req_by_cache", true);

export const options = {
  scenarios: {
    warmup: {
      executor: "ramping-vus",
      exec: "warmupFn",
      stages: [{ duration: "4s", target: 100 }],
      gracefulRampDown: "1s",
    },
    load: {
      executor: "ramping-vus",
      exec: "loadFn",
      startTime: "5s",
      stages: [
        { duration: "5s",  target: 100 },
        { duration: "30s", target: 100 },
      ],
      gracefulRampDown: "1s",
    },
  },
  thresholds: {
    "http_req_duration{scenario:load}": ["p(99)<200"],
    "http_req_failed{scenario:load}":   ["rate<0.001"],
    ...cacheSubMetrics,
  },
};

export function warmupFn() {
  http.get(`${BASE_URL}/health`);
}

export function loadFn() {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  const cacheTag = res.headers[CACHE_HEADER] || "NONE";
  const okTag = res.status > 0 && res.status < 400 ? "1" : "0";
  cacheCount.add(1, { cache: cacheTag, ok: okTag });
  reqByCache.add(res.timings.duration, { cache: cacheTag, ok: okTag });
  check(res, { "200": (r) => r.status === 200 });
}
