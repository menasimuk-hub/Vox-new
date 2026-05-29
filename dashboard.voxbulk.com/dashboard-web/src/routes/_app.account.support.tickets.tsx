import { createFileRoute, Link } from "@tanstack/react-router";
import * as React from "react";
import { ArrowLeft, Plus, Send, CheckCircle2, Search, Mail, Clock, AlertTriangle, MessageSquare } from "lucide-react";
import { toast } from "sonner";

import { PageHeader } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/utils";
import {
  useCloseSupportTicket,
  useCreateSupportTicket,
  useReplySupportTicket,
  useSupportTicket,
  useSupportTickets,
} from "@/lib/queries";

export const Route = createFileRoute("/_app/account/support/tickets")({
  head: () => ({ meta: [{ title: "Support tickets — VoxBulk" }] }),
  component: TicketsPage,
});

type TicketStatus = "open" | "pending" | "closed";
type Priority = "low" | "normal" | "high" | "urgent";

const statusMeta: Record<TicketStatus, { label: string; dot: string; chip: string }> = {
  open: { label: "Open", dot: "bg-success", chip: "bg-success/10 text-success border-success/20" },
  pending: { label: "Pending", dot: "bg-warning", chip: "bg-warning/10 text-warning border-warning/20" },
  closed: { label: "Closed", dot: "bg-muted-foreground", chip: "bg-muted text-muted-foreground border-border" },
};

const priorityMeta: Record<Priority, string> = {
  low: "text-muted-foreground",
  normal: "text-foreground",
  high: "text-warning",
  urgent: "text-destructive",
};

