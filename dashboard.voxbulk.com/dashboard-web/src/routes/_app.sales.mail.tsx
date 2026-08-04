import * as React from "react";
import { createFileRoute } from "@tanstack/react-router";
import {
  ArrowLeft,
  CornerUpLeft,
  Forward,
  Gift,
  Inbox,
  Mail,
  Paperclip,
  PenSquare,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  Star,
  Trash2,
  Users,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { apiFetch } from "@/lib/api";
import { requireSalesRep } from "@/lib/guards/settings-route";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/_app/sales/mail")({
  head: () => ({ meta: [{ title: "Mail — Sales — VoxBulk" }] }),
  beforeLoad: () => requireSalesRep(),
  component: SalesMailPage,
});

type TabKey = "inbox" | "sent" | "starred" | "trash" | "contacts";
type ViewMode = "list" | "read" | "compose";
type ComposeMode = "new" | "reply" | "replyAll" | "forward";

type MailStatus = {
  configured?: boolean;
  has_imap?: boolean;
  has_smtp?: boolean;
  signature_preview?: string;
  promo_code?: string;
  smtp_username?: string;
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
  direction?: string;
};

type MailDetail = MailMessage & {
  body_text?: string | null;
  body_html?: string | null;
  cc_email?: string | null;
  is_deleted?: boolean;
};

type MailContact = { id: string; email: string; name?: string | null; company?: string | null };

type ComposeAttachment = {
  id: string;
  name: string;
  contentType: string;
  dataBase64: string;
  size: number;
};

