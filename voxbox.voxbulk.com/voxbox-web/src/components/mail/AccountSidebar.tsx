import { ChevronDown, ChevronUp, Inbox, Plus, Settings, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MailAccount, MailMessage } from "@/lib/mail-store";

interface Props {
  accounts: MailAccount[];
  messages: MailMessage[];
  selectedAccount: string; // "all" or account id
  onSelect: (id: string) => void;
  onMove: (id: string, dir: -1 | 1) => void;
  onOpenSettings: () => void;
  displayName: string;
}

export function AccountSidebar({
  accounts,
  messages,
  selectedAccount,
  onSelect,
  onMove,
  onOpenSettings,
  displayName,
}: Props) {
  const unreadFor = (id: string) =>
    messages.filter((m) => m.folder === "inbox" && m.unread && (id === "all" || m.accountId === id))
      .length;

  return (
    <nav className="flex h-full flex-col gap-1 p-3">
      <div className="px-2 pb-3">
        <p className="text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
          Signed in
        </p>
        <p className="truncate font-display text-sm font-semibold">{displayName}</p>
      </div>

      <button
        onClick={() => onSelect("all")}
        className={cn(
          "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
          selectedAccount === "all"
            ? "bg-sidebar-primary text-sidebar-primary-foreground"
            : "hover:bg-sidebar-accent",
        )}
      >
        <Inbox className="size-4" />
        <span className="flex-1 text-left">All accounts</span>
        {unreadFor("all") > 0 && (
          <span className="rounded-full bg-background/25 px-2 py-0.5 text-xs font-semibold">
            {unreadFor("all")}
          </span>
        )}
      </button>

      <p className="px-3 pb-1 pt-4 text-[11px] font-semibold uppercase tracking-widest text-muted-foreground">
        Accounts
      </p>

      <ul className="space-y-0.5">
        {accounts.map((a, i) => {
          const active = selectedAccount === a.id;
          const count = unreadFor(a.id);
          return (
            <li key={a.id} className="group relative">
              <button
                onClick={() => onSelect(a.id)}
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm transition-colors",
                  active
                    ? "bg-sidebar-primary text-sidebar-primary-foreground"
                    : "hover:bg-sidebar-accent",
                )}
              >
                <span
                  className="size-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: a.color }}
                />
                <span className="flex-1 truncate text-left">
                  <span className="block truncate font-medium">{a.name}</span>
                  <span
                    className={cn(
                      "block truncate text-[11px]",
                      active ? "opacity-80" : "text-muted-foreground",
                    )}
                  >
                    {a.email}
                  </span>
                </span>
                {count > 0 && (
                  <span
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-semibold",
                      active ? "bg-background/25" : "bg-primary text-primary-foreground",
                    )}
                  >
                    {count}
                  </span>
                )}
              </button>
              <div className="absolute right-1 top-1/2 hidden -translate-y-1/2 flex-col group-hover:flex">
                <button
                  aria-label={`Move ${a.name} up`}
                  disabled={i === 0}
                  onClick={() => onMove(a.id, -1)}
                  className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground disabled:opacity-30"
                >
                  <ChevronUp className="size-3" />
                </button>
                <button
                  aria-label={`Move ${a.name} down`}
                  disabled={i === accounts.length - 1}
                  onClick={() => onMove(a.id, 1)}
                  className="rounded p-0.5 text-muted-foreground hover:bg-background hover:text-foreground disabled:opacity-30"
                >
                  <ChevronDown className="size-3" />
                </button>
              </div>
            </li>
          );
        })}
      </ul>

      <div className="mt-auto space-y-1 pt-4">
        <Button variant="ghost" className="w-full justify-start gap-2" onClick={onOpenSettings}>
          <Plus className="size-4" /> Add account
        </Button>
        <Button variant="ghost" className="w-full justify-start gap-2" onClick={onOpenSettings}>
          <Settings className="size-4" /> Settings
        </Button>
        <p className="flex items-center gap-1.5 px-3 pt-2 text-[11px] text-muted-foreground">
          <Mail className="size-3" /> Voxbox unified mail
        </p>
      </div>
    </nav>
  );
}
