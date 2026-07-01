import * as React from "react";
import * as SelectPrimitive from "@radix-ui/react-select";
import { Check, Loader2, Play } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectTrigger, SelectValue } from "@/components/ui/select";
import { cn } from "@/lib/utils";
import type { InterviewAgent } from "@/lib/queries";
import { pickDefaultInterviewAgent, previewInterviewAgentVoice } from "@/lib/queries";
import {
  agentsForRegion,
  buildRegionMenuOptions,
  interviewAgentDisplayName,
  interviewAgentGenderLabel,
} from "@/lib/interview-agents";
import { regionFlagImageUrl } from "@/lib/interview-agent-regions";

/** Shared chrome for region dropdown + agent pills (same height, border, focus). */
const PICKER_CONTROL =
  "h-9 shrink-0 rounded-md border border-border bg-background shadow-sm transition-[border-color,background-color,box-shadow] outline-none";
const PICKER_SELECTED = "border-primary bg-primary/5 ring-1 ring-inset ring-primary/30";
const PICKER_INTERACTIVE =
  "focus-visible:outline-none focus-visible:bg-muted/50";

type Props = {
  agents: InterviewAgent[];
  selectedRegion: string;
  resolvedAgentId: string;
  onSelectAgent: (id: string) => void;
  onRegionChange: (region: string) => void;
};

function RoundFlag({ code, className }: { code: string; className?: string }) {
  const normalized = String(code || "GB").trim().toUpperCase();
  return (
    <span
      className={cn(
        "inline-flex size-4 shrink-0 overflow-hidden rounded-full border border-border/50 bg-muted/20",
        className,
      )}
      aria-hidden
    >
      <img
        src={regionFlagImageUrl(normalized)}
        alt=""
        className="size-full object-cover"
        loading="lazy"
        decoding="async"
      />
    </span>
  );
}

function RegionSelectItem({ code, label }: { code: string; label: string }) {
  const normalized = String(code).trim().toUpperCase();
  return (
    <SelectPrimitive.Item
      value={normalized}
      textValue={label}
      className="relative flex w-full cursor-default select-none items-center rounded-sm py-1.5 pl-2 pr-8 text-sm outline-none focus:bg-accent focus:text-accent-foreground data-[disabled]:pointer-events-none data-[disabled]:opacity-50"
    >
      <span className="absolute right-2 flex h-3.5 w-3.5 items-center justify-center">
        <SelectPrimitive.ItemIndicator>
          <Check className="h-4 w-4" />
        </SelectPrimitive.ItemIndicator>
      </span>
      <span className="inline-flex items-center gap-2">
        <RoundFlag code={normalized} />
        <SelectPrimitive.ItemText>{label}</SelectPrimitive.ItemText>
      </span>
    </SelectPrimitive.Item>
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
        PICKER_CONTROL,
        "inline-flex items-center overflow-hidden text-sm",
        selected ? PICKER_SELECTED : "hover:bg-muted/30",
      )}
    >
      <button
        type="button"
        className={cn(
          "inline-flex h-full w-9 shrink-0 items-center justify-center border-r border-border/80 hover:bg-muted/60 disabled:cursor-not-allowed disabled:opacity-40",
          PICKER_INTERACTIVE,
        )}
        disabled={!previewAvailable || previewBusy}
        title={previewAvailable ? `Play ${name} sample` : previewHint}
        aria-label={previewAvailable ? `Play ${name} voice sample` : previewHint}
        onClick={onPreview}
      >
        {previewBusy ? <Loader2 className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
      </button>
      <button
        type="button"
        className={cn(
          "inline-flex h-full items-center gap-1.5 px-2.5 hover:bg-muted/50",
          PICKER_INTERACTIVE,
        )}
        onClick={onSelect}
      >
        <span className="whitespace-nowrap font-medium">{name}</span>
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
  const normalizedSelected = String(selectedRegion || "GB").trim().toUpperCase();
  const activeRegion = regionOptions.some((o) => o.code === normalizedSelected)
    ? normalizedSelected
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
    const normalized = String(code).trim().toUpperCase();
    onRegionChange(normalized);
    const pool = agentsForRegion(agents, normalized);
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
        <div className="flex flex-nowrap items-center gap-3 overflow-x-auto pb-0.5">
          <Select value={activeRegion} onValueChange={handleRegionChange}>
            <SelectTrigger
              className={cn(
                PICKER_CONTROL,
                "w-auto min-w-[8rem] max-w-none gap-1.5 pl-2 pr-2",
                "border-border bg-background ring-0 ring-offset-0",
                "focus:ring-1 focus:ring-inset focus:ring-primary/30 focus:ring-offset-0 focus:border-primary",
                "data-[state=open]:border-primary data-[state=open]:bg-primary/5 data-[state=open]:ring-1 data-[state=open]:ring-inset data-[state=open]:ring-primary/30",
              )}
            >
              <RoundFlag code={activeRegion} />
              <SelectValue placeholder="Select accent" />
            </SelectTrigger>
            <SelectContent>
              {regionOptions.map((option) => (
                <RegionSelectItem key={option.code} code={option.code} label={option.label} />
              ))}
            </SelectContent>
          </Select>

          {regionAgents.length === 0 ? (
            <p className="text-xs text-muted-foreground whitespace-nowrap">No agents for this accent.</p>
          ) : (
            regionAgents.map((agent) => (
              <AgentRow
                key={agent.id}
                agent={agent}
                selected={resolvedAgentId === agent.id}
                previewBusy={previewAgentId === agent.id}
                onSelect={() => onSelectAgent(agent.id)}
                onPreview={(e) => void playPreview(agent, e)}
              />
            ))
          )}
        </div>
      )}

      {selectedAgent?.sample_phrase ? (
        <p className="text-[10px] italic text-muted-foreground">&ldquo;{selectedAgent.sample_phrase}&rdquo;</p>
      ) : null}
    </div>
  );
}
