import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { type ComponentType, useEffect, useState } from "react";
import { SiteHeader, SiteFooter } from "@/components/SiteShell";
import { toast } from "sonner";
import {
  Stethoscope,
  Eye,
  Flower2,
  Heart,
  MoreHorizontal,
  Check,
  Loader2,
  ArrowRight,
} from "lucide-react";
import { getUserAccessToken, retoverFetch } from "@/lib/retoverApi";

export const Route = createFileRoute("/onboarding")({
  head: () => ({ meta: [{ title: "Choose your industry — VOXBULK.COM" }] }),
  component: Onboarding,
});

type Industry = "dental" | "opticians" | "beauty" | "wellness" | "other";

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

const industries: Array<{
  id: Industry;
  label: string;
  desc: string;
  Icon: ComponentType<{ className?: string; size?: number }>;
  tint: string;
}> = [
  {
    id: "dental",
    label: "Dental",
    desc: "Clinics, orthodontics, hygiene",
    Icon: Stethoscope,
    tint: "from-primary/15 to-primary/0",
  },
  {
    id: "opticians",
    label: "Opticians",
    desc: "Optometry & eyewear",
    Icon: Eye,
    tint: "from-blue-500/15 to-blue-500/0",
  },
  {
    id: "beauty",
    label: "Beauty",
    desc: "Salons & aesthetics",
    Icon: Flower2,
    tint: "from-purple-500/15 to-purple-500/0",
  },
  {
    id: "wellness",
    label: "Wellness",
    desc: "Physio, massage, osteo",
    Icon: Heart,
    tint: "from-emerald-500/15 to-emerald-500/0",
  },
  {
    id: "other",
    label: "Something else",
    desc: "Tell us about your business",
    Icon: MoreHorizontal,
    tint: "from-amber-500/15 to-amber-500/0",
  },
];

function Onboarding() {
  const navigate = useNavigate();
  const [picked, setPicked] = useState<Industry | null>(null);
  const [saving, setSaving] = useState(false);
  const [userEmail, setUserEmail] = useState<string>("");

  useEffect(() => {
    const token = getUserAccessToken();
    if (!token) {
      navigate({ to: "/signin" });
      return;
    }
    // best-effort: show email if present from localStorage session
    setUserEmail(localStorage.getItem("retover_user_email") || "");
  }, [navigate]);

  const save = async () => {
    if (!picked) return;
    setSaving(true);
    try {
      await retoverFetch("/auth/me/role", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role: picked }),
      });

      toast.success("All set! Welcome to VOXBULK.COM");
      navigate({ to: "/" });
    } catch (e: unknown) {
      toast.error(errorMessage(e, "Could not save your selection"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[820px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <span className="eyebrow">Welcome{userEmail && `, ${userEmail.split("@")[0]}`}</span>
            <h1 className="mt-3 text-[34px] md:text-[44px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              What kind of business do you{" "}
              <span className="italic font-serif font-normal text-primary">run</span>?
            </h1>
            <p className="mt-3 text-body text-[15.5px] max-w-[520px] mx-auto">
              We'll tailor your dashboard, scripts, and integrations to your industry.
            </p>
          </div>

          <div className="mt-10 grid sm:grid-cols-2 gap-4">
            {industries.map((it) => {
              const active = picked === it.id;
              return (
                <button
                  key={it.id}
                  onClick={() => setPicked(it.id)}
                  className={`relative text-left bg-white border rounded-2xl p-5 transition-all ${
                    active
                      ? "border-primary shadow-glow -translate-y-0.5"
                      : "border-border hover:border-primary/40 hover:-translate-y-0.5"
                  }`}
                >
                  <div
                    className={`absolute inset-0 rounded-2xl bg-gradient-to-br ${it.tint} pointer-events-none opacity-0 ${active ? "opacity-100" : ""} transition-opacity`}
                  />
                  <div className="relative flex items-start gap-4">
                    <div
                      className={`w-12 h-12 rounded-xl flex items-center justify-center transition-colors ${active ? "bg-primary text-white" : "bg-secondary text-heading"}`}
                    >
                      <it.Icon size={22} />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <h3 className="text-[17px] font-bold text-heading">{it.label}</h3>
                        {active && <Check size={16} className="text-primary" strokeWidth={3} />}
                      </div>
                      <p className="mt-1 text-[13.5px] text-body">{it.desc}</p>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>

          <div className="mt-8 flex items-center justify-center">
            <button
              disabled={!picked || saving}
              onClick={save}
              className="btn-primary !px-8 !py-3.5 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {saving ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <>
                  Continue <ArrowRight size={16} />
                </>
              )}
            </button>
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
