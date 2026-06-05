import { ChevronRight, MessageSquare, Phone, Sparkles } from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";

type Channel = "whatsapp" | "phone";

type ChannelPickerProps = {
  anonymous: boolean;
  setAnonymous: (value: boolean) => void;
  onPick: (channel: Channel) => void;
};

export function ChannelPicker({ anonymous, setAnonymous, onPick }: ChannelPickerProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Choose a channel</CardTitle>
        <CardDescription>How will patients receive this survey?</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <ChannelCard
            icon={<MessageSquare className="size-6" />}
            title="WhatsApp Survey"
            desc="Chat-style questions delivered to patients' WhatsApp. Highest response rate."
            badge="Fastest replies"
            onClick={() => onPick("whatsapp")}
          />
          <ChannelCard
            icon={<Phone className="size-6" />}
            title="AI phone call Survey"
            desc="Friendly AI voice agent calls each patient and records the answers."
            badge="Best for depth"
            onClick={() => onPick("phone")}
          />
        </div>

        <div className="flex items-start justify-between gap-3 rounded-xl border border-border bg-background/40 p-4">
          <div>
            <p className="text-sm font-medium">Anonymous responses</p>
            <p className="text-xs text-muted-foreground">
              When on, replies are recorded without name or phone number. Useful for honest feedback.
            </p>
          </div>
          <Switch checked={anonymous} onCheckedChange={setAnonymous} />
        </div>
      </CardContent>
    </Card>
  );
}

function ChannelCard({
  icon,
  title,
  desc,
  badge,
  onClick,
}: {
  icon: React.ReactNode;
  title: string;
  desc: string;
  badge: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="group relative overflow-hidden rounded-2xl border border-border bg-gradient-to-br from-background to-accent/10 p-5 text-left transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg"
    >
      <div className="mb-3 inline-flex items-center gap-2 rounded-full bg-primary/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wider text-primary">
        <Sparkles className="size-3" /> {badge}
      </div>
      <div className="mb-3 grid size-12 place-items-center rounded-xl bg-primary/10 text-primary ring-1 ring-primary/20 transition-transform group-hover:scale-110">
        {icon}
      </div>
      <p className="text-base font-semibold">{title}</p>
      <p className="mt-1 text-xs text-muted-foreground">{desc}</p>
      <span className="mt-3 inline-flex items-center gap-1 text-xs font-medium text-primary opacity-0 transition-opacity group-hover:opacity-100">
        Start wizard <ChevronRight className="size-3.5" />
      </span>
    </button>
  );
}
