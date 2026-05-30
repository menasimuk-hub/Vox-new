import { useRouterState } from "@tanstack/react-router";
import { Bell, Moon, Search, Sun, Plug, Sparkles, Send, X, Bot, User as UserIcon, Menu } from "lucide-react";
import * as React from "react";

import { useSidebar } from "@/components/ui/sidebar";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { useTheme } from "@/lib/theme";
import { titleForPath } from "@/lib/page-titles";
import { useConnections, bookingSystemName } from "@/lib/connections";
import { initialsFromName, useSession } from "@/lib/session";

function SidebarToggle() {
  const { toggleSidebar } = useSidebar();

  return (
    <button
      type="button"
      onClick={toggleSidebar}
      aria-label="Toggle sidebar"
      className="flex h-8 w-8 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
  const { bookingSystem } = useConnections();
  const connectedName = bookingSystemName(bookingSystem);
  const avatar = initialsFromName(
    session?.org?.name || session?.org?.display_name || session?.profile?.email || "U",
  );

  return (
    <header className="sticky top-0 z-20 flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/85 px-3 backdrop-blur sm:h-16 sm:gap-3 md:px-6">
      <SidebarToggle />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-semibold leading-tight">{title}</h1>
        {subtitle && <p className="hidden truncate text-[11px] text-muted-foreground sm:block">{subtitle}</p>}
      </div>

      <div className="ml-auto flex shrink-0 items-center gap-1 sm:gap-2">
        {showSearch && (
          <div className="relative hidden md:block">
            <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input placeholder="Search surveys by name or company…" className="h-9 w-80 pl-8 bg-card" />
          </div>
        )}
        <span className="hidden lg:inline-flex items-center gap-1.5 rounded-full border border-border bg-card px-2.5 py-1 text-[11px] text-muted-foreground">
          <span className="size-1.5 rounded-full bg-success" />
          <Plug className="size-3" />
          {connectedName} connected
        </span>
        <Button size="icon" variant="ghost" className="size-8 sm:size-9" onClick={toggle} aria-label="Toggle theme">
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
        <div className="hidden sm:block">
          <NotificationsBell />
        </div>
        <div className="grid size-8 place-items-center rounded-full bg-accent text-accent-foreground text-xs font-semibold sm:size-9">{avatar}</div>
      </div>
    </header>
  );
}

function NotificationsBell() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button size="icon" variant="ghost" className="relative" aria-label="Notifications">
          <Bell className="size-4" />
          <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-primary" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          Notifications <span className="text-[11px] text-muted-foreground">3 new</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {[
          { title: "Survey 'NPS Q4' reached 1k responses", time: "2m" },
          { title: "Recovery campaign rebooked 3 patients", time: "18m" },
          { title: "Payment failed for 'Whitening promo'", time: "1h" },
        ].map((n) => (
          <DropdownMenuItem key={n.title} className="flex flex-col items-start gap-0.5">
            <span className="text-sm">{n.title}</span>
            <span className="text-[11px] text-muted-foreground">{n.time} ago</span>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

type Msg = { role: "user" | "ai"; text: string };

const SUGGESTIONS = [
  "Why did 3 calls fail last night?",
  "Draft a recall script for hygiene",
  "Summarise NPS Q4 results",
  "Which patients should I prioritise today?",
];

export function LiveChatFab() {
  const { chatOpen, toggleChat, closeChat } = useConnections();
  const [minimized, setMinimized] = React.useState(false);
  const [pos, setPos] = React.useState({ x: 0, y: 0 });
  const dragRef = React.useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null);
  const [messages, setMessages] = React.useState<Msg[]>([
    { role: "ai", text: "Hi — I'm VoxBulk AI. Ask about campaigns, scripts, or metrics." },
  ]);
  const [input, setInput] = React.useState("");
  const [thinking, setThinking] = React.useState(false);
  const endRef = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, thinking, chatOpen]);

  const onPointerDown = (e: React.PointerEvent) => {
    if ((e.target as HTMLElement).closest("button,input,textarea")) return;
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

  function send(text: string) {
    const t = text.trim();
    if (!t) return;
    setMessages((m) => [...m, { role: "user", text: t }]);
    setInput("");
    setThinking(true);
    setTimeout(() => {
      setMessages((m) => [...m, { role: "ai", text: aiReply(t) }]);
      setThinking(false);
    }, 900);
  }

  if (minimized) {
    return (
      <button
        type="button"
        onClick={() => setMinimized(false)}
        className="fixed bottom-4 right-4 z-20 grid size-10 place-items-center rounded-full border border-border bg-background shadow-md"
        aria-label="Open Ask AI"
        title="Ask AI"
      >
        <Sparkles className="size-4 text-primary" />
      </button>
    );
  }

  return (
    <>
      {!chatOpen && (
        <Button
          onClick={toggleChat}
          className="fixed bottom-4 right-4 z-20 h-10 gap-1.5 rounded-full bg-[#0f1b3d] px-3 shadow-md hover:bg-[#16244a] sm:bottom-5 sm:right-5"
          aria-label="Ask AI"
        >
          <Sparkles className="size-4" />
          <span className="hidden text-sm font-medium sm:inline">Ask AI</span>
        </Button>
      )}
      {chatOpen && (
        <div
          className="fixed z-20 flex h-[min(520px,calc(100vh-6rem))] w-[min(360px,calc(100vw-2rem))] flex-col overflow-hidden rounded-2xl border border-border bg-popover shadow-2xl touch-none"
          style={{ bottom: 72, right: 16, transform: `translate(${pos.x}px, ${pos.y}px)` }}
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
              <button type="button" onClick={() => setMinimized(true)} className="rounded p-1 opacity-80 hover:bg-primary-foreground/10" aria-label="Minimize">—</button>
              <button type="button" onClick={closeChat} className="rounded p-1 opacity-80 hover:bg-primary-foreground/10" aria-label="Close"><X className="size-4" /></button>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto bg-muted/30 px-3 py-3 text-sm">
            {messages.map((m, i) => (
              <ChatBubble key={i} role={m.role} text={m.text} />
            ))}
            {thinking && (
              <div className="flex items-start gap-2">
                <div className="grid size-6 shrink-0 place-items-center rounded-full bg-primary/15 text-primary"><Bot className="size-3.5" /></div>
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
      <div className={"grid size-6 shrink-0 place-items-center rounded-full " + (isAi ? "bg-primary/15 text-primary" : "bg-accent text-accent-foreground")}>
        {isAi ? <Bot className="size-3.5" /> : <UserIcon className="size-3.5" />}
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

function aiReply(q: string): string {
  const t = q.toLowerCase();
  if (t.includes("fail")) return "3 calls failed last night: 2 voicemails (no answer after 3 retries) and 1 invalid number. I've queued WhatsApp follow-ups for the voicemails — want me to send them now?";
  if (t.includes("recall") || t.includes("hygiene")) return "Drafted a 35-second hygiene recall script in a warm UK tone. It mentions the 6-month interval and offers two slots from your Dentally calendar. Open Settings → System → Script builder to preview.";
  if (t.includes("nps")) return "NPS Q4 stands at +52 (1,204 responses, 78% response rate). Top theme: 'friendly staff' (+). Watch-out: 'waiting times' mentioned in 11% of detractors.";
  if (t.includes("priori")) return "Today's top 5: 3 high-LTV patients overdue for hygiene, 1 no-show from Tuesday, and 1 lapsed whitening enquiry. Shall I start an AI call batch?";
  return "Got it. I can pull campaign metrics, draft scripts, or kick off a workflow — tell me a bit more about what you'd like to see.";
}
