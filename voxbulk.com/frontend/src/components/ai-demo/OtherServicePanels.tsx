type SurveysData = {
  segments?: Array<{
    id: string;
    name: string;
    response_rate: number;
    avg_minutes: number;
    sentiment?: { pos: number; neu: number; neg: number };
  }>;
  voice_note?: { label: string; transcript_en: string; original_lang?: string };
};

export function SurveysDemoPanel({ data, highlightTarget }: { data: SurveysData | null; highlightTarget?: string | null }) {
  const pulse = (id: string) => (highlightTarget === id ? "ring-2 ring-primary ring-offset-2 animate-pulse" : "");
  return (
    <div className="space-y-4" data-demo-section="surveys">
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("segments")}`} data-demo-target="segments">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-3">Audience segments</div>
        <div className="grid gap-2">
          {(data?.segments || []).map((s) => (
            <div key={s.id} data-demo-target={`${s.id}-segment`} className={`rounded-xl border border-border p-3 ${pulse(`${s.id}-segment`)}`}>
              <div className="font-semibold text-heading">{s.name}</div>
              <div className="text-[13px] text-body mt-1">
                {(s.response_rate * 100).toFixed(0)}% response · ~{s.avg_minutes} min
              </div>
            </div>
          ))}
        </div>
      </div>
      {data?.voice_note && (
        <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("voice-note")}`} data-demo-target="voice-note">
          <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-2">{data.voice_note.label}</div>
          <p className="text-[14px] text-heading italic">“{data.voice_note.transcript_en}”</p>
        </div>
      )}
    </div>
  );
}

type RecruitData = {
  role?: string;
  candidates?: Array<{ id: string; name: string; ats: number; skills: number; comms: number; fit: number; status: string }>;
  calling_now?: { id: string; name: string; label: string };
};

export function RecruitmentDemoPanel({ data, highlightTarget }: { data: RecruitData | null; highlightTarget?: string | null }) {
  const pulse = (id: string) => (highlightTarget === id ? "ring-2 ring-primary ring-offset-2 animate-pulse" : "");
  return (
    <div className="space-y-4" data-demo-section="recruitment">
      {data?.calling_now && (
        <div className={`rounded-2xl border border-emerald-300 bg-emerald-50 p-4 ${pulse("calling-now")}`} data-demo-target="calling-now">
          <div className="text-[11px] font-bold uppercase text-emerald-800">Calling now</div>
          <div className="font-semibold text-heading mt-1">{data.calling_now.name}</div>
          <div className="text-[13px] text-body">{data.calling_now.label}</div>
        </div>
      )}
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("candidates")}`} data-demo-target="candidates">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-3">
          {data?.role || "Role"} candidates
        </div>
        <div className="space-y-2 max-h-64 overflow-auto">
          {(data?.candidates || []).map((c) => (
            <div key={c.id} className="rounded-xl border border-border px-3 py-2 flex justify-between gap-2 text-[13px]">
              <div>
                <div className="font-semibold text-heading">{c.name}</div>
                <div className="text-muted-text">ATS {c.ats} · skills {c.skills} · comms {c.comms} · fit {c.fit}</div>
              </div>
              <span className="text-[11px] font-semibold text-primary">{c.status}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

type ExpoData = {
  show?: string;
  days?: Array<{ day: string; leads: number }>;
  totals?: { hot: number; warm: number; cold: number };
  sample_leads?: Array<{ id: string; name: string; company: string; score: string; day: string }>;
};

export function ExpoDemoPanel({
  data,
  highlightTarget,
  liveRows,
}: {
  data: ExpoData | null;
  highlightTarget?: string | null;
  liveRows: Array<{ name?: string; company?: string; score?: string }>;
}) {
  const pulse = (id: string) => (highlightTarget === id ? "ring-2 ring-primary ring-offset-2 animate-pulse" : "");
  return (
    <div className="space-y-4" data-demo-section="expo">
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("expo-trend")}`} data-demo-target="expo-trend">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-2">{data?.show || "Show"}</div>
        <div className="grid grid-cols-3 gap-2">
          {(data?.days || []).map((d) => (
            <div key={d.day} className="rounded-xl border border-border p-3 text-center">
              <div className="text-[12px] text-muted-text">{d.day}</div>
              <div className="text-[20px] font-bold text-heading">{d.leads}</div>
            </div>
          ))}
        </div>
        {data?.totals && (
          <div className="mt-3 flex gap-3 text-[13px]" data-demo-target="expo-scores">
            <span>Hot {data.totals.hot}</span>
            <span>Warm {data.totals.warm}</span>
            <span>Cold {data.totals.cold}</span>
          </div>
        )}
      </div>
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("expo-leads")}`} data-demo-target="expo-leads">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-2">Leads</div>
        <ul className="space-y-2 text-[13px]">
          {liveRows.map((r, i) => (
            <li key={`live-${i}`} className="rounded-xl border border-emerald-400 bg-emerald-50 px-3 py-2">
              <strong>{r.name || "You"}</strong> · {r.company || "Demo"} · Hot
            </li>
          ))}
          {(data?.sample_leads || []).map((l) => (
            <li key={l.id} className="rounded-xl border border-border px-3 py-2">
              <strong>{l.name}</strong> · {l.company} · {l.score} · {l.day}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

type SmartData = {
  reps?: Array<{ id: string; name: string; leads: number; hot: number; warm: number; cold: number }>;
};

export function SmartCardDemoPanel({
  data,
  highlightTarget,
  view,
}: {
  data: SmartData | null;
  highlightTarget?: string | null;
  view: "rep" | "manager";
}) {
  const pulse = (id: string) => (highlightTarget === id ? "ring-2 ring-primary ring-offset-2 animate-pulse" : "");
  const reps = data?.reps || [];
  const shown = view === "manager" ? reps : reps.slice(0, 1);
  return (
    <div className="space-y-4" data-demo-section="smart_card">
      <div className={`rounded-2xl border border-border bg-white p-4 ${pulse("smart-view")}`} data-demo-target="smart-view">
        <div className="text-[11px] font-semibold uppercase tracking-wider text-muted-text mb-2">
          {view === "manager" ? "Manager view — all reps" : "Rep view — your leads only"}
        </div>
        <div className="space-y-2">
          {shown.map((r) => (
            <div key={r.id} className="rounded-xl border border-border px-3 py-2 text-[13px]">
              <div className="font-semibold text-heading">{r.name}</div>
              <div className="text-body">
                {r.leads} leads · Hot {r.hot} · Warm {r.warm} · Cold {r.cold}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
