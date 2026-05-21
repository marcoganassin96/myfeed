export const BASE_URL = __ENV.API_URL || "";
export const headers = {
  Authorization: `Bearer ${__ENV.COGNITO_TOKEN || ""}`,
  "Content-Type": "application/json",
};
export const NEWSLETTER_IDS = (__ENV.NEWSLETTER_IDS || "").split(",").filter(Boolean);
export const EVENT_IDS      = (__ENV.EVENT_IDS      || "").split(",").filter(Boolean);
