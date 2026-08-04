import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  Inbox,
  Send,
  Star,
  Trash2,
  Tag,
  Users,
  Search,
  PenSquare,
  RefreshCw,
  Paperclip,
  Sparkles,
  Gift,
  X,
  Mail,
} from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/sales/mail")({
  head: () => ({ meta: [{ title: "Mail — Sales — VoxBulk" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesMailPage,
});

type TabKey = "inbox" | "sent" | "starred" | "trash" | "labels" | "contacts";

type MailStatus = {
  configured?: boolean;
  has_imap?: boolean;
  has_smtp?: boolean;
  signature_preview?: string;
  promo_code?: string;
};

type MailMessage = {
  id: string;
  from_email?: string;
  from_name?: string | null;
  to_email?: string | null;
  subject?: string;
  preview?: string;
  date?: string | null;
  is_read?: boolean;
  is_starred?: boolean;
  has_attachments?: boolean;
};

type MailDetail = MailMessage & {
  body_text?: string | null;
  body_html?: string | null;
  cc_email?: string | null;
};

type MailLabel = { id: string; name: string; color: string };
type MailContact = { id: string; email: string; name?: string | null; company?: string | null };

const TABS: { key: TabKey; label: string; icon: typeof Inbox; folder?: string }[] = [
  { key: "inbox", label: "Inbox", icon: Inbox, folder: "INBOX" },
  { key: "sent", label: "Sent", icon: Send, folder: "Sent" },
  { key: "starred", label: "Starred", icon: Star, folder: "Starred" },
  { key: "trash", label: "Trash", icon: Trash2, folder: "Trash" },
  { key: "labels", label: "Labels", icon: Tag },
  { key: "contacts", label: "Contacts", icon: Users },
];

function formatWhen(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  const now = new Date();
  if (d.toDateString() === now.toDateString()) {
    return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  return d.toLocaleDateString([], { day: "numeric", month: "short" });
}

function SalesMailPage() {
  const [tab, setTab] = React.useState<TabKey>("inbox");
  const [status, setStatus] = React.useState<MailStatus | null>(null);
  const [messages, setMessages] = React.useState<MailMessage[]>([]);
  const [labels, setLabels] = React.useState<MailLabel[]>([]);
  const [contacts, setContacts] = React.useState<MailContact[]>([]);
  const [selected, setSelected] = React.useState<MailDetail | null>(null);
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [syncing, setSyncing] = React.useState(false);
  const [composeOpen, setComposeOpen] = React.useState(false);

  const [to, setTo] = React.useState("");
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const [polishing, setPolishing] = React.useState(false);
  const [newLabel, setNewLabel] = React.useState("");

  const loadStatus = React.useCallback(async () => {
    const res = await apiFetch<MailStatus & { ok?: boolean }>("/sales/mail/status");
    setStatus(res);
    return res;
  }, []);

  const loadMessages = React.useCallback(async (folder: string) => {
    const res = await apiFetch<{ items: MailMessage[] }>(
      `/sales/mail/messages?folder=${encodeURIComponent(folder)}&limit=80`,
    );
    setMessages(res.items || []);
  }, []);

  const loadLabels = React.useCallback(async () => {
    const res = await apiFetch<{ items: MailLabel[] }>("/sales/mail/labels");
    setLabels(res.items || []);
  }, []);

  const loadContacts = React.useCallback(async () => {
    const res = await apiFetch<{ items: MailContact[] }>("/sales/mail/contacts");
    setContacts(res.items || []);
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const st = await loadStatus();
      const meta = TABS.find((t) => t.key === tab);
      if (tab === "labels") await loadLabels();
      else if (tab === "contacts") await loadContacts();
      else if (st?.configured || st?.has_imap) await loadMessages(meta?.folder || "INBOX");
      else setMessages([]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load mail");
    } finally {
      setLoading(false);
    }
  }, [tab, loadStatus, loadMessages, loadLabels, loadContacts]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSync = async () => {
    setSyncing(true);
    try {
      await apiFetch("/sales/mail/sync", {
        method: "POST",
        body: JSON.stringify({ folder: "INBOX", limit: 50 }),
      });
      toast.success("Inbox synced");
      await loadMessages("INBOX");
      setTab("inbox");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const openMessage = async (id: string) => {
    try {
      const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${id}`);
      setSelected(res.message);
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, is_read: true } : m)));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not open message");
    }
  };

  const insertPromo = () => {
    const code = status?.promo_code || "";
    if (!code) {
      toast.error("No promo code on your sales account");
      return;
    }
    setBody((prev) => `${prev}${prev ? "\n\n" : ""}Use my promo code: ${code}`);
  };

  const polish = async () => {
    if (!body.trim()) return;
    setPolishing(true);
    try {
      const res = await apiFetch<{ polished: string }>("/sales/mail/polish", {
        method: "POST",
        body: JSON.stringify({ body }),
      });
      setBody(res.polished || body);
      toast.success("Draft polished");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Polish failed");
    } finally {
      setPolishing(false);
    }
  };

  const send = async () => {
    setSending(true);
    try {
      const html = body
        .split(/\n/)
        .map((line) => `<p>${line.replace(/</g, "&lt;").replace(/>/g, "&gt;") || "<br/>"}</p>`)
        .join("");
      await apiFetch("/sales/mail/send", {
        method: "POST",
        body: JSON.stringify({
          to,
          subject,
          body_html: html,
          body_text: body,
          insert_promo: false,
        }),
      });
      toast.success("Message sent");
      setComposeOpen(false);
      setTo("");
      setSubject("");
      setBody("");
      if (tab === "sent") await loadMessages("Sent");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
    }
  };

  const createLabel = async () => {
    if (!newLabel.trim()) return;
    try {
      await apiFetch("/sales/mail/labels", {
        method: "POST",
        body: JSON.stringify({ name: newLabel.trim() }),
      });
      setNewLabel("");
      await loadLabels();
      toast.success("Label created");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create label");
    }
  };

  const deleteLabel = async (id: string) => {
    try {
      await apiFetch(`/sales/mail/labels/${id}`, { method: "DELETE" });
      await loadLabels();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete label");
    }
  };

  const filtered = messages.filter((m) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      (m.subject || "").toLowerCase().includes(q) ||
      (m.from_email || "").toLowerCase().includes(q) ||
      (m.from_name || "").toLowerCase().includes(q) ||
      (m.preview || "").toLowerCase().includes(q)
    );
  });

  const configured = Boolean(status?.configured);

  return (
    <div className="flex w-full flex-col gap-4">
      <PageHeader
        eyebrow="Sales · Mail"
        title="Sales mail"
        description="Inbox for your salesman mailbox. Credentials are set by admin — passwords stay hidden."
        actions={
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" className="gap-1.5" disabled={!configured || syncing} onClick={() => void onSync()}>
              <RefreshCw className={cn("size-4", syncing && "animate-spin")} /> Sync
            </Button>
            <Button className="gap-1.5" disabled={!status?.has_smtp} onClick={() => setComposeOpen(true)}>
              <PenSquare className="size-4" /> Compose
            </Button>
          </div>
        }
      />

      <div className="flex flex-wrap gap-1 border-b border-border pb-0">
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => {
              setSelected(null);
              setTab(t.key);
            }}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-t-lg px-3 py-2 text-sm font-medium transition",
              tab === t.key
                ? "border-b-2 border-primary bg-muted/40 text-foreground"
                : "text-muted-foreground hover:bg-muted/30 hover:text-foreground",
            )}
          >
            <t.icon className="size-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {!configured && !loading ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-2 p-10 text-center">
            <Mail className="size-8 text-muted-foreground" />
            <p className="font-medium">Mailbox not configured</p>
            <p className="max-w-md text-sm text-muted-foreground">
              Ask an admin to set your IMAP and SMTP details (and signature) on your salesman profile. Passwords are
              encrypted and never shown here.
            </p>
            <div className="mt-2 flex gap-2 text-xs text-muted-foreground">
              <Badge variant={status?.has_imap ? "default" : "secondary"}>IMAP {status?.has_imap ? "ok" : "missing"}</Badge>
              <Badge variant={status?.has_smtp ? "default" : "secondary"}>SMTP {status?.has_smtp ? "ok" : "missing"}</Badge>
            </div>
          </CardContent>
        </Card>
      ) : null}

      {tab === "labels" ? (
        <Card>
          <CardContent className="space-y-4 p-4">
            <div className="flex flex-wrap gap-2">
              <Input
                className="max-w-xs"
                placeholder="New label name"
                value={newLabel}
                onChange={(e) => setNewLabel(e.target.value)}
              />
              <Button type="button" onClick={() => void createLabel()}>
                Create label
              </Button>
            </div>
            {labels.length === 0 ? (
              <p className="text-sm text-muted-foreground">No labels yet.</p>
            ) : (
              <ul className="space-y-2">
                {labels.map((lb) => (
                  <li key={lb.id} className="flex items-center justify-between rounded-lg border px-3 py-2">
                    <span className="flex items-center gap-2 text-sm">
                      <span className="size-2.5 rounded-full" style={{ background: lb.color }} />
                      {lb.name}
                    </span>
                    <Button type="button" size="sm" variant="ghost" onClick={() => void deleteLabel(lb.id)}>
                      <Trash2 className="size-3.5" />
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab === "contacts" ? (
        <Card>
          <CardContent className="p-0">
            {contacts.length === 0 ? (
              <p className="p-8 text-center text-sm text-muted-foreground">
                Contacts appear automatically when you add sales customers with an email.
              </p>
            ) : (
              <ul className="divide-y">
                {contacts.map((c) => (
                  <li key={c.id} className="flex items-center justify-between gap-3 px-4 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium">{c.name || c.email}</p>
                      <p className="truncate text-xs text-muted-foreground">
                        {c.email}
                        {c.company ? ` · ${c.company}` : ""}
                      </p>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setTo(c.email);
                        setComposeOpen(true);
                      }}
                    >
                      Email
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      ) : null}

      {tab !== "labels" && tab !== "contacts" && configured ? (
        <div className="grid gap-4 lg:grid-cols-[1.1fr_1fr]">
          <Card className="overflow-hidden">
            <div className="flex items-center gap-2 border-b px-3 py-2">
              <Search className="size-4 text-muted-foreground" />
              <Input
                className="h-8 border-0 bg-transparent shadow-none focus-visible:ring-0"
                placeholder="Search mail"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
              />
            </div>
            <CardContent className="max-h-[min(70vh,640px)] space-y-0 overflow-y-auto p-0">
              {loading ? (
                <p className="p-8 text-center text-sm text-muted-foreground">Loading…</p>
              ) : filtered.length === 0 ? (
                <p className="p-8 text-center text-sm text-muted-foreground">No messages in this folder.</p>
              ) : (
                filtered.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    onClick={() => void openMessage(m.id)}
                    className={cn(
                      "flex w-full items-start gap-3 border-b px-3 py-2.5 text-left transition hover:bg-muted/40",
                      !m.is_read && "bg-primary/5",
                      selected?.id === m.id && "bg-muted/60",
                    )}
                  >
                    <span
                      className={cn(
                        "mt-1.5 size-1.5 shrink-0 rounded-full",
                        m.is_read ? "bg-transparent" : "bg-primary",
                      )}
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <p className={cn("truncate text-sm", !m.is_read && "font-semibold")}>
                          {m.from_name || m.from_email || "Unknown"}
                        </p>
                        <span className="shrink-0 text-[10px] text-muted-foreground">{formatWhen(m.date)}</span>
                      </div>
                      <p className={cn("truncate text-sm", !m.is_read ? "font-medium" : "text-muted-foreground")}>
                        {m.subject || "(no subject)"}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{m.preview}</p>
                    </div>
                    {m.has_attachments ? <Paperclip className="mt-1 size-3.5 shrink-0 text-muted-foreground" /> : null}
                    {m.is_starred ? <Star className="mt-1 size-3.5 shrink-0 fill-amber-400 text-amber-400" /> : null}
                  </button>
                ))
              )}
            </CardContent>
          </Card>

          <Card className="min-h-[280px]">
            <CardContent className="p-4">
              {!selected ? (
                <p className="py-16 text-center text-sm text-muted-foreground">Select a message to read</p>
              ) : (
                <div className="space-y-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h2 className="text-lg font-semibold leading-tight">{selected.subject || "(no subject)"}</h2>
                      <p className="mt-1 text-sm text-muted-foreground">
                        From {selected.from_name || selected.from_email}
                        {selected.from_name && selected.from_email ? ` <${selected.from_email}>` : ""}
                      </p>
                      <p className="text-xs text-muted-foreground">{formatWhen(selected.date)}</p>
                    </div>
                    <Button type="button" size="icon" variant="ghost" onClick={() => setSelected(null)}>
                      <X className="size-4" />
                    </Button>
                  </div>
                  {selected.body_html ? (
                    <div
                      className="prose prose-sm dark:prose-invert max-w-none rounded-lg border bg-muted/20 p-3"
                      dangerouslySetInnerHTML={{ __html: selected.body_html }}
                    />
                  ) : (
                    <pre className="whitespace-pre-wrap rounded-lg border bg-muted/20 p-3 text-sm">
                      {selected.body_text || ""}
                    </pre>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      ) : null}

      <Dialog open={composeOpen} onOpenChange={setComposeOpen}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>Compose</DialogTitle>
            <DialogDescription>Send from your salesman SMTP mailbox.</DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label>To</Label>
              <Input
                list="sales-mail-contacts"
                value={to}
                onChange={(e) => setTo(e.target.value)}
                placeholder="name@company.com"
              />
              <datalist id="sales-mail-contacts">
                {contacts.map((c) => (
                  <option key={c.id} value={c.email}>
                    {c.name || c.company || c.email}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="space-y-1.5">
              <Label>Subject</Label>
              <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
            </div>
            <div className="space-y-1.5">
              <Label>Message</Label>
              <Textarea rows={8} value={body} onChange={(e) => setBody(e.target.value)} />
            </div>
            <div className="flex flex-wrap gap-2">
              <Button type="button" size="sm" variant="outline" className="gap-1" onClick={insertPromo}>
                <Gift className="size-3.5" /> Insert promo
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="gap-1"
                disabled={polishing}
                onClick={() => void polish()}
              >
                <Sparkles className="size-3.5" /> {polishing ? "Polishing…" : "AI polish"}
              </Button>
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setComposeOpen(false)}>
              Cancel
            </Button>
            <Button type="button" disabled={sending || !to.trim() || !subject.trim()} onClick={() => void send()}>
              {sending ? "Sending…" : "Send"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
