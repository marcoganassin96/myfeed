import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  vus: 200, duration: "60s",
  thresholds: { http_req_duration: ["p(99)<300"], http_req_failed: ["rate<0.001"] },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  check(http.get(`${BASE_URL}/newsletters/${id}?_cb=${Date.now()}`, { headers }),
        { "200": (r) => r.status === 200 });
}
