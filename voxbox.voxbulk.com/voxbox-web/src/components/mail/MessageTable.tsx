import { formatDistanceToNow } from "date-fns";
import {
  AlertCircle,
  Archive,
  CornerUpLeft,
  Forward,
  Mail,
  Paperclip,
  PenSquare,
  Star,
  Trash2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { cn } from "@/lib/utils";
import type { MailAccount, MailMessage } from "@/lib/mail-store";

interface Props {
  messages: MailMessage[];
  accounts: MailAccount[];
  selected: string[];
  onToggleSelect: (id: string) => void;
  onToggleAll: () => void;
  onBulkDelete: () => void;
  onCompose: () => void;
  onOpen: (m: MailMessage) => void;
  onReply: (m: MailMessage) => void;
  onForward: (m: MailMessage) => void;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onStar: (id: string) => void;
  onImportant: (id: string) => void;
}

export function MessageTable({
  messages,
  accounts,
  selected,
  onToggleSelect,
  onToggleAll,
  onBulkDelete,
  onCompose,
  onOpen,
  onReply,
  onForward,
  onDelete,
  onArchive,
  onStar,
  onImportant,
}: Props) {
  if (messages.length === 0) {
    return (
      <div className="rounded-xl border bg-card p-12 text-center text-sm text-muted-foreground">
        Nothing here. Enjoy the empty inbox.
      </div>
    );
  }

  const allSelected = messages.every((m) => selected.includes(m.id));
  const single =
    selected.length === 1 ? messages.find((m) => m.id === selected[0]) : undefined;

  return (
    <div className="overflow-hidden rounded-xl border bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b bg-surface-2 px-3 py-2 sm:gap-3 sm:px-4">
        <Checkbox
          checked={allSelected}
          onCheckedChange={onToggleAll}
          aria-label="Select all messages"
        />
        <span className="text-xs text-muted-foreground">
          {selected.length > 0 ? `${selected.length} selected` : "Select all"}
        </span>
        {selected.length > 0 ? (
          <div className="ml-auto flex flex-wrap items-center gap-1">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="secondary">
                  <Mail className="size-3.5" /> Send email
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem onClick={onCompose}>
                  <PenSquare className="size-3.5" /> Compose new
                </DropdownMenuItem>
                {single ? (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem onClick={() => onReply(single)}>
                      <CornerUpLeft className="size-3.5" /> Reply
                    </DropdownMenuItem>
                    <DropdownMenuItem onClick={() => onForward(single)}>
                      <Forward className="size-3.5" /> Forward
                    </DropdownMenuItem>
                  </>
                ) : null}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button
              size="sm"
              variant="ghost"
              className="text-destructive hover:text-destructive"
              onClick={onBulkDelete}
            >
              <Trash2 className="size-3.5" /> Delete
            </Button>
          </div>
        ) : null}
      </div>
      <ul className="divide-y">
        {messages.map((m) => {
          const acc = accounts.find((a) => a.id === m.accountId);
          return (
            <li
              key={m.id}
              className={cn(
                "group flex cursor-pointer items-start gap-3 px-3 py-3 transition-colors hover:bg-surface-2 sm:px-4",
                m.unread && "bg-accent/40",
                selected.includes(m.id) && "bg-primary/10",
              )}
              onClick={() => onOpen(m)}
            >
              <span onClick={(e) => e.stopPropagation()} className="mt-1">
                <Checkbox
                  checked={selected.includes(m.id)}
                  onCheckedChange={() => onToggleSelect(m.id)}
                  aria-label={`Select ${m.subject}`}
                />
              </span>
              <span
                className="mt-2 size-2.5 shrink-0 rounded-full"
                style={{ backgroundColor: acc?.color ?? "var(--accent-1)" }}
                title={acc?.email}
              />
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline gap-2">
                  <p className={cn("truncate text-sm", m.unread ? "font-semibold" : "font-medium")}>
                    {m.from}
                  </p>
                  <span className="hidden truncate text-xs text-muted-foreground sm:inline">
                    {m.fromEmail}
                  </span>
                  <span className="ml-auto shrink-0 text-xs text-muted-foreground">
                    {formatDistanceToNow(new Date(m.date), { addSuffix: true })}
                  </span>
                </div>
                <p className={cn("truncate text-sm", m.unread && "font-semibold")}>
                  {m.important && (
                    <AlertCircle className="mr-1 inline size-3.5 -translate-y-px text-warning" />
                  )}
                  {m.subject}
                </p>
                <p className="truncate text-xs text-muted-foreground">
                  {m.hasAttachment && <Paperclip className="mr-1 inline size-3" />}
                  {m.preview}
                </p>
                <div
                  className="mt-2 hidden flex-wrap gap-1 group-hover:flex max-sm:flex"
                  onClick={(e) => e.stopPropagation()}
                >
                  <Button size="sm" variant="secondary" onClick={() => onReply(m)}>
                    <CornerUpLeft className="size-3.5" /> Reply
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onForward(m)}>
                    <Forward className="size-3.5" /> Forward
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onStar(m.id)}>
                    <Star className={cn("size-3.5", m.starred && "fill-warning text-warning")} />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onImportant(m.id)}>
                    <AlertCircle className={cn("size-3.5", m.important && "text-warning")} />
                  </Button>
                  <Button size="sm" variant="ghost" onClick={() => onArchive(m.id)}>
                    <Archive className="size-3.5" />
                  </Button>
                  <Button
                    size="sm"
                    variant="ghost"
                    className="text-destructive hover:text-destructive"
                    onClick={() => onDelete(m.id)}
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
