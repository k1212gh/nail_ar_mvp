// 패리티 드라이버: fixtures JSON(파일경로 argv[2]) → 각 케이스 buildWarpSpec → stdout JSON.
import { readFileSync } from "node:fs";
import { buildWarpSpec } from "../web/warp_spec.mjs";

const cases = JSON.parse(readFileSync(process.argv[2], "utf-8"));
const out = cases.map(c => buildWarpSpec(c.params, c.tier, c.grid));
process.stdout.write(JSON.stringify(out));
