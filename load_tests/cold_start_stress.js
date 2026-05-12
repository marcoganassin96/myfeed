import http from "k6/http";
import { check } from "k6";
import { Trend } from "k6/metrics";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";
import { cacheSubMetrics, handleSummary, cacheCount, CACHE_HEADER } from "./summary.js";

export { handleSummary };

const reqByCache = new Trend("req_by_cache", true);

export const options = {
  stages: [
    { duration: "10s", target: 1000 },
    { duration: "30s", target: 1000 },
    { duration: "10s", target: 0 },
  ],
  thresholds: {
    http_req_failed: ["rate<0.01"],
    ...cacheSubMetrics,
  },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  const cacheTag = res.headers[CACHE_HEADER] || "NONE";
  const okTag = res.status > 0 && res.status < 400 ? "1" : "0";
  cacheCount.add(1, { cache: cacheTag, ok: okTag });
  reqByCache.add(res.timings.duration, { cache: cacheTag, ok: okTag });
  check(res, { "not 5xx": (r) => r.status < 500 });
}
