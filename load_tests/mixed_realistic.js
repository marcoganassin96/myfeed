import http from "k6/http";
import { check, sleep } from "k6";
import { Trend } from "k6/metrics";
import { BASE_URL, headers, NEWSLETTER_IDS, EVENT_IDS } from "./config.js";
import { cacheSubMetrics, handleSummary, cacheCount, CACHE_HEADER } from "./summary.js";

export { handleSummary };

const reqByCache = new Trend("req_by_cache", true);

export const options = {
  vus: 1000, duration: "120s",
  thresholds: {
    http_req_duration: ["p(95)<200"],
    http_req_failed: ["rate<0.01"],
    ...cacheSubMetrics,
  },
};

const TYPES = ["view", "click", "deep_dive"];

export default function () {
  const roll = Math.random();
  if (roll < 0.6) {
    const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
    const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
    const cacheTag = res.headers[CACHE_HEADER] || "NONE";
    const okTag = res.status > 0 && res.status < 400 ? "1" : "0";
    cacheCount.add(1, { cache: cacheTag, ok: okTag });
    reqByCache.add(res.timings.duration, { cache: cacheTag, ok: okTag });
    check(res, { "nl 200": (r) => r.status === 200 });
  } else if (roll < 0.9) {
    const event_id = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
    check(http.post(`${BASE_URL}/interactions`,
          JSON.stringify({ event_id, type: TYPES[Math.floor(Math.random() * TYPES.length)] }), { headers }),
          { "ix 201": (r) => r.status === 201 });
  } else {
    check(http.get(`${BASE_URL}/subscriptions`, { headers }), { "sub 200": (r) => r.status === 200 });
  }
  sleep(0.05);
}
