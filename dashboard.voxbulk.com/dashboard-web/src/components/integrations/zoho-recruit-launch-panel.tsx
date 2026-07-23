import * as React from "react";
import { ExternalLink, Loader2, Rocket } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { apiFetch } from "@/lib/api";

type Candidate = {
  id: string;
  name: string;
  email: string;
  phone: string;
  job_title: string;
};

type ScreeningRow = {
  id: string;
  partner_reference_id: string;
  job_title: string;
  candidate_name: string;
  status: string;
  result_status?: string | null;
  candidate_score?: number | null;
  screening_link: string;
  created_at?: string | null;
};

export function ZohoRecruitLaunchPanel({ onLaunched }: { onLaunched?: () => void }) {
  const [loadingCandidates, setLoadingCandidates] = React.useState(false);
  const [candidates, setCandidates] = React.useState<Candidate[]>([]);
  const [selectedId, setSelectedId] = React.useState("");
  const [name, setName] = React.useState("");
  const [phone, setPhone] = React.useState("");
  const [email, setEmail] = React.useState("");
  const [candidateId, setCandidateId] = React.useState("");
  const [jobTitle, setJobTitle] = React.useState("AI voice screening");
  const [language, setLanguage] = React.useState<"en" | "ar">("en");
  const [question, setQuestion] = React.useState("Tell me about your relevant experience for this role.");
  const [busy, setBusy] = React.useState(false);
  const [lastLink, setLastLink] = React.useState("");
  const [recent, setRecent] = React.useState<ScreeningRow[]>([]);

  const loadRecent = React.useCallback(async () => {
    try {
      const data = await apiFetch<{ items?: ScreeningRow[] }>("/service-orders/zoho-recruit/screenings");
      setRecent(data?.items || []);
    } catch {
      /* ignore */
    }
  }, []);

  const loadCandidates = React.useCallback(async () => {
    setLoadingCandidates(true);
    try {
      const data = await apiFetch<{ items?: Candidate[] }>("/service-orders/zoho-recruit/candidates");
      setCandidates(data?.items || []);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not load Zoho candidates");
    } finally {
      setLoadingCandidates(false);
    }
  }, []);

  React.useEffect(() => {
    void loadCandidates();
    void loadRecent();
  }, [loadCandidates, loadRecent]);

  const applyCandidate = (id: string) => {
    setSelectedId(id);
    const c = candidates.find((row) => row.id === id);
    if (!c) return;
    setCandidateId(c.id);
    setName(c.name || "");
    setPhone(c.phone || "");
    setEmail(c.email || "");
    if (c.job_title) setJobTitle(c.job_title);
  };

  const launch = async () => {
    if (!candidateId.trim()) {
      toast.error("Zoho Candidate ID is required (for score writeback)");
      return;
    }
    if (!phone.trim()) {
      toast.error("Candidate phone is required");
      return;
    }
    setBusy(true);
    setLastLink("");
    try {
      const data = await apiFetch<{
        screening_link?: string;
        status?: string;
        invite_error?: string | null;
      }>("/service-orders/zoho-recruit/screenings", {
        method: "POST",
        body: JSON.stringify({
          partner_reference_id: candidateId.trim(),
          candidate_name: name.trim() || "Candidate",
          candidate_phone: phone.trim(),
          candidate_email: email.trim() || undefined,
          job_title: jobTitle.trim() || "AI voice screening",
          preferred_language: language,
          screening_questions: [question.trim() || "Tell me about your relevant experience for this role."],
        }),
      });
      const link = data?.screening_link || "";
      setLastLink(link);
      toast.success(link ? "Screening created — invite sent" : "Screening created");
      if (data?.invite_error) toast.message(`Invite note: ${data.invite_error}`);
      await loadRecent();
      onLaunched?.();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Could not create screening");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4 rounded-md border bg-muted/20 p-3">
      <div>
        <p className="text-sm font-medium">Launch AI voice screening</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
          Pick a Zoho Candidate (or paste ID + phone). VoxBulk sends the booking invite, runs the call, then writes the
          score back to that Candidate in Zoho.
        </p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <Label className="text-sm">Zoho candidates</Label>
          <Button type="button" variant="ghost" size="sm" disabled={loadingCandidates} onClick={() => void loadCandidates()}>
            {loadingCandidates ? <Loader2 className="size-3.5 animate-spin" /> : "Refresh"}
          </Button>
        </div>
        <select
          className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm shadow-xs"
          value={selectedId}
          onChange={(e) => applyCandidate(e.target.value)}
        >
          <option value="">Select from Zoho…</option>
          {candidates.map((c) => (
            <option key={c.id} value={c.id}>
              {(c.name || "Unnamed") + (c.phone ? ` · ${c.phone}` : "")}
            </option>
          ))}
        </select>
      </div>

      <div className="grid gap-2">
        <div className="space-y-1.5">
          <Label htmlFor="zr-cid" className="text-sm">
            Zoho Candidate ID
          </Label>
          <Input id="zr-cid" value={candidateId} onChange={(e) => setCandidateId(e.target.value)} placeholder="e.g. 123456000000123456" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-name" className="text-sm">
            Name
          </Label>
          <Input id="zr-name" value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-phone" className="text-sm">
            Phone
          </Label>
          <Input id="zr-phone" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="+44…" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-email" className="text-sm">
            Email (optional)
          </Label>
          <Input id="zr-email" value={email} onChange={(e) => setEmail(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-job" className="text-sm">
            Job title
          </Label>
          <Input id="zr-job" value={jobTitle} onChange={(e) => setJobTitle(e.target.value)} />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-lang" className="text-sm">
            Language
          </Label>
          <select
            id="zr-lang"
            className="flex h-9 w-full rounded-md border border-input bg-background px-3 text-sm"
            value={language}
            onChange={(e) => setLanguage(e.target.value === "ar" ? "ar" : "en")}
          >
            <option value="en">English</option>
            <option value="ar">Arabic</option>
          </select>
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="zr-q" className="text-sm">
            Screening question
          </Label>
          <Input id="zr-q" value={question} onChange={(e) => setQuestion(e.target.value)} />
        </div>
      </div>

      <Button type="button" className="w-full gap-1.5" disabled={busy} onClick={() => void launch()}>
        {busy ? <Loader2 className="size-4 animate-spin" /> : <Rocket className="size-4" />}
        Launch screening
      </Button>

      {lastLink ? (
        <a
          href={lastLink}
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center gap-1 break-all text-xs text-primary underline-offset-2 hover:underline"
        >
          <ExternalLink className="size-3.5 shrink-0" />
          {lastLink}
        </a>
      ) : null}

      {recent.length > 0 ? (
        <div className="space-y-2 border-t pt-3">
          <p className="text-xs font-medium text-muted-foreground">Recent screenings</p>
          <ul className="space-y-2">
            {recent.slice(0, 8).map((row) => (
              <li key={row.id} className="rounded border bg-background px-2 py-1.5 text-[11px]">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium text-foreground">{row.candidate_name || row.partner_reference_id}</span>
                  <span className="text-muted-foreground">{row.result_status || row.status}</span>
                </div>
                {row.screening_link ? (
                  <a href={row.screening_link} target="_blank" rel="noreferrer" className="text-primary hover:underline">
                    Open booking link
                  </a>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
