import { MessageCircle, Phone } from "lucide-react";

import { cn } from "@/lib/utils";

export type SurveyChannelKind = "whatsapp" | "ai_call" | null;

type SurveyIdentityHeaderProps = {
  surveyName: string;
  surveyId?: string | null;
  channel?: SurveyChannelKind;
  compact?: boolean;
  className?: string;
};

function channelIcon(channel: SurveyChannelKind) {
  if (channel === "whatsapp") return <MessageCircle className="size-4 shrink-0 text-primary" aria-hidden />;
  if (channel === "ai_call") return <Phone className="size-4 shrink-0 text-primary" aria-hidden />;
  return null;
}

export function SurveyIdentityHeader({
  surveyName,
  surveyId,
  channel = null,
  compact = false,
  className,
}: SurveyIdentityHeaderProps) {
  const name = surveyName.trim() || "Survey";
  const id = String(surveyId || "").trim();

  if (compact) {
    return (
      <div className={cn("flex min-w-0 flex-col gap-0.5", className)}>
        <div className="flex min-w-0 items-center gap-2">
          {channelIcon(channel)}
          <span className="truncate font-medium">{name}</span>
        </div>
        {id ? (
          <span className="font-mono text-[11px] text-muted-foreground">ID {id}</span>
        ) : null}
      </div>
    );
  }

  return (
    <div className={cn("space-y-1", className)}>
      <div className="flex items-center gap-2">
        {channelIcon(channel)}
        <p className="text-sm font-semibold leading-tight">{name}</p>
      </div>
      {id ? (
        <p className="font-mono text-xs text-muted-foreground">
          Survey ID: <span className="text-foreground">{id}</span>
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">Survey ID will appear after you save this draft.</p>
      )}
    </div>
  );
}
