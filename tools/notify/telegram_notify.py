#!/usr/bin/env python3
"""telegram_notify.py — two-way feedback bridge over a Telegram bot (no deps).

Lets the autonomous session PUSH progress summaries + next-step plans to you, and
READ your confirmations back. Uses only the Python stdlib (urllib).

Setup (once):
  1) In Telegram, message @BotFather -> /newbot -> get a BOT TOKEN.
  2) Message your new bot anything (say "hi").
  3) Run:  python telegram_notify.py setup --token <BOT_TOKEN>
     -> it finds your chat id and saves tools/notify/telegram_config.json.
Then:
  python telegram_notify.py send "M2 done: APK built (12MB). Next: install on glasses. Confirm?"
  python telegram_notify.py poll            # print your latest replies (for confirm loop)
"""
import sys, os, json, argparse, urllib.request, urllib.parse

CFG = os.path.join(os.path.dirname(__file__), "telegram_config.json")


def _load():
    cfg = {}
    if os.path.exists(CFG):
        with open(CFG) as f:
            cfg = json.load(f)
    cfg.setdefault("token", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    cfg.setdefault("chat_id", os.environ.get("TELEGRAM_CHAT_ID", ""))
    cfg.setdefault("last_update_id", 0)
    return cfg


def _save(cfg):
    with open(CFG, "w") as f:
        json.dump(cfg, f, indent=2)


def _api(token, method, params=None):
    url = f"https://api.telegram.org/bot{token}/{method}"
    data = urllib.parse.urlencode(params).encode() if params else None
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=30) as r:
        return json.load(r)


def cmd_setup(a):
    token = a.token or _load()["token"]
    if not token:
        print("need --token <BOT_TOKEN>"); return 2
    res = _api(token, "getUpdates")
    if not res.get("ok"):
        print("API error:", res); return 1
    updates = res.get("result", [])
    if not updates:
        print("No messages yet. Send your bot any message in Telegram, then re-run setup."); return 3
    chat_id = str(updates[-1]["message"]["chat"]["id"])
    _save({"token": token, "chat_id": chat_id, "last_update_id": updates[-1]["update_id"]})
    print(f"Saved. chat_id={chat_id}. Test:  python telegram_notify.py send \"hello\"")
    return 0


def cmd_send(a):
    cfg = _load()
    if not (cfg["token"] and cfg["chat_id"]):
        print("not configured (run setup or set env vars)"); return 2
    res = _api(cfg["token"], "sendMessage", {"chat_id": cfg["chat_id"], "text": a.text})
    print("sent" if res.get("ok") else res)
    return 0 if res.get("ok") else 1


def cmd_poll(a):
    cfg = _load()
    if not cfg["token"]:
        print("not configured"); return 2
    res = _api(cfg["token"], "getUpdates", {"offset": cfg["last_update_id"] + 1, "timeout": 0})
    msgs = res.get("result", [])
    for u in msgs:
        m = u.get("message", {})
        print(f"[{m.get('date')}] {m.get('text','')}")
        cfg["last_update_id"] = u["update_id"]
    if msgs:
        _save(cfg)
    elif not a.quiet:
        print("(no new replies)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup"); s.add_argument("--token")
    s.set_defaults(fn=cmd_setup)
    s = sub.add_parser("send"); s.add_argument("text")
    s.set_defaults(fn=cmd_send)
    s = sub.add_parser("poll"); s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_poll)
    a = ap.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
