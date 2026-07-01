import * as React from "react";
import { Loader2, Play } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { InterviewAgent } from "@/lib/queries";
import { pickDefaultInterviewAgent, previewInterviewAgentVoice } from "@/lib/queries";
import {
  agentsForRegion,
  buildRegionMenuOptions,
  interviewAgentDisplayName,
  interviewAgentGenderLabel,
} from "@/lib/interview-agents";
import { regionFlagEmoji } from "@/lib/interview-agent-regions";

type Props = {
  agents: InterviewAgent[];
  selectedRegion: string;
  resolvedAgentId: string;
  onSelectAgent: (id: string) => void;
  onRegionChange: (region: string) => void;
};

function RoundFlag({ emoji, className }: { emoji: string; className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-5 shrink-0 items-center justify-center rounded-full bg-muted/80 text-sm leading-none",
        className,
      )}
      aria-hidden
    >
      {emoji}
    </span>
  );
}

function AgentRow({
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
  const genderTag = interviewAgentGenderLabel(agent);
  const previewAvailable = agent.voice_preview_available !== false;
  const previewHint = agent.voice_preview_hint || "Voice preview unavailable";

  return (
    <div
      className={cn(
        "inline-flex h-9 min-w-[8.5rem] items-center overflow-hidden rounded-md border text-sm",
        selected ? "border-primary bg-primary/5 ring-1 ring-primary/20" : "border-border bg-background",
      )}
    >
      <button
        type="button"
        className="inline-flex h-full w-10 shrink-0 items-center justify-center border-r border-border/80 hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-40"
        disabled={!previewAvailable || previewBusy}
        title={previewAvailable ? `Play ${name} sample` : previewHint}
        aria-label={previewAvailable ? `Play ${name} voice sample` : previewHint}
        onClick={onPreview}
      >
        {previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
      </button>
      <button
        type="button"
        className="inline-flex h-full min-w-0 flex-1 items-center gap-1.5 px-3 hover:bg-muted/50"
        onClick={onSelect}
      >
        <span className="truncate font-medium">{name}</span>
        {genderTag ? (
          <Badge variant="outline" className="h-4 shrink-0 px-1 text-[9px] font-medium leading-none text-muted-foreground">
            {genderTag}
          </Badge>
        ) : null}
      </button>
    </div>
  );
}

export function InterviewAgentPicker({
  agents,
  selectedRegion,
  resolvedAgentId,
  onSelectAgent,
  onRegionChange,
}: Props) {
  const [previewAgentId, setPreviewAgentId] = React.useState<string | null>(null);
  const audioRef = React.useRef<HTMLAudioElement | null>(null);

  const regionOptions = React.useMemo(() => buildRegionMenuOptions(agents), [agents]);
  const activeRegion = regionOptions.some((o) => o.code === selectedRegion)
    ? selectedRegion
    : regionOptions[0]?.code || "GB";
  const regionAgents = agentsForRegion(agents, activeRegion);
  const selectedAgent = regionAgents.find((a) => a.id === resolvedAgentId) || agents.find((a) => a.id === resolvedAgentId);

  const playPreview = async (agent: InterviewAgent, e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (agent.voice_preview_available === false) {
      toast.error(agent.voice_preview_hint || "Voice preview unavailable");
      return;
    }
    if (previewAgentId && previewAgentId !== agent.id) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setPreviewAgentId(null);
    }
    if (previewAgentId === agent.id) return;

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

  const handleRegionChange = (code: string) => {
    onRegionChange(code);
    const pool = agentsForRegion(agents, code);
    const next = pickDefaultInterviewAgent(pool) || pool[0];
    if (next) onSelectAgent(next.id);
  };

  return (
    <div className="md:col-span-2 space-y-2">
      <Label className="text-xs">Language &amp; AI voice agent</Label>
      <p className="text-[10px] text-muted-foreground">Choose the accent your candidates will hear. Tap ▶ to preview.</p>

      {agents.length === 0 ? (
        <p className="text-xs text-muted-foreground">No voice agents configured — ask your admin.</p>
      ) : regionOptions.length === 0 ? (
        <p className="text-xs text-muted-foreground">No voice agents available.</p>
      ) : (
        <>
          <Select value={activeRegion} onValueChange={handleRegionChange}>
            <SelectTrigger className="h-9 w-full max-w-xs">
              <SelectValue placeholder="Select accent">
                <span className="inline-flex items-center gap-2">
                  <RoundFlag emoji={regionFlagEmoji(activeRegion)} />
                  <span>{regionOptions.find((o) => o.code === activeRegion)?.label || activeRegion}</span>
                </span>
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              {regionOptions.map((option) => (
                <SelectItem key={option.code} value={option.code}>
                  <span className="inline-flex items-center gap-2">
                    <RoundFlag emoji={option.flagEmoji} />
                    <span>{option.label}</span>
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {regionAgents.length === 0 ? (
            <p className="text-xs text-muted-foreground">No agents for this accent.</p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {regionAgents.map((agent) => (
                <AgentRow
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
        </>
      )}

      {selectedAgent?.sample_phrase ? (
        <p className="text-[10px] italic text-muted-foreground">&ldquo;{selectedAgent.sample_phrase}&rdquo;</p>
      ) : null}
    </div>
  );
}
