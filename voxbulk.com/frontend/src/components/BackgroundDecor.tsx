/**
 * Subtle ambient illustrations: floating soft shapes + dotted pattern.
 * Always 5-10% opacity. Place inside a `relative` parent with `overflow-hidden`.
 */
export function AmbientBackdrop({ variant = "default" }: { variant?: "default" | "warm" | "cool" }) {
  const c1 = variant === "warm" ? "var(--accent)" : "var(--primary)";
  const c2 = variant === "warm" ? "var(--primary)" : "var(--accent)";
  return (
    <div aria-hidden className="absolute inset-0 pointer-events-none overflow-hidden">
      {/* dotted pattern */}
      <div
        className="absolute inset-0 opacity-[0.06]"
        style={{
          backgroundImage:
            "radial-gradient(currentColor 1px, transparent 1px)",
          backgroundSize: "22px 22px",
          color: "var(--heading)",
          maskImage:
            "radial-gradient(ellipse 70% 60% at 50% 40%, #000 35%, transparent 85%)",
          WebkitMaskImage:
            "radial-gradient(ellipse 70% 60% at 50% 40%, #000 35%, transparent 85%)",
        }}
      />
      {/* soft blobs */}
      <div
        className="absolute -top-24 -left-24 w-[420px] h-[420px] rounded-full blur-3xl opacity-[0.10] float-a"
        style={{ background: `radial-gradient(circle at 30% 30%, ${c1}, transparent 70%)` }}
      />
      <div
        className="absolute -bottom-32 -right-20 w-[480px] h-[480px] rounded-full blur-3xl opacity-[0.08] float-b"
        style={{ background: `radial-gradient(circle at 70% 70%, ${c2}, transparent 70%)` }}
      />
      {/* hairline rings */}
      <svg
        className="absolute -right-32 top-10 w-[520px] h-[520px] opacity-[0.06] spin-slow"
        viewBox="0 0 200 200" fill="none"
      >
        <circle cx="100" cy="100" r="80" stroke="var(--heading)" strokeWidth="0.4" strokeDasharray="2 4" />
        <circle cx="100" cy="100" r="60" stroke="var(--heading)" strokeWidth="0.4" />
        <circle cx="100" cy="100" r="40" stroke="var(--heading)" strokeWidth="0.4" strokeDasharray="1 3" />
      </svg>
      {/* tiny floating icons */}
      <FloatingDot className="top-[18%] left-[12%] float-a" color={c1} />
      <FloatingDot className="top-[60%] left-[8%] float-c" color={c2} />
      <FloatingDot className="top-[30%] right-[10%] float-b" color={c1} />
      <FloatingDot className="bottom-[15%] right-[20%] float-c" color={c2} />
    </div>
  );
}

function FloatingDot({ className, color }: { className?: string; color: string }) {
  return (
    <div
      className={`absolute w-2 h-2 rounded-full opacity-[0.25] ${className ?? ""}`}
      style={{ background: color, boxShadow: `0 0 24px ${color}` }}
    />
  );
}
