import { useRouterState, useNavigate } from "@tanstack/react-router";
import { Bell, History, Moon, Search, Sun, Sparkles, Send, ThumbsDown, ThumbsUp, Trash2, X, User as UserIcon, Menu } from "lucide-react";
import * as React from "react";

import { useSidebar } from "@/components/ui/sidebar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useTheme } from "@/lib/theme";
import { titleForPath } from "@/lib/page-titles";
import { useConnections } from "@/lib/connections";
import { useSession } from "@/lib/session";
import {
  useMarkAllNotificationsRead,
  useMarkNotificationRead,
  useNotificationUnreadCount,
  useUnreadNotifications,
  useAssistantChat,
  useAssistantConfirm,
  useAssistantReportSupport,
  useAssistantConversations,
  useDeleteAssistantConversation,
  useAssistantMessageFeedback,
} from "@/lib/queries";
import { UserMenu } from "@/components/user-menu";
import { normalizeOrgRole } from "@/lib/org-roles";
import { useAssistantHighlight } from "@/lib/assistant-highlight";
import { executeUiCommands, isSameAssistantRoute } from "@/lib/assistant-ui-commands";
import { useServices, type ServiceKey } from "@/lib/services";
import type { AssistantChatResponse, AssistantNextAction } from "@/lib/types/assistant";
import { brandAssets } from "@/lib/brand";
import { PwaInstallButton } from "@/components/pwa-install";
import { apiFetch } from "@/lib/api";
import { useQueryClient } from "@tanstack/react-query";
import type { AssistantMessage } from "@/lib/types/assistant";

function AiBrandIcon({ className }: { className?: string }) {
  return <img src={brandAssets.iconDark} alt="" className={className} aria-hidden />;
}

function SidebarToggle() {
  const { toggleSidebar } = useSidebar();

  return (
    <button
      type="button"
      onClick={toggleSidebar}
      aria-label="Toggle sidebar"
      className="flex h-11 w-11 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring md:h-8 md:w-8"
    >
      <Menu className="size-4" />
      <span className="sr-only">Toggle sidebar</span>
    </button>
  );
}

export function TopBar() {
  const path = useRouterState({ select: (r) => r.location.pathname });
  const { theme, toggle } = useTheme();
  const { session } = useSession();
  const { title, subtitle } = titleForPath(path);
  const showSearch = path.startsWith("/surveys");
  const { toggleChat } = useConnections();
  const orgName = session?.org?.name || session?.org?.display_name || "Company";
  const role = normalizeOrgRole(session?.profile?.role);
  const contextLine = `${orgName} · ${role.charAt(0).toUpperCase()}${role.slice(1)}`;

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/85 px-3 backdrop-blur sm:h-16 sm:gap-3 md:px-6">
      <SidebarToggle />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold leading-tight">{title}</h1>
        <p className="hidden truncate text-[11px] text-muted-foreground sm:block">
          {subtitle || `Viewing ${contextLine}`}
        </p>
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
        {showSearch && (
          <div className="relative hidden md:block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Search surveys by name or company…" className="h-9 w-80 pl-8 bg-card" />
          </div>
        )}
        <Button
          onClick={toggleChat}
          className="h-11 gap-1.5 bg-[#0f1b3d] text-white border border-[#0f1b3d] hover:bg-[#16244a] hover:scale-[1.03] active:scale-[0.97] transition-all px-2.5 shadow-[0_0_12px_rgba(15,27,61,0.25)] md:h-9 md:px-3 cursor-pointer"
          aria-label="Ask AI"
          title="Ask AI"
        >
          <Sparkles className="size-4 text-amber-300 animate-pulse" />
          <span className="hidden text-xs font-semibold sm:inline">Ask AI</span>
        </Button>
        <PwaInstallButton />
        <Button size="icon" variant="ghost" className="size-11 md:size-9" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
        <NotificationsBell />
        <UserMenu />
      </div>
    </header>
  );
}

