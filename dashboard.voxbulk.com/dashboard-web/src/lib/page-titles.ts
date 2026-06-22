type T = { title: string; subtitle?: string };

const map: Record<string, T> = {
  "/": { title: "Dashboard", subtitle: "Live · Overview" },

  "/interviews": { title: "Saved interviews", subtitle: "Manage campaigns" },
  "/interviews/new": { title: "Create new interview", subtitle: "AI phone screening" },
  "/interviews/results": { title: "Interview results", subtitle: "Candidates & transcripts" },
  "/interviews/reports": { title: "Interview reports", subtitle: "Campaign performance" },

  "/surveys": { title: "Saved surveys", subtitle: "Manage campaigns" },
  "/surveys/new": { title: "Create new survey", subtitle: "AI phone or WhatsApp" },
  "/surveys/results": { title: "Survey results", subtitle: "Anonymous aggregates" },
  "/surveys/reports": { title: "Survey reports", subtitle: "Campaign performance" },

  "/feedback": { title: "Saved QR surveys", subtitle: "Manage locations" },
  "/feedback/new": { title: "Create QR survey", subtitle: "WhatsApp feedback wizard" },
  "/feedback/results": { title: "Feedback results", subtitle: "Responses by location" },
  "/feedback/compare": { title: "Compare locations", subtitle: "Multi-location survey comparison" },
  "/feedback/edit": { title: "Edit QR survey", subtitle: "Topics and closing questions" },

  "/recovery": { title: "Recovery queue", subtitle: "Missed-appointment outreach" },
  "/recovery/no-show": { title: "No-show follow-up", subtitle: "AI calling settings" },
  "/recovery/emergency": { title: "Emergency reschedule", subtitle: "Mass cancel + rebook" },
  "/recovery/recall": { title: "Recall campaigns", subtitle: "Dental recall outreach" },
  "/recovery/offers": { title: "Offer campaigns", subtitle: "Promotional fill" },

  "/follow-up": { title: "Reminder sequences", subtitle: "WhatsApp reminders" },

  "/appointments": { title: "Appointment manager", subtitle: "CRM confirmations & AI calls" },
  "/appointments/setup": { title: "Setup wizard", subtitle: "CRM, WhatsApp & AI calls" },
  "/appointments/reports": { title: "Reports", subtitle: "Appointment performance" },
  "/follow-up": { title: "Reminder sequences", subtitle: "WhatsApp reminders" },

  "/campaigns": { title: "My templates", subtitle: "Broadcast campaigns" },
  "/campaigns/new": { title: "Create template", subtitle: "WhatsApp broadcast" },
  "/campaigns/send": { title: "Send campaign", subtitle: "Broadcast to audience" },

  "/settings/services": { title: "Services", subtitle: "Enable / disable modules" },
  "/settings/profile": { title: "Profile settings", subtitle: "Company & revenue" },
  "/settings/system": { title: "System settings", subtitle: "API, WhatsApp, AI calling" },
  "/settings/team": { title: "Team members", subtitle: "Invite & roles" },
  "/settings/opt-out": { title: "Opt-out list", subtitle: "Do-not-contact" },
  "/settings/audit": { title: "Audit log", subtitle: "Compliance activity" },

  "/account/packages": { title: "Packages & pricing", subtitle: "Plans & bundles" },
  "/account/feedback/packages": { title: "Customer feedback plans", subtitle: "QR survey packages" },
  "/account/billing": { title: "Billing", subtitle: "Subscription & invoices" },
  "/account/usage": { title: "Usage", subtitle: "Campaign usage & charges" },
  "/account/support": { title: "Support", subtitle: "Get help" },
  "/account/support/faq": { title: "Documentation & FAQ", subtitle: "Help centre" },
  "/account/support/tickets": { title: "Support tickets", subtitle: "Email conversations" },
};

export function titleForPath(path: string): T {
  const clean = path.split("?")[0].split("#")[0].replace(/\/+$/, "") || "/";
  if (map[clean]) return map[clean];
  const keys = Object.keys(map).sort((a, b) => b.length - a.length);
  const k = keys.find((key) => clean.startsWith(key + "/") || clean === key);
  return k ? map[k] : { title: "VoxBulk" };
}
