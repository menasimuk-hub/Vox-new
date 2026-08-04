import { useEffect, useState } from "react";
import { PenSquare, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { MailAccount } from "@/lib/mail-store";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  accounts: MailAccount[];
  defaultAccountId?: string;
  onSend: (payload: {
    accountId: string;
    to: string;
    subject: string;
    body: string;
  }) => Promise<void>;
}

export function ComposeDialog({
  open,
  onOpenChange,
  accounts,
  defaultAccountId,
  onSend,
}: Props) {
  const active = accounts.filter((a) => !a.frozen);
  const [accountId, setAccountId] = useState("");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [sending, setSending] = useState(false);

  useEffect(() => {
    if (!open) return;
    const preferred =
      (defaultAccountId && active.some((a) => a.id === defaultAccountId) && defaultAccountId) ||
      active[0]?.id ||
      "";
    setAccountId(preferred);
    setTo("");
    setSubject("");
    setBody("");
  }, [open, defaultAccountId, accounts]);

  const signature = active.find((a) => a.id === accountId)?.signature?.trim() || "";

  async function submit() {
    if (!accountId || !to.trim() || !body.trim()) return;
    setSending(true);
    try {
      await onSend({
        accountId,
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
      });
      onOpenChange(false);
    } finally {
      setSending(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <PenSquare className="size-4" /> New message
          </DialogTitle>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1.5">
            <Label>From</Label>
            <Select value={accountId} onValueChange={setAccountId}>
              <SelectTrigger>
                <SelectValue placeholder="Choose mailbox" />
              </SelectTrigger>
              <SelectContent>
                {active.map((a) => (
                  <SelectItem key={a.id} value={a.id}>
                    {a.name || a.email} ({a.email})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="compose-to">To</Label>
            <Input
              id="compose-to"
              type="email"
              value={to}
              onChange={(e) => setTo(e.target.value)}
              placeholder="recipient@example.com"
              autoFocus
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="compose-subject">Subject</Label>
            <Input
              id="compose-subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Subject"
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="compose-body">Message</Label>
            <Textarea
              id="compose-body"
              rows={10}
              value={body}
              onChange={(e) => setBody(e.target.value)}
              placeholder="Write your message…"
            />
          </div>
          {signature ? (
            <p className="whitespace-pre-wrap rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              {signature}
            </p>
          ) : null}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            disabled={sending || !accountId || !to.trim() || !body.trim()}
            onClick={() => void submit()}
          >
            <Send className="size-4" /> {sending ? "Sending…" : "Send"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
