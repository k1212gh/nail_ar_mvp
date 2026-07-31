import { useEffect, useState } from "react";
import { api, BASE } from "./api.js";
import type { StreamSession } from "./api.js";

const RELAY = "http://161.33.176.78:8090";
const VIEW_TOKEN = "0fe58e809a663293ac059252c0d181d8";

function useList<T>(loader: () => Promise<T[]>, deps: any[] = []) {
  const [items, setItems] = useState<T[]>([]);
  const [err, setErr] = useState("");
  const reload = () => loader().then(setItems).catch((e) => setErr(e.message));
  useEffect(() => { reload(); }, deps); // eslint-disable-line
  return { items, reload, err };
}

// ---------- 중계 / 대시보드 ----------
export function StreamView({ stream, setStream }: { stream: StreamSession; setStream: (s: StreamSession) => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [engine, setEngine] = useState<{ edgeEngine?: string; phoneHost?: string }>({});
  const on = stream.state === "on" || stream.state === "starting";
  useEffect(() => { api.stream.get().then((s: any) => setEngine({ edgeEngine: s.edgeEngine, phoneHost: s.phoneHost })).catch(() => {}); }, [stream.state]);
  const engineLabel = engine.edgeEngine === "phone" ? `📱 폰${engine.phoneHost ? ` (${engine.phoneHost})` : " ⚠️IP미설정"}` : "🖥️ 이 PC";
  const toggle = async () => {
    setBusy(true); setErr("");
    try { const r = await api.stream.set(!on); setStream({ ...stream, state: r.state }); }
    catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };
  return (
    <div>
      <h2>중계 / 대시보드</h2>
      <div className="row">
        <div className={"streambox " + stream.state}>
          <div className="statusline">
            상태: <b>{{ off: "꺼짐", starting: "켜는중…", on: "송출중 🔴", error: "오류" }[stream.state]}</b>
            {stream.fps != null && <> · {stream.fps.toFixed(0)}fps</>}
            {stream.glassesConnected != null && <> · 안경 {stream.glassesConnected ? "연결" : "미연결"}</>}
          </div>
          <div className="engine-badge">검출 엔진: <b>{engineLabel}</b></div>
          <button className={on ? "big danger" : "big primary"} onClick={toggle} disabled={busy}>
            {busy ? "…" : on ? "■ 중계 끄기" : "▶ 중계 켜기"}
          </button>
          {err && <div className="err">{err} {err.includes("에이전트") && "— 안경측 PC에서 @nail/agent 실행 필요"}</div>}
        </div>
        <div className="live">
          <div className="livehdr">라이브 뷰</div>
          {on ? <img src={`${RELAY}/stream?token=${VIEW_TOKEN}`} alt="live" />
              : <div className="liveoff">중계가 꺼져 있습니다</div>}
        </div>
      </div>
      <p className="muted">사장님 원격 시청 링크: <code>{RELAY}/monitor?token={VIEW_TOKEN}</code></p>
    </div>
  );
}

// ---------- 예약 ----------
export function ReservationsView() {
  const { items, reload } = useList<any>(() => api.reservations.list());
  const { items: services } = useList<any>(() => api.services.list());
  const [f, setF] = useState({ name: "", phone: "", serviceId: "", date: new Date().toISOString().slice(0, 16) });
  const create = async () => {
    if (!f.name || !f.phone) return;
    const svc = services.find((s) => s.id === f.serviceId);
    const start = new Date(f.date);
    const end = new Date(start.getTime() + (svc?.durationMin ?? 60) * 60000);
    await api.reservations.create({ name: f.name, phone: f.phone, serviceId: f.serviceId || undefined, startAt: start.toISOString(), endAt: end.toISOString() });
    setF({ ...f, name: "", phone: "" }); reload();
  };
  const setStatus = async (id: string, status: string) => { await api.reservations.update(id, { status }); reload(); };
  return (
    <div>
      <h2>예약</h2>
      <div className="card form">
        <input placeholder="고객명" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input placeholder="연락처" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        <select value={f.serviceId} onChange={(e) => setF({ ...f, serviceId: e.target.value })}>
          <option value="">시술 선택</option>
          {services.map((s) => <option key={s.id} value={s.id}>{s.name} ({s.durationMin}분)</option>)}
        </select>
        <input type="datetime-local" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} />
        <button onClick={create}>예약 추가</button>
      </div>
      <table className="tbl">
        <thead><tr><th>시간</th><th>고객</th><th>연락처</th><th>상태</th><th></th></tr></thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.id}>
              <td>{r.startAt.slice(0, 16).replace("T", " ")}</td>
              <td>{r.name}</td><td>{r.phone}</td>
              <td><span className={"badge " + r.status}>{r.status}</span></td>
              <td className="actions">
                <button onClick={() => setStatus(r.id, "confirmed")}>확정</button>
                <button onClick={() => setStatus(r.id, "done")}>완료</button>
                <button className="danger" onClick={() => setStatus(r.id, "canceled")}>취소</button>
              </td>
            </tr>
          ))}
          {!items.length && <tr><td colSpan={5} className="muted">예약 없음</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// ---------- 회원 ----------
export function MembersView() {
  const { items, reload } = useList<any>(() => api.members.list());
  const [f, setF] = useState({ name: "", phone: "", memo: "" });
  const create = async () => { if (!f.name || !f.phone) return; await api.members.create({ ...f, tags: [] }); setF({ name: "", phone: "", memo: "" }); reload(); };
  return (
    <div>
      <h2>회원</h2>
      <div className="card form">
        <input placeholder="이름" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />
        <input placeholder="연락처" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} />
        <input placeholder="메모" value={f.memo} onChange={(e) => setF({ ...f, memo: e.target.value })} />
        <button onClick={create}>회원 추가</button>
      </div>
      <table className="tbl">
        <thead><tr><th>이름</th><th>연락처</th><th>태그</th><th>메모</th><th></th></tr></thead>
        <tbody>
          {items.map((m) => (
            <tr key={m.id}>
              <td>{m.name}</td><td>{m.phone}</td>
              <td>{(m.tags ?? []).map((t: string) => <span key={t} className="tag">{t}</span>)}</td>
              <td>{m.memo}</td>
              <td className="actions"><button className="danger" onClick={async () => { await api.members.remove(m.id); reload(); }}>삭제</button></td>
            </tr>
          ))}
          {!items.length && <tr><td colSpan={5} className="muted">회원 없음</td></tr>}
        </tbody>
      </table>
    </div>
  );
}

