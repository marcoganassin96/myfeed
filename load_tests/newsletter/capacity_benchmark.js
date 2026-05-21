import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS } from "./config.js";

// Stepped VU ramp — observation only, no pass/fail thresholds.
// After running, inspect k6 output per stage:
//   1. Find last stage where p99 < 100ms AND error_rate < 0.1% → this is your safe req/s (S)
//   2. Note CPU% from CloudWatch ECS metrics at that stage
//   3. Optional: set ALBRequestCountPerTarget threshold = S × 60 × 0.7 in Terraform
//   4. Update aws_appautoscaling_policy.cpu target_value to observed CPU% if different from 70
export const options = {
  stages: [
    { duration: "2m", target: 10 },
    { duration: "2m", target: 25 },
    { duration: "2m", target: 50 },
    { duration: "2m", target: 100 },
    { duration: "2m", target: 150 },
    { duration: "2m", target: 200 },
    { duration: "1m", target: 0 },
  ],
};

export default function () {
  const id = NEWSLETTER_IDS[Math.floor(Math.random() * NEWSLETTER_IDS.length)];
  const res = http.get(`${BASE_URL}/newsletters/${id}`, { headers });
  check(res, { "200": (r) => r.status === 200 });
}
