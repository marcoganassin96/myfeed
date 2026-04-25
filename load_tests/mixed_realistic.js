import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS, EVENT_IDS } from "./config.js";

export const options = {
  vus: 1000, duration: "120s",
  thresholds: { http_req_duration: ["p(95)<200"], http_req_failed: ["rate<0.01"] },
};

const TYPES = ["view", "click", "deep_dive"];

export default function () {
  const roll = Math.random();
  if (roll < 0.6) {
    const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
    check(http.get(`${BASE_URL}/newsletters/${id}`, { headers }), { "nl 200": (r) => r.status === 200 });
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