function navigateFromNotificationAction(
  navigate: ReturnType<typeof useNavigate>,
  actionUrl: string,
) {
  const url = new URL(actionUrl, window.location.origin);
  const path = url.pathname;
  const ticket = url.searchParams.get("ticket");
  const orderId = url.searchParams.get("orderId");

  if (path === "/account/support/tickets" && ticket) {
    void navigate({ to: "/account/support/tickets", search: { ticket } });
    return;
  }
  if (path === "/surveys/results" && orderId) {
    void navigate({ to: "/surveys/results", search: { orderId } });
    return;
  }
  const interviewMatch = path.match(/^\/interviews\/results\/([^/]+)$/);
  if (interviewMatch) {
    void navigate({ to: "/interviews/results/$orderId", params: { orderId: interviewMatch[1] } });
    return;
  }
  void navigate({ to: path });
}

function NotificationsBell() {
  const navigate = useNavigate();
  const [open, setOpen] = React.useState(false);
  const unreadQ = useNotificationUnreadCount();
  const listQ = useUnreadNotifications(10);
  const markRead = useMarkNotificationRead();
  const markAllRead = useMarkAllNotificationsRead();
  const unread = Number(unreadQ.data?.count || 0);
  const items = (listQ.data || []) as Array<{
    id: number;
    title?: string;
    message?: string;
    action_url?: string | null;
    read_at?: string | null;
    created_at?: string;
  }>;

  React.useEffect(() => {
    if (open) {
      void unreadQ.refetch();
      void listQ.refetch();
    }
  }, [open, unreadQ, listQ]);

  return (
    <DropdownMenu open={open} onOpenChange={setOpen}>
      <DropdownMenuTrigger asChild>
        <Button size="icon" variant="ghost" className="relative size-11 md:size-9" aria-label="Notifications">
          <Bell className="size-4" />
          {unread > 0 ? (
            <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[9px] font-semibold text-primary-foreground">
              {unread > 9 ? "9+" : unread}
            </span>
          ) : null}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-[min(20rem,calc(100vw-2rem))]">
        <DropdownMenuLabel className="flex items-center justify-between gap-2">
          <span>Notifications</span>
          <div className="flex items-center gap-2">
            {unread > 0 ? <span className="text-[11px] text-muted-foreground">{unread} new</span> : null}
            {unread > 0 ? (
              <button
                type="button"
                className="text-[11px] font-medium text-primary hover:underline disabled:opacity-50"
                disabled={markAllRead.isPending}
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  void markAllRead.mutateAsync();
                }}
              >
                Clear all
              </button>
            ) : null}
          </div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {listQ.isLoading ? (
          <DropdownMenuItem disabled>Loading…</DropdownMenuItem>
        ) : items.length === 0 ? (
          <DropdownMenuItem disabled>No new notifications</DropdownMenuItem>
        ) : (
          items.map((n) => (
            <DropdownMenuItem
              key={n.id}
              className="flex flex-col items-start gap-0.5"
              onClick={() => {
                void (async () => {
                  if (!n.read_at) await markRead.mutateAsync(n.id);
                  setOpen(false);
                  if (n.action_url) navigateFromNotificationAction(navigate, n.action_url);
                })();
              }}
            >
              <span className="text-sm font-medium">{n.title || "Notification"}</span>
              {n.message ? <span className="text-xs text-muted-foreground line-clamp-2">{n.message}</span> : null}
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

const SUGGESTIONS = [
  "Why is my wallet low?",
  "Can I launch my survey?",
  "Show my survey results",
  "What's my usage this period?",
];

function assistantWelcomeName(email?: string | null): string | null {
  if (!email) return null;
  const local = email.split("@")[0]?.split(/[.+_-]/)[0];
  if (!local) return null;
  return local.charAt(0).toUpperCase() + local.slice(1);
}

const SERVICE_WELCOME_LABELS: Record<ServiceKey, string> = {
  interviews: "interviews",
  surveys: "surveys",
  feedback: "customer feedback",
  appointments: "appointments",
  recovery: "recovery",
  followup: "follow up",
  campaigns: "campaigns",
};

function buildAssistantWelcome(email?: string | null, enabled: ServiceKey[] = []): string {
  const name = assistantWelcomeName(email);
  const modules =
    enabled.length > 0
      ? enabled.map((k) => SERVICE_WELCOME_LABELS[k]).join(", ")
      : "billing, usage, and support";
  const greet = name ? `Hi ${name}` : "Hi";
  return `${greet} — I'm your VoxBulk assistant. Ask about ${modules}, billing, usage, or support. I only cover modules enabled on your account.`;
}

function enabledServicesForAssistant(allowed: Record<ServiceKey, boolean>): string[] {
  return (Object.entries(allowed) as Array<[ServiceKey, boolean]>)
    .filter(([, on]) => on)
    .map(([key]) => key);
}

type Msg = {
  role: "user" | "ai";
  text: string;
  response?: AssistantChatResponse;
  messageId?: string;
  feedback?: "up" | "down";
};

function sourceTypeLabel(sourceType?: string | null): string | null {
  if (sourceType === "knowledge_base") return "From Help Centre";
  if (sourceType === "general_ai") return "General AI";
  if (sourceType === "account_data") return "Your account data";
  if (sourceType === "mixed") return "Help + account";
  return null;
}

export function LiveChatFab() {
  const { chatOpen, closeChat } = useConnections();
  const { session } = useSession();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const currentRoute = useRouterState({ select: (s) => s.location.pathname });
  const { allowed } = useServices();
  const { setHighlight, applyNextAction } = useAssistantHighlight();
  const chatM = useAssistantChat();
  const confirmM = useAssistantConfirm();
  const reportM = useAssistantReportSupport();
  const feedbackM = useAssistantMessageFeedback();
  const convsQ = useAssistantConversations();
  const deleteConvM = useDeleteAssistantConversation();
  const enabledForAssistant = React.useMemo(
    () => enabledServicesForAssistant(allowed) as ServiceKey[],
    [allowed],
  );
  const welcomeText = React.useMemo(
    () => buildAssistantWelcome(session?.profile?.email, enabledForAssistant),
    [session?.profile?.email, enabledForAssistant],
  );
  const orgId = session?.org?.id;
  const [pos, setPos] = React.useState({ x: 0, y: 0 });
  const dragRef = React.useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const [messages, setMessages] = React.useState<Msg[]>([]);
  const [input, setInput] = React.useState("");
  const [history, setHistory] = React.useState<Array<{ role: string; text: string }>>([]);
  const [reportedTokens, setReportedTokens] = React.useState<Record<string, string>>({});
  const [conversationId, setConversationId] = React.useState<string | null>(null);
  const [showHistory, setShowHistory] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);
  const chatScrollRef = React.useRef<HTMLDivElement>(null);

  function resetChat() {
    setMessages([{ role: "ai", text: welcomeText }]);
    setHistory([]);
    setReportedTokens({});
    setConversationId(null);
  }

  React.useEffect(() => {
    resetChat();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [welcomeText, orgId]);

  React.useEffect(() => {
    if (!chatOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeChat();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [chatOpen, closeChat]);

  // Scroll only inside the chat panel — never the main document (that looked like a page reload).
  React.useEffect(() => {
    if (!chatOpen) return;
    const box = chatScrollRef.current;
    if (box) {
      box.scrollTop = box.scrollHeight;
      return;
    }
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "nearest" });
  }, [messages, chatOpen]);

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button,input,textarea,a")) return;
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y };
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    setPos({
      x: dragRef.current.origX + (e.clientX - dragRef.current.startX),
      y: dragRef.current.origY + (e.clientY - dragRef.current.startY),
    });
  };
  const onPointerUp = () => { dragRef.current = null; };

  function applyResponse(res: AssistantChatResponse, userText: string) {
    if (res.highlight_type && res.highlight_id) {
      setHighlight({ type: res.highlight_type, id: res.highlight_id, label: res.highlight_label });
    }
    executeUiCommands(res.ui_commands, {
      navigate: (route) => void navigate({ to: route }),
      setHighlight,
      currentPath: currentRoute,
    });
    if (res.conversation_id) setConversationId(res.conversation_id);
    setMessages((m) => [
      ...m,
      { role: "ai", text: res.primary_message, response: res, messageId: res.message_id || undefined },
    ]);
    setHistory((h) => [...h, { role: "user", text: userText }, { role: "assistant", text: res.primary_message }].slice(-16));
    void qc.invalidateQueries({ queryKey: ["assistant", "conversations"] });
  }

  async function sendReport(token: string) {
    if (!token || reportM.isPending || reportedTokens[token]) return;
    try {
      const out = await reportM.mutateAsync({ support_report_token: token });
      setReportedTokens((prev) => ({ ...prev, [token]: out.ticket_ref || "sent" }));
      setMessages((m) => [...m, { role: "ai", text: out.message }]);
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "Could not send the report right now. Please try again or open Support tickets." }]);
    }
  }

  async function sendFeedback(messageId: string, rating: "up" | "down") {
    if (!messageId || feedbackM.isPending) return;
    try {
      await feedbackM.mutateAsync({ messageId, rating });
      setMessages((prev) =>
        prev.map((m) => (m.messageId === messageId ? { ...m, feedback: rating } : m)),
      );
    } catch {
      /* ignore */
    }
  }

  async function loadConversation(id: string) {
    try {
      const rows = await apiFetch<AssistantMessage[]>(`/assistant/conversations/${id}/messages`);
      setConversationId(id);
      setShowHistory(false);
      const mapped: Msg[] = rows.map((row) => {
        if (row.role === "user") return { role: "user", text: row.content };
        return {
          role: "ai",
          text: row.content,
          messageId: row.id,
          response: {
            ok: true,
            primary_message: row.content,
            highlight_type: "",
            next_actions: [],
            confidence: 1,
            source_type: row.source_type,
            sources: row.sources || [],
            message_id: row.id,
            conversation_id: id,
          },
        };
      });
      setMessages(mapped.length ? mapped : [{ role: "ai", text: welcomeText }]);
      setHistory(
        rows.map((r) => ({
          role: r.role === "assistant" ? "assistant" : "user",
          text: r.content,
        })).slice(-16),
      );
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "Could not load that conversation." }]);
    }
  }

  async function send(text: string) {
    const t = text.trim();
    if (!t || chatM.isPending || confirmM.isPending) return;
    setMessages((m) => [...m, { role: "user", text: t }]);
    setInput("");
    try {
      const res = await chatM.mutateAsync({
        message: t,
        history,
        conversation_id: conversationId,
        context: {
          current_route: currentRoute,
          enabled_services: enabledForAssistant,
        },
      });
      applyResponse(res, t);
    } catch {
      setMessages((m) => [...m, { role: "ai", text: "Assistant unavailable. Try again in a moment." }]);
    }
  }

  async function onNextAction(action: AssistantNextAction) {
    if (action.kind === "confirm" && action.action_id) {
      try {
        const res = await confirmM.mutateAsync({ action_id: action.action_id, confirmed: true });
        applyResponse(res, "Confirmed action");
      } catch (err) {
        const msg = err instanceof Error ? err.message : "Could not complete action.";
        setMessages((m) => [...m, { role: "ai", text: msg }]);
      }
      return;
    }
    if (action.kind === "navigate" && action.route) {
      if (!isSameAssistantRoute(currentRoute, action.route)) {
        void navigate({ to: action.route });
      }
      return;
    }
    applyNextAction(action);
  }

  const thinking = chatM.isPending || confirmM.isPending || reportM.isPending;

  return (
    <>
      {chatOpen && (
        <div
          className="fixed z-50 flex h-[min(520px,calc(100vh-6rem))] w-[min(360px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl touch-none"
          style={{ bottom: 16, right: 16, transform: `translate(${pos.x}px, ${pos.y}px)` }}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        >
          <div className="flex cursor-grab items-center justify-between border-b border-border bg-gradient-to-r from-primary to-primary/80 px-3 py-2 text-primary-foreground active:cursor-grabbing">
            <div className="flex items-center gap-2">
              <Sparkles className="size-4" />
              <p className="text-sm font-semibold">VoxBulk AI</p>
            </div>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={() => setShowHistory((v) => !v)}
                className="inline-flex min-h-11 min-w-11 items-center justify-center rounded opacity-80 hover:bg-primary-foreground/10 md:min-h-0 md:min-w-0 md:p-1"
                aria-label="History"
              >
                <History className="size-4" />
              </button>
              <button type="button" onClick={closeChat} className="inline-flex min-h-11 min-w-11 items-center justify-center rounded opacity-80 hover:bg-primary-foreground/10 md:min-h-0 md:min-w-0 md:p-1" aria-label="Close"><X className="size-4" /></button>
            </div>
          </div>

          {showHistory ? (
            <div className="flex-1 space-y-2 overflow-y-auto bg-muted/30 px-3 py-3 text-sm">
              <div className="flex items-center justify-between">
                <p className="text-xs font-medium text-muted-foreground">Your conversations</p>
                <button type="button" className="text-[11px] text-primary" onClick={() => { resetChat(); setShowHistory(false); }}>
                  New chat
                </button>
              </div>
              {(convsQ.data || []).map((c) => (
                <div key={c.id} className="flex items-center gap-2 rounded-lg border border-border bg-card px-2 py-2">
                  <button type="button" className="min-w-0 flex-1 text-left text-xs" onClick={() => void loadConversation(c.id)}>
                    <span className="block truncate font-medium">{c.title || "Conversation"}</span>
                    <span className="text-[10px] text-muted-foreground">{c.updated_at?.slice(0, 16)}</span>
                  </button>
                  <button
                    type="button"
                    className="rounded p-1 text-muted-foreground hover:text-destructive"
                    aria-label="Delete conversation"
                    onClick={() => void deleteConvM.mutateAsync(c.id).then(() => {
                      if (conversationId === c.id) resetChat();
                    })}
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </div>
              ))}
              {!convsQ.data?.length ? (
                <p className="text-center text-xs text-muted-foreground">No saved chats yet.</p>
              ) : null}
            </div>
          ) : (
          <div
            ref={chatScrollRef}
            className="flex-1 space-y-3 overflow-y-auto bg-muted/30 px-3 py-3 text-sm"
            aria-live="polite"
          >
            {messages.map((m, i) => (
              <div key={i}>
                <ChatBubble role={m.role} text={m.text} />
                {m.role === "ai" && m.response?.source_type ? (
                  <div className="ml-8 mt-1.5 flex flex-wrap gap-1">
                    <span className="rounded-full border border-border bg-muted/60 px-2 py-0.5 text-[10px] text-muted-foreground">
                      {sourceTypeLabel(m.response.source_type)}
                    </span>
                    {(m.response.sources || []).slice(0, 3).map((src, idx) => (
                      <button
                        key={`${src.source_id || src.id || idx}`}
                        type="button"
                        onClick={() => src.url && void navigate({ to: src.url })}
                        className="rounded-full border border-primary/25 bg-card px-2 py-0.5 text-[10px] text-primary hover:bg-primary/10"
                      >
                        {src.title || "Source"}
                      </button>
                    ))}
                  </div>
                ) : null}
                {m.role === "ai" && m.messageId ? (
                  <div className="ml-8 mt-1.5 flex items-center gap-1">
                    <button
                      type="button"
                      aria-label="Helpful"
                      onClick={() => void sendFeedback(m.messageId!, "up")}
                      className={"rounded p-1 " + (m.feedback === "up" ? "text-primary" : "text-muted-foreground hover:text-foreground")}
                    >
                      <ThumbsUp className="size-3.5" />
                    </button>
                    <button
                      type="button"
                      aria-label="Not helpful"
                      onClick={() => void sendFeedback(m.messageId!, "down")}
                      className={"rounded p-1 " + (m.feedback === "down" ? "text-primary" : "text-muted-foreground hover:text-foreground")}
                    >
                      <ThumbsDown className="size-3.5" />
                    </button>
                    {m.feedback === "down" ? (
                      <button
                        type="button"
                        onClick={() => void navigate({ to: "/account/support" })}
                        className="ml-1 rounded-full border border-warning/40 bg-warning/10 px-2 py-0.5 text-[10px] font-medium"
                      >
                        Send to Support
                      </button>
                    ) : null}
                  </div>
                ) : null}
                {m.role === "ai" && m.response?.next_actions?.length ? (
                  <div className="ml-8 mt-1.5 flex flex-wrap gap-1">
                    {m.response.next_actions.map((a) => (
                      <button
                        key={a.id}
                        type="button"
                        onClick={() => void onNextAction(a)}
                        className="rounded-full border border-primary/30 bg-card px-2.5 py-1 text-[11px] font-medium text-primary transition hover:bg-primary/10"
                      >
                        {a.label}
                      </button>
                    ))}
                  </div>
                ) : null}
                {m.role === "ai" && m.response?.suggested_prompts?.length ? (
                  <div className="ml-8 mt-1.5 flex flex-wrap gap-1">
                    {m.response.suggested_prompts.map((prompt) => (
                      <button
                        key={prompt}
                        type="button"
                        onClick={() => void send(prompt)}
                        className="rounded-full border border-border bg-muted/50 px-2.5 py-1 text-[11px] text-muted-foreground transition hover:border-primary/40 hover:text-foreground"
                      >
                        {prompt}
                      </button>
                    ))}
                  </div>
                ) : null}
                {m.role === "ai" && m.response?.error_occurred && m.response.support_report_token ? (
                  <div className="ml-8 mt-1.5">
                    <button
                      type="button"
                      disabled={Boolean(reportedTokens[m.response.support_report_token])}
                      onClick={() => void sendReport(m.response!.support_report_token!)}
                      className="rounded-full border border-warning/40 bg-warning/10 px-2.5 py-1 text-[11px] font-medium text-warning-foreground transition hover:bg-warning/20 disabled:opacity-60"
                    >
                      {reportedTokens[m.response.support_report_token]
                        ? `Reported (${reportedTokens[m.response.support_report_token]})`
                        : "Send to Support"}
                    </button>
                  </div>
                ) : null}
                {m.role === "ai" && m.response?.blocking_reason ? (
                  <p className="ml-8 mt-1 text-[11px] text-warning">{m.response.blocking_reason}</p>
                ) : null}
              </div>
            ))}
            {thinking && (
              <div className="flex items-start gap-2">
                <div className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/15 p-0.5"><AiBrandIcon className="size-full object-contain" /></div>
                <div className="rounded-2xl rounded-bl-sm border border-border bg-card px-3 py-2">
                  <div className="flex gap-1">
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:0ms]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:120ms]" />
                    <span className="size-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:240ms]" />
                  </div>
                </div>
              </div>
            )}
            {messages.length <= 1 && (
              <div className="flex flex-wrap gap-1.5 pt-1">
                {SUGGESTIONS.map((s) => (
                  <button key={s} onClick={() => send(s)} className="rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground transition hover:border-primary/40 hover:text-foreground">
                    {s}
                  </button>
                ))}
              </div>
            )}
            <div ref={endRef} />
          </div>
          )}

          <form
            onSubmit={(e) => { e.preventDefault(); send(input); }}
            className="flex items-center gap-2 border-t border-border bg-background p-2"
          >
            <Input
              autoFocus
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask VoxBulk AI…"
              className="h-9 border-none bg-muted/50 focus-visible:ring-1"
            />
            <Button type="submit" size="icon" className="size-9 shrink-0" disabled={!input.trim() || thinking}>
              <Send className="size-4" />
            </Button>
          </form>
        </div>
      )}
    </>
  );
}

function ChatBubble({ role, text }: { role: "user" | "ai"; text: string }) {
  const isAi = role === "ai";
  return (
    <div className={"flex items-start gap-2 " + (isAi ? "" : "flex-row-reverse")}>
      <div className={"grid size-6 shrink-0 place-items-center rounded-full p-0.5 " + (isAi ? "bg-primary/15" : "bg-accent text-accent-foreground")}>
        {isAi ? <AiBrandIcon className="size-full object-contain" /> : <UserIcon className="size-3.5" />}
      </div>
      <div className={
        "max-w-[80%] rounded-2xl px-3 py-2 text-[13px] leading-relaxed " +
        (isAi
          ? "rounded-bl-sm border border-border bg-card text-foreground"
          : "rounded-br-sm bg-primary text-primary-foreground")
      }>
        {text}
      </div>
    </div>
  );
}
