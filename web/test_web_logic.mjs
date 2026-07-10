// 웹 비-GL 로직 검증(노드). buildWarpSpec(공유) + gridIndices + paramsFromNail + chooseTier.
import { buildWarpSpec } from "./warp_spec.mjs";
import { gridIndices } from "./warp_gl.js";
import { paramsFromNail, chooseTier } from "./design_render.js";

let fails = 0;
function ok(cond, msg) { if (!cond) { console.error("  [FAIL] " + msg); fails++; } else console.log("  [ok] " + msg); }
const finite = (a) => a.every((p) => Number.isFinite(p[0]) && Number.isFinite(p[1]));

// 인덱스
ok(gridIndices(1, 1).length === 6, "gridIndices(1,1)=6");
ok(gridIndices(6, 5).length === 6 * 5 * 6, "gridIndices(6,5)=180");

// params (P0-1: tilt 0)
const n = { cx: 100, cy: 120, ex: 0, ey: -1, len: 80, wid: 50 };
const p = paramsFromNail(n, { scale: 0.9, curve: 0.0 });
ok(p.tilt_deg === 0, "마스크 nail → tilt_deg=0 (P0-1)");
ok(p.axis_minor[0] === 1 && p.axis_minor[1] === 0, "minor ⟂ major");
ok(p.length === 80 && p.width === 50, "len/wid 전달");

// tier
ok(chooseTier({ curv_half_angle: 0, tilt_deg: 0 }) === "plane", "기본 plane");
ok(chooseTier({ curv_half_angle: 0.5, tilt_deg: 0 }) === "mesh", "곡률→mesh");
ok(chooseTier({ curv_half_angle: 0, tilt_deg: 10 }) === "tilt", "tilt→tilt");
ok(chooseTier({ curv_half_angle: 0.5 }, "auto", 5) === "plane", "저fps→plane 강등");

// spec 정점 수
const sp = buildWarpSpec(p, "plane", [1, 1]);
ok(sp.screen.length === 4 && sp.uv.length === 4 && finite(sp.screen), "plane 4정점 유한");
const pm = paramsFromNail(n, { scale: 0.9, curve: 0.8 });
const sm = buildWarpSpec(pm, "mesh", [6, 5]);
ok(sm.screen.length === 42 && finite(sm.screen), "mesh(6,5) 42정점 유한");
ok(gridIndices(6, 5).every((i) => i < 42), "인덱스 정점범위 내");

// 곡률 압축(능선 vs 가장자리, 보조축 투영). grid[6,5] → 행 정점 nx+1=6개.
const rowLen = 5 + 1;
const top = sm.screen.slice(0, rowLen);
const proj = top.map((q) => q[0] * p.axis_minor[0] + q[1] * p.axis_minor[1]);
const gaps = proj.slice(1).map((v, i) => Math.abs(v - proj[i]));   // 길이 5
const mid = Math.floor(gaps.length / 2);
ok(gaps[0] < gaps[mid] && gaps[gaps.length - 1] < gaps[mid], "곡률: 가장자리 s간격 < 능선");

console.log(fails === 0 ? "\nWEB LOGIC OK" : `\n${fails} FAIL`);
process.exit(fails === 0 ? 0 : 1);
