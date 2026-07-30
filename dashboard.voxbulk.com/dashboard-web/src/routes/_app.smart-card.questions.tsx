import { createFileRoute } from "@tanstack/react-router";
import { useQuery } from "@tanstack/react-query";

import { PageHeader } from "@/components/page-header";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { apiFetch } from "@/lib/api";

type Question = {
  question_key: string;
  label: string;
  prompt: string;
  description?: string | null;
  kind?: string;
  sort_order?: number;
};

export const Route = createFileRoute("/_app/smart-card/questions")({
  component: SmartCardQuestionsPage,
});

function SmartCardQuestionsPage() {
  const q = useQuery({
    queryKey: ["smart-card", "questions"],
    queryFn: () => apiFetch<{ ok: boolean; items: Question[] }>("/smart-card/questions"),
  });

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Smart Card QR"
        title="Questions"
        description="Questionnaire prompts used on WhatsApp and web. Admins edit wording in Admin → WA Templates → Smart Card QR."
      />
      <div className="grid gap-3">
        {(q.data?.items || []).map((item) => (
          <Card key={item.question_key}>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">
                {item.label || item.question_key}
                <span className="ml-2 text-xs font-normal text-muted-foreground">{item.question_key}</span>
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm text-muted-foreground">
              <p className="text-foreground">{item.prompt}</p>
              {item.description ? <p className="text-xs">{item.description}</p> : null}
            </CardContent>
          </Card>
        ))}
      </div>
      {!q.isLoading && !(q.data?.items || []).length ? (
        <p className="text-sm text-muted-foreground">No active questions yet — run API seed / deploy.</p>
      ) : null}
    </div>
  );
}
