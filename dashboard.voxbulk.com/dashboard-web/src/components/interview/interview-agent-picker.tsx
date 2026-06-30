import * as React from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { InterviewAgent } from "@/lib/queries";
import { previewInterviewAgentVoice } from "@/lib/queries";
import { interviewAgentDisplayName, resolveInterviewAgentDialect } from "@/lib/interview-agents";

type Props = {
  agents: InterviewAgent[];
  languageAgents: InterviewAgent[];
  allAgents: InterviewAgent[];
  interviewLanguage: "en" | "ar";
  resolvedAgentId: string;
  onSelectAgent: (id: string) => void;
  onLanguageChange: (lang: "en" | "ar") => void;
};

function dialectBadgeClass(code?: string) {
  if (code === "SA") return "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300";
  if (code === "EG") return "border-amber-500/40 bg-amber-500/10 text-amber-800 dark:text-amber-300";
  if (code === "GB") return "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300";
  return "border-border bg-muted/40 text-muted-foreground";
}

export function InterviewAgentPicker({
  agents,
  languageAgents,
  allAgents,
  interviewLanguage,
  resolvedAgentId,
  onSelectAgent,
  onLanguageChange,
}: Props) {
  const [previewAgentId, setPreviewAgentId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const playPreview = async (agent: InterviewAgent, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (previewAgentId) return;
    setPreviewAgentId(agent.id);
    try {
      const data = await previewInterviewAgentVoice(agent.id);
      const src = `data:${data.content_type};base64,${data.audio_base64}`;
      if (audioRef.current) {
        audioRef.current.pause();
      }
      const audio = new Audio(src);
      audioRef.current = audio;
      audio.onended = () => setPreviewAgentId(null);
      audio.onerror = () => {
        setPreviewAgentId(null);
        toast.error("Could not play voice sample");
      };
      await audio.play();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Voice preview unavailable");
      setPreviewAgentId(null);
    }
  };

  return (
    <div className="md:col-span-2 space-y-1.5">
      <Label className="text-xs">Language &amp; AI voice agent</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={interviewLanguage} onValueChange={(v) => onLanguageChange(v as "en" | "ar")}>
          <SelectTrigger className="h-8 w-[130px] shrink-0">
            <SelectValue placeholder="Language" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="en">English</SelectItem>
            <SelectItem value="ar" disabled={allAgents.filter((a) => a.language === "ar").length === 0}>
              Arabic
            </SelectItem>
          </SelectContent>
        </Select>

        {agents.length === 0 ? (
          <p className="text-xs text-muted-foreground">No voice agents configured — ask your admin.</p>
        ) : languageAgents.length === 0 ? (
          <p className="text-xs text-muted-foreground">
            No {interviewLanguage === "ar" ? "Arabic" : "English"} agents available.
          </p>
        ) : (
          languageAgents.map((agent) => {
            const selected = resolvedAgentId === agent.id;
            const name = interviewAgentDisplayName(agent);
            const dialect = resolveInterviewAgentDialect(agent);
            const previewBusy = previewAgentId === agent.id;
            return (
              <div
                key={agent.id}
                className={cn(
                  "inline-flex h-8 items-center overflow-hidden rounded-md border text-sm",
                  selected ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border bg-background",
                )}
              >
                <button
                  type="button"
                  className="inline-flex h-full items-center gap-1 px-2.5 hover:bg-muted/50"
                  onClick={() => onSelectAgent(agent.id)}
                >
                  <span className="font-medium">{name}</span>
                  <Badge variant="outline" className={cn("h-4 px-1 text-[9px] font-semibold leading-none", dialectBadgeClass(dialect.dialect_code))}>
                    {dialect.dialect_code}
                  </Badge>
                </button>
                <button
                  type="button"
                  className="inline-flex h-full w-7 shrink-0 items-center justify-center border-l border-border/80 hover:bg-muted/60 disabled:opacity-50"
                  disabled={previewBusy}
                  title={`Play ${name} sample`}
                  aria-label={`Play ${name} voice sample`}
                  onClick={(e) => void playPreview(agent, e)}
                >
                  {previewBusy ? <Loader2 className="size-3 animate-spin" /> : <Play className="size-3" />}
                </button>
              </div>
            );
          })
        )}
      </div>
      {interviewLanguage === "ar" ? (
        <p className="text-[10px] text-muted-foreground">
          Sultan (SA) Gulf · Jammal (EG) Egyptian — tap ▶ for a free sample.
        </p>
      ) : null}
      {allAgents.filter((a) => a.language === "ar").length === 0 ? (
        <p className="text-[10px] text-muted-foreground">Arabic needs an Arabic agent in Admin → Agents.</p>
      ) : null}
    </div>
  );
}
