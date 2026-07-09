import fs from "fs";
import path from "path";

const dir = path.resolve("src/components/feedback-survey/themes");

for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".tsx"))) {
  let src = fs.readFileSync(path.join(dir, file), "utf8");
  src = src.replace(/import \{ createFileRoute \} from "@tanstack\/react-router";\r?\n?/g, "");
  src = src.replace(
    /import \{ SurveyTemplate, type Theme(?:, type Question)?(?:, DEFAULT_QUESTIONS)? \} from "@\/components\/survey\/SurveyTemplate";\r?\n?/g,
    'import type { Theme, Copy } from "../types";\n',
  );
  src = src.replace(/export const Route = createFileRoute[\s\S]*$/m, "");
  src = src.replace(/const T: Theme/g, "export const theme: Theme");
  src = src.replace(/function Art\(\)/g, "export function Art()");
  const copyMatch = src.match(/copy=\{\{([\s\S]*?)\}\}/);
  if (copyMatch && !src.includes("export const copy")) {
    src += `\nexport const copy: Copy = {${copyMatch[1]}};\n`;
  }
  src = src.trim() + "\n";
  fs.writeFileSync(path.join(dir, file), src);
}
console.log("processed", fs.readdirSync(dir).filter((f) => f.endsWith(".tsx")).length, "themes");
