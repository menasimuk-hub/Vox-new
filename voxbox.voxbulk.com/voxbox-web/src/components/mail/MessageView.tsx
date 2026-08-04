import { useEffect, useMemo, useRef, useState } from "react";
import { format } from "date-fns";
import {
  ArrowLeft,
  Forward,
  ImagePlus,
  Link2,
  Loader2,
  Send,
  Sparkles,
  Star,
  Trash2,
  Archive,
  Wand2,
  X,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { generateAiReply } from "@/lib/ai-reply.functions";
import type { MailAccount, MailAttachment, MailMessage } from "@/lib/mail-store";
import { cn } from "@/lib/utils";

interface Props {
  message: MailMessage;
  account?: MailAccount | undefined;
  mode: "read" | "reply" | "forward";
  /** True while full HTML body is still downloading */
  loadingBody?: boolean;
  onBack: () => void;
  onSend: (body: string, kind: "reply" | "forward", attachments: MailAttachment[]) => void;
  onDelete: (id: string) => void;
  onArchive: (id: string) => void;
  onStar: (id: string) => void;
}

export function MessageView({
  message,
  account,
  mode,
  loadingBody = false,
  onBack,
  onSend,
  onDelete,
  onArchive,
  onStar,
}: Props) {
  const [composing, setComposing] = useState(mode !== "read");
  const [kind, setKind] = useState<"reply" | "forward">(mode === "forward" ? "forward" : "reply");
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [attachments, setAttachments] = useState<MailAttachment[]>([]);
  const [linkOpen, setLinkOpen] = useState(false);
  const [linkLabel, setLinkLabel] = useState("");
  const [linkUrl, setLinkUrl] = useState("");
  const [viewTab, setViewTab] = useState<"text" | "html">("text");
  const fileRef = useRef<HTMLInputElement>(null);
  const signature = account?.signature?.trim() ?? "";

  const plainText = useMemo(() => {
    const t = (message.text || "").trim();
    if (t) return t;
    return (message.preview || "").trim();
  }, [message.text, message.preview]);

  const hasHtml = Boolean((message.html || "").trim());

  useEffect(() => {
    // Gmail-like: show text immediately; flip to HTML once the rich body arrives.
    if (hasHtml && !loadingBody) setViewTab("html");
    else setViewTab("text");
  }, [message.id, hasHtml, loadingBody]);

  async function writeWithAi() {
    setLoading(true);
    try {
      const res = await generateAiReply({
        subject: message.subject,
        from: `${message.from} <${message.fromEmail}>`,
        body: message.text,
        tone: "professional",
        mode: "write",
        draft: "",
      });
      if (res.error || !res.reply) toast.error(res.error || "AI could not write a reply.");
      else {
        setBody(res.reply);
        toast.success("AI draft ready — edit it before sending.");
      }
    } catch {
      toast.error("AI request failed.");
    } finally {
      setLoading(false);
    }
  }

  async function fixWithAi() {
    if (!body.trim()) {
      toast.error("Write something first, then let AI polish it.");
      return;
    }
    setFixing(true);
    try {
      const res = await generateAiReply({
        subject: message.subject,
        from: `${message.from} <${message.fromEmail}>`,
        body: message.text,
        tone: "professional",
        mode: "fix",
        draft: body,
      });
      if (res.error || !res.reply) toast.error(res.error || "AI could not rewrite your text.");
      else {
        setBody(res.reply);
        toast.success("Rewritten by AI.");
      }
    } catch {
      toast.error("AI request failed.");
    } finally {
      setFixing(false);
    }
  }

  function addImages(files: FileList | null) {
    if (!files) return;
    Array.from(files).forEach((file) => {
      if (!file.type.startsWith("image/")) {
        toast.error(`${file.name} is not an image.`);
        return;
      }
      if (file.size > 4_000_000) {
        toast.error(`${file.name} is larger than 4 MB.`);
        return;
      }
      const reader = new FileReader();
      reader.onload = () =>
        setAttachments((prev) => [
          ...prev,
          {
            id: `${Date.now()}-${file.name}`,
            kind: "image",
            name: file.name,
            url: String(reader.result),
          },
        ]);
      reader.readAsDataURL(file);
    });
  }

  function insertLink() {
    const url = linkUrl.trim();
    if (!url) return;
    const label = linkLabel.trim() || url;
    setBody((b) => `${b}${b && !b.endsWith("\n") ? "\n" : ""}${label}: ${url}\n`);
    setAttachments((prev) => [
      ...prev,
      { id: `${Date.now()}-link`, kind: "link", name: label, url },
    ]);
    setLinkLabel("");
    setLinkUrl("");
    setLinkOpen(false);
    toast.success("Link added.");
  }

  function send() {
    const withSig = signature ? `${body.trimEnd()}\n\n${signature}` : body;
    onSend(withSig, kind, attachments);
    setBody("");
    setAttachments([]);
    setComposing(false);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="ghost" size="sm" onClick={onBack}>
          <ArrowLeft className="size-4" /> Back
        </Button>
        <div className="ml-auto flex gap-1">
          <Button variant="ghost" size="sm" onClick={() => onStar(message.id)}>
            <Star className={cn("size-4", message.starred && "fill-warning text-warning")} />
          </Button>
          <Button variant="ghost" size="sm" onClick={() => onArchive(message.id)}>
            <Archive className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            className="text-destructive hover:text-destructive"
            onClick={() => onDelete(message.id)}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </div>

      <article className="rounded-xl border bg-card p-4 sm:p-6">
        <h1 className="font-display text-xl font-semibold sm:text-2xl">{message.subject}</h1>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{message.from}</span>
          <span>&lt;{message.fromEmail}&gt;</span>
          <span>→ {account?.email ?? message.to}</span>
          <span className="ml-auto">{format(new Date(message.date), "PPp")}</span>
        </div>

        <Tabs
          value={viewTab}
          onValueChange={(v) => setViewTab(v as "text" | "html")}
          className="mt-5"
        >
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <TabsList>
              <TabsTrigger value="text">Plain text</TabsTrigger>
              <TabsTrigger value="html" disabled={!hasHtml && loadingBody}>
                HTML
              </TabsTrigger>
            </TabsList>
            {loadingBody && !hasHtml ? (
              <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
                <Loader2 className="size-3.5 animate-spin" /> Loading formatted view…
              </span>
            ) : null}
          </div>
          <TabsContent value="text">
            <pre className="whitespace-pre-wrap font-sans text-sm leading-relaxed">
              {plainText || (loadingBody ? "Loading…" : "No message body.")}
            </pre>
          </TabsContent>
          <TabsContent value="html">
            {hasHtml ? (
              <div
                className="mail-html text-sm leading-relaxed"
                dangerouslySetInnerHTML={{ __html: message.html }}
              />
            ) : (
              <p className="text-sm text-muted-foreground">
                {loadingBody ? "Loading HTML…" : "No HTML version for this message."}
              </p>
            )}
          </TabsContent>
        </Tabs>

        {message.attachments && message.attachments.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2 border-t pt-3">
            {message.attachments.map((a) =>
              a.kind === "image" ? (
                <img
                  key={a.id}
                  src={a.url}
                  alt={a.name}
                  className="size-20 rounded-lg border object-cover"
                />
              ) : (
                <a
                  key={a.id}
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 rounded-lg border px-2 py-1 text-xs text-primary"
                >
                  <Link2 className="size-3" /> {a.name}
                </a>
              ),
            )}
          </div>
        )}
      </article>

      {!composing ? (
        <div className="flex gap-2">
          <Button
            onClick={() => {
              setKind("reply");
              setComposing(true);
            }}
          >
            <Send className="size-4" /> Reply
          </Button>
          <Button
            variant="secondary"
            onClick={() => {
              setKind("forward");
              setComposing(true);
            }}
          >
            <Forward className="size-4" /> Forward
          </Button>
        </div>
      ) : (
        <div className="space-y-3 rounded-xl border bg-card p-4">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-display text-sm font-semibold">
              {kind === "reply" ? `Reply to ${message.from}` : "Forward message"}
            </p>
            <div className="ml-auto flex flex-wrap gap-1">
              <Button size="sm" variant="secondary" disabled={loading} onClick={writeWithAi}>
                <Sparkles className={cn("size-4", loading && "animate-pulse")} />
                {loading ? "Writing…" : "Reply with AI"}
              </Button>
              <Button size="sm" variant="outline" disabled={fixing} onClick={fixWithAi}>
                <Wand2 className={cn("size-4", fixing && "animate-pulse")} />
                {fixing ? "Fixing…" : "Fix with AI"}
              </Button>
            </div>
          </div>

          <Textarea
            rows={9}
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="Write your message, or let AI draft it and edit here…"
          />

          {signature && (
            <p className="whitespace-pre-wrap rounded-lg bg-surface-2 px-3 py-2 text-xs text-muted-foreground">
              {signature}
            </p>
          )}

          {attachments.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {attachments.map((a) => (
                <span
                  key={a.id}
                  className="group relative inline-flex items-center gap-1 rounded-lg border bg-surface-2 px-2 py-1 text-xs"
                >
                  {a.kind === "image" ? (
                    <img src={a.url} alt={a.name} className="size-6 rounded object-cover" />
                  ) : (
                    <Link2 className="size-3.5" />
                  )}
                  <span className="max-w-[10rem] truncate">{a.name}</span>
                  <button
                    aria-label={`Remove ${a.name}`}
                    onClick={() => setAttachments((p) => p.filter((x) => x.id !== a.id))}
                  >
                    <X className="size-3.5 text-muted-foreground hover:text-destructive" />
                  </button>
                </span>
              ))}
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            <Button disabled={!body.trim()} onClick={send}>
              <Send className="size-4" /> Send
            </Button>
            <Button variant="secondary" size="sm" onClick={() => fileRef.current?.click()}>
              <ImagePlus className="size-4" /> Image
            </Button>
            <Button variant="secondary" size="sm" onClick={() => setLinkOpen(true)}>
              <Link2 className="size-4" /> Link
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              hidden
              onChange={(e) => {
                addImages(e.target.files);
                e.target.value = "";
              }}
            />
            <Button variant="ghost" onClick={() => setComposing(false)}>
              Cancel
            </Button>
          </div>
        </div>
      )}

      <Dialog open={linkOpen} onOpenChange={setLinkOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Insert hyperlink</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="link-label">Text</Label>
              <Input
                id="link-label"
                value={linkLabel}
                onChange={(e) => setLinkLabel(e.target.value)}
                placeholder="Booking details"
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="link-url">URL</Label>
              <Input
                id="link-url"
                value={linkUrl}
                onChange={(e) => setLinkUrl(e.target.value)}
                placeholder="https://example.com/page"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setLinkOpen(false)}>
              Cancel
            </Button>
            <Button onClick={insertLink}>Insert link</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