// 업로드 이미지를 canvas로 축소(최대 maxPx) → JPEG data URL. DB/전송 부담 최소(≈20~60KB).
function downscaleToDataUrl(file: File, maxPx = 360): Promise<string> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const scale = Math.min(1, maxPx / Math.max(img.width, img.height));
      const w = Math.round(img.width * scale), h = Math.round(img.height * scale);
      const cv = document.createElement("canvas"); cv.width = w; cv.height = h;
      const ctx = cv.getContext("2d"); if (!ctx) return reject(new Error("canvas 미지원"));
      ctx.drawImage(img, 0, 0, w, h);
      resolve(cv.toDataURL("image/jpeg", 0.82));
    };
    img.onerror = () => reject(new Error("이미지 열기 실패"));
    img.src = URL.createObjectURL(file);
  });
}

// ---------- 디자인 ----------
export function DesignsView() {
  const { items, reload } = useList<any>(() => api.designs.list());
  const [name, setName] = useState("");
  const [tags, setTags] = useState("");
  const [thumb, setThumb] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const pick = async (file?: File) => {
    if (!file) return;
    setErr("");
    try { setThumb(await downscaleToDataUrl(file)); if (!name) setName(file.name.replace(/\.[^.]+$/, "")); }
    catch (e: any) { setErr(e.message); }
  };
  const add = async () => {
    if (!name && !thumb) return;
    setBusy(true); setErr("");
    try {
      await api.designs.create({ name: name || "새 디자인", thumbnailUrl: thumb || undefined, tags: tags.split(",").map((t) => t.trim()).filter(Boolean) });
      setName(""); setTags(""); setThumb(""); reload();
    } catch (e: any) { setErr(e.message); } finally { setBusy(false); }
  };

  return (
    <div>
      <h2>네일 디자인 카탈로그</h2>
      <div className="card design-form">
        <label className="uploader">
          {thumb ? <img src={thumb} className="up-preview" /> : <div className="up-empty">📷<br />이미지 선택</div>}
          <input type="file" accept="image/*" hidden onChange={(e) => pick(e.target.files?.[0])} />
        </label>
        <div className="design-fields">
          <input placeholder="디자인명" value={name} onChange={(e) => setName(e.target.value)} />
          <input placeholder="태그 (쉼표로 구분: 프렌치, 글리터)" value={tags} onChange={(e) => setTags(e.target.value)} />
          <div className="row-btns">
            <button className="primary" onClick={add} disabled={busy}>{busy ? "추가 중…" : "디자인 추가"}</button>
            {thumb && <button onClick={() => setThumb("")}>이미지 지우기</button>}
          </div>
          {err && <div className="err">{err}</div>}
          <div className="muted">사진을 올리면 자동으로 축소됩니다. 실제 네일 사진·레퍼런스 이미지를 등록하세요.</div>
        </div>
      </div>
      <div className="grid">
        {items.map((d) => (
          <div key={d.id} className="dcard">
            <div className="dthumb">{d.thumbnailUrl ? <img src={d.thumbnailUrl} /> : "💅"}</div>
            <div className="dname">{d.name}</div>
            <div>{(d.tags ?? []).map((t: string) => <span key={t} className="tag">{t}</span>)}</div>
            <button className="dcard-del" title="삭제" onClick={async () => { if (confirm(`'${d.name}' 삭제?`)) { await api.designs.remove(d.id); reload(); } }}>🗑</button>
          </div>
        ))}
        {!items.length && <div className="muted">디자인 없음 — 위에서 사진을 올려 추가하세요</div>}
      </div>
    </div>
  );
}

