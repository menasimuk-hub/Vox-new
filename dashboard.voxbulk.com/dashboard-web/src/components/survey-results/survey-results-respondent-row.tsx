import { PanelRightOpen } from "lucide-react";

import { AiFollowUpStatusIcon, type AiFollowUpReport } from "@/components/ai-follow-up-report";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type WaAnswer = {
  question?: string;
  answer?: string;
  answer_text?: string;
};
type ExtractedAnswer = { question?: string; answer?: string };

export type SurveyResultRespondent = {
  id?: string;
  name?: string;
  phone?: string | null;
  sentiment_label?: string | null;
  status_label?: string;
  completed_at?: string | null;
  needs_follow_up?: boolean;
  is_unhappy?: boolean;
  wa_answers?: WaAnswer[];
  extracted_answers?: ExtractedAnswer[];
  ai_follow_up?: AiFollowUpReport | null;
  ai_follow_up_status?: string | null;
};

function toneForAnswer(label: string): string {
  const lower = label.toLowerCase();
  const num = parseInt(label, 10);
  if (lower === "yes" || lower.includes("excellent") || num >= 9) return "bg-success";
  if (lower === "no" || lower.includes("poor") || (Number.isFinite(num) && num <= 6)) return "bg-destructive";
  if (lower.includes("good") || num === 7 || num === 8) return "bg-info";
  return "bg-warning";
}

function quickViewDots(respondent: SurveyResultRespondent) {
  const answers = [...(respondent.wa_answers || []), ...(respondent.extracted_answers || [])].slice(0, 5);
  if (!answers.length) {
    return Array.from({ length: 5 }).map((_, i) => (
      <span key={i} className="size-2 rounded-full bg-muted" />
    ));
  }
  return answers.map((row, i) => {
    const label = String(row.answer_text || row.answer || "").trim() || "—";
    return <span key={i} className={cn("size-2 rounded-full", toneForAnswer(label))} title={label} />;
  });
}

function sentimentTone(label: string | null | undefined) {
  const lower = String(label || "").toLowerCase();
  if (lower.includes("negative") || lower.includes("unhappy") || lower.includes("poor")) return "destructive" as const;
  if (lower.includes("positive") || lower.includes("happy") || lower.includes("excellent")) return "default" as const;
  return "outline" as const;
}

export function SurveyResultsRespondentRow({
  respondent,
  completedLabel,
  onOpen,
}: {
  respondent: SurveyResultRespondent;
  completedLabel?: string;
  onOpen: () => void;
}) {
  const name = respondent.name || "Respondent";
  const phone = respondent.phone || "—";
  const sentiment = respondent.sentiment_label || (respondent.is_unhappy ? "Unhappy" : "Neutral");
  const completed =
    completedLabel ||
    (respondent.completed_at
      ? new Date(respondent.completed_at).toLocaleString("en-GB", { dateStyle: "short", timeStyle: "short" })
      : "—");

  return (
    <tr className="border-b border-border/60 hover:bg-muted/30">
      <td className="px-4 py-3 pr-3">
        <span className="font-medium">{name}</span>
      </td>
      <td className="px-4 py-3 pr-3 text-muted-foreground">{phone}</td>
      <td className="px-4 py-3 pr-3">
        <Badge variant={sentimentTone(sentiment)}>{sentiment}</Badge>
      </td>
      <td className="px-4 py-3 pr-3 text-xs text-muted-foreground whitespace-nowrap">{completed}</td>
      <td className="px-4 py-3 pr-3">
        <div className="flex items-center gap-1">{quickViewDots(respondent)}</div>
      </td>
      <td className="px-4 py-3 text-right">
        <div className="inline-flex items-center gap-1">
          <AiFollowUpStatusIcon status={respondent.ai_follow_up_status || respondent.ai_follow_up?.status} />
          <Button variant="ghost" size="icon" className="size-8" onClick={onOpen} aria-label="More details" title="More details">
            <PanelRightOpen className="size-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
}
