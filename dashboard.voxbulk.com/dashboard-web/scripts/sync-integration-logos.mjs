/**
 * Write official Simple Icons SVGs into public/integrations/.
 * Pipedrive uses the lettermark "p" path from Pipedrive's official wordmark.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  siCalendly,
  siCaldotcom,
  siGooglecalendar,
  siHubspot,
  siZoho,
} from "simple-icons";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.resolve(__dirname, "../public/integrations");

/** Official Pipedrive wordmark "p" glyph (Pipedrive OÜ brand asset). */
const PIPEDRIVE_P_PATH =
  "M44.138 23.65c-10.288 0-16.238 4.616-19.108 7.805-.341-2.748-2.154-6.313-9.227-6.313H.443V41.22h6.295c1.065 0 1.408.34 1.408 1.403v73.412h18.31V88.482c0-.744-.015-1.439-.034-2.061 2.86 2.627 8.322 6.243 16.854 6.243 17.896 0 30.408-14.186 30.408-34.504 0-20.64-11.88-34.51-29.546-34.51m-3.72 53.066c-9.857 0-14.335-9.438-14.335-18.182 0-13.773 7.532-18.682 14.58-18.682 8.643 0 14.456 7.452 14.456 18.553 0 12.659-7.39 18.311-14.7 18.311";

function writeSimpleIcon(filename, icon) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="${icon.title}">
  <path fill="#${icon.hex}" d="${icon.path}"/>
</svg>
`;
  fs.writeFileSync(path.join(outDir, filename), svg, "utf8");
  console.log("wrote", filename, icon.slug);
}

function writeMicrosoftIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" role="img" aria-label="Microsoft">
  <path fill="#F25022" d="M1 1h10v10H1z"/>
  <path fill="#7FBA00" d="M13 1h10v10H13z"/>
  <path fill="#00A4EF" d="M1 13h10v10H1z"/>
  <path fill="#FFB900" d="M13 13h10v10H13z"/>
</svg>
`;
  fs.writeFileSync(path.join(outDir, "microsoft.svg"), svg, "utf8");
  console.log("wrote microsoft.svg");
}

function writePipedriveIcon() {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 80 100" role="img" aria-label="Pipedrive">
  <rect width="80" height="100" rx="18" fill="#22B573"/>
  <g transform="translate(10 8) scale(0.76) translate(0 -16)">
    <path fill="#FFFFFF" d="${PIPEDRIVE_P_PATH}"/>
  </g>
</svg>
`;
  fs.writeFileSync(path.join(outDir, "pipedrive.svg"), svg, "utf8");
  console.log("wrote pipedrive.svg");
}

fs.mkdirSync(outDir, { recursive: true });

writeSimpleIcon("hubspot.svg", siHubspot);
writeSimpleIcon("calendly.svg", siCalendly);
writeSimpleIcon("cal-com.svg", siCaldotcom);
writeSimpleIcon("google-calendar.svg", siGooglecalendar);
writeSimpleIcon("zoho.svg", siZoho);
writeMicrosoftIcon();
writePipedriveIcon();
