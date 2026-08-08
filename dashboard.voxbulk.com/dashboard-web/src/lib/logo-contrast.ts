/**
 * Logo contrast detection + WebP conversion (native Canvas API only).
 *
 * Pipeline: validate PNG/JPG → sample luminance → convert to WebP → apply opposite plate.
 * Used by Smart Card, Customer Feedback, and Expo (upload + display).
 */

export type LogoTone = "light" | "dark";

export type LogoProcessResult = {
  /** WebP file ready to upload (or original if WebP encode failed). */
  file: File;
  tone: LogoTone;
  /** Average perceived luminance of opaque logo pixels (0–255). */
  luminance: number;
  webpConverted: boolean;
  originalName: string;
};

export const LOGO_FORMAT_ERROR = "Error: Only PNG and JPG images are supported";

/** Perceived-luminance threshold on 0–255 (ITU-R BT.601). */
export const LUMINANCE_THRESHOLD = 128;

/** Max pixels sampled for brightness (performance). */
export const MAX_SAMPLE_PIXELS = 1600;

/** Analysis canvas max edge (high-res logos are downscaled first). */
export const ANALYSIS_MAX_EDGE = 256;

/** WebP encode quality (0–1). */
export const WEBP_QUALITY = 0.85;

/** Max source dimension before WebP encode (memory guard). */
export const ENCODE_MAX_EDGE = 1600;

/** Alpha below this is treated as transparent and ignored. */
export const ALPHA_OPAQUE_MIN = 128;

/** Near-white/near-background delta for JPG flat backgrounds. */
export const BACKGROUND_COLOR_DELTA = 28;

const DEBUG =
  typeof import.meta !== "undefined" &&
  Boolean((import.meta as ImportMeta & { env?: { DEV?: boolean } }).env?.DEV);

function debugLog(...args: unknown[]) {
  if (DEBUG) console.debug("[logo-contrast]", ...args);
}

const ALLOWED_MIME = new Set(["image/png", "image/jpeg", "image/jpg"]);
const ALLOWED_EXT = new Set([".png", ".jpg", ".jpeg"]);
const REJECTED_MIME = new Set([
  "image/svg+xml",
  "image/gif",
  "image/webp",
  "image/avif",
  "image/bmp",
  "image/x-icon",
]);
const REJECTED_EXT = new Set([".svg", ".gif", ".webp", ".avif", ".bmp", ".ico"]);

/** Validate MIME type / extension — PNG and JPG only as *input*. */
export function validateLogoFormat(file: File | Blob & { name?: string }): void {
  const name = ("name" in file && file.name ? String(file.name) : "logo").toLowerCase();
  const mime = String(file.type || "").toLowerCase();
  const dot = name.lastIndexOf(".");
  const ext = dot >= 0 ? name.slice(dot) : "";

  if (REJECTED_MIME.has(mime) || REJECTED_EXT.has(ext)) {
    throw new Error(LOGO_FORMAT_ERROR);
  }
  const mimeOk = !mime || ALLOWED_MIME.has(mime) || mime === "image/jpg";
  const extOk = !ext || ALLOWED_EXT.has(ext);
  if (!mimeOk || !extOk) {
    throw new Error(LOGO_FORMAT_ERROR);
  }
  if (!mime && !ext) {
    throw new Error(LOGO_FORMAT_ERROR);
  }
}

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

/** Load an image URL/blob with CORS + exponential backoff on network failure. */
export async function loadImageElement(
  src: string,
  opts?: { crossOrigin?: string | null; retries?: number },
): Promise<HTMLImageElement> {
  const retries = opts?.retries ?? 3;
  let lastErr: unknown;
  for (let attempt = 0; attempt < retries; attempt++) {
    try {
      return await new Promise<HTMLImageElement>((resolve, reject) => {
        const img = new Image();
        if (opts?.crossOrigin !== null) {
          img.crossOrigin = opts?.crossOrigin ?? "anonymous";
        }
        img.decoding = "async";
        img.onload = () => resolve(img);
        img.onerror = () => reject(new Error("Could not load logo image"));
        img.src = src;
      });
    } catch (e) {
      lastErr = e;
      await sleep(Math.min(2000, 200 * 2 ** attempt));
    }
  }
  throw lastErr instanceof Error ? lastErr : new Error("Could not load logo image");
}

