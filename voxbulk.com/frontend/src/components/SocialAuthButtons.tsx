import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";
import { apiFetch } from "@/lib/api";

/** Always shown in the sign-in UI — matches the marketing design. */
export const MARKETING_SOCIAL_PROVIDERS = ["google", "apple", "linkedin"] as const;

type ProviderId = (typeof MARKETING_SOCIAL_PROVIDERS)[number];

type SocialAuthButtonsProps = {
  onOAuth: (provider: string) => void;
  oauthLoading?: string | null;
  compact?: boolean;
};

export function SocialAuthButtons({ onOAuth, oauthLoading, compact }: SocialAuthButtonsProps) {
  const [readyProviders, setReadyProviders] = useState<Set<string>>(new Set());

  useEffect(() => {
    void apiFetch<Array<{ provider: string; login_supported?: boolean }>>("/auth/social-login/providers")
      .then((rows) => {
        const supported = new Set(
          (Array.isArray(rows) ? rows : [])
            .filter((row) => row.login_supported)
            .map((row) => row.provider),
        );
        setReadyProviders(supported);
      })
      .catch(() => setReadyProviders(new Set()));
  }, []);

  const handleClick = (provider: ProviderId) => {
    if (!readyProviders.has(provider)) {
      toast.error(`${labelFor(provider)} is not configured yet. Enable it in admin → Integrations.`);
      return;
    }
    onOAuth(provider);
  };

  return (
    <div className={`grid ${compact ? "gap-2" : "gap-2.5"}`}>
      {MARKETING_SOCIAL_PROVIDERS.map((provider) => (
        <SocialBtn
          key={provider}
          onClick={() => handleClick(provider)}
          loading={oauthLoading === provider}
          label={labelFor(provider)}
          icon={iconFor(provider)}
          compact={compact}
        />
      ))}
    </div>
  );
}

function labelFor(provider: ProviderId) {
  if (provider === "google") return "Continue with Google";
  if (provider === "apple") return "Continue with Apple";
  return "Continue with LinkedIn";
}

function iconFor(provider: ProviderId) {
  if (provider === "google") return <GoogleIcon />;
  if (provider === "apple") return <AppleIcon />;
  return <LinkedInIcon />;
}

function SocialBtn({
  onClick,
  label,
  icon,
  loading,
  compact,
}: {
  onClick: () => void;
  label: string;
  icon: React.ReactNode;
  loading?: boolean;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={loading}
      className={`flex items-center justify-center gap-2.5 ${compact ? "h-11" : "h-12"} rounded-xl border border-border bg-white hover:bg-secondary/60 text-[13.5px] font-medium text-heading transition-colors disabled:opacity-60`}
    >
      {loading ? <Loader2 size={15} className="animate-spin" /> : icon}
      {label}
    </button>
  );
}

function GoogleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 48 48">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.4 29.2 35.5 24 35.5c-6.4 0-11.5-5.1-11.5-11.5S17.6 12.5 24 12.5c2.9 0 5.6 1.1 7.6 2.9l5.7-5.7C33.6 6.5 29 4.5 24 4.5 13.2 4.5 4.5 13.2 4.5 24S13.2 43.5 24 43.5 43.5 34.8 43.5 24c0-1.2-.1-2.4-.4-3.5z" />
      <path fill="#FF3D00" d="m6.3 14.7 6.6 4.8C14.7 16 19 12.5 24 12.5c2.9 0 5.6 1.1 7.6 2.9l5.7-5.7C33.6 6.5 29 4.5 24 4.5 16.3 4.5 9.7 8.6 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 43.5c5 0 9.5-1.9 12.9-5l-6-4.9c-1.9 1.4-4.3 2.4-6.9 2.4-5.2 0-9.6-3.4-11.2-8L6.4 33C9.7 39.2 16.3 43.5 24 43.5z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-.8 2.2-2.2 4-4 5.3l6 4.9c-.4.4 6.7-4.9 6.7-14.2 0-1.2-.1-2.4-.4-3.5z" />
    </svg>
  );
}

function AppleIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
      <path d="M16.7 12.7c0-2.5 2-3.7 2.1-3.8-1.1-1.7-2.9-1.9-3.5-1.9-1.5-.2-2.9.9-3.7.9-.8 0-2-.9-3.2-.8-1.6 0-3.2 1-4 2.4-1.7 3-.4 7.4 1.2 9.8.8 1.2 1.8 2.5 3.1 2.5 1.2 0 1.7-.8 3.2-.8 1.5 0 1.9.8 3.2.8 1.3 0 2.2-1.2 3-2.4.9-1.4 1.3-2.7 1.4-2.8-.1 0-2.7-1-2.8-3.9zM14.3 5.3c.7-.8 1.1-2 1-3.1-1 0-2.2.7-2.9 1.5-.6.7-1.2 1.9-1 3 1.1.1 2.2-.6 2.9-1.4z" />
    </svg>
  );
}

function LinkedInIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="#0A66C2">
      <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.13 1.45-2.13 2.94v5.67H9.35V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.07 2.07 0 1 1 0-4.14 2.07 2.07 0 0 1 0 4.14zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.72V1.72C24 .77 23.2 0 22.22 0z" />
    </svg>
  );
}
