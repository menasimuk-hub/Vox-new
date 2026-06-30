import * as React from "react";
import { Loader2, Play, Volume2 } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { InterviewAgent } from "@/lib/queries";
import { previewInterviewAgentVoice } from "@/lib/queries";

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

function genderLabel(gender?: string) {
  if (gender === "female") return "Female";
  if (gender === "male") return "Male";
  return "";
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

  const playPreview = async (agent: InterviewAgent) => {
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
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Voice preview unavailable");
      setPreviewAgentId(null);
    }
  };

  return (
    <div className="md:col-span-2 space-y-3">
      <Label className="text-xs">Language &amp; AI voice agent</Label>
      <div className="flex flex-wrap items-center gap-2">
        <Select value={interviewLanguage} onValueChange={(v) => onLanguageChange(v as "en" | "ar")}>
          <SelectTrigger className="h-9 w-[150px] shrink-0">
            <SelectValue placeholder="Language" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="en">English</SelectItem>
            <SelectItem value="ar" disabled={allAgents.filter((a) => a.language === "ar").length === 0}>
              Arabic
            </SelectItem>
          </SelectContent>
        </Select>
      </div>

      {agents.length === 0 ? (
        <p className="text-xs text-muted-foreground">No voice agents configured yet. Ask your admin to enable interview agents.</p>
      ) : languageAgents.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No {interviewLanguage === "ar" ? "Arabic" : "English"} interview agents available.
        </p>
      ) : (
        <div className="grid gap-2 sm:grid-cols-2">
          {languageAgents.map((agent) => {
            const selected = resolvedAgentId === agent.id;
            const name = agent.voice_label || agent.name;
            const code = agent.dialect_code || (agent.language === "ar" ? "AR" : "GB");
            const previewBusy = previewAgentId === agent.id;
            return (
              <div
                key={agent.id}
                className={cn(
                  "rounded-xl border p-3 transition-colors",
                  selected ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border bg-card hover:border-primary/30",
                )}
              >
                <div className="flex items-start justify-between gap-2">
                  <button type="button" className="min-w-0 flex-1 text-left" onClick={() => onSelectAgent(agent.id)}>
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-medium text-sm">{name}</span>
                      <Badge variant="outline" className={cn("text-[10px] font-semibold", dialectBadgeClass(code))}>
                        {code}
                      </Badge>
                      {genderLabel(agent.gender) ? (
                        <span className="text-[10px] text-muted-foreground">{genderLabel(agent.gender)}</span>
                      ) : null}
                    </div>
                    <p className="mt-1 text-xs font-medium text-foreground/90">{agent.dialect_label || agent.voice_type_label}</p>
                    <p className="mt-0.5 text-[11px] leading-snug text-muted-foreground">
                      {agent.dialect_description || agent.voice_type_label || "AI phone interviewer"}
                    </p>
                  </button>
                  <Button
                    type="button"
                    size="icon"
                    variant="outline"
                    className="size-8 shrink-0"
                    disabled={previewBusy}
                    title="Play short voice sample (free preview)"
                    onClick={() => void playPreview(agent)}
                  >
                    {previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                  </Button>
                </div>
                {selected ? (
                  <p className="mt-2 flex items-center gap-1 text-[10px] text-primary">
                    <Volume2 className="size-3" /> Selected for this interview
                  </p>
                ) : null}
              </div>
            );
          })}
        </div>
      )}

      {interviewLanguage === "ar" ? (
        <p className="text-[11px] text-muted-foreground">
          <strong>Sultan (SA)</strong> — Saudi Gulf colloquial. <strong>Jammal (EG)</strong> — Egyptian tone. Tap{" "}
          <Play className="inline size-3" /> for a free short sample (no wallet charge).
        </p>
      ) : null}
      {allAgents.filter((a) => a.language === "ar").length === 0 ? (
        <p className="text-[11px] text-muted-foreground">Arabic requires an Arabic interview agent in Admin → Agents.</p>
      ) : null}
    </div>
  );
}