// ---------- 설정 (검출 엔진 선택: PC vs 폰) ----------
type Settings = { edgeEngine: "pc" | "phone"; phoneHost: string; phonePort: number; penOcclusion: boolean };

export function SettingsView() {
  const [s, setS] = useState<Settings | null>(null);
  const [saved, setSaved] = useState(false);
  const [err, setErr] = useState("");
  const [testMsg, setTestMsg] = useState("");
  const [testing, setTesting] = useState(false);

  useEffect(() => { api.settings.get().then(setS).catch((e) => setErr(e.message)); }, []);
  if (!s) return <div><h2>설정</h2><div className="muted">{err || "불러오는 중…"}</div></div>;

  const patch = (p: Partial<Settings>) => setS({ ...s, ...p });
  const save = async () => {
    setErr(""); setSaved(false);
    try { const r = await api.settings.update(s); setS(r); setSaved(true); setTimeout(() => setSaved(false), 2000); }
    catch (e: any) { setErr(e.message); }
  };
  const test = async () => {
    setTesting(true); setTestMsg("");
    try { const r = await api.settings.testEdge({ host: s.phoneHost, port: s.phonePort }); setTestMsg((r.ok ? "✅ " : "❌ ") + r.message); }
    catch (e: any) { setTestMsg("❌ " + e.message); } finally { setTesting(false); }
  };

  return (
    <div>
      <h2>설정 — 손톱 검출 엔진</h2>
      <p className="muted">손톱 검출(YOLO)을 <b>어디서 돌릴지</b> 고릅니다. 매장 상황에 맞게 선택하세요.</p>

      <div className="row">
        <label className={"engine-card" + (s.edgeEngine === "pc" ? " sel" : "")} onClick={() => patch({ edgeEngine: "pc" })}>
          <div className="ec-hd"><input type="radio" checked={s.edgeEngine === "pc"} readOnly /> 🖥️ <b>이 PC (권장)</b></div>
          <ul>
            <li>이 매장 PC의 GPU로 검출 — 가장 빠르고 정확</li>
            <li>안경을 USB로 이 PC에 연결</li>
            <li>추가 설치 없음 (에이전트만 실행)</li>
          </ul>
        </label>
        <label className={"engine-card" + (s.edgeEngine === "phone" ? " sel" : "")} onClick={() => patch({ edgeEngine: "phone" })}>
          <div className="ec-hd"><input type="radio" checked={s.edgeEngine === "phone"} readOnly /> 📱 <b>폰 (온디바이스)</b></div>
          <ul>
            <li>폰이 직접 검출 — PC 없이 폰+안경만 (약 7.5fps)</li>
            <li>안경과 폰이 <b>같은 WiFi</b>에 있어야 함</li>
            <li>폰에 "Nail Edge Server" 앱 설치 필요</li>
          </ul>
        </label>
      </div>

      {s.edgeEngine === "phone" && (
        <div className="card">
          <h3>📱 폰 에지 설정</h3>
          <div className="form">
            <label>폰 IP <input placeholder="예: 192.168.0.23" value={s.phoneHost} onChange={(e) => patch({ phoneHost: e.target.value })} /></label>
            <label>포트 <input type="number" style={{ width: 90 }} value={s.phonePort} onChange={(e) => patch({ phonePort: Number(e.target.value) || 8444 })} /></label>
            <button onClick={test} disabled={testing || !s.phoneHost}>{testing ? "확인 중…" : "연결 테스트"}</button>
          </div>
          {testMsg && <div className={testMsg.startsWith("✅") ? "ok-msg" : "err"}>{testMsg}</div>}
          <details className="guide">
            <summary>폰 설치 방법 (처음 1회)</summary>
            <ol>
              <li>폰과 안경을 <b>같은 WiFi</b>(매장 공유기)에 연결합니다.</li>
              <li>폰에 <code>app-debug.apk</code>(Nail Edge Server)를 설치: <code>adb install -r app-debug.apk</code></li>
              <li>폰에서 <b>"Nail Edge Server"</b> 앱 실행 → <b>[시작]</b> → 화면에 표시된 <b>폰 IP</b> 확인.</li>
              <li>그 IP를 위 칸에 입력하고 <b>연결 테스트</b> → ✅ 나오면 저장.</li>
              <li>이후 <b>중계 켜기</b>를 누르면 안경이 폰 검출로 동작합니다.</li>
            </ol>
            <p className="muted">APK 빌드/원리: <code>docs/PHONE_EDGE_SERVER_PLAN.md</code>. 폰 실측 320²@0.08 = 134ms(7.5fps).</p>
          </details>
        </div>
      )}

      <div className="card">
        <label className="chk"><input type="checkbox" checked={s.penOcclusion} onChange={(e) => patch({ penOcclusion: e.target.checked })} /> 펜/도구 <b>가림방지</b> 사용 (손톱 위 펜을 디자인이 덮지 않게)</label>
      </div>

      <div className="save-row">
        <button className="big primary" onClick={save}>설정 저장</button>
        {saved && <span className="ok-msg">저장됨 ✓</span>}
        {err && <span className="err">{err}</span>}
      </div>

      <h2 style={{ marginTop: 32 }}>계정</h2>
      <PasswordCard />
    </div>
  );
}

