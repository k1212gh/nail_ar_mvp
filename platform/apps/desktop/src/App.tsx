import { useEffect, useState } from "react";
import { api, token, connectWs } from "./api.js";
import type { StreamSession } from "./api.js";
import { StreamView, DesignsView, DevicesView, SettingsView } from "./views.js";
// 예약/회원은 백오피스 확장 시 되살림 (views.tsx에 코드 유지):
//   import { ReservationsView, MembersView } from "./views.js";

type User = { id: string; name: string; role: string };
type Tab = "stream" | "designs" | "devices" | "settings"; // | "reservations" | "members"

const TABS: { id: Tab; label: string; icon: string }[] = [
  { id: "stream", label: "중계 / 대시보드", icon: "📹" },
  { id: "designs", label: "디자인", icon: "💅" },
  { id: "devices", label: "제원(AR설정)", icon: "🕶️" },
  { id: "settings", label: "설정(검출엔진)", icon: "⚙️" },
  // { id: "reservations", label: "예약", icon: "📅" },
  // { id: "members", label: "회원", icon: "👤" },
];

export function App() {
  const [user, setUser] = useState<User | null>(null);
  const [booting, setBooting] = useState(true);

  useEffect(() => {
    if (!token.get()) { setBooting(false); return; }
    api.me().then(setUser).catch(() => token.clear()).finally(() => setBooting(false));
  }, []);

  if (booting) return <div className="center">로딩…</div>;
  if (!user) return <Login onLogin={setUser} />;
  return <Shell user={user} onLogout={() => { token.clear(); setUser(null); }} />;
}

function Login({ onLogin }: { onLogin: (u: User) => void }) {
  const [name, setName] = useState("사장님");
  const [pw, setPw] = useState("nail1234");
  const [err, setErr] = useState("");
  const submit = async (e: React.FormEvent) => {
    e.preventDefault(); setErr("");
    try { const r = await api.login(name, pw); token.set(r.token); onLogin(r.user); }
    catch (x: any) { setErr(x.message ?? "로그인 실패"); }
  };
  return (
    <div className="center">
      <form className="card login" onSubmit={submit}>
        <h1>💅 네일샵 백오피스</h1>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="이름" />
        <input value={pw} onChange={(e) => setPw(e.target.value)} type="password" placeholder="비밀번호" />
        {err && <div className="err">{err}</div>}
        <button type="submit">로그인</button>
        <div className="hint">기본: 사장님 / nail1234</div>
      </form>
    </div>
  );
}

function Shell({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [tab, setTab] = useState<Tab>("stream");
  const [stream, setStream] = useState<StreamSession>({ id: "s1", state: "off" });

  useEffect(() => connectWs((ev) => { if (ev.type === "stream.state") setStream(ev.session); }), []);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">💅 NailShop</div>
        <nav>
          {TABS.map((t) => (
            <button key={t.id} className={tab === t.id ? "nav active" : "nav"} onClick={() => setTab(t.id)}>
              <span>{t.icon}</span> {t.label}
              {t.id === "stream" && <span className={"dot " + stream.state}>●</span>}
            </button>
          ))}
        </nav>
        <div className="who">
          <div>{user.name} <span className="role">{user.role}</span></div>
          <button className="link" onClick={onLogout}>로그아웃</button>
        </div>
      </aside>
      <main className="content">
        {tab === "stream" && <StreamView stream={stream} setStream={setStream} />}
        {tab === "designs" && <DesignsView />}
        {tab === "devices" && <DevicesView />}
        {tab === "settings" && <SettingsView />}
        {/* 예약/회원 (보류): {tab === "reservations" && <ReservationsView />} {tab === "members" && <MembersView />} */}
      </main>
    </div>
  );
}
