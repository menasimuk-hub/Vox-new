import { Mic } from "lucide-react";

const SPEAK_THRESHOLD = 0.06;

function VoiceWaves({ level, color }: { level: number; color: "navy" | "teal" }) {
  const active = level > SPEAK_THRESHOLD;
  const bars = [0.35, 0.55, 0.85, 0.55, 0.35];
  const barColor = color === "navy" ? "bg-navy" : "bg-teal";
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
      ? "ring-navy/60 shadow-[0_0_16px_rgba(26,45,92,0.25)]"
      : "ring-teal/70 shadow-[0_0_16px_rgba(20,184,166,0.35)]"
    : present
      ? isAi
        ? "ring-navy/25"
        : "ring-teal/25"
      : "ring-border";

  return (
    <div className="flex flex-col items-center gap-2">
      <div className={`relative flex size-16 items-center justify-center rounded-full ring-2 transition-all ${ringClass}`}>
        <div
          className={`flex size-12 items-center justify-center rounded-full text-sm font-semibold ${
            isAi ? "bg-navy/10 text-navy" : "bg-teal/10 text-teal"
          }`}
        >
          {isAi ? (
            <img src="/brand/icon-black.svg" alt="VoxBulk" className="size-7 object-contain" />
          ) : (
            <span>{initials || "?"}</span>
          )}
        </div>
        {!isAi && micOn ? (
          <span className="absolute -bottom-0.5 -right-0.5 flex size-5 items-center justify-center rounded-full bg-teal text-white ring-2 ring-white">
            <Mic className="size-2.5" />
          </span>
        ) : null}
        {isAi && present ? (
          <span className="absolute -top-0.5 -right-0.5 size-2.5 rounded-full bg-navy ring-2 ring-white" />
        ) : null}
      </div>
      <VoiceWaves level={level} color={isAi ? "navy" : "teal"} />
      <div className="text-center">
        <p className="text-[11px] font-semibold text-heading">{label}</p>
        {sublabel ? <p className="text-[10px] text-muted-text">{sublabel}</p> : null}
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
    <div className="flex items-start justify-center gap-6">
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
