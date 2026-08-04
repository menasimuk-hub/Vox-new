import { AlertCircle, Mail, MailOpen, Paperclip, Send, Star } from "lucide-react";
import type { KpiData } from "@/lib/api";
import type { MailMessage } from "@/lib/mail-store";

function Kpi({
  label,
  value,
  icon: Icon,
  tone,
}: {
  label: string;
  value: number | string;
  icon: React.ElementType;
  tone?: "brand" | "warning" | "success";
}) {
  const toneClass =
    tone === "warning"
      ? "text-warning"
      : tone === "success"
        ? "text-success"
        : "text-primary";
  return (
    <div className="rounded-xl border bg-card px-4 py-3">
      <div className="flex items-center justify-between">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          {label}
        </p>
        <Icon className={`size-4 ${toneClass}`} />
      </div>
      <p className="mt-1 font-display text-2xl font-semibold">{value}</p>
    </div>
  );
}

export function KpiRow({ messages, kpi }: { messages: MailMessage[]; kpi?: KpiData }) {
  const inbox = messages.filter((m) => m.folder === "inbox");
  const unread = kpi?.unread ?? inbox.filter((m) => m.unread).length;
  const important = kpi?.important ?? inbox.filter((m) => m.important).length;
  const starred = kpi?.starred ?? inbox.filter((m) => m.starred).length;
  const inboxCount = kpi?.total ?? inbox.length;
  const attachments = inbox.filter((m) => m.hasAttachment).length;
  const sent = messages.filter((m) => m.folder === "sent").length;
  const today = inbox.filter(
    (m) => Date.now() - new Date(m.date).getTime() < 24 * 3600 * 1000,
  ).length;

  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
      <Kpi label="Inbox" value={inboxCount} icon={Mail} />
      <Kpi label="Unread" value={unread} icon={MailOpen} tone="warning" />
      <Kpi label="Today" value={today} icon={MailOpen} />
      <Kpi label="Important" value={important} icon={AlertCircle} tone="warning" />
      <Kpi label="Starred" value={starred} icon={Star} tone="success" />
      <Kpi label="Sent" value={sent} icon={Send} tone="success" />
      <div className="col-span-2 hidden items-center gap-2 rounded-xl border bg-card px-4 py-3 text-sm text-muted-foreground md:col-span-3 xl:hidden">
        <Paperclip className="size-4" /> {attachments} messages with attachments
      </div>
    </div>
  );
}
