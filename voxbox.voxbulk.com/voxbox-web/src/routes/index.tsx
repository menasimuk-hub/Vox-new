import { useEffect, useState } from "react";
import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { Moon, Sun, LogIn } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ApiError, getToken, login } from "@/lib/api";
import { SESSION_KEY } from "@/lib/mail-store";
import { useTheme } from "@/lib/use-theme";

export const Route = createFileRoute("/")({
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { theme, toggle } = useTheme();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (window.localStorage.getItem(SESSION_KEY) && getToken()) {
      navigate({ to: "/mail" });
    }
  }, [navigate]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await login(username.trim(), password);
      window.localStorage.setItem(SESSION_KEY, "1");
      navigate({ to: "/mail" });
    } catch (err) {
      const msg = err instanceof ApiError ? err.message : "Wrong username or password.";
      toast.error(msg);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="flex min-h-screen flex-col bg-background">
      <header className="flex items-center gap-2 p-4">
        <img
          src={theme === "dark" ? "/brand/logo-white.png" : "/brand/logo-black.png"}
          alt="VoxBulk"
          className="h-7 w-auto"
        />
        <Button variant="ghost" size="sm" className="ml-auto" onClick={toggle}>
          {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
        </Button>
      </header>

      <div className="flex flex-1 items-center justify-center px-4 pb-16">
        <div className="w-full max-w-sm">
          <h1 className="font-display text-3xl font-semibold">Welcome back</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            All your mailboxes in one place — no more logging in and out.
          </p>

          <form onSubmit={submit} className="mt-8 space-y-4 rounded-xl border bg-card p-5">
            <div className="space-y-1.5">
              <Label htmlFor="u">Username</Label>
              <Input
                id="u"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Username"
                required
              />
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="p">Password</Label>
              <Input
                id="p"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••"
                required
              />
            </div>
            <Button type="submit" className="w-full" disabled={submitting}>
              <LogIn className="size-4" /> {submitting ? "Signing in…" : "Sign in"}
            </Button>
            <p className="text-center text-xs text-muted-foreground">
              Use credentials from server <span className="font-medium">.env</span>
            </p>
          </form>
        </div>
      </div>
    </main>
  );
}