function formatWhen(value: unknown) {
  if (!value) return "—";
  try {
    const d = new Date(String(value));
    const diff = Date.now() - d.getTime();
    const mins = Math.round(diff / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    const hrs = Math.round(mins / 60);
    if (hrs < 48) return `${hrs}h ago`;
    return d.toLocaleDateString(undefined, { day: "numeric", month: "short" });
  } catch {
    return String(value);
  }
}

function normalizeStatus(status: string): TicketStatus {
  const s = status.toLowerCase();
  if (s === "closed" || s === "resolved") return "closed";
  if (s === "pending" || s === "waiting") return "pending";
  return "open";
}

function TicketsPage() {
  const [filter, setFilter] = React.useState<TicketStatus | "all">("all");
  const [search, setSearch] = React.useState("");
  const [newOpen, setNewOpen] = React.useState(false);
  const [reply, setReply] = React.useState("");

  const ticketsQ = useSupportTickets(filter === "all" ? undefined : filter);
  const tickets = (ticketsQ.data || []) as Array<Record<string, unknown>>;

  const [activeId, setActiveId] = React.useState<string>("");
  React.useEffect(() => {
    if (!activeId && tickets[0]?.id != null) setActiveId(String(tickets[0].id));
  }, [tickets, activeId]);

  const ticketDetailQ = useSupportTicket(activeId || null);
  const createM = useCreateSupportTicket();
  const replyM = useReplySupportTicket();
  const closeM = useCloseSupportTicket();

  const activeSummary = tickets.find((t) => String(t.id) === activeId);
  const detail = ticketDetailQ.data as { ticket?: Record<string, unknown>; messages?: Array<Record<string, unknown>> } | undefined;
  const messages = detail?.messages || [];

  const list = tickets.filter((t) =>
    (filter === "all" || normalizeStatus(String(t.status || "open")) === filter) &&
    (String(t.subject || "").toLowerCase().includes(search.toLowerCase()) ||
      String(t.public_ref || t.id || "").toLowerCase().includes(search.toLowerCase())),
  );

  const counts = {
    all: tickets.length,
    open: tickets.filter((t) => normalizeStatus(String(t.status || "")) === "open").length,
    pending: tickets.filter((t) => normalizeStatus(String(t.status || "")) === "pending").length,
    closed: tickets.filter((t) => normalizeStatus(String(t.status || "")) === "closed").length,
  };

  const sendReply = async () => {
    if (!activeId || !reply.trim()) return;
    try {
      await replyM.mutateAsync({ ticketId: activeId, message: reply.trim() });
      setReply("");
      toast.success("Reply sent");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Reply failed");
    }
  };

  const closeTicket = async () => {
    if (!activeId) return;
    try {
      await closeM.mutateAsync(activeId);
      toast.success("Ticket closed");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not close ticket");
    }
  };

  const createTicket = async (subject: string, category: string, priority: Priority, body: string) => {
    try {
      const created = await createM.mutateAsync({ subject, category, message: body, priority });
      setActiveId(String((created as Record<string, unknown>).id));
      setNewOpen(false);
      toast.success("Ticket created");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create ticket");
    }
  };

  const activeStatus = normalizeStatus(String(activeSummary?.status || detail?.ticket?.status || "open"));

  return (
    <div className="flex w-full flex-col gap-6">
      <PageHeader
        eyebrow={<Link to="/account/support" className="inline-flex items-center gap-1 hover:text-foreground"><ArrowLeft className="size-3" /> Support</Link>}
        title="Email support tickets"
        description="Track every conversation with our team. Reply, set priority, and close when resolved."
        actions={
          <Dialog open={newOpen} onOpenChange={setNewOpen}>
            <DialogTrigger asChild><Button className="gap-1.5"><Plus className="size-4" /> New ticket</Button></DialogTrigger>
            <DialogContent><NewTicketForm onCreate={createTicket} loading={createM.isPending} /></DialogContent>
          </Dialog>
        }
      />

      <div className="grid gap-3 md:grid-cols-4">
        <KpiTile icon={Mail} label="All tickets" value={counts.all} active={filter === "all"} onClick={() => setFilter("all")} />
        <KpiTile icon={AlertTriangle} label="Open" value={counts.open} tone="success" active={filter === "open"} onClick={() => setFilter("open")} />
        <KpiTile icon={Clock} label="Pending" value={counts.pending} tone="warning" active={filter === "pending"} onClick={() => setFilter("pending")} />
        <KpiTile icon={CheckCircle2} label="Closed" value={counts.closed} tone="muted" active={filter === "closed"} onClick={() => setFilter("closed")} />
      </div>

      <Card>
        <CardContent className="grid gap-0 p-0 md:grid-cols-[320px_1fr]">
          <div className="border-b border-border md:border-b-0 md:border-r">
            <div className="border-b border-border p-3">
              <div className="relative">
                <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                <Input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search tickets…" className="h-9 pl-8" />
              </div>
            </div>
            <div className="max-h-[560px] divide-y divide-border overflow-y-auto">
              {ticketsQ.isLoading ? (
                <div className="space-y-2 p-4"><Skeleton className="h-14 w-full" /><Skeleton className="h-14 w-full" /></div>
              ) : list.length === 0 ? (
                <p className="p-6 text-center text-xs text-muted-foreground">No tickets match.</p>
              ) : list.map((t) => {
                const id = String(t.id);
                const st = normalizeStatus(String(t.status || "open"));
                return (
                  <button
                    key={id}
                    onClick={() => setActiveId(id)}
                    className={cn("w-full px-3 py-3 text-left transition hover:bg-accent/40", activeId === id && "bg-accent/60")}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[10px] font-medium text-muted-foreground">{String(t.public_ref || id)}</span>
                      <span className={cn("inline-flex items-center gap-1 rounded-full border px-1.5 py-0.5 text-[10px]", statusMeta[st].chip)}>
                        <span className={cn("size-1.5 rounded-full", statusMeta[st].dot)} />{statusMeta[st].label}
                      </span>
                    </div>
                    <p className="mt-1 line-clamp-2 text-sm font-medium">{String(t.subject || "Support ticket")}</p>
                    <div className="mt-1 flex items-center justify-between text-[11px] text-muted-foreground">
                      <span className="truncate">{String(t.category || "General")} · <span className={priorityMeta[String(t.priority || "normal") as Priority] || priorityMeta.normal}>{String(t.priority || "normal")}</span></span>
                      <span>{formatWhen(t.updated_at || t.last_message_at)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="flex min-h-[560px] flex-col">
            {!activeId || !activeSummary ? (
              <div className="flex flex-1 items-center justify-center text-sm text-muted-foreground">Select a ticket</div>
            ) : (
              <>
                <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border p-4">
                  <div>
                    <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                      <span>{String(activeSummary.public_ref || activeId)}</span>·<span>{String(activeSummary.category || "General")}</span>·<span>{String(activeSummary.created_by_email || activeSummary.requester || "")}</span>
                    </div>
                    <h2 className="mt-1 text-base font-semibold">{String(activeSummary.subject || "")}</h2>
                    <div className="mt-1.5 flex items-center gap-2">
                      <Badge variant="outline" className={statusMeta[activeStatus].chip}>{statusMeta[activeStatus].label}</Badge>
                      <Badge variant="outline" className={priorityMeta[String(activeSummary.priority || "normal") as Priority] || priorityMeta.normal}>{String(activeSummary.priority || "normal")} priority</Badge>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {activeStatus !== "closed" && (
                      <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void closeTicket()} disabled={closeM.isPending}>
                        <CheckCircle2 className="size-3.5" /> Close ticket
                      </Button>
                    )}
                  </div>
                </div>

                <div className="flex-1 space-y-4 overflow-y-auto bg-muted/20 p-4">
                  {ticketDetailQ.isLoading ? (
                    <Skeleton className="h-24 w-full" />
                  ) : messages.map((m) => {
                    const me = String(m.sender_type || "").toLowerCase() === "customer";
                    const author = String(m.sender_email || (me ? "You" : "VoxBulk support"));
                    return (
                      <div key={String(m.id)} className={cn("flex gap-3", me && "flex-row-reverse")}>
                        <div className={cn("grid size-8 shrink-0 place-items-center rounded-full text-xs font-semibold", me ? "bg-primary text-primary-foreground" : "bg-accent text-accent-foreground")}>
                          {author.split(" ").map((s) => s[0]).slice(0, 2).join("")}
                        </div>
                        <div className={cn("max-w-[75%] rounded-2xl border border-border bg-card p-3 text-sm shadow-sm", me && "bg-primary/5")}>
                          <div className="flex items-center justify-between gap-3 text-[11px] text-muted-foreground">
                            <span className="font-medium text-foreground">{author}</span>
                            <span>{formatWhen(m.created_at)}</span>
                          </div>
                          <p className="mt-1.5 whitespace-pre-wrap leading-relaxed">{String(m.body || "")}</p>
                        </div>
                      </div>
                    );
                  })}
                </div>

                <div className="border-t border-border p-3">
                  {activeStatus === "closed" ? (
                    <div className="flex items-center justify-between rounded-md border border-dashed border-border p-3 text-xs text-muted-foreground">
                      <span><MessageSquare className="mr-1 inline size-3" /> This ticket is closed.</span>
                    </div>
                  ) : (
                    <>
                      <Textarea rows={3} value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Write a reply…" />
                      <div className="mt-2 flex items-center justify-between">
                        <p className="text-[11px] text-muted-foreground">Replies are emailed to our support team.</p>
                        <Button onClick={() => void sendReply()} disabled={!reply.trim() || replyM.isPending} className="gap-1.5">
                          <Send className="size-4" /> {replyM.isPending ? "Sending…" : "Send reply"}
                        </Button>
                      </div>
                    </>
                  )}
                </div>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

function KpiTile({ icon: Icon, label, value, tone, active, onClick }: { icon: React.ComponentType<{ className?: string }>; label: string; value: number; tone?: "success" | "warning" | "muted"; active?: boolean; onClick: () => void }) {
  const toneCls =
    tone === "success" ? "text-success bg-success/10" :
    tone === "warning" ? "text-warning bg-warning/10" :
    tone === "muted" ? "text-muted-foreground bg-muted" :
    "text-primary bg-primary/10";
  return (
    <button onClick={onClick} className={cn("flex items-center gap-3 rounded-xl border border-border bg-card p-4 text-left transition hover:border-primary/40", active && "ring-2 ring-primary/40")}>
      <div className={cn("grid size-10 place-items-center rounded-lg", toneCls)}><Icon className="size-5" /></div>
      <div>
        <p className="text-[11px] uppercase tracking-wider text-muted-foreground">{label}</p>
        <p className="text-xl font-semibold">{value}</p>
      </div>
    </button>
  );
}

function NewTicketForm({ onCreate, loading }: { onCreate: (subject: string, category: string, priority: Priority, body: string) => void; loading?: boolean }) {
  const [subject, setSubject] = React.useState("");
  const [category, setCategory] = React.useState("Integrations");
  const [priority, setPriority] = React.useState<Priority>("normal");
  const [body, setBody] = React.useState("");
  return (
    <>
      <DialogHeader><DialogTitle>New support ticket</DialogTitle></DialogHeader>
      <div className="space-y-3">
        <div className="space-y-1.5"><Label className="text-xs">Subject</Label><Input value={subject} onChange={(e) => setSubject(e.target.value)} placeholder="Brief summary" /></div>
        <div className="grid gap-3 md:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs">Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {["Integrations", "Billing", "Feature request", "AI calling", "WhatsApp", "Other"].map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Priority</Label>
            <Select value={priority} onValueChange={(v) => setPriority(v as Priority)}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>
                {(["low", "normal", "high", "urgent"] as Priority[]).map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        </div>
        <div className="space-y-1.5"><Label className="text-xs">Describe the issue</Label><Textarea rows={5} value={body} onChange={(e) => setBody(e.target.value)} placeholder="What happened? Include steps, IDs, screenshots…" /></div>
      </div>
      <DialogFooter>
        <Button disabled={!subject.trim() || !body.trim() || loading} onClick={() => onCreate(subject.trim(), category, priority, body.trim())}>
          {loading ? "Creating…" : "Create ticket"}
        </Button>
      </DialogFooter>
    </>
  );
}
