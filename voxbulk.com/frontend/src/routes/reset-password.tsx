import { createFileRoute, Link, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { z } from "zod";
import { SiteFooter, SiteHeader } from "@/components/SiteShell";
import { toast } from "sonner";
import { Loader2, Lock, ArrowRight } from "lucide-react";
import logo from "@/assets/logo-rekovo.svg";
import { resetPasswordRequest } from "@/lib/retoverApi";

export const Route = createFileRoute("/reset-password")({
  head: () => ({
    meta: [
      { title: "Reset password — VOXBULK.COM" },
      { name: "description", content: "Set a new password for your VOXBULK.COM account." },
    ],
  }),
  component: ResetPasswordPage,
});

const schema = z
  .object({
    password: z.string().min(6, "Password must be at least 6 characters").max(128),
    confirm: z.string().min(6, "Password must be at least 6 characters").max(128),
  })
  .refine((d) => d.password === d.confirm, {
    message: "Passwords do not match",
    path: ["confirm"],
  });

const errorMessage = (error: unknown, fallback: string) =>
  error instanceof Error ? error.message : fallback;

function ResetPasswordPage() {
  const navigate = useNavigate();
  const token = useMemo(() => {
    if (typeof window === "undefined") return "";
    return new URLSearchParams(window.location.search).get("token") || "";
  }, []);

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  useEffect(() => {
    if (!token.trim()) {
      toast.error("Missing reset token. Open the link from your email.");
    }
  }, [token]);

  const onSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const parsed = schema.safeParse({ password, confirm });
    if (!parsed.success) {
      toast.error(parsed.error.issues[0]?.message || "Invalid input");
      return;
    }
    if (!token.trim()) {
      toast.error("Missing reset token.");
      return;
    }
    setLoading(true);
    try {
      const res = await resetPasswordRequest({ token, password });
      setDone(true);
      toast.success(String(res?.message || "Password updated."));
    } catch (err: unknown) {
      toast.error(errorMessage(err, "Could not reset password."));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-background text-body antialiased min-h-screen flex flex-col">
      <SiteHeader />
      <main className="flex-1 pt-[110px] md:pt-[130px] pb-24">
        <div className="max-w-[480px] mx-auto px-5 md:px-10">
          <div className="text-center">
            <img src={logo} alt="VOXBULK.COM" className="h-10 mx-auto" />
            <h1 className="mt-5 text-[30px] md:text-[36px] font-bold tracking-[-0.03em] text-heading leading-[1.1]">
              Set a new password
            </h1>
            <p className="mt-2 text-body text-[15px]">
              Choose a password you have not used here before.
            </p>
          </div>

          <div className="mt-8 bg-white border border-border rounded-2xl p-6 md:p-7 shadow-elegant">
            {!token.trim() ? (
              <div className="rounded-xl border border-border bg-secondary/50 p-4 text-[14px] text-body text-center">
                This page needs a valid link from your reset email.{" "}
                <Link to="/signin" className="text-primary font-semibold underline">
                  Back to sign in
                </Link>
              </div>
            ) : done ? (
              <div className="space-y-4 text-center">
                <p className="text-[15px] text-body">You can sign in with your new password.</p>
                <button
                  type="button"
                  className="btn-primary w-full !py-3"
                  onClick={() => navigate({ to: "/signin" })}
                >
                  Go to sign in <ArrowRight size={15} />
                </button>
              </div>
            ) : (
              <form onSubmit={onSubmit} className="space-y-3">
                <label className="block">
                  <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                    New password
                  </span>
                  <div className="mt-1.5 relative">
                    <Lock
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                    />
                    <input
                      type="password"
                      required
                      minLength={6}
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    />
                  </div>
                </label>
                <label className="block">
                  <span className="text-[12.5px] font-semibold uppercase tracking-wider text-muted-text">
                    Confirm password
                  </span>
                  <div className="mt-1.5 relative">
                    <Lock
                      size={16}
                      className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text"
                    />
                    <input
                      type="password"
                      required
                      minLength={6}
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      placeholder="••••••••"
                      className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/30 text-[15px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
                    />
                  </div>
                </label>
                <button type="submit" disabled={loading} className="btn-primary w-full !py-3 mt-2">
                  {loading ? (
                    <Loader2 size={16} className="animate-spin" />
                  ) : (
                    <>
                      Update password <ArrowRight size={15} />
                    </>
                  )}
                </button>
                <p className="text-center text-[13px] text-muted-text">
                  <Link to="/signin" className="text-primary font-semibold hover:underline">
                    Cancel and return to sign in
                  </Link>
                </p>
              </form>
            )}
          </div>
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}
