import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

type SurveyUploadConsentProps = {
  uploadConsent: boolean;
  setUploadConsent: (v: boolean) => void;
};

export function SurveyUploadConsent({ uploadConsent, setUploadConsent }: SurveyUploadConsentProps) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
        uploadConsent ? "border-primary bg-primary/5" : "border-warning/50 bg-warning/5",
      )}
    >
      <Checkbox checked={uploadConsent} onCheckedChange={(v) => setUploadConsent(!!v)} className="mt-0.5" />
      <div>
        <p className="text-sm font-medium">
          By uploading, you confirm all contacts have consented to be contacted for survey purposes.
        </p>
      </div>
    </label>
  );
}

export const SURVEY_LAUNCH_CONSENT_TEXT =
  "I confirm all contacts in this list have consented to be contacted for survey purposes, and I accept full responsibility as data controller.";
