import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";
import { cacheSubMetrics, handleSummary, cacheCount, CACHE_HEADER } from "./summary.js";

export { handleSummary };

const reqByCache = new Trend("req_by_cache", true);

export const options = {
  vus: 500, duration: "60s",
  thresholds: {
    http_req_duration: ["p(99)<50"],
    http_req_failed: ["rate<0.001"],
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
  if (res.status !== 200) console.log(`FAIL ${res.status} id=${id}: ${res.body.substring(0, 200)}`);
  check(res, { "200": (r) => r.status === 200, "has newsletter_id": (r) => !!JSON.parse(r.body).newsletter_id });
  sleep(0.1);
}