// 비밀번호 변경 카드 (기본 nail1234 → 실운영 전 교체)
function PasswordCard() {
  const [cur, setCur] = useState("");
  const [nx, setNx] = useState("");
  const [nx2, setNx2] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const submit = async () => {
    setMsg(null);
    if (nx.length < 4) return setMsg({ ok: false, text: "새 비밀번호는 4자 이상" });
    if (nx !== nx2) return setMsg({ ok: false, text: "새 비밀번호가 서로 다릅니다" });
    try { await api.changePassword(cur, nx); setMsg({ ok: true, text: "비밀번호가 변경되었습니다" }); setCur(""); setNx(""); setNx2(""); }
    catch (e: any) { setMsg({ ok: false, text: e.message }); }
  };
  return (
    <div className="card">
      <h3>비밀번호 변경</h3>
      <div className="form">
        <input type="password" placeholder="현재 비밀번호" value={cur} onChange={(e) => setCur(e.target.value)} />
        <input type="password" placeholder="새 비밀번호" value={nx} onChange={(e) => setNx(e.target.value)} />
        <input type="password" placeholder="새 비밀번호 확인" value={nx2} onChange={(e) => setNx2(e.target.value)} />
        <button className="primary" onClick={submit} disabled={!cur || !nx}>변경</button>
      </div>
      {msg && <div className={msg.ok ? "ok-msg" : "err"}>{msg.text}</div>}
    </div>
  );
}

// ---------- 제원 (AR 세팅) ----------
export function DevicesView() {
  const { items, reload } = useList<any>(() => api.deviceProfiles.list());
  return (
    <div>
      <h2>제원 (안경/edge AR 설정)</h2>
      <p className="muted">기존 push_calib를 대체 — 여기서 세팅을 관리하고 적용합니다.</p>
      {items.map((p) => (
        <div key={p.id} className="card devcard">
          <div className="devhdr">
            <b>{p.label}</b> <span className="tag">{p.type}</span>
            {p.active && <span className="badge confirmed">활성</span>}
            {!p.active && <button onClick={async () => { await api.deviceProfiles.update(p.id, { active: true }); reload(); }}>활성화</button>}
          </div>
          <table className="kv">
            <tbody>{Object.entries(p.settings ?? {}).map(([k, v]) => <tr key={k}><td>{k}</td><td><b>{String(v)}</b></td></tr>)}</tbody>
          </table>
        </div>
      ))}
      {!items.length && <div className="muted">제원 프로필 없음</div>}
    </div>
  );
}
