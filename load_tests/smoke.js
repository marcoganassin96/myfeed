import http from "k6/http";
import { check } from "k6";
import { BASE_URL, headers, NEWSLETTER_IDS, EVENT_IDS } from "./config.js";

export const options = {
  vus: 1,
  iterations: 1,
  thresholds: {
    http_req_duration: ["p(99)<10000"],
    http_req_failed: ["rate<0.01"],
  },
};

export default function () {
  const nlId = NEWSLETTER_IDS[0];
  const eventId = EVENT_IDS[0];

  check(http.get(`${BASE_URL}/newsletters/${nlId}`, { headers }), {
    "newsletter 200": (r) => r.status === 200,
  });

  check(http.get(`${BASE_URL}/subscriptions`, { headers }), {
    "subscriptions 200": (r) => r.status === 200,
  });

  check(
    http.post(
      `${BASE_URL}/interactions`,
      JSON.stringify({ event_id: eventId, type: "view" }),
      { headers }
    ),
    { "interaction 201": (r) => r.status === 201 }
  );

  check(http.post(`${BASE_URL}/deep-dive/${eventId}`, null, { headers }), {
    "deep-dive 200": (r) => r.status === 200,
    "SSE content-type": (r) => (r.headers["Content-Type"] || "").includes("text/event-stream"),
  });
}