function colorDist(r: number, g: number, b: number, br: number, bg: number, bb: number) {
  return Math.abs(r - br) + Math.abs(g - bg) + Math.abs(b - bb);
}

/**
 * Sample ~MAX_SAMPLE_PIXELS opaque pixels and return average perceived luminance.
 * Ignores transparent pixels and flat JPG backgrounds (corner-sampled).
 */
export function detectLogoLuminanceFromImageData(data: ImageData): {
  luminance: number;
  tone: LogoTone;
  samples: number;
} {
  const { data: px, width, height } = data;
  if (!width || !height) {
    return { luminance: LUMINANCE_THRESHOLD, tone: "dark", samples: 0 };
  }

  // Corner average ≈ likely JPG paper/white background.
  const corners = [
    [0, 0],
    [width - 1, 0],
    [0, height - 1],
    [width - 1, height - 1],
  ] as const;
  let cr = 0;
  let cg = 0;
  let cb = 0;
  for (const [x, y] of corners) {
    const i = (y * width + x) * 4;
    cr += px[i];
    cg += px[i + 1];
    cb += px[i + 2];
  }
  cr = Math.round(cr / 4);
  cg = Math.round(cg / 4);
  cb = Math.round(cb / 4);

  const total = width * height;
  const step = Math.max(1, Math.floor(Math.sqrt(total / MAX_SAMPLE_PIXELS)));

  let sum = 0;
  let count = 0;
  for (let y = 0; y < height; y += step) {
    for (let x = 0; x < width; x += step) {
      const i = (y * width + x) * 4;
      const a = px[i + 3];
      if (a < ALPHA_OPAQUE_MIN) continue;
      const r = px[i];
      const g = px[i + 1];
      const b = px[i + 2];
      // Skip near-background pixels (white / flat JPG mats).
      if (colorDist(r, g, b, cr, cg, cb) <= BACKGROUND_COLOR_DELTA) continue;
      // ITU-R BT.601 perceived luminance
      sum += 0.299 * r + 0.587 * g + 0.114 * b;
      count += 1;
    }
  }

  // Fallback: if everything looked like background, use all opaque pixels.
  if (count < 8) {
    sum = 0;
    count = 0;
    for (let y = 0; y < height; y += step) {
      for (let x = 0; x < width; x += step) {
        const i = (y * width + x) * 4;
        if (px[i + 3] < ALPHA_OPAQUE_MIN) continue;
        sum += 0.299 * px[i] + 0.587 * px[i + 1] + 0.114 * px[i + 2];
        count += 1;
      }
    }
  }

  const luminance = count > 0 ? sum / count : LUMINANCE_THRESHOLD;
  const tone: LogoTone = luminance >= LUMINANCE_THRESHOLD ? "light" : "dark";
  debugLog("luminance", { luminance: Math.round(luminance), tone, samples: count, step });
  return { luminance, tone, samples: count };
}

