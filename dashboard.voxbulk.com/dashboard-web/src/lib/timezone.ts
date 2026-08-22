const TIMEZONE_LABELS: Record<string, string> = {
  "Europe/London": "UK time",
  "Australia/Sydney": "Sydney time",
  "America/New_York": "US Eastern time",
  "America/Chicago": "US Central time",
  "America/Los_Angeles": "US Pacific time",
  "America/Toronto": "Toronto time",
  "Asia/Dubai": "UAE time",
  "Asia/Singapore": "Singapore time",
  "Asia/Kolkata": "India time",
  "Africa/Johannesburg": "South Africa time",
};

export function detectBrowserTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || "Europe/London";
  } catch {
    return "Europe/London";
  }
}

export function timezoneLabel(tz: string): string {
  return TIMEZONE_LABELS[tz] || tz.replace(/_/g, " ");
}

export function pickSupportedTimezone(
  browserTz: string,
  supported: string[] | undefined,
  fallback = "Europe/London",
): string {
  const list = supported?.length ? supported : [fallback];
  if (list.includes(browserTz)) return browserTz;
  return list.includes(fallback) ? fallback : list[0];
}

export function formatTimezoneOption(tz: string): string {
  const label = timezoneLabel(tz);
  return label === tz ? tz : `${label} (${tz})`;
}
