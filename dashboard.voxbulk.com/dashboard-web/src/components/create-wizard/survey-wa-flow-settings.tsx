import * as React from "react";
import { Check, Wand2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";

const STEP_ROLE_LABELS: Record<string, string> = {
  start: "Start",
  completion: "Completion",
  rating: "Rating",
  yes_no: "Yes / No",
  helpfulness: "Helpfulness",
  abc_choice: "A / B / C choice",
  reason: "Reason",
  feeling_word: "Feeling word",
  follow_up: "Follow-up",
  improvement: "Improvement",
};

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1.5">
      <span className="text-sm font-medium">{label}</span>
      {children}
    </label>
  );
}

export type SurveyWaFlowSettingsProps = {
  goal: string;
  setGoal: (v: string) => void;
  privacyMode: "off" | "on";
  setPrivacyMode: (v: "off" | "on") => void;
  pageCount: 3 | 4 | 5 | 6;
  typeCount: number;
  autoSelectSteps: boolean;
  setAutoSelectSteps: (v: boolean) => void;
  resolvedPageRoles: string[];
  pageOrderValid: boolean;
  stepBankByRole: Record<string, { title?: string; body?: string; display_name?: string }>;
  stepBankLoading: boolean;
  approved: boolean;
  generating: boolean;
  canGenerate: boolean;
  onGenerateWaSurvey: () => Promise<boolean>;
};

export function SurveyWaFlowSettings({
  goal,
  setGoal,
  privacyMode,
  setPrivacyMode,
  pageCount,
  typeCount,
  autoSelectSteps,
  setAutoSelectSteps,
  resolvedPageRoles,
  pageOrderValid,
  stepBankByRole,
  stepBankLoading,
  approved,
  generating,
  canGenerate,
  onGenerateWaSurvey,
}: SurveyWaFlowSettingsProps) {
  return (
    <div className="space-y-4 rounded-xl border border-border bg-muted/20 p-4">
      <div>
        <p className="text-sm font-semibold">Survey flow & settings</p>
        <p className="text-xs text-muted-foreground">
          Set your goal and privacy mode, review the WhatsApp page flow, then generate the survey from your template
          selections above.
        </p>
      </div>

      <Field label="Survey goal">
        <Textarea rows={3} value={goal} onChange={(e) => setGoal(e.target.value)} />
      </Field>

      <div className="grid gap-4 md:grid-cols-2">
        <Field label="Privacy mode">
          <Select value={privacyMode} onValueChange={(v) => setPrivacyMode(v as "off" | "on")}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="off">Off — identified / normal templates</SelectItem>
              <SelectItem value="on">On — anonymous templates only</SelectItem>
            </SelectContent>
          </Select>
        </Field>
        <Field label="Survey length">
          <div className="rounded-lg border border-border bg-background/40 px-3 py-2.5 text-sm">
            <p className="font-medium">{pageCount} WhatsApp pages</p>
            <p className="mt-0.5 text-xs text-muted-foreground">
              Welcome + {typeCount} question{typeCount === 1 ? "" : "s"} + thank-you
            </p>
          </div>
        </Field>
      </div>

      <div className="space-y-3 rounded-lg border border-border bg-background/40 p-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium">Message flow</p>
            <p className="text-xs text-muted-foreground">Start and completion are always included.</p>
          </div>
          <div className="flex items-center gap-2">
            <Label htmlFor="auto-steps" className="text-xs text-muted-foreground">
              Auto-select best steps
            </Label>
            <Switch id="auto-steps" checked={autoSelectSteps} onCheckedChange={setAutoSelectSteps} />
          </div>
        </div>
        {stepBankLoading ? (
          <Skeleton className="h-16 w-full" />
        ) : (
          <ol className="space-y-1.5">
            {resolvedPageRoles.map((role, idx) => (
              <li key={`preview-${role}-${idx}`} className="rounded-md border border-dashed border-border px-3 py-2 text-sm">
                <span className="text-muted-foreground">{idx + 1}. </span>
                <span className="font-medium">{STEP_ROLE_LABELS[role] || role}</span>
                {stepBankByRole[role]?.title ? (
                  <span className="ml-2 text-xs text-muted-foreground">— {String(stepBankByRole[role].title)}</span>
                ) : null}
              </li>
            ))}
          </ol>
        )}
        {!pageOrderValid ? (
          <p className="text-xs text-destructive">
            Need exactly {pageCount} pages with unique middle steps between start and completion.
          </p>
        ) : null}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          className="gap-1.5"
          type="button"
          onClick={() => void onGenerateWaSurvey()}
          disabled={generating || !canGenerate || !pageOrderValid}
        >
          <Wand2 className="size-4" /> {generating ? "Generating…" : "Generate survey"}
        </Button>
        {approved ? (
          <span className="inline-flex items-center gap-1 text-xs text-success">
            <Check className="size-3.5" /> Generated & ready for preview
          </span>
        ) : (
          <span className="text-xs text-muted-foreground">Or click Next — we generate before contacts.</span>
        )}
      </div>
    </div>
  );
}
