import type { ReactNode } from "react";

const W = 390;
const H = 800;

/** iPhone-style device shell that renders a 390x800 mobile template scaled to fit. */
export function PhoneFrame({ children, scale = 0.72 }: { children: ReactNode; scale?: number }) {
  return (
    <div
      className="relative shrink-0"
      style={{ width: (W + 24) * scale, height: (H + 24) * scale }}
      aria-hidden={false}
    >
      <div
        className="absolute left-0 top-0 origin-top-left rounded-[52px] bg-navy p-3 shadow-[0_40px_90px_-40px_rgba(10,22,40,0.65)] ring-1 ring-black/20"
        style={{ width: W + 24, height: H + 24, transform: `scale(${scale})` }}
      >
        <div className="relative h-full w-full overflow-hidden rounded-[42px] bg-white">
          {/* status bar */}
          <div className="pointer-events-none absolute inset-x-0 top-0 z-20 flex h-9 items-center justify-between px-6 text-[11px] font-semibold text-white mix-blend-difference">
            <span>9:41</span>
            <span className="flex items-center gap-1">
              <svg width="16" height="11" viewBox="0 0 16 11" fill="currentColor"><rect x="0" y="7" width="3" height="4" rx="1" /><rect x="4.3" y="5" width="3" height="6" rx="1" /><rect x="8.6" y="2.6" width="3" height="8.4" rx="1" /><rect x="12.9" y="0" width="3" height="11" rx="1" /></svg>
              <svg width="22" height="11" viewBox="0 0 22 11" fill="none"><rect x="0.5" y="0.5" width="18" height="10" rx="3" stroke="currentColor" /><rect x="2" y="2" width="13" height="7" rx="1.8" fill="currentColor" /><path d="M20 4v3a2 2 0 0 0 0-3Z" fill="currentColor" /></svg>
            </span>
          </div>
          {/* notch */}
          <div className="absolute left-1/2 top-2 z-30 h-6 w-28 -translate-x-1/2 rounded-full bg-navy" />
          <div className="h-full w-full pt-1">{children}</div>
          {/* home indicator */}
          <div className="absolute bottom-2 left-1/2 z-30 h-1 w-28 -translate-x-1/2 rounded-full bg-black/25" />
        </div>
      </div>
    </div>
  );
}

export const PHONE_W = W;
export const PHONE_H = H;
