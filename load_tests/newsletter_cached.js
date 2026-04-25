import http from "k6/http";
import { check, sleep } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  vus: 500, duration: "60s",
  thresholds: { http_req_duration: ["p(99)<50"], http_req_failed: ["rate<0.001"] },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  check(res, { "200": (r) => r.status === 200, "has newsletter_id": (r) => !!JSON.parse(r.body).newsletter_id });
  sleep(0.1);
}
