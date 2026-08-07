/** Build Expo scan-landing URL + QR image URLs with provider fallbacks. */

export function resolveExpoWebUrl(input: {
  web_url?: string | null;
  qr_token?: string | null;
  publicSiteBase?: string | null;
}): string {
  const direct = String(input.web_url || "").trim();
  if (direct.startsWith("http://") || direct.startsWith("https://")) return direct;
  const token = String(input.qr_token || "").trim();
  if (!token) return "";
  const site = String(input.publicSiteBase || "https://voxbulk.com").replace(/\/+$/, "");
  return `${site}/expo/${encodeURIComponent(token)}`;
}

export function buildExpoQrImageCandidates(webUrl: string, size = 200): string[] {
  const data = String(webUrl || "").trim();
  if (!data) return [];
  const enc = encodeURIComponent(data);
  return [
    `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&margin=8&data=${enc}`,
    `https://quickchart.io/qr?text=${enc}&size=${size}&margin=1`,
  ];
}

export function buildExpoQrImageUrl(webUrl: string, size = 200): string {
  return buildExpoQrImageCandidates(webUrl, size)[0] || "";
}

/** Format ISO datetime/date for Expo package windows (UK-friendly). */
export function formatExpoDay(iso?: string | null): string | null {
  if (!iso) return null;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    const bare = String(iso).slice(0, 10);
    return /^\d{4}-\d{2}-\d{2}$/.test(bare) ? bare : null;
  }
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

export function formatExpoWindow(startIso?: string | null, endIso?: string | null): string | null {
  const start = formatExpoDay(startIso);
  const end = formatExpoDay(endIso);
  if (start && end) return `${start} → ${end}`;
  return start || end || null;
}

