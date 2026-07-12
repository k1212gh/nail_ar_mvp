/* app.js — 무빌드 React(UMD)+htm. 서버는 안 건드리고 버튼으로 오케스트레이션만. */
const html = htm.bind(React.createElement);
const { useState, useEffect, useRef, useCallback } = React;

function Pill({ on, warn, children }) {
  const cls = on ? "pill on" : warn ? "pill warn" : "pill off";
  return html`<span className=${cls}>${children}</span>`;
}

function App() {
  const [info, setInfo] = useState(null);
  const [run, setRun] = useState([]);          // 실행중 프로세스명
  const [tunnel, setTunnel] = useState(false);
  const [glasses, setGlasses] = useState(false);
  const [nails, setNails] = useState(null);
  const [logs, setLogs] = useState([]);
  const [frame, setFrame] = useState(null);
  const [detect, setDetect] = useState(null);
  const [cross, setCross] = useState({ x: 0.15, y: 0.15, slot: "TL" });
  const logRef = useRef(null);

  const push = useCallback((name, line) => {
    setLogs((L) => [...L.slice(-400), { name, line, t: Date.now() }]);
    if (/nails=(\d+)/.test(line)) { const m = line.match(/nails=(\d+)/); setNails(+m[1]); }
  }, []);

  useEffect(() => {
    window.api.info().then(setInfo);
    window.api.onLog(({ name, line }) => push(name, line));
    const poll = async () => {
      setRun(await window.api.running());
      const rl = await window.api.reverseList(); setTunnel(/tcp:8443/.test(rl));
      const dv = await window.api.devices(); setGlasses(/\bdevice\b/.test(dv));
      const f = await window.api.frame("frame"); if (f.ok) setFrame(f.dataUrl);
      const d = await window.api.frame("detect"); if (d.ok) setDetect(d.dataUrl);
    };
    poll(); const id = setInterval(poll, 1500); return () => clearInterval(id);
  }, [push]);

  useEffect(() => { if (logRef.current) logRef.current.scrollTop = logRef.current.scrollHeight; }, [logs]);

  const serverOn = run.includes("edge_serve");
  const eyeOn = run.includes("eye_reg");
  const act = (fn) => async () => { const r = await fn(); if (r && r.msg) push("ui", r.msg); if (typeof r === "string") push("adb", r); };

  return html`
    <header>
      <h1>💅 네일-AR 보정 스테이션</h1>
      <${Pill} on=${serverOn}>에지서버 ${serverOn ? "ON" : "off"}<//>
      <${Pill} on=${glasses} warn=${!glasses}>안경 ${glasses ? "연결" : "미연결"}<//>
      <${Pill} on=${tunnel} warn=${!tunnel}>터널 ${tunnel ? "OK" : "끊김"}<//>
      <${Pill} on=${eyeOn}>눈추적 ${eyeOn ? "ON" : "off"}<//>
      <${Pill}>nails ${nails ?? "-"}<//>
      <span style=${{ marginLeft: "auto", color: "var(--mut)", fontSize: "12px" }}>
        ${info ? (info.pyExists ? "venv ✓" : "venv 없음!") : ""}
      </span>
    </header>
    <main>
      <div className="side">
        <h2>서버 / 안경</h2>
        <button className=${serverOn ? "danger" : "primary"}
          onClick=${act(() => serverOn ? window.api.stopServer() : window.api.startServer())}>
          ${serverOn ? "⏹ 에지서버 정지" : "▶ 에지서버 시작"}</button>
        <button onClick=${act(() => window.api.connectGlasses("com.DefaultCompany.NailMesh"))}>
          🔌 안경 연결 (reverse+wake+NailMesh)</button>
        <button onClick=${act(() => window.api.connectGlasses("com.DefaultCompany.Nail"))}>
          🔌 안경 연결 (Nail 앱)</button>

        <h2>눈추적 (외부캠 자동정합)</h2>
        <button className=${eyeOn ? "danger" : ""}
          onClick=${act(() => eyeOn ? window.api.stopEyeReg() : window.api.startEyeReg({ fps: 2, package: "com.DefaultCompany.NailMesh", calibScale: 1.3 }))}>
          ${eyeOn ? "⏹ 눈추적 정지" : "👁 눈추적 시작 (NailMesh)"}</button>
        <small class="mut">웹캠으로 눈 측정 → A/B push. 안경 쓰고 웹캠 응시.</small>

        <h2>모니터 4점 보정 (마법사)</h2>
        <div className="wiz">
          <div className="step"><span className="num">1</span>
            <button onClick=${() => window.api.monitorCalib("show-pattern")}>모니터 패턴 표시</button></div>
          <div className="step"><span className="num">2</span>
            <button onClick=${() => window.api.monitorCalib("detect")}>모서리 검출 + PnP</button></div>
          <div className="step"><span className="num">3</span>
            <select value=${cross.slot} onChange=${(e) => setCross({ ...cross, slot: e.target.value })}>
              ${["TL", "TR", "BR", "BL"].map((s) => html`<option key=${s}>${s}</option>`)}
            </select>
            <input type="number" step="0.05" value=${cross.x} style=${{ width: "60px" }}
              onChange=${(e) => setCross({ ...cross, x: +e.target.value })} />
            <input type="number" step="0.05" value=${cross.y} style=${{ width: "60px" }}
              onChange=${(e) => setCross({ ...cross, y: +e.target.value })} />
          </div>
          <div className="row">
            <button onClick=${() => window.api.monitorCalib("crosshair", ["--x", String(cross.x), "--y", String(cross.y)])}>크로스헤어 이동</button>
            <button onClick=${() => window.api.monitorCalib("record", ["--slot", cross.slot, "--x", String(cross.x), "--y", String(cross.y)])}>대응점 기록</button>
          </div>
          <div className="row">
            <button onClick=${() => window.api.monitorCalib("status")}>수집 상태</button>
            <button onClick=${() => window.api.monitorCalib("solve", ["--push"])}>풀기+적용</button>
            <button onClick=${() => window.api.monitorCalib("reset")}>초기화</button>
          </div>
          <small class="mut">2~3개 거리에서 4모서리 정렬·기록 → 풀기. VAC 흐림이 정밀도 상한.</small>
        </div>
      </div>

      <div className="content">
        <div className="preview">
          <figure><figcaption>안경 카메라 (라이브)</figcaption>
            <img src=${frame || ""} alt="glasses" /></figure>
          <figure><figcaption>검출 오버레이 (nails>0일 때)</figcaption>
            <img src=${detect || ""} alt="detect" /></figure>
        </div>
        <div className="log" ref=${logRef}>
          ${logs.map((l, i) => html`<div className="l" key=${i}>
            <span className=${l.line.includes("exit") || /error|Error|ERR/.test(l.line) ? "err" : "tag"}>[${l.name}]</span> ${l.line}</div>`)}
          ${logs.length === 0 ? html`<div className="l" style=${{ color: "var(--mut)" }}>로그가 여기 표시됩니다. "에지서버 시작"부터 눌러보세요.</div>` : null}
        </div>
      </div>
    </main>`;
}

ReactDOM.createRoot(document.getElementById("root")).render(html`<${App} />`);
