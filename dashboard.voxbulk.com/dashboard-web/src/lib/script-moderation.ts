export type ScriptModerationConfig = {
  script_approved?: boolean;
  script_moderation_status?: string;
  script_moderation_reason?: string;
  script_moderation_category?: string;
};

export function scriptModerationBanner(config: ScriptModerationConfig | null | undefined): string | null {
  const status = String(config?.script_moderation_status || "").trim().toLowerCase();
  const reason = String(config?.script_moderation_reason || "").trim();
  if (status === "pending_admin_review") {
    return reason
      ? `Script blocked: ${reason} Edit the text and approve again, or wait for VoxBulk admin approval.`
      : "Script pending admin review. Edit the text and approve again, or wait for VoxBulk admin approval.";
  }
  if (status === "rejected") {
    return reason
      ? `Script rejected: ${reason} Please edit the text and approve again.`
      : "Script rejected. Please edit the text and approve again.";
  }
  return null;
}

export function syncApprovedFromModerationConfig(config: ScriptModerationConfig | null | undefined): boolean {
  if (!config) return false;
  const status = String(config.script_moderation_status || "").trim().toLowerCase();
  if (status === "approved" && config.script_approved === true) return true;
  if (!status && config.script_approved === true) return true;
  return false;
}

export function moderationApproveToast(config: ScriptModerationConfig | null | undefined): {
  ok: boolean;
  message: string;
} {
  if (syncApprovedFromModerationConfig(config)) {
    return { ok: true, message: "Script approved" };
  }
  const banner = scriptModerationBanner(config);
  return { ok: false, message: banner || "Script could not be approved" };
}
