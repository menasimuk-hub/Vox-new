import { useEffect, useState } from "react";
import { useSearchParams, useNavigate } from "@tanstack/react-router";
import { z } from "zod";
import { toast } from "sonner";
import { Lock, ArrowRight, Loader2, AlertCircle } from "lucide-react";
import { BrandLogo } from "@/components/BrandLogo";

export function ResetPassword() {
  const [searchParams] = useSearchParams({ from: "/" });
  const navigate = useNavigate();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [tokenValid, setTokenValid] = useState<boolean | null>(null);

  const token = (searchParams as Record<string, string>).token || "";

  useEffect(() => {
    if (!token) {
      setTokenValid(false);
      return;
    }
    // Token validity will be checked on submit
    setTokenValid(true);
  }, [token]);

  const handleReset = async (e: React.FormEvent) => {
    e.preventDefault();

    const passwordSchema = z.string().min(6, "Password must be at least 6 characters").max(128);
    const pwd = passwordSchema.safeParse(password);
    if (!pwd.success) {
      toast.error(pwd.error.issues[0].message);
      return;
    }

    if (password !== confirmPassword) {
      toast.error("Passwords don't match");
      return;
    }

    setLoading(true);
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL}/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token, password }),
      });

      if (!res.ok) {
        const error = await res.json().catch(() => ({}));
        throw new Error(error.detail || "Failed to reset password");
      }

      toast.success("Password reset successfully!");
      setTimeout(() => navigate({ to: "/signin" }), 1500);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  if (tokenValid === false) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-primary/5 via-background to-accent/5 flex items-center justify-center p-4">
        <div className="w-full max-w-[460px] bg-white rounded-3xl shadow-elevated border border-border p-8 text-center">
          <div className="mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-full bg-destructive/10">
            <AlertCircle className="h-8 w-8 text-destructive" />
          </div>
          <h1 className="text-2xl font-bold text-heading">Invalid reset link</h1>
          <p className="mt-2 text-muted-text">
            This password reset link is invalid or has expired.
          </p>
          <button
            onClick={() => navigate({ to: "/signin" })}
            className="mt-6 btn-primary w-full"
          >
            Back to sign in
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-primary/5 via-background to-accent/5 flex items-center justify-center p-4">
      <div className="w-full max-w-[460px] bg-white rounded-3xl shadow-elevated border border-border overflow-hidden">
        {/* Decorative top */}
        <div className="relative h-24 bg-gradient-to-br from-primary/10 via-primary/5 to-accent/10 border-b border-border overflow-hidden">
          <div className="absolute inset-0 bg-grid opacity-50" />
          <div className="absolute inset-0 flex items-center justify-center">
            <BrandLogo surface="light" className="h-7 w-auto object-contain" />
          </div>
        </div>

        <div className="p-7">
          <h2 className="text-[24px] font-bold tracking-[-0.02em] text-heading text-center">
            Reset your password
          </h2>
          <p className="mt-1 text-[13.5px] text-body text-center">
            Enter a new password for your account.
          </p>

          <form onSubmit={handleReset} className="space-y-3 mt-6">
            <div className="relative">
              <label htmlFor="password" className="sr-only">New password</label>
              <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
              <input
                id="password"
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="New password"
                minLength={6}
                className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            <div className="relative">
              <label htmlFor="confirm-password" className="sr-only">Confirm password</label>
              <Lock size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-text" />
              <input
                id="confirm-password"
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm password"
                minLength={6}
                className="w-full pl-10 pr-3 py-3 rounded-xl border border-border bg-secondary/40 text-[14.5px] focus:outline-none focus:ring-2 focus:ring-primary/30 focus:border-primary"
              />
            </div>

            <button type="submit" disabled={loading} className="btn-primary w-full !py-3 mt-4">
              {loading ? <Loader2 size={16} className="animate-spin" /> : <>Reset password <ArrowRight size={15} /></>}
            </button>
          </form>

          <p className="mt-4 text-center text-[13px] text-muted-text">
            Remember your password?{" "}
            <button
              onClick={() => navigate({ to: "/signin" })}
              className="text-primary font-semibold hover:underline"
            >
              Sign in
            </button>
          </p>
        </div>
      </div>
    </div>
  );
}

export default ResetPassword;
