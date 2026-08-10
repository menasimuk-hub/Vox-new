/** Generic animated backdrop for mobile template previews. Driven by theme accents. */
export function TemplateArt({
  accent,
  accent2,
  motifs = [],
  grid = true,
}: {
  accent: string;
  accent2: string;
  motifs?: string[];
  grid?: boolean;
}) {
  const id = `tplgrid-${accent.replace(/[^a-z0-9]/gi, "")}`;
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 overflow-hidden">
      <div
        className="tpl-blob-a absolute -left-24 -top-24 h-80 w-80 rounded-full blur-3xl"
        style={{ background: accent, opacity: 0.22 }}
      />
      <div
        className="tpl-blob-b absolute -right-24 bottom-0 h-80 w-80 rounded-full blur-3xl"
        style={{ background: accent2, opacity: 0.18 }}
      />
      {grid && (
        <svg className="absolute inset-0 h-full w-full opacity-[0.06]" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <pattern id={id} width="34" height="34" patternUnits="userSpaceOnUse">
              <path d="M 34 0 L 0 0 0 34" fill="none" stroke="currentColor" strokeWidth="0.6" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill={`url(#${id})`} />
        </svg>
      )}
      <svg className="tpl-orbit-slow absolute -right-16 top-16 h-64 w-64 opacity-25" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="72" stroke={accent} strokeWidth="0.8" strokeDasharray="3 9" />
        <circle cx="100" cy="28" r="3" fill={accent2} />
      </svg>
      <svg className="tpl-orbit-rev absolute -left-20 bottom-10 h-56 w-56 opacity-20" viewBox="0 0 200 200" fill="none">
        <circle cx="100" cy="100" r="80" stroke={accent2} strokeWidth="0.8" strokeDasharray="2 12" />
        <circle cx="180" cy="100" r="3" fill={accent} />
      </svg>
      {motifs.slice(0, 4).map((m, i) => (
        <span
          key={`${m}-${i}`}
          className={i % 2 === 0 ? "tpl-drift-slow absolute text-[22px]" : "tpl-drift-slower absolute text-[20px]"}
          style={{
            top: ["16%", "44%", "68%", "84%"][i],
            [i % 2 === 0 ? "left" : "right"]: ["8%", "10%", "14%", "34%"][i],
            opacity: 0.35,
            animationDelay: `${i * 0.9}s`,
          }}
        >
          {m}
        </span>
      ))}
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="tpl-twinkle absolute text-[10px]"
          style={{
            top: ["28%", "58%", "76%"][i],
            left: ["78%", "22%", "62%"][i],
            color: i % 2 ? accent2 : accent,
            animationDelay: `${i * 0.7}s`,
          }}
        >
          ◆
        </span>
      ))}
    </div>
  );
}
