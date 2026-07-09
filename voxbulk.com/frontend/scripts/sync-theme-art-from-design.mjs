import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const designDir = "C:/Users/zaghlol/Downloads/Voxbulk-Designs/feedback-flow-main/src/routes";
const prodDir = path.resolve(__dirname, "../src/components/feedback-survey/themes");

const ART_NAMES = ["BackgroundArt", "SummerArt", "WinterArt", "Art"];

function extractFunction(src, names) {
  for (const name of names) {
    const sig = `function ${name}(`;
    const idx = src.indexOf(sig);
    if (idx < 0) continue;
    const brace = src.indexOf("{", idx);
    if (brace < 0) continue;
    let depth = 0;
    for (let i = brace; i < src.length; i++) {
      const c = src[i];
      if (c === "{") depth++;
      else if (c === "}") {
        depth--;
        if (depth === 0) return { name, body: src.slice(idx, i + 1) };
      }
    }
  }
  return null;
}

function extractThemeConst(src) {
  const m = src.match(/const T:\s*Theme\s*=\s*(\{[\s\S]*?\n\});/);
  return m ? m[1] : null;
}

function transformArt(artSrc, themeName = "theme") {
  let out = artSrc
    .replace(/function (BackgroundArt|SummerArt|WinterArt|Art)\(/, "export function Art(")
    .replace(/\bT\./g, `${themeName}.`)
    .replace(/\bT\b(?=[,;\)\s])/g, themeName);
  return out;
}

function needsReactHooks(src) {
  return /\buseMemo\b/.test(src) || /\buseEffect\b/.test(src) || /\buseRef\b/.test(src);
}

function buildProdFile(themeObj, artFn, extraHelpers = "") {
  const imports = needsReactHooks(artFn + extraHelpers)
    ? 'import * as React from "react";\nimport type { Theme } from "../types";\n\n'
    : 'import type { Theme } from "../types";\n\n';
  return `${imports}export const theme: Theme = ${themeObj};\n\n${extraHelpers}${artFn}\n`;
}

let updated = 0;
for (const file of fs.readdirSync(prodDir).filter((f) => f.endsWith(".tsx"))) {
  const designPath = path.join(designDir, file);
  if (!fs.existsSync(designPath)) {
    console.warn("skip (no design):", file);
    continue;
  }
  const designSrc = fs.readFileSync(designPath, "utf8");
  const art = extractFunction(designSrc, ART_NAMES);
  if (!art) {
    console.warn("skip (no art fn):", file);
    continue;
  }
  const themeObj = extractThemeConst(designSrc);
  if (!themeObj) {
    console.warn("skip (no theme):", file);
    continue;
  }

  let extraHelpers = "";
  if (file === "survey-winter.tsx") {
    const snow = extractFunction(designSrc, ["Snowflake"]);
    if (snow) extraHelpers = transformArt(snow.body).replace("export function Art", "function Snowflake") + "\n\n";
  }

  const artFn = transformArt(art.body);
  const out = buildProdFile(themeObj, artFn, extraHelpers);
  const prev = fs.readFileSync(path.join(prodDir, file), "utf8");
  if (prev !== out) {
    fs.writeFileSync(path.join(prodDir, file), out);
    updated++;
    console.log("updated", file);
  }
}
console.log("done,", updated, "themes updated");
