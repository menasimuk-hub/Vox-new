import { QRCodeSVG } from "qrcode.react";

export function DemoQrCard({ url, label }: { url: string; label?: string }) {
  if (!url) return null;
  return (
    <div className="rounded-2xl border border-border bg-white p-5 shadow-elegant text-center" data-demo-target="live-qr">
      <div className="text-[12px] font-semibold uppercase tracking-wider text-muted-text mb-3">
        {label || "Scan with your phone"}
      </div>
      <div className="inline-flex rounded-xl bg-white p-3 border border-border">
        <QRCodeSVG value={url} size={168} level="M" includeMargin={false} />
      </div>
      <p className="mt-3 text-[12px] text-body break-all">{url}</p>
    </div>
  );
}
