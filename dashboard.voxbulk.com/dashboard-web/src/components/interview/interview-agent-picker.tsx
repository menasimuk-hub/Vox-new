import * as React from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { InterviewAgent } from "@/lib/queries";
import { previewInterviewAgentVoice } from "@/lib/queries";
import {
  groupEnglishInterviewAgents,
  interviewAgentDisplayName,
  interviewAgentGenderLabel,
  resolveInterviewAgentDialect,
} from "@/lib/interview-agents";

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
  if (code === "US") return "border-red-500/35 bg-red-500/10 text-red-800 dark:text-red-300";
  if (code === "CA") return "border-rose-500/35 bg-rose-500/10 text-rose-800 dark:text-rose-300";
  if (code === "AU") return "border-orange-500/35 bg-orange-500/10 text-orange-900 dark:text-orange-300";
  if (code === "IE") return "border-green-600/35 bg-green-600/10 text-green-800 dark:text-green-300";
  if (code === "SC") return "border-sky-600/35 bg-sky-600/10 text-sky-900 dark:text-sky-300";
  if (code === "GB") return "border-blue-500/40 bg-blue-500/10 text-blue-700 dark:text-blue-300";
  return "border-border bg-muted/40 text-muted-foreground";
}

function AgentPill({
  agent,
  selected,
  previewBusy,
  onSelect,
  onPreview,
}: {
  agent: InterviewAgent;
  selected: boolean;
  previewBusy: boolean;
  onSelect: () => void;
  onPreview: (e: React.MouseEvent) => void;
}) {
  const name = interviewAgentDisplayName(agent);
  const dialect = resolveInterviewAgentDialect(agent);
  const genderTag = interviewAgentGenderLabel(agent);
  const flag = agent.flag_emoji || dialect.flag_emoji;

  return (
    <div
      className={cn(
        "inline-flex h-9 min-w-[7.5rem] items-center overflow-hidden rounded-md border text-sm",
        selected ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border bg-background",
      )}
    >
      <button
        type="button"
        className="inline-flex h-full min-w-0 flex-1 items-center gap-1.5 px-3 hover:bg-muted/50"
        onClick={onSelect}
      >
        {flag ? <span className="text-base leading-none" aria-hidden>{flag}</span> : null}
        <span className="truncate font-medium">{name}</span>
        {genderTag ? (
          <Badge variant="outline" className="h-4 shrink-0 px-1 text-[9px] font-medium leading-none text-muted-foreground">
            {genderTag}
          </Badge>
        ) : null}
        <Badge variant="outline" className={cn("h-4 shrink-0 px-1 text-[9px] font-semibold leading-none", dialectBadgeClass(dialect.dialect_code))}>
          {dialect.dialect_code}
        </Badge>
      </button>
      <button
        type="button"
        className="inline-flex h-full w-[3.15rem] shrink-0 items-center justify-center border-l border-border/80 hover:bg-muted/60 disabled:opacity-50"
        disabled={previewBusy}
        title={`Play ${name} sample`}
        aria-label={`Play ${name} voice sample`}
        onClick={onPreview}
      >
        {previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
      </button>
    </div>
  );
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

  const selectedAgent = languageAgents.find((a) => a.id === resolvedAgentId) || allAgents.find((a) => a.id === resolvedAgentId);

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

  const englishGroups = interviewLanguage === "en" ? groupEnglishInterviewAgents(languageAgents) : [];

  return (
    <div className="md:col-span-2 space-y-2">
      <Label className="text-xs">Language &amp; AI voice agent</Label>
      <p className="text-[10px] text-muted-foreground">Choose the accent your candidates will hear. Tap ▶ to preview.</p>

      <div className="flex flex-wrap items-center gap-2">
        <Select value={interviewLanguage} onValueChange={(v) => onLanguageChange(v as "en" | "ar")}>
          <SelectTrigger className="h-9 w-[130px] shrink-0">
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
        <p className="text-xs text-muted-foreground">No voice agents configured — ask your admin.</p>
      ) : languageAgents.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          No {interviewLanguage === "ar" ? "Arabic" : "English"} agents available.
        </p>
      ) : interviewLanguage === "en" && englishGroups.length > 0 ? (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {englishGroups.map((group) => (
            <div key={group.region} className="space-y-1.5">
              <div className="text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">{group.label}</div>
              <div className="flex flex-wrap gap-2">
                {group.agents.map((agent) => (
                  <AgentPill
                    key={agent.id}
                    agent={agent}
                    selected={resolvedAgentId === agent.id}
                    previewBusy={previewAgentId === agent.id}
                    onSelect={() => onSelectAgent(agent.id)}
                    onPreview={(e) => void playPreview(agent, e)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="flex flex-wrap gap-2">
          {languageAgents.map((agent) => (
            <AgentPill
              key={agent.id}
              agent={agent}
              selected={resolvedAgentId === agent.id}
              previewBusy={previewAgentId === agent.id}
              onSelect={() => onSelectAgent(agent.id)}
              onPreview={(e) => void playPreview(agent, e)}
            />
          ))}
        </div>
      )}

      {selectedAgent?.sample_phrase ? (
        <p className="text-[10px] italic text-muted-foreground">&ldquo;{selectedAgent.sample_phrase}&rdquo;</p>
      ) : null}

      {interviewLanguage === "ar" ? (
        <p className="text-[10px] text-muted-foreground">
          Sultan (SA) Gulf · Jammal (EG) Egyptian — tap ▶ for a sample.
        </p>
      ) : null}
      {allAgents.filter((a) => a.language === "ar").length === 0 ? (
        <p className="text-[10px] text-muted-foreground">Arabic needs an Arabic agent in Admin → Agents.</p>
      ) : null}
    </div>
  );
}