const FOLDERS: { key: TabKey; label: string; icon: typeof Inbox; folder?: string }[] = [
  { key: "inbox", label: "Inbox", icon: Inbox, folder: "INBOX" },
  { key: "starred", label: "Starred", icon: Star, folder: "Starred" },
  { key: "sent", label: "Sent", icon: Send, folder: "Sent" },
  { key: "trash", label: "Trash", icon: Trash2, folder: "Trash" },
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

function formatFull(iso?: string | null) {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString([], { dateStyle: "medium", timeStyle: "short" });
}

function textToHtml(text: string) {
  return text
    .split(/\n/)
    .map((line) => `<p>${line.replace(/</g, "&lt;").replace(/>/g, "&gt;") || "<br/>"}</p>`)
    .join("");
}

function quotedForward(msg: MailDetail) {
  const header = [
    "---------- Forwarded message ----------",
    `From: ${msg.from_name || msg.from_email || ""} <${msg.from_email || ""}>`,
    `Date: ${formatFull(msg.date)}`,
    `Subject: ${msg.subject || ""}`,
    `To: ${msg.to_email || ""}`,
    "",
  ].join("\n");
  return `${header}${msg.body_text || ""}`;
}

function SalesMailPage() {
  const [tab, setTab] = React.useState<TabKey>("inbox");
  const [view, setView] = React.useState<ViewMode>("list");
  const [status, setStatus] = React.useState<MailStatus | null>(null);
  const [messages, setMessages] = React.useState<MailMessage[]>([]);
  const [contacts, setContacts] = React.useState<MailContact[]>([]);
  const [selectedIds, setSelectedIds] = React.useState<string[]>([]);
  const [openMessage, setOpenMessage] = React.useState<MailDetail | null>(null);
  const [query, setQuery] = React.useState("");
  const [loading, setLoading] = React.useState(true);
  const [syncing, setSyncing] = React.useState(false);
  const [confirmDelete, setConfirmDelete] = React.useState<"bulk" | "empty-trash" | null>(null);

  const [composeMode, setComposeMode] = React.useState<ComposeMode>("new");
  const [to, setTo] = React.useState("");
  const [cc, setCc] = React.useState("");
  const [showCc, setShowCc] = React.useState(false);
  const [subject, setSubject] = React.useState("");
  const [body, setBody] = React.useState("");
  const [attachments, setAttachments] = React.useState<ComposeAttachment[]>([]);
  const [sending, setSending] = React.useState(false);
  const [aiBusy, setAiBusy] = React.useState<"write" | "fix" | null>(null);
  const fileRef = React.useRef<HTMLInputElement>(null);
  const replyContextRef = React.useRef<MailDetail | null>(null);

  const loadStatus = React.useCallback(async () => {
    const res = await apiFetch<MailStatus & { ok?: boolean }>("/sales/mail/status");
    setStatus(res);
    return res;
  }, []);

  const loadMessages = React.useCallback(async (folder: string) => {
    const res = await apiFetch<{ items: MailMessage[] }>(
      `/sales/mail/messages?folder=${encodeURIComponent(folder)}&limit=120`,
    );
    setMessages(res.items || []);
  }, []);

  const loadContacts = React.useCallback(async () => {
    const res = await apiFetch<{ items: MailContact[] }>("/sales/mail/contacts");
    setContacts(res.items || []);
  }, []);

  const refresh = React.useCallback(async () => {
    setLoading(true);
    try {
      const st = await loadStatus();
      const meta = FOLDERS.find((t) => t.key === tab);
      if (tab === "contacts") await loadContacts();
      else if (st?.configured || st?.has_imap) await loadMessages(meta?.folder || "INBOX");
      else setMessages([]);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load mail");
    } finally {
      setLoading(false);
    }
  }, [tab, loadStatus, loadMessages, loadContacts]);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  const onSync = async () => {
    setSyncing(true);
    try {
      await apiFetch("/sales/mail/sync", {
        method: "POST",
        body: JSON.stringify({ folder: "INBOX", limit: 80 }),
      });
      toast.success("Inbox synced");
      setTab("inbox");
      setView("list");
      await loadMessages("INBOX");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sync failed");
    } finally {
      setSyncing(false);
    }
  };

  const openCompose = (mode: ComposeMode = "new", msg?: MailDetail | null, prefillTo?: string) => {
    replyContextRef.current = msg || null;
    setComposeMode(mode);
    setAttachments([]);
    setAiBusy(null);
    if (mode === "new") {
      setTo(prefillTo || "");
      setCc("");
      setShowCc(false);
      setSubject("");
      setBody("");
    } else if (msg) {
      const from = msg.from_email || "";
      if (mode === "reply") {
        setTo(from);
        setCc("");
        setShowCc(false);
        setSubject((msg.subject || "").toLowerCase().startsWith("re:") ? msg.subject || "" : `Re: ${msg.subject || ""}`);
        setBody("");
      } else if (mode === "replyAll") {
        setTo(from);
        const others = [msg.to_email, msg.cc_email]
          .filter(Boolean)
          .join(",")
          .split(",")
          .map((s) => s.trim())
          .filter((e) => e && e.toLowerCase() !== from.toLowerCase() && e.toLowerCase() !== (status?.smtp_username || "").toLowerCase());
        setCc([...new Set(others)].join(", "));
        setShowCc(true);
        setSubject((msg.subject || "").toLowerCase().startsWith("re:") ? msg.subject || "" : `Re: ${msg.subject || ""}`);
        setBody("");
      } else {
        setTo("");
        setCc("");
        setShowCc(false);
        setSubject((msg.subject || "").toLowerCase().startsWith("fw:") || (msg.subject || "").toLowerCase().startsWith("fwd:")
          ? msg.subject || ""
          : `Fwd: ${msg.subject || ""}`);
        setBody(quotedForward(msg));
      }
    }
    setView("compose");
    setOpenMessage(null);
  };

  const openMessage = async (id: string) => {
    try {
      const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${id}`);
      setOpenMessage(res.message);
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, is_read: true } : m)));
      setView("read");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not open message");
    }
  };

  const toggleStar = async (id: string, starred: boolean) => {
    try {
      await apiFetch(`/sales/mail/messages/${id}`, {
        method: "PATCH",
        body: JSON.stringify({ is_starred: !starred }),
      });
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, is_starred: !starred } : m)));
      if (openMessage?.id === id) setOpenMessage({ ...openMessage, is_starred: !starred });
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update star");
    }
  };

  const deleteIds = async (ids: string[], permanent = false) => {
    if (!ids.length) return;
    try {
      await apiFetch("/sales/mail/messages/delete", {
        method: "POST",
        body: JSON.stringify({ ids, permanent: permanent || tab === "trash" }),
      });
      toast.success(permanent || tab === "trash" ? "Deleted permanently" : "Moved to trash");
      setSelectedIds([]);
      if (openMessage && ids.includes(openMessage.id)) {
        setOpenMessage(null);
        setView("list");
      }
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed");
    }
  };

  const emptyTrash = async () => {
    try {
      await apiFetch("/sales/mail/trash/empty", { method: "POST", body: "{}" });
      toast.success("Trash emptied");
      setConfirmDelete(null);
      await refresh();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not empty trash");
    }
  };

  const runAi = async (mode: "write" | "fix") => {
    if (mode === "fix" && !body.trim()) {
      toast.error("Write a draft first, then fix with AI.");
      return;
    }
    setAiBusy(mode);
    try {
      const ctx = replyContextRef.current || openMessage;
      const res = await apiFetch<{ polished: string }>("/sales/mail/polish", {
        method: "POST",
        body: JSON.stringify({
          mode,
          body,
          subject,
          from: ctx ? `${ctx.from_name || ""} <${ctx.from_email || ""}>` : "",
          context_body: ctx?.body_text || "",
        }),
      });
      if (!res.polished) {
        toast.error("AI returned an empty draft");
        return;
      }
      setBody(res.polished);
      toast.success(mode === "write" ? "AI draft ready — edit before sending" : "Rewritten by AI");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "AI request failed");
    } finally {
      setAiBusy(null);
    }
  };

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    Array.from(files).forEach((file) => {
      if (file.size > 5_000_000) {
        toast.error(`${file.name} is larger than 5 MB`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        setAttachments((prev) => [
          ...prev,
          {
            id: `${Date.now()}-${file.name}`,
            name: file.name,
            contentType: file.type || "application/octet-stream",
            dataBase64: String(reader.result || ""),
            size: file.size,
          },
        ]);
      };
      reader.readAsDataURL(file);
    });
  };

  const send = async () => {
    if (!to.trim() || !subject.trim() || !body.trim()) return;
    setSending(true);
    try {
      await apiFetch("/sales/mail/send", {
        method: "POST",
        body: JSON.stringify({
          to: to.trim(),
          cc: cc.trim() || undefined,
          subject: subject.trim(),
          body_html: textToHtml(body),
          body_text: body,
          attachments: attachments.map((a) => ({
            filename: a.name,
            content_type: a.contentType,
            data_base64: a.dataBase64,
          })),
        }),
      });
      toast.success("Message sent");
      setView("list");
      setTab("sent");
      setAttachments([]);
      await loadMessages("Sent");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed");
    } finally {
      setSending(false);
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

  const filtered = messages.filter((m) => {
    if (!query.trim()) return true;
    const q = query.toLowerCase();
    return (
      (m.subject || "").toLowerCase().includes(q) ||
      (m.from_email || "").toLowerCase().includes(q) ||
      (m.from_name || "").toLowerCase().includes(q) ||
      (m.preview || "").toLowerCase().includes(q) ||
      (m.to_email || "").toLowerCase().includes(q)
    );
  });

  const configured = Boolean(status?.configured);
  const allSelected = filtered.length > 0 && filtered.every((m) => selectedIds.includes(m.id));
  const singleSelected = selectedIds.length === 1 ? filtered.find((m) => m.id === selectedIds[0]) : undefined;

  const sidebar = (
    <aside className="flex w-full flex-col gap-2 lg:w-52 lg:shrink-0">
      <Button
        className="w-full justify-start gap-2"
        disabled={!status?.has_smtp}
        onClick={() => openCompose("new")}
      >
        <PenSquare className="size-4" /> Compose
      </Button>
      <nav className="rounded-xl border bg-card p-1.5">
        {FOLDERS.map((f) => (
          <button
            key={f.key}
            type="button"
            onClick={() => {
              setTab(f.key);
              setView("list");
              setOpenMessage(null);
              setSelectedIds([]);
            }}
            className={cn(
              "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition",
              tab === f.key && view !== "compose"
                ? "bg-primary/10 font-medium text-foreground"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
          >
            <f.icon className="size-4" />
            {f.label}
          </button>
        ))}
      </nav>
      <Button variant="outline" className="justify-start gap-2" disabled={!configured || syncing} onClick={() => void onSync()}>
        <RefreshCw className={cn("size-4", syncing && "animate-spin")} /> Sync inbox
      </Button>
      {tab === "trash" ? (
        <Button variant="ghost" className="justify-start gap-2 text-destructive hover:text-destructive" onClick={() => setConfirmDelete("empty-trash")}>
          <Trash2 className="size-4" /> Empty trash
        </Button>
      ) : null}
    </aside>
  );

  if (view === "compose") {
    return (
      <div className="flex w-full flex-col gap-4 pb-10">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="ghost" size="sm" onClick={() => setView(openMessage ? "read" : "list")}>
            <ArrowLeft className="size-4" /> Back
          </Button>
          <h1 className="text-xl font-semibold tracking-tight">
            {composeMode === "new"
              ? "New message"
              : composeMode === "forward"
                ? "Forward"
                : composeMode === "replyAll"
                  ? "Reply all"
                  : "Reply"}
          </h1>
          <div className="ml-auto flex flex-wrap gap-1">
            {(composeMode === "reply" || composeMode === "replyAll") && (
              <Button size="sm" variant="secondary" disabled={aiBusy !== null} onClick={() => void runAi("write")}>
                <Sparkles className={cn("size-4", aiBusy === "write" && "animate-pulse")} />
                {aiBusy === "write" ? "Writing…" : "Reply with AI"}
              </Button>
            )}
            <Button size="sm" variant="outline" disabled={aiBusy !== null || !body.trim()} onClick={() => void runAi("fix")}>
              <Wand2 className={cn("size-4", aiBusy === "fix" && "animate-pulse")} />
              {aiBusy === "fix" ? "Fixing…" : "Fix with AI"}
            </Button>
            <Button size="sm" disabled={sending || !to.trim() || !subject.trim() || !body.trim()} onClick={() => void send()}>
              <Send className="size-4" /> {sending ? "Sending…" : "Send"}
            </Button>
          </div>
        </div>

        <div className="mx-auto w-full max-w-3xl space-y-4 rounded-xl border bg-card p-4 sm:p-6">
          <div className="space-y-1.5">
            <Label>From</Label>
            <Input value={status?.smtp_username || "Mailbox not configured"} disabled />
          </div>
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label>To</Label>
              {!showCc ? (
                <button type="button" className="text-xs text-primary hover:underline" onClick={() => setShowCc(true)}>
                  Cc
                </button>
              ) : null}
            </div>
            <Input
              list="sales-mail-contacts"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="name@company.com"
            />
          </div>
          {showCc ? (
            <div className="space-y-1.5">
              <Label>Cc</Label>
              <Input value={cc} onChange={(e) => setCc(e.target.value)} placeholder="cc@company.com" />
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label>Subject</Label>
            <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label>Message</Label>
            <Textarea
              rows={14}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your message, or use Reply with AI / Fix with AI…"
              className="min-h-[280px] font-sans text-sm leading-relaxed"
            />
          </div>
          {status?.signature_preview ? (
            <p className="whitespace-pre-wrap rounded-lg bg-muted/40 px-3 py-2 text-xs text-muted-foreground">
              Signature will be appended on send
            </p>
          ) : null}
          {attachments.length > 0 ? (
            <div className="flex flex-wrap gap-2">
              {attachments.map((a) => (
                <span key={a.id} className="inline-flex items-center gap-1 rounded-lg border bg-muted/30 px-2 py-1 text-xs">
                  <Paperclip className="size-3" />
                  <span className="max-w-[10rem] truncate">{a.name}</span>
                  <button type="button" aria-label={`Remove ${a.name}`} onClick={() => setAttachments((p) => p.filter((x) => x.id !== a.id))}>
                    <X className="size-3.5 text-muted-foreground hover:text-destructive" />
                  </button>
                </span>
              ))}
            </div>
          ) : null}
          <div className="flex flex-wrap gap-2">
            <Button type="button" size="sm" variant="secondary" onClick={() => fileRef.current?.click()}>
              <Paperclip className="size-4" /> Attach
            </Button>
            <Button type="button" size="sm" variant="outline" onClick={insertPromo}>
              <Gift className="size-4" /> Insert promo
            </Button>
            <input
              ref={fileRef}
              type="file"
              multiple
              hidden
              onChange={(e) => {
                addFiles(e.target.files);
                e.target.value = "";
              }}
            />
          </div>
          <datalist id="sales-mail-contacts">
            {contacts.map((c) => (
              <option key={c.id} value={c.email}>
                {c.name || c.company || c.email}
              </option>
            ))}
          </datalist>
        </div>
      </div>
    );
  }

  if (view === "read" && openMessage) {
    const msg = openMessage;
    return (
      <div className="flex w-full flex-col gap-4 pb-10">
        <div className="flex flex-wrap items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setView("list");
              setOpenMessage(null);
            }}
          >
            <ArrowLeft className="size-4" /> Back to list
          </Button>
          <div className="ml-auto flex flex-wrap gap-1">
            <Button variant="ghost" size="sm" onClick={() => void toggleStar(msg.id, Boolean(msg.is_starred))}>
              <Star className={cn("size-4", msg.is_starred && "fill-amber-400 text-amber-400")} />
            </Button>
            <Button variant="ghost" size="sm" onClick={() => void deleteIds([msg.id])}>
              <Trash2 className="size-4 text-destructive" />
            </Button>
          </div>
        </div>

        <article className="rounded-xl border bg-card p-4 sm:p-6">
          <h1 className="text-xl font-semibold tracking-tight sm:text-2xl">{msg.subject || "(no subject)"}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
            <span className="font-medium text-foreground">{msg.from_name || msg.from_email}</span>
            {msg.from_email ? <span>&lt;{msg.from_email}&gt;</span> : null}
            <span>→ {msg.to_email || status?.smtp_username || "me"}</span>
            {msg.cc_email ? <span>Cc {msg.cc_email}</span> : null}
            <span className="ml-auto">{formatFull(msg.date)}</span>
          </div>
          <div className="mt-5">
            {msg.body_html ? (
              <div
                className="prose prose-sm dark:prose-invert max-w-none text-sm leading-relaxed"
                dangerouslySetInnerHTML={{ __html: msg.body_html }}
              />
            ) : (
              <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">{msg.body_text || "No message body."}</pre>
            )}
          </div>
          {msg.has_attachments ? (
            <p className="mt-4 flex items-center gap-1.5 border-t pt-3 text-xs text-muted-foreground">
              <Paperclip className="size-3.5" /> This message has attachments (synced metadata)
            </p>
          ) : null}
        </article>

        <div className="flex flex-wrap gap-2">
          <Button onClick={() => openCompose("reply", msg)}>
            <CornerUpLeft className="size-4" /> Reply
          </Button>
          <Button variant="secondary" onClick={() => openCompose("replyAll", msg)}>
            <Users className="size-4" /> Reply all
          </Button>
          <Button variant="secondary" onClick={() => openCompose("forward", msg)}>
            <Forward className="size-4" /> Forward
          </Button>
          <Button variant="outline" onClick={() => openCompose("new")}>
            <PenSquare className="size-4" /> Compose new
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex w-full flex-col gap-4 pb-8 lg:flex-row lg:items-start">
      {sidebar}
      <div className="min-w-0 flex-1 space-y-3">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-[11px] font-medium uppercase tracking-[0.18em] text-muted-foreground">Sales · Mail</p>
            <h1 className="text-2xl font-semibold tracking-tight">{FOLDERS.find((f) => f.key === tab)?.label || "Mail"}</h1>
            <p className="text-sm text-muted-foreground">
              Full mailbox for your salesman account — send, reply, forward, delete, and attach files.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Badge variant={status?.has_imap ? "default" : "secondary"}>IMAP {status?.has_imap ? "ready" : "off"}</Badge>
            <Badge variant={status?.has_smtp ? "default" : "secondary"}>SMTP {status?.has_smtp ? "ready" : "off"}</Badge>
          </div>
        </div>

        {!configured && !loading ? (
          <div className="rounded-xl border bg-card p-10 text-center">
            <Mail className="mx-auto size-8 text-muted-foreground" />
            <p className="mt-3 font-medium">Mailbox not configured</p>
            <p className="mx-auto mt-1 max-w-md text-sm text-muted-foreground">
              Ask admin to set your username and password on the salesman profile (server: voxbulk.com). Passwords stay encrypted.
            </p>
          </div>
        ) : null}

        {tab === "contacts" && configured ? (
          <div className="overflow-hidden rounded-xl border bg-card">
            {contacts.length === 0 ? (
              <p className="p-10 text-center text-sm text-muted-foreground">
                Contacts appear when you add sales customers with an email.
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
                      size="sm"
                      variant="outline"
                      onClick={() => openCompose("new", null, c.email)}
                    >
                      Email
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}

        {tab !== "contacts" && configured ? (
          <div className="overflow-hidden rounded-xl border bg-card">
            <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2 sm:gap-3 sm:px-4">
              <Checkbox
                checked={allSelected}
                onCheckedChange={() => {
                  if (allSelected) setSelectedIds([]);
                  else setSelectedIds(filtered.map((m) => m.id));
                }}
                aria-label="Select all messages"
              />
              <span className="text-xs text-muted-foreground">
                {selectedIds.length > 0 ? `${selectedIds.length} selected` : "Select all"}
              </span>
              <div className="relative ml-2 min-w-[10rem] flex-1">
                <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-muted-foreground" />
                <Input
                  className="h-8 border-0 bg-transparent pl-7 shadow-none focus-visible:ring-0"
                  placeholder="Search mail"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                />
              </div>
              {selectedIds.length > 0 ? (
                <div className="flex flex-wrap items-center gap-1">
                  {singleSelected ? (
                    <>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={() => void openMessage(singleSelected.id).then(() => undefined)}
                      >
                        <Mail className="size-3.5" /> Open
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={async () => {
                          const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${singleSelected.id}`);
                          openCompose("reply", res.message);
                        }}
                      >
                        <CornerUpLeft className="size-3.5" /> Reply
                      </Button>
                      <Button
                        size="sm"
                        variant="secondary"
                        onClick={async () => {
                          const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${singleSelected.id}`);
                          openCompose("forward", res.message);
                        }}
                      >
                        <Forward className="size-3.5" /> Forward
                      </Button>
                    </>
                  ) : null}
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => setConfirmDelete("bulk")}
                  >
                    <Trash2 className="size-3.5" /> Delete
                  </Button>
                </div>
              ) : (
                <Button size="sm" className="ml-auto gap-1.5" disabled={!status?.has_smtp} onClick={() => openCompose("new")}>
                  <PenSquare className="size-3.5" /> Compose
                </Button>
              )}
            </div>

            {loading ? (
              <p className="p-10 text-center text-sm text-muted-foreground">Loading…</p>
            ) : filtered.length === 0 ? (
              <p className="p-10 text-center text-sm text-muted-foreground">Nothing here. Enjoy the empty folder.</p>
            ) : (
              <ul className="divide-y">
                {filtered.map((m) => (
                  <li
                    key={m.id}
                    className={cn(
                      "group flex cursor-pointer items-start gap-3 px-3 py-3 transition-colors hover:bg-muted/40 sm:px-4",
                      !m.is_read && "bg-primary/5",
                      selectedIds.includes(m.id) && "bg-primary/10",
                    )}
                    onClick={() => void openMessage(m.id)}
                  >
                    <span onClick={(e) => e.stopPropagation()} className="mt-1">
                      <Checkbox
                        checked={selectedIds.includes(m.id)}
                        onCheckedChange={() =>
                          setSelectedIds((prev) =>
                            prev.includes(m.id) ? prev.filter((x) => x !== m.id) : [...prev, m.id],
                          )
                        }
                        aria-label={`Select ${m.subject}`}
                      />
                    </span>
                    <button
                      type="button"
                      className="mt-1"
                      onClick={(e) => {
                        e.stopPropagation();
                        void toggleStar(m.id, Boolean(m.is_starred));
                      }}
                    >
                      <Star className={cn("size-3.5", m.is_starred ? "fill-amber-400 text-amber-400" : "text-muted-foreground")} />
                    </button>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-baseline gap-2">
                        <p className={cn("truncate text-sm", !m.is_read ? "font-semibold" : "font-medium")}>
                          {tab === "sent" ? m.to_email || "—" : m.from_name || m.from_email || "Unknown"}
                        </p>
                        <span className="hidden truncate text-xs text-muted-foreground sm:inline">
                          {tab === "sent" ? "" : m.from_email}
                        </span>
                        <span className="ml-auto shrink-0 text-xs text-muted-foreground">{formatWhen(m.date)}</span>
                      </div>
                      <p className={cn("truncate text-sm", !m.is_read ? "font-medium" : "text-muted-foreground")}>
                        {m.subject || "(no subject)"}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">{m.preview}</p>
                    </div>
                    {m.has_attachments ? <Paperclip className="mt-1 size-3.5 shrink-0 text-muted-foreground" /> : null}
                    <div className="hidden shrink-0 gap-0.5 opacity-0 group-hover:flex sm:flex sm:opacity-100" onClick={(e) => e.stopPropagation()}>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        onClick={async () => {
                          const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${m.id}`);
                          openCompose("reply", res.message);
                        }}
                      >
                        <CornerUpLeft className="size-3.5" />
                      </Button>
                      <Button
                        size="icon"
                        variant="ghost"
                        className="size-7"
                        onClick={async () => {
                          const res = await apiFetch<{ message: MailDetail }>(`/sales/mail/messages/${m.id}`);
                          openCompose("forward", res.message);
                        }}
                      >
                        <Forward className="size-3.5" />
                      </Button>
                      <Button size="icon" variant="ghost" className="size-7 text-destructive" onClick={() => void deleteIds([m.id])}>
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ) : null}
      </div>

      <AlertDialog open={confirmDelete !== null} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{confirmDelete === "empty-trash" ? "Empty trash?" : "Delete messages?"}</AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete === "empty-trash"
                ? "Permanently delete all messages in trash. This cannot be undone."
                : tab === "trash"
                  ? "Permanently delete the selected messages."
                  : "Move selected messages to trash."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (confirmDelete === "empty-trash") void emptyTrash();
                else void deleteIds(selectedIds);
                setConfirmDelete(null);
              }}
            >
              Confirm
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
