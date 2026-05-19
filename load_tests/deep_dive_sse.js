import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, EVENT_IDS } from "./config.js";

export const options = {
  vus: 50, duration: "60s",
  thresholds: { http_req_duration: ["p(95)<500"], http_req_failed: ["rate<0.01"] },
};

export default function () {
  const id = EVENT_IDS[Math.floor(Math.random() * EVENT_IDS.length)];
  const res = http.post(`${BASE_URL}/deep-dive/${id}`, null, { headers });
  check(res, {
    "200": (r) => r.status === 200,
    "SSE content-type": (r) => (r.headers["Content-Type"] || "").includes("text/event-stream"),
    "done:true present": (r) => r.body.includes('"done":true') || r.body.includes('"done": true'),
  });
}
