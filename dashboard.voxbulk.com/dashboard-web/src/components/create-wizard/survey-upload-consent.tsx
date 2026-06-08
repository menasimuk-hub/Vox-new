import { MessageCircle, Phone } from "lucide-react";

import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";

type SurveyUploadConsentProps = {
  channel: "whatsapp" | "phone";
  typeAck: boolean;
  setTypeAck: (v: boolean) => void;
  uploadConsent: boolean;
  setUploadConsent: (v: boolean) => void;
};

export function SurveyUploadConsent({
  channel,
  typeAck,
  setTypeAck,
  uploadConsent,
  setUploadConsent,
}: SurveyUploadConsentProps) {
  const isWa = channel === "whatsapp";

  return (
    <div className="space-y-3">
      <label
        className={cn(
          "flex cursor-pointer items-start gap-3 rounded-xl border p-4 transition",
          typeAck ? "border-primary bg-primary/5" : "border-border bg-background",
        )}
      >
        <Checkbox checked={typeAck} onCheckedChange={(v) => setTypeAck(!!v)} className="mt-0.5" />
        <div className="space-y-2 text-sm">
          <p className="font-medium">Survey type</p>
          <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
            <span className={cn("inline-flex items-center gap-1.5", isWa && "font-medium text-foreground")}>
              <MessageCircle className="size-3.5" /> WA survey
            </span>
            <span className={cn("inline-flex items-center gap-1.5", !isWa && "font-medium text-foreground")}>
              <Phone className="size-3.5" /> Calling survey
            </span>
          </div>
          <p className="text-xs text-muted-foreground">
            {isWa
              ? "You are uploading contacts for a WhatsApp survey campaign."
              : "You are uploading contacts for an AI calling survey campaign."}
          </p>
        </div>
      </label>

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
    </div>
  );
}

export const SURVEY_LAUNCH_CONSENT_TEXT =
  "I confirm all contacts in this list have consented to be contacted for survey purposes, and I accept full responsibility as data controller.";
