import { Bot, Mic } from "lucide-react";

const SPEAK_THRESHOLD = 0.06;

function VoiceWaves({ level, color }: { level: number; color: "violet" | "emerald" }) {
  const active = level > SPEAK_THRESHOLD;
  const bars = [0.35, 0.55, 0.85, 0.55, 0.35];
  const barColor = color === "violet" ? "bg-violet-400" : "bg-emerald-400";
  return (
    <div className="flex h-5 items-end justify-center gap-0.5">
      {bars.map((scale, i) => (
        <span
          key={i}
          className={`w-1 rounded-full transition-all duration-75 ${barColor} ${active ? "opacity-100" : "opacity-25"}`}
          style={{ height: active ? `${6 + level * 14 * scale}px` : "4px" }}
        />
      ))}
    </div>
  );
}

type ParticipantProps = {
  label: string;
  sublabel?: string;
  initials?: string;
  level: number;
  variant: "ai" | "user";
  present?: boolean;
  micOn?: boolean;
};

function ParticipantAvatar({ label, sublabel, initials, level, variant, present, micOn }: ParticipantProps) {
  const speaking = level > SPEAK_THRESHOLD;
  const isAi = variant === "ai";
  const ringClass = speaking
    ? isAi
      ? "ring-violet-400/80 shadow-[0_0_20px_rgba(139,92,246,0.45)]"
      : "ring-emerald-400/90 shadow-[0_0_20px_rgba(52,211,153,0.45)]"
    : present
      ? isAi
        ? "ring-violet-500/40"
        : "ring-emerald-500/30"
      : "ring-white/10";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className={`relative flex size-20 items-center justify-center rounded-full ring-2 transition-all ${ringClass}`}>
        <div
          className={`flex size-16 items-center justify-center rounded-full text-lg font-semibold ${
            isAi ? "bg-violet-500/20 text-violet-200" : "bg-emerald-500/15 text-emerald-200"
          }`}
        >
          {isAi ? <Bot className="size-8" /> : <span>{initials || "?"}</span>}
        </div>
        {!isAi && micOn ? (
          <span className="absolute -bottom-0.5 -right-0.5 flex size-6 items-center justify-center rounded-full bg-emerald-600 text-white ring-2 ring-[#0a0e17]">
            <Mic className="size-3" />
          </span>
        ) : null}
        {isAi && present ? (
          <span className="absolute -top-0.5 -right-0.5 size-3 rounded-full bg-violet-400 ring-2 ring-[#0a0e17]" />
        ) : null}
      </div>
      <VoiceWaves level={level} color={isAi ? "violet" : "emerald"} />
      <div className="text-center">
        <p className="text-xs font-medium text-white">{label}</p>
        {sublabel ? <p className="text-[10px] text-slate-400">{sublabel}</p> : null}
      </div>
    </div>
  );
}

export function VoiceCallAvatars({
  aiLabel,
  aiLevel,
  aiPresent,
  userLabel,
  userInitials,
  userLevel,
  micOn,
}: {
  aiLabel: string;
  aiLevel: number;
  aiPresent: boolean;
  userLabel: string;
  userInitials: string;
  userLevel: number;
  micOn: boolean;
}) {
  return (
    <div className="flex items-start justify-center gap-8">
      <ParticipantAvatar
        label={aiLabel}
        sublabel={aiPresent ? (aiLevel > SPEAK_THRESHOLD ? "Speaking" : "Listening") : "Joining…"}
        level={aiLevel}
        variant="ai"
        present={aiPresent}
      />
      <ParticipantAvatar
        label={userLabel}
        sublabel={userLevel > SPEAK_THRESHOLD ? "You're speaking" : micOn ? "Mic on" : "Mic muted"}
        initials={userInitials}
        level={userLevel}
        variant="user"
        micOn={micOn}
      />
    </div>
  );
}
