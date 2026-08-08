import * as React from "react";

import {
  detectLogoToneFromSrc,
  getCachedLogoTone,
  logoPlateStyles,
  normalizeLogoTone,
  setCachedLogoTone,
  type LogoTone,
} from "@/lib/logo-contrast";
import { cn } from "@/lib/utils";

type Props = {
  src: string;
  alt?: string;
  preferredTone?: LogoTone | string | null;
  className?: string;
  imgClassName?: string;
  compact?: boolean;
};

/** Contrast plate for org logos (Settings preview, Expo print card, etc.). */
export function AdaptiveLogo({
  src,
  alt = "",
  preferredTone,
  className,
  imgClassName,
  compact = false,
}: Props) {
  const initial = normalizeLogoTone(preferredTone) || getCachedLogoTone(src) || "dark";
  const [tone, setTone] = React.useState<LogoTone>(initial);
  const [analyzing, setAnalyzing] = React.useState(!normalizeLogoTone(preferredTone) && !getCachedLogoTone(src));

  React.useEffect(() => {
    const pref = normalizeLogoTone(preferredTone);
    if (pref) {
      setTone(pref);
      setCachedLogoTone(src, pref);
      setAnalyzing(false);
      return;
    }
    const cached = getCachedLogoTone(src);
    if (cached) {
      setTone(cached);
      setAnalyzing(false);
      return;
    }
    let cancelled = false;
    setAnalyzing(true);
    void (async () => {
      const result = await detectLogoToneFromSrc(src, { crossOrigin: null });
      if (cancelled) return;
      setTone(result.tone);
      setCachedLogoTone(src, result.tone);
      setAnalyzing(false);
    })();
    return () => {
      cancelled = true;
    };
  }, [src, preferredTone]);

  const plate = logoPlateStyles(tone);

  return (
    <div className={cn("relative inline-flex shrink-0", className)}>
      {tone === "light" && plate.glow ? (
        <div
          aria-hidden
          className="pointer-events-none absolute -inset-2 rounded-2xl transition-opacity duration-300"
          style={{ background: plate.glow, filter: "blur(6px)", opacity: analyzing ? 0.5 : 1 }}
        />
      ) : null}
      <div
        className={cn(
          "relative flex items-center justify-center transition-[background,box-shadow,border-color] duration-300",
          compact ? "h-7 max-w-[120px] rounded-lg px-1.5 py-0.5" : "rounded-xl p-1",
        )}
        style={{
          background: plate.background,
          border: plate.border,
          boxShadow: plate.boxShadow,
        }}
        data-logo-tone={tone}
      >
        <img
          src={src}
          alt={alt}
          decoding="async"
          className={cn(
            "object-contain transition-opacity duration-300",
            compact ? "h-[18px] w-auto max-w-[104px]" : "max-h-full max-w-full",
            analyzing ? "opacity-70" : "opacity-100",
            imgClassName,
          )}
        />
        {analyzing ? (
          <span aria-hidden className="pointer-events-none absolute inset-0 animate-pulse rounded-[inherit] bg-white/10" />
        ) : null}
      </div>
    </div>
  );
}
