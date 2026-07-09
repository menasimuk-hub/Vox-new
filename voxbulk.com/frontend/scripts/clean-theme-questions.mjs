import fs from "fs";
import path from "path";

const dir = path.resolve("src/components/feedback-survey/themes");
for (const file of fs.readdirSync(dir).filter((f) => f.endsWith(".tsx"))) {
  let src = fs.readFileSync(path.join(dir, file), "utf8");
  src = src.replace(/const QUESTIONS[\s\S]*?\];\r?\n\r?\n/g, "");
  fs.writeFileSync(path.join(dir, file), src);
}
console.log("cleaned");