function drawForAnalysis(img: CanvasImageSource, naturalW: number, naturalH: number): ImageData {
  const scale = Math.min(1, ANALYSIS_MAX_EDGE / Math.max(naturalW, naturalH, 1));
  const w = Math.max(1, Math.round(naturalW * scale));
  const h = Math.max(1, Math.round(naturalH * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) throw new Error("Canvas is not available");
  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(img as CanvasImageSource, 0, 0, w, h);
  return ctx.getImageData(0, 0, w, h);
}

/** Detect light/dark tone from a loaded HTMLImageElement. */
export function detectLogoToneFromImage(img: HTMLImageElement): {
  luminance: number;
  tone: LogoTone;
} {
  const w = img.naturalWidth || img.width;
  const h = img.naturalHeight || img.height;
  const { luminance, tone } = detectLogoLuminanceFromImageData(drawForAnalysis(img, w, h));
  return { luminance, tone };
}

/** Detect from object URL / remote URL (with CORS). Defaults to dark (light plate) on failure. */
export async function detectLogoToneFromSrc(
  src: string,
  opts?: { crossOrigin?: string | null },
): Promise<{ luminance: number; tone: LogoTone }> {
  try {
    const img = await loadImageElement(src, opts);
    return detectLogoToneFromImage(img);
  } catch (e) {
    debugLog("detect failed, defaulting to dark tone", e);
    return { luminance: 40, tone: "dark" };
  }
}

/** Convert a loaded image to a WebP Blob via Canvas. Falls back by throwing. */
export async function convertImageToWebpBlob(
  img: HTMLImageElement,
  quality = WEBP_QUALITY,
): Promise<Blob> {
  const nw = img.naturalWidth || img.width;
  const nh = img.naturalHeight || img.height;
  const scale = Math.min(1, ENCODE_MAX_EDGE / Math.max(nw, nh, 1));
  const w = Math.max(1, Math.round(nw * scale));
  const h = Math.max(1, Math.round(nh * scale));
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas is not available");
  ctx.clearRect(0, 0, w, h);
  ctx.drawImage(img, 0, 0, w, h);

  const blob = await new Promise<Blob | null>((resolve) => {
    canvas.toBlob((b) => resolve(b), "image/webp", quality);
  });
  if (!blob || blob.size < 16) {
    throw new Error("WebP conversion failed");
  }
  return blob;
}

function webpFileName(originalName: string): string {
  const base = originalName.replace(/\.[^.]+$/, "") || "logo";
  return `${base}.webp`;
}

/**
 * Full upload pipeline: validate → detect → WebP convert (async, non-blocking UX via await).
 * On WebP failure, returns the original PNG/JPG with detected tone.
 */
export async function processLogoUpload(file: File): Promise<LogoProcessResult> {
  validateLogoFormat(file);
  const originalName = file.name || "logo.png";
  const objectUrl = URL.createObjectURL(file);
  try {
    const img = await loadImageElement(objectUrl, { crossOrigin: null });
    const { luminance, tone } = detectLogoToneFromImage(img);

    let outFile = file;
    let webpConverted = false;
    try {
      const blob = await convertImageToWebpBlob(img);
      outFile = new File([blob], webpFileName(originalName), { type: "image/webp" });
      webpConverted = true;
      debugLog("webp ok", { before: file.size, after: outFile.size });
    } catch (e) {
      debugLog("webp failed, keeping original", e);
    }

    return {
      file: outFile,
      tone,
      luminance,
      webpConverted,
      originalName,
    };
  } finally {
    URL.revokeObjectURL(objectUrl);
  }
}

/** Opposite plate styles — light logo needs dark plate (and soft glow). */
export function logoPlateStyles(tone: LogoTone): {
  background: string;
  border: string;
  boxShadow: string;
  glow?: string;
} {
  if (tone === "light") {
    return {
      background: "linear-gradient(160deg, rgba(15,23,42,0.96), rgba(30,41,59,0.94))",
      border: "1px solid rgba(255,255,255,0.22)",
      boxShadow: "0 0 0 1px rgba(255,255,255,0.06), 0 8px 18px -12px rgba(0,0,0,0.55)",
      glow:
        "radial-gradient(circle at 50% 45%, rgba(255,255,255,0.85) 0%, rgba(255,255,255,0.35) 42%, rgba(255,255,255,0) 72%)",
    };
  }
  return {
    background: "linear-gradient(160deg, rgba(255,255,255,0.97), rgba(248,250,252,0.94))",
    border: "1px solid rgba(15,23,42,0.14)",
    boxShadow: "0 0 0 1px rgba(15,23,42,0.04), 0 8px 18px -12px rgba(0,0,0,0.28)",
  };
}

/** In-memory + sessionStorage cache for repeated logo URLs. */
const toneMemory = new Map<string, LogoTone>();

export function getCachedLogoTone(src: string): LogoTone | null {
  if (!src) return null;
  if (toneMemory.has(src)) return toneMemory.get(src)!;
  try {
    const raw = sessionStorage.getItem(`logo_tone:${src}`);
    if (raw === "light" || raw === "dark") {
      toneMemory.set(src, raw);
      return raw;
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function setCachedLogoTone(src: string, tone: LogoTone) {
  if (!src) return;
  toneMemory.set(src, tone);
  try {
    sessionStorage.setItem(`logo_tone:${src}`, tone);
  } catch {
    /* ignore */
  }
}

export function normalizeLogoTone(value: unknown): LogoTone | null {
  const v = String(value || "").toLowerCase().trim();
  if (v === "light" || v === "dark") return v;
  return null;
}
