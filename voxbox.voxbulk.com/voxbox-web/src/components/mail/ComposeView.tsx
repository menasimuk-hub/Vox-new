import { useEffect, useRef, useState } from "react";
import {
  ArrowLeft,
  Code2,
  FileText,
  ImagePlus,
  Paperclip,
  Send,
  Type,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { generateAiReply } from "@/lib/ai-reply.functions";
import type { MailAccount } from "@/lib/mail-store";
import { cn } from "@/lib/utils";

export type ComposeAttachment = {
  id: string;
  name: string;
  contentType: string;
  dataBase64: string;
  size: number;
};

export type ComposeSendPayload = {
  accountId: string;
  to: string;
  subject: string;
  body: string;
  bodyHtml?: string;
  format: "text" | "html";
  attachments: ComposeAttachment[];
};

interface Props {
  accounts: MailAccount[];
  defaultAccountId?: string;
  onBack: () => void;
  onSend: (payload: ComposeSendPayload) => Promise<void>;
}

function textToHtml(text: string): string {
  const esc = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
  return `<div style="font-family:Segoe UI,Arial,sans-serif;font-size:14px;line-height:1.5;color:#1a1a1a">${esc.replace(/\n/g, "<br/>")}</div>`;
}

export function ComposeView({ accounts, defaultAccountId, onBack, onSend }: Props) {
  const active = accounts.filter((a) => !a.frozen);
  const [accountId, setAccountId] = useState("");
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [format, setFormat] = useState<"text" | "html">("text");
  const [attachments, setAttachments] = useState<ComposeAttachment[]>([]);
  const [sending, setSending] = useState(false);
  const [polishing, setPolishing] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const preferred =
      (defaultAccountId && active.some((a) => a.id === defaultAccountId) && defaultAccountId) ||
      active[0]?.id ||
      "";
    setAccountId(preferred);
  }, [defaultAccountId, accounts]);

  const fromAccount = active.find((a) => a.id === accountId);
  const signature = fromAccount?.signature?.trim() || "";

  async function polishWithAi() {
    if (!body.trim()) {
      toast.error("Write a draft first, then polish with AI.");
      return;
    }
    setPolishing(true);
    try {
      const res = await generateAiReply({
        subject: subject || "(new message)",
        from: fromAccount ? `${fromAccount.name} <${fromAccount.email}>` : "",
        body: "",
        tone: "professional",
        mode: "fix",
        draft: body,
      });
      if (res.error || !res.reply) toast.error(res.error || "AI could not polish the draft.");
      else {
        setBody(res.reply);
        toast.success("Draft polished — review before sending.");
      }
    } catch {
      toast.error("AI request failed.");
    } finally {
      setPolishing(false);
    }
  }

  function addFiles(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach((file) => {
      if (file.size > 5_000_000) {
        toast.error(`${file.name} is larger than 5 MB.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = String(reader.result || "");
        setAttachments((prev) => [
          ...prev,
          {
            id: `${Date.now()}-${file.name}`,
            name: file.name,
            contentType: file.type || "application/octet-stream",
            dataBase64: dataUrl,
            size: file.size,
          },
        ]);
      };
      reader.readAsDataURL(file);
    });
  }

  async function submit() {
    if (!accountId || !to.trim() || !body.trim()) return;
    setSending(true);
    try {
      const payload: ComposeSendPayload = {
        accountId,
        to: to.trim(),
        subject: subject.trim(),
        body: body.trim(),
        format,
        attachments,
      };
      if (format === "html") {
        payload.bodyHtml = body.trim().includes("<") ? body.trim() : textToHtml(body.trim());
      }
      await onSend(payload);
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" /> Back
        </Button>
        <h1 className="font-display text-xl font-semibold">New message</h1>
        <div className="ml-auto flex flex-wrap gap-1">
          <Button
            size="sm"
            variant="secondary"
            disabled={polishing || !body.trim()}
            onClick={() => void polishWithAi()}
          >
            <Wand2 className={cn("size-4", polishing && "animate-pulse")} />
            {polishing ? "Polishing…" : "AI polish"}
          </Button>
          <Button
            size="sm"
            disabled={sending || !accountId || !to.trim() || !body.trim()}
            onClick={() => void submit()}
          >
            <Send className="size-4" /> {sending ? "Sending…" : "Send"}
          </Button>
        </div>
      </div>

      <div className="space-y-4 rounded-xl border bg-card p-4 sm:p-6">
        <div className="space-y-1.5">
          <Label>From</Label>
          <Select value={accountId} onValueChange={setAccountId}>
            <SelectTrigger className="h-11">
              <SelectValue placeholder="Choose mailbox to send from" />
            </SelectTrigger>
            <SelectContent>
              {active.map((a) => (
                <SelectItem key={a.id} value={a.id}>
                  <span className="flex items-center gap-2">
                    <span
                      className="size-2.5 rounded-full"
                      style={{ backgroundColor: a.color }}
                    />
                    {a.name || a.email} — {a.email}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Pick which mailbox sends this email. Recipients see that address as From.
          </p>
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
            className="h-11"
          />
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="compose-subject">Subject</Label>
          <Input
            id="compose-subject"
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject"
            className="h-11"
          />
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <Label>Message</Label>
          <Tabs value={format} onValueChange={(v) => setFormat(v as "text" | "html")}>
            <TabsList>
              <TabsTrigger value="text" className="gap-1.5">
                <Type className="size-3.5" /> Plain text
              </TabsTrigger>
              <TabsTrigger value="html" className="gap-1.5">
                <Code2 className="size-3.5" /> HTML
              </TabsTrigger>
            </TabsList>
          </Tabs>
        </div>

        <Textarea
          rows={14}
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={
            format === "html"
              ? "Write HTML or plain text (plain text is wrapped as professional HTML on send)…"
              : "Write your message…"
          }
          className="min-h-[280px] font-sans text-sm leading-relaxed"
        />

        {format === "html" ? (
          <div className="rounded-lg border bg-muted/40 p-3">
            <p className="mb-2 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
              <FileText className="size-3.5" /> HTML preview
            </p>
            <div
              className="mail-html prose prose-sm max-w-none text-sm"
              dangerouslySetInnerHTML={{
                __html: body.trim().includes("<") ? body : textToHtml(body),
              }}
            />
          </div>
        ) : null}

        {signature ? (
          <p className="whitespace-pre-wrap rounded-lg bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
            Signature will be added on send:{"\n"}
            {signature}
          </p>
        ) : null}

        {attachments.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {attachments.map((a) => (
              <span
                key={a.id}
                className="inline-flex items-center gap-1.5 rounded-lg border bg-muted/50 px-2 py-1 text-xs"
              >
                <Paperclip className="size-3.5" />
                <span className="max-w-[12rem] truncate">{a.name}</span>
                <span className="text-muted-foreground">
                  ({Math.max(1, Math.round(a.size / 1024))} KB)
                </span>
                <button
                  type="button"
                  aria-label={`Remove ${a.name}`}
                  onClick={() => setAttachments((p) => p.filter((x) => x.id !== a.id))}
                >
                  <X className="size-3.5 text-muted-foreground hover:text-destructive" />
                </button>
              </span>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 border-t pt-4">
          <Button type="button" variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
            <Paperclip className="size-4" /> Attach file
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            onClick={() => {
              const input = fileRef.current;
              if (input) {
                input.accept = "image/*";
                input.click();
                window.setTimeout(() => {
                  if (input) input.accept = "*/*";
                }, 0);
              }
            }}
          >
            <ImagePlus className="size-4" /> Image
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
          <Button
            className="ml-auto"
            disabled={sending || !accountId || !to.trim() || !body.trim()}
            onClick={() => void submit()}
          >
            <Send className="size-4" /> {sending ? "Sending…" : "Send email"}
          </Button>
        </div>
      </div>
    </div>
  );
}
