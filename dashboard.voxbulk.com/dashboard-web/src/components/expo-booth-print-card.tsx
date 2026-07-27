import * as React from "react";

import { brandAssets } from "@/lib/brand";
import { buildExpoQrImageCandidates, resolveExpoWebUrl } from "@/lib/expo-qr";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";

const DEFAULT_HEADLINE = "No time to wait?";
const DEFAULT_SUBLINE = "Scan and chat with our AI.";
const DEFAULT_SUPPORT =
  "Get answers and your catalogue in seconds —\nWhatsApp or web, under a minute.";
const DEFAULT_POWERED =
  "Powered by VOXBULK AI · Instant lead capture · Every scan becomes a lead";
const FOOTER_BAR = "EXPO · voxbulk.com · expo@voxbulk.com";

export type ExpoBoothPrintCardProps = {
  boothId?: string | null;
  /** Preferred QR image URL from API (may be blocked — component falls back). */
  qrSrc?: string | null;
  webUrl?: string | null;
  qrToken?: string | null;
  company: string;
  boothCode?: string | null;
  eventName: string;
  eventDates?: string | null;
  className?: string;
};

type StoredCopy = {
  headline: string;
  subline: string;
  support: string;
  powered: string;
};

function storageKey(boothId: string) {
  return `voxbulk.expo.printCard.${boothId}`;
}

