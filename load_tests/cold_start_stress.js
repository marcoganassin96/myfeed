import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

export const options = {
  stages: [
    { duration: "10s", target: 1000 },
    { duration: "30s", target: 1000 },
    { duration: "10s", target: 0 },
  ],
  thresholds: { http_req_failed: ["rate<0.01"] },
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  check(http.get(`${BASE_URL}/newsletters/${id}`, { headers }), { "not 5xx": (r) => r.status < 500 });
}
