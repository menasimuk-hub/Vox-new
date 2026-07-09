const DEV_PUBLIC = "http://localhost:5173";

export function publicSurveyOrigin(): string {
  const productionDefault =
    typeof window !== "undefined" && window.location.hostname === "dashboard.voxbulk.com"
      ? "https://voxbulk.com"
      : DEV_PUBLIC;
  const raw = String(import.meta.env.VITE_PUBLIC_APP_URL || productionDefault)
    .trim()
    .replace(/\/+$/, "");
  try {
    const u = new URL(raw.includes("://") ? raw : `http://${raw}`);
    return u.origin;
  } catch {
    return DEV_PUBLIC;
  }
}

export function previewThemeUrl(themeId: string, company?: string): string {
  const base = publicSurveyOrigin();
  const q = company ? `?company=${encodeURIComponent(company)}` : "";
  return `${base}/survey/preview/${themeId}${q}`;
}

export function themePreviewQrUrl(themeId: string, company: string, size = 120): string {
  const url = previewThemeUrl(themeId, company);
  return `https://api.qrserver.com/v1/create-qr-code/?size=${size}x${size}&margin=6&data=${encodeURIComponent(url)}`;
}

export type WebThemeWizardState = {
  baseTemplateId: string;
  overlayIds: string[];
  overlayMode: "auto" | "fixed";
  customEventLabel: string;
};

export function buildWebThemePayload(state: WebThemeWizardState) {
  return {
    base_template_id: state.baseTemplateId,
    overlay_ids: state.overlayIds,
    overlay_mode: state.overlayMode,
    custom_event_label: state.customEventLabel.trim() || undefined,
  };
}

export function webThemeFromApi(raw?: Record<string, unknown> | null): WebThemeWizardState {
  if (!raw) {
    return { baseTemplateId: "auto", overlayIds: [], overlayMode: "auto", customEventLabel: "" };
  }
  return {
    baseTemplateId: String(raw.base_template_id || "auto"),
    overlayIds: Array.isArray(raw.overlay_ids) ? raw.overlay_ids.map((id) => String(id)) : [],
    overlayMode: raw.overlay_mode === "fixed" ? "fixed" : "auto",
    customEventLabel: String(raw.custom_event_label || ""),
  };
}