function loadStored(boothId: string | null | undefined): Partial<StoredCopy> | null {
  if (!boothId || typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(storageKey(boothId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<StoredCopy>;
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

function saveStored(boothId: string | null | undefined, copy: StoredCopy) {
  if (!boothId || typeof window === "undefined") return;
  try {
    localStorage.setItem(storageKey(boothId), JSON.stringify(copy));
  } catch {
    /* ignore quota */
  }
}

function useExpoQrSrc(preferred: string | null | undefined, webUrl: string) {
  const candidates = React.useMemo(() => {
    const list: string[] = [];
    const pref = String(preferred || "").trim();
    if (pref) list.push(pref);
    for (const c of buildExpoQrImageCandidates(webUrl, 200)) {
      if (c && !list.includes(c)) list.push(c);
    }
    return list;
  }, [preferred, webUrl]);

  const [index, setIndex] = React.useState(0);
  React.useEffect(() => {
    setIndex(0);
  }, [candidates.join("|")]);

  const src = candidates[index] || "";
  const onError = () => {
    setIndex((i) => (i + 1 < candidates.length ? i + 1 : i));
  };
  return { src, onError, hasQr: Boolean(src) };
}

/**
 * Pixel-faithful port of qr print.html — editable top/bottom copy, live preview, browser print.
 */
export function ExpoBoothPrintCard({
  boothId,
  qrSrc: preferredQr,
  webUrl: webUrlProp,
  qrToken,
  company,
  boothCode,
  eventName,
  eventDates,
  className,
}: ExpoBoothPrintCardProps) {
  const stored = React.useMemo(() => loadStored(boothId), [boothId]);
  const [headline, setHeadline] = React.useState(stored?.headline || DEFAULT_HEADLINE);
  const [subline, setSubline] = React.useState(stored?.subline || DEFAULT_SUBLINE);
  const [support, setSupport] = React.useState(stored?.support || DEFAULT_SUPPORT);
  const [powered, setPowered] = React.useState(stored?.powered || DEFAULT_POWERED);

  React.useEffect(() => {
    saveStored(boothId, { headline, subline, support, powered });
  }, [boothId, headline, subline, support, powered]);

  const webUrl = resolveExpoWebUrl({ web_url: webUrlProp, qr_token: qrToken });
  const { src: qrSrc, onError: onQrError, hasQr } = useExpoQrSrc(preferredQr, webUrl);

  const exhibitor = String(company || "").trim() || "Exhibitor";
  const boothLabel = String(boothCode || "").trim();
  const eventLabel = String(eventName || "").trim() || "Event";
  const datesLabel = String(eventDates || "").trim();
  const supportLines = support.split(/\n/).filter((l) => l.length > 0);

  const handlePrint = () => {
    window.print();
  };

  return (
    <div className={["expo-booth-print-root", className].filter(Boolean).join(" ")}>
      <style>{`
        @media print {
          body * { visibility: hidden !important; }
          .expo-booth-print-root,
          .expo-booth-print-root * { visibility: visible !important; }
          .expo-booth-print-root {
            position: absolute !important;
            left: 0 !important;
            top: 0 !important;
            width: 100% !important;
            margin: 0 !important;
            padding: 0 !important;
            background: white !important;
          }
          .expo-booth-print-root .no-print { display: none !important; }
          .expo-booth-print-root .booth-card {
            box-shadow: none !important;
            border: 1px solid #ccc !important;
          }
        }
      `}</style>

      <div
        className="no-print mb-4 space-y-3 rounded-xl border p-4"
        style={{ background: "#f0f4f9", borderColor: "#1a2d5c" }}
      >
        <div>
          <p className="text-sm font-semibold" style={{ color: "#1a2d5c" }}>
            Print this card and place it at your expo booth
          </p>
          <p className="mt-0.5 text-xs" style={{ color: "#6b6560" }}>
            Edit the text below — the live preview updates instantly. Your booth QR is saved with the booth
            {webUrl ? (
              <>
                {" "}
                (
                <a href={webUrl} target="_blank" rel="noreferrer" className="underline">
                  open scan link
                </a>
                )
              </>
            ) : null}
            .
          </p>
        </div>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="expo-print-headline">Top headline</Label>
            <Input
              id="expo-print-headline"
              value={headline}
              onChange={(e) => setHeadline(e.target.value)}
              maxLength={80}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="expo-print-subline">Top subline</Label>
            <Input
              id="expo-print-subline"
              value={subline}
              onChange={(e) => setSubline(e.target.value)}
              maxLength={80}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="expo-print-support">Support line</Label>
            <Textarea
              id="expo-print-support"
              value={support}
              onChange={(e) => setSupport(e.target.value)}
              rows={2}
              maxLength={200}
            />
          </div>
          <div className="space-y-1.5 sm:col-span-2">
            <Label htmlFor="expo-print-powered">Bottom note</Label>
            <Input
              id="expo-print-powered"
              value={powered}
              onChange={(e) => setPowered(e.target.value)}
              maxLength={120}
            />
          </div>
        </div>
        <Button
          type="button"
          onClick={handlePrint}
          disabled={!hasQr}
          style={{ background: "#1a2d5c", color: "#fff" }}
          className="hover:opacity-90"
        >
          Print Booth Card →
        </Button>
        {!hasQr ? (
          <p className="text-xs text-destructive">
            QR image is still loading. If it stays blank, open the scan link above and try again after refresh.
          </p>
        ) : null}
      </div>

      <table
        role="presentation"
        width="100%"
        cellSpacing={0}
        cellPadding={0}
        style={{
          background: "#f5f1ea",
          padding: "32px 16px",
          fontFamily: "system-ui,-apple-system,'Segoe UI',sans-serif",
          color: "#2a2824",
          lineHeight: 1.65,
          width: "100%",
          borderCollapse: "collapse",
        }}
      >
        <tbody>
          <tr>
            <td align="center">
              <table
                role="presentation"
                className="booth-card"
                width="100%"
                cellSpacing={0}
                cellPadding={0}
                style={{
                  maxWidth: 450,
                  background: "#ffffff",
                  border: "2px solid #1a2d5c",
                  borderRadius: 16,
                  overflow: "hidden",
                  boxShadow: "0 8px 32px rgba(0,0,0,0.12)",
                  borderCollapse: "collapse",
                }}
              >
                <tbody>
                  <tr>
                    <td
                      style={{
                        padding: "20px 24px 12px",
                        borderBottom: "2px solid #1a2d5c",
                        background: "#fbf8f3",
                      }}
                    >
                      <table width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ borderCollapse: "collapse" }}>
                        <tbody>
                          <tr>
                            <td valign="middle">
                              <img
                                src={brandAssets.logoBlack}
                                alt="VOXBULK"
                                width={120}
                                style={{
                                  display: "block",
                                  border: 0,
                                  outline: "none",
                                  maxWidth: 120,
                                  height: "auto",
                                }}
                              />
                            </td>
                            <td align="right" valign="middle">
                              <span
                                style={{
                                  display: "inline-block",
                                  background: "#1a2d5c",
                                  color: "#ffffff",
                                  borderRadius: 20,
                                  padding: "4px 14px",
                                  fontSize: 10,
                                  fontWeight: 700,
                                  letterSpacing: "0.08em",
                                  textTransform: "uppercase",
                                }}
                              >
                                EXPO
                              </span>
                            </td>
                          </tr>
                        </tbody>
                      </table>
                    </td>
                  </tr>

                  <tr>
                    <td style={{ padding: "28px 24px", textAlign: "center" }}>
                      <p
                        style={{
                          margin: "0 0 8px",
                          fontSize: 20,
                          fontWeight: 800,
                          color: "#1a2d5c",
                          letterSpacing: "-0.02em",
                        }}
                      >
                        {headline || DEFAULT_HEADLINE}
                      </p>
                      <p
                        style={{
                          margin: "0 0 4px",
                          fontSize: 18,
                          fontWeight: 700,
                          color: "#b45309",
                        }}
                      >
                        {subline || DEFAULT_SUBLINE}
                      </p>

                      <p
                        style={{
                          margin: "8px 0 20px",
                          fontSize: 13,
                          color: "#6b6560",
                          lineHeight: 1.5,
                        }}
                      >
                        {supportLines.length
                          ? supportLines.map((line, i) => (
                              <React.Fragment key={`${i}-${line}`}>
                                {i > 0 ? <br /> : null}
                                {line}
                              </React.Fragment>
                            ))
                          : DEFAULT_SUPPORT.split("\n").map((line, i) => (
                              <React.Fragment key={`d-${i}`}>
                                {i > 0 ? <br /> : null}
                                {line}
                              </React.Fragment>
                            ))}
                      </p>

                      <div
                        style={{
                          display: "inline-block",
                          background: "#ffffff",
                          padding: 12,
                          border: "2px solid #e5e0d8",
                          borderRadius: 12,
                          marginBottom: 12,
                        }}
                      >
                        {qrSrc ? (
                          <img
                            src={qrSrc}
                            alt="Scan to chat with AI"
                            referrerPolicy="no-referrer"
                            onError={onQrError}
                            style={{
                              width: 160,
                              height: 160,
                              display: "block",
                              border: 0,
                              outline: "none",
                            }}
                          />
                        ) : (
                          <div
                            style={{
                              width: 160,
                              height: 160,
                              display: "grid",
                              placeItems: "center",
                              fontSize: 12,
                              color: "#6b6560",
                              textAlign: "center",
                              padding: 8,
                            }}
                          >
                            QR unavailable
                            {webUrl ? (
                              <>
                                <br />
                                <span style={{ fontSize: 9, wordBreak: "break-all" }}>{webUrl}</span>
                              </>
                            ) : null}
                          </div>
                        )}
                      </div>

                      <p style={{ margin: 0, fontSize: 14, fontWeight: 700, color: "#1a2d5c" }}>
                        📱 Scan to chat
                      </p>
                      <p style={{ margin: "4px 0 0", fontSize: 11, color: "#6b6560" }}>
                        WhatsApp or web — no app download needed
                      </p>

                      <hr
                        style={{
                          border: "none",
                          borderTop: "1px solid #e5e0d8",
                          margin: "20px 0",
                        }}
                      />

                      <table width="100%" cellPadding={0} cellSpacing={0} border={0} style={{ borderCollapse: "collapse" }}>
                        <tbody>
                          <tr>
                            <td valign="top" style={{ paddingRight: 8, width: "50%" }}>
                              <div
                                style={{
                                  background: "#f5f1ea",
                                  borderRadius: 8,
                                  padding: "10px 12px",
                                  border: "1px solid #e5e0d8",
                                  minHeight: 60,
                                  textAlign: "left",
                                }}
                              >
                                <p
                                  style={{
                                    margin: 0,
                                    fontSize: 9,
                                    fontWeight: 700,
                                    color: "#6b6560",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                  }}
                                >
                                  Exhibitor
                                </p>
                                <p
                                  style={{
                                    margin: "2px 0 0",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    color: "#1a2d5c",
                                  }}
                                >
                                  {exhibitor}
                                </p>
                                {boothLabel ? (
                                  <p style={{ margin: "2px 0 0", fontSize: 10, color: "#6b6560" }}>
                                    Booth #{boothLabel}
                                  </p>
                                ) : null}
                              </div>
                            </td>
                            <td valign="top" style={{ paddingLeft: 8, width: "50%" }}>
                              <div
                                style={{
                                  background: "#f5f1ea",
                                  borderRadius: 8,
                                  padding: "10px 12px",
                                  border: "1px solid #e5e0d8",
                                  minHeight: 60,
                                  textAlign: "left",
                                }}
                              >
                                <p
                                  style={{
                                    margin: 0,
                                    fontSize: 9,
                                    fontWeight: 700,
                                    color: "#6b6560",
                                    textTransform: "uppercase",
                                    letterSpacing: "0.05em",
                                  }}
                                >
                                  Event
                                </p>
                                <p
                                  style={{
                                    margin: "2px 0 0",
                                    fontSize: 12,
                                    fontWeight: 600,
                                    color: "#1a2d5c",
                                  }}
                                >
                                  {eventLabel}
                                </p>
                                {datesLabel ? (
                                  <p style={{ margin: "2px 0 0", fontSize: 10, color: "#6b6560" }}>
                                    {datesLabel}
                                  </p>
                                ) : null}
                              </div>
                            </td>
                          </tr>
                        </tbody>
                      </table>

                      <p
                        style={{
                          margin: "12px 0 0",
                          fontSize: 9,
                          color: "#a39a91",
                          textAlign: "center",
                        }}
                      >
                        {powered || DEFAULT_POWERED}
                      </p>
                    </td>
                  </tr>

                  <tr>
                    <td
                      style={{
                        padding: "10px 24px",
                        background: "#1a2d5c",
                        textAlign: "center",
                      }}
                    >
                      <p
                        style={{
                          margin: 0,
                          fontSize: 10,
                          color: "rgba(255,255,255,0.4)",
                          letterSpacing: "0.05em",
                        }}
                      >
                        {FOOTER_BAR}
                      </p>
                    </td>
                  </tr>
                </tbody>
              </table>
            </td>
          </tr>
        </tbody>
      </table>

      <div
        className="no-print mt-4 text-center"
        style={{
          padding: 16,
          background: "#f0f4f9",
          borderTop: "2px solid #1a2d5c",
        }}
      >
        <button
          type="button"
          onClick={handlePrint}
          disabled={!hasQr}
          style={{
            background: "#1a2d5c",
            color: "#ffffff",
            border: "none",
            padding: "10px 32px",
            borderRadius: 8,
            fontSize: 14,
            fontWeight: 600,
            cursor: hasQr ? "pointer" : "not-allowed",
            opacity: hasQr ? 1 : 0.5,
          }}
        >
          🖨️ Print Booth Card
        </button>
        <p style={{ margin: "6px 0 0", fontSize: 11, color: "#6b6560" }}>
          Place this card on your booth table or stand for visitors to scan
        </p>
      </div>
    </div>
  );
}
