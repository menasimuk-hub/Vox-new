import { useCallback, useEffect, useMemo, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import {
  Archive,
  Inbox,
  LogOut,
  Menu,
  Moon,
  RefreshCw,
  Search,
  Send,
  Settings as SettingsIcon,
  Star,
  Sun,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
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
import { AccountSidebar } from "@/components/mail/AccountSidebar";
import { KpiRow } from "@/components/mail/KpiRow";
import { MessageTable } from "@/components/mail/MessageTable";
import { MessageView } from "@/components/mail/MessageView";
import { SettingsView } from "@/components/mail/SettingsView";
import {
  clearToken,
  createAccount,
  deleteAccount,
  fetchAccounts,
  fetchKpi,
  fetchMessage,
  fetchMessages,
  fetchMe,
  patchMessage,
  reorderAccounts,
  sendMessage,
  syncMail,
  testAccount,
  updateAccount,
  updateCredentials,
  type KpiData,
} from "@/lib/api";
import {
  SESSION_KEY,
  type AppUser,
  type MailAccount,
  type MailAttachment,
  type MailMessage,
} from "@/lib/mail-store";
import { useTheme } from "@/lib/use-theme";
import { cn } from "@/lib/utils";

export const Route = createFileRoute("/mail")({
  component: MailApp,
});

type Tab = "inbox" | "unread" | "important" | "starred" | "sent" | "archive" | "trash";

const TABS: Array<{ id: Tab; label: string; icon: React.ElementType }> = [
  { id: "inbox", label: "Inbox", icon: Inbox },
  { id: "unread", label: "Unread", icon: Inbox },
  { id: "important", label: "Important", icon: Inbox },
  { id: "starred", label: "Starred", icon: Star },
  { id: "sent", label: "Sent", icon: Send },
  { id: "archive", label: "Archive", icon: Archive },
  { id: "trash", label: "Trash", icon: Trash2 },
];

function tabToQuery(tab: Tab): { folder?: string; tab?: string } {
  if (tab === "sent") return { folder: "sent" };
  if (tab === "archive") return { folder: "archive" };
  if (tab === "trash") return { folder: "trash" };
  if (tab === "unread" || tab === "important" || tab === "starred") return { tab };
  return { folder: "inbox" };
}

function MailApp() {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const [user, setUser] = useState<AppUser>({ username: "", displayName: "" });
  const [accounts, setAccounts] = useState<MailAccount[]>([]);
  const [messages, setMessages] = useState<MailMessage[]>([]);
  const [kpi, setKpi] = useState<KpiData | null>(null);
  const [ready, setReady] = useState(false);
  const [tab, setTab] = useState<Tab>("inbox");
  const [account, setAccount] = useState("all");
  const [query, setQuery] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const [openMessage, setOpenMessage] = useState<MailMessage | null>(null);
  const [viewMode, setViewMode] = useState<"read" | "reply" | "forward">("read");
  const [showSettings, setShowSettings] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [loadingMessages, setLoadingMessages] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [confirmDelete, setConfirmDelete] = useState<
    { kind: "single"; id: string } | { kind: "bulk" } | null
  >(null);

  const activeIds = useMemo(
    () => accounts.filter((a) => !a.frozen).map((a) => a.id),
    [accounts],
  );

  const scoped = useMemo(
    () =>
      messages.filter(
        (m) => activeIds.includes(m.accountId) && (account === "all" || m.accountId === account),
      ),
    [messages, account, activeIds],
  );

  const listed = useMemo(
    () => [...scoped].sort((a, b) => +new Date(b.date) - +new Date(a.date)),
    [scoped],
  );

  const refreshKpi = useCallback(async (accountId = account) => {
    try {
      const data = await fetchKpi(accountId);
      setKpi(data);
    } catch {
      /* KPI optional until backend is live */
    }
  }, [account]);

  const refreshMessages = useCallback(async () => {
    setLoadingMessages(true);
    try {
      const q = tabToQuery(tab);
      const rows = await fetchMessages({
        accountId: account,
        folder: q.folder,
        tab: q.tab,
        q: query.trim() || undefined,
      });
      setMessages(rows);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load messages.");
    } finally {
      setLoadingMessages(false);
    }
  }, [account, tab, query]);

  const refreshAccounts = useCallback(async () => {
    const rows = await fetchAccounts();
    setAccounts(rows);
    return rows;
  }, []);

  useEffect(() => {
    if (!window.localStorage.getItem(SESSION_KEY)) {
      navigate({ to: "/" });
      return;
    }

    (async () => {
      try {
        const me = await fetchMe();
        setUser({ username: me.username, displayName: me.displayName });
        await refreshAccounts();
        await refreshMessages();
        await refreshKpi();
        setReady(true);
      } catch {
        clearToken();
        window.localStorage.removeItem(SESSION_KEY);
        navigate({ to: "/" });
      }
    })();
  }, [navigate, refreshAccounts, refreshKpi, refreshMessages]);

  useEffect(() => {
    if (!ready) return;
    const t = window.setTimeout(() => {
      void refreshMessages();
    }, query ? 300 : 0);
    return () => window.clearTimeout(t);
  }, [ready, refreshMessages, query, tab, account]);

  useEffect(() => {
    if (!ready) return;
    void refreshKpi();
  }, [ready, account, refreshKpi]);

  useEffect(() => {
    if (!openId) {
      setOpenMessage(null);
      return;
    }
    const cached = messages.find((m) => m.id === openId);
    if (cached?.html || cached?.text) {
      setOpenMessage(cached);
      return;
    }
    void fetchMessage(openId)
      .then(setOpenMessage)
      .catch((e) => toast.error(e instanceof Error ? e.message : "Could not load message."));
  }, [openId, messages]);

  async function patch(id: string, p: Partial<MailMessage>) {
    try {
      const updated = await patchMessage(id, p);
      setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...updated } : m)));
      if (openId === id) setOpenMessage((prev) => (prev ? { ...prev, ...updated } : prev));
      await refreshKpi();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Update failed.");
    }
  }

  function openMsg(m: MailMessage, mode: "read" | "reply" | "forward" = "read") {
    setOpenId(m.id);
    setViewMode(mode);
    setShowSettings(false);
    if (m.unread) void patch(m.id, { unread: false });
  }

  async function sync() {
    setSyncing(true);
    try {
      const res = await syncMail();
      await refreshAccounts();
      await refreshMessages();
      await refreshKpi();
      toast.success(res.message || "All accounts synced.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Sync failed.");
    } finally {
      setSyncing(false);
    }
  }

  async function sendReply(body: string, kind: "reply" | "forward", _attachments: MailAttachment[]) {
    if (!openMessage) return;
    try {
      await sendMessage(openMessage.id, { kind, body });
      toast.success(kind === "reply" ? "Reply sent." : "Message forwarded.");
      setOpenId(null);
      await refreshMessages();
      await refreshKpi();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Send failed.");
    }
  }

  async function moveAccount(id: string, dir: -1 | 1) {
    const list = [...accounts];
    const i = list.findIndex((a) => a.id === id);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= list.length) return;
    const tmp = list[i]!;
    list[i] = list[j]!;
    list[j] = tmp;
    setAccounts(list);
    try {
      await reorderAccounts(list.map((a) => a.id));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not reorder accounts.");
      await refreshAccounts();
    }
  }

  function logout() {
    clearToken();
    window.localStorage.removeItem(SESSION_KEY);
    navigate({ to: "/" });
  }

  async function runDelete() {
    if (!confirmDelete) return;
    const ids =
      confirmDelete.kind === "single" ? [confirmDelete.id] : selected;
    try {
      await Promise.all(ids.map((id) => patchMessage(id, { folder: "trash" })));
      if (confirmDelete.kind === "single" && openId === confirmDelete.id) setOpenId(null);
      setSelected((s) => s.filter((x) => !ids.includes(x)));
      await refreshMessages();
      await refreshKpi();
      toast.success(ids.length === 1 ? "Moved to trash." : `${ids.length} messages moved to trash.`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Delete failed.");
    }
    setConfirmDelete(null);
  }

  async function saveAccount(a: MailAccount): Promise<MailAccount> {
    const exists = accounts.some((x) => x.id === a.id && !a.id.startsWith("a"));
    try {
      const saved = exists ? await updateAccount(a) : await createAccount(a);
      setAccounts((prev) => {
        const idx = prev.findIndex((x) => x.id === a.id || x.id === saved.id);
        if (idx >= 0) {
          const next = [...prev];
          next[idx] = saved;
          return next;
        }
        return [...prev, saved];
      });
      return saved;
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not save account.");
      throw e;
    }
  }

  async function removeAccount(id: string) {
    try {
      await deleteAccount(id);
      setAccounts((prev) => prev.filter((a) => a.id !== id));
      setMessages((prev) => prev.filter((m) => m.accountId !== id));
      if (account === id) setAccount("all");
      await refreshKpi();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not delete account.");
    }
  }

  async function saveUser(u: AppUser) {
    if (!u.currentPassword) {
      toast.error("Enter your current password to update profile.");
      return;
    }
    try {
      await updateCredentials({
        username: u.username !== user.username ? u.username : undefined,
        password: u.password || undefined,
        displayName: u.displayName !== user.displayName ? u.displayName : undefined,
        currentPassword: u.currentPassword,
      });
      setUser({ username: u.username, displayName: u.displayName });
      toast.success("Profile updated.");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not update profile.");
    }
  }

  const sidebar = (
    <AccountSidebar
      accounts={accounts}
      messages={messages}
      selectedAccount={account}
      displayName={user.displayName}
      onSelect={(id) => {
        setAccount(id);
        setOpenId(null);
        setShowSettings(false);
        setMobileNav(false);
        setSelected([]);
      }}
      onMove={moveAccount}
      onOpenSettings={() => {
        setShowSettings(true);
        setOpenId(null);
        setMobileNav(false);
      }}
    />
  );

  if (!ready) return <div className="min-h-screen bg-background" />;

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-30 border-b bg-surface/95 backdrop-blur">
        <div className="flex items-center gap-2 px-3 py-2.5 sm:px-4">
          <Sheet open={mobileNav} onOpenChange={setMobileNav}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="sm" className="lg:hidden">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 bg-sidebar p-0">
              <SheetTitle className="sr-only">Accounts</SheetTitle>
              {sidebar}
            </SheetContent>
          </Sheet>

          <img
            src={theme === "dark" ? "/brand/logo-white.png" : "/brand/logo-black.png"}
            alt="VoxBulk"
            className="hidden h-6 w-auto sm:block"
          />

          <div className="relative ml-2 hidden max-w-sm flex-1 md:block">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search all mail…"
              className="pl-8"
            />
          </div>

          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="sm" onClick={() => void sync()} disabled={syncing}>
              <RefreshCw className={cn("size-4", syncing && "animate-spin")} />
              <span className="hidden sm:inline">Sync</span>
            </Button>
            <Button variant="ghost" size="sm" onClick={toggle} aria-label="Toggle theme">
              {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setShowSettings(true);
                setOpenId(null);
              }}
            >
              <SettingsIcon className="size-4" />
            </Button>
            <span className="hidden px-2 text-sm font-medium sm:inline">{user.displayName}</span>
            <Button variant="ghost" size="sm" onClick={logout}>
              <LogOut className="size-4" />
            </Button>
          </div>
        </div>

        <div className="flex gap-1 overflow-x-auto px-2 pb-1.5 sm:px-3">
          {TABS.map((t) => {
            const active = !showSettings && tab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => {
                  setTab(t.id);
                  setOpenId(null);
                  setShowSettings(false);
                  setSelected([]);
                }}
                className={cn(
                  "shrink-0 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-primary text-primary-foreground"
                    : "text-muted-foreground hover:bg-surface-2 hover:text-foreground",
                )}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </header>

      <div className="flex">
        <aside className="sticky top-[89px] hidden h-[calc(100vh-89px)] w-72 shrink-0 overflow-y-auto border-r bg-sidebar lg:block">
          {sidebar}
        </aside>

        <main className="min-w-0 flex-1 space-y-4 p-3 sm:p-5">
          <div className="relative md:hidden">
            <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search all mail…"
              className="pl-8"
            />
          </div>

          {showSettings ? (
            <SettingsView
              accounts={accounts}
              user={user}
              onSaveAccount={(a) => saveAccount(a)}
              onDeleteAccount={(id) => void removeAccount(id)}
              onSaveUser={(u) => void saveUser(u)}
              onTestAccount={(a) => testAccount(a.id)}
            />
          ) : openMessage ? (
            <>
              <div className="space-y-3 lg:hidden">
                <div className="flex gap-1 overflow-x-auto">
                  {TABS.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => {
                        setTab(t.id);
                        setOpenId(null);
                      }}
                      className={cn(
                        "shrink-0 rounded-lg border px-3 py-1.5 text-xs font-medium",
                        tab === t.id
                          ? "bg-primary text-primary-foreground"
                          : "bg-card text-muted-foreground",
                      )}
                    >
                      {t.label}
                    </button>
                  ))}
                </div>
                <KpiRow messages={scoped} kpi={kpi ?? undefined} />
              </div>
              <MessageView
                message={openMessage}
                account={accounts.find((a) => a.id === openMessage.accountId)}
                mode={viewMode}
                onBack={() => setOpenId(null)}
                onSend={(body, kind, attachments) => void sendReply(body, kind, attachments)}
                onDelete={(id) => setConfirmDelete({ kind: "single", id })}
                onArchive={(id) => {
                  void patch(id, { folder: "archive" });
                  setOpenId(null);
                  void refreshMessages();
                  toast.success("Archived.");
                }}
                onStar={(id) => void patch(id, { starred: !openMessage.starred })}
              />
            </>
          ) : (
            <>
              <KpiRow messages={scoped} kpi={kpi ?? undefined} />
              <div className="flex items-center justify-between">
                <h1 className="font-display text-lg font-semibold">
                  {TABS.find((t) => t.id === tab)?.label}
                  <span className="ml-2 text-sm font-normal text-muted-foreground">
                    {loadingMessages ? "Loading…" : `${listed.length} messages`} ·{" "}
                    {account === "all"
                      ? "all accounts"
                      : accounts.find((a) => a.id === account)?.email}
                  </span>
                </h1>
              </div>
              <MessageTable
                messages={listed}
                accounts={accounts}
                selected={selected}
                onToggleSelect={(id) =>
                  setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]))
                }
                onToggleAll={() =>
                  setSelected((s) =>
                    listed.every((m) => s.includes(m.id)) ? [] : listed.map((m) => m.id),
                  )
                }
                onBulkDelete={() => setConfirmDelete({ kind: "bulk" })}
                onOpen={(m) => openMsg(m)}
                onReply={(m) => openMsg(m, "reply")}
                onForward={(m) => openMsg(m, "forward")}
                onDelete={(id) => setConfirmDelete({ kind: "single", id })}
                onArchive={(id) => {
                  void patch(id, { folder: "archive" });
                  void refreshMessages();
                  toast.success("Archived.");
                }}
                onStar={(id) => {
                  const starred = !messages.find((m) => m.id === id)?.starred;
                  void patch(id, { starred });
                }}
                onImportant={(id) => {
                  const important = !messages.find((m) => m.id === id)?.important;
                  void patch(id, { important });
                }}
              />
            </>
          )}
        </main>
      </div>

      <AlertDialog open={!!confirmDelete} onOpenChange={(o) => !o && setConfirmDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>
              {confirmDelete?.kind === "bulk"
                ? `Delete ${selected.length} messages?`
                : "Delete this message?"}
            </AlertDialogTitle>
            <AlertDialogDescription>
              {confirmDelete?.kind === "bulk"
                ? "The selected messages will be moved to Trash."
                : "This message will be moved to Trash."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={() => void runDelete()}
            >
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
