"""스트라바에서 달리기 가져오기 — 삼성 헬스 → 헬스싱크 → 스트라바 → 여기(30분마다). 파라님 2026-09-25.

  앱 열쇠   ~/.helth/strava-app.json {"client_id": "...", "client_secret": "..."} (파라님이 strava.com/settings/api 에서 만든 것)
  토큰      ~/.helth/strava.json (봇이 씀 — /strava <주소> 로 처음 받고, 만료되면 스스로 새로 받음)
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path

import requests

log = logging.getLogger("strava")
HOME = Path(os.path.expanduser("~")) / ".helth"
APP, TOK = HOME / "strava-app.json", HOME / "strava.json"
REDIRECT = "http://localhost/exchange_token"


def _j(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(p: Path, o: dict) -> None:
    HOME.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(o, ensure_ascii=False), encoding="utf-8")
    os.chmod(p, 0o600)


def app() -> dict:
    return _j(APP)


def auth_url() -> str | None:
    a = app()
    if not a.get("client_id"):
        return None
    return ("https://www.strava.com/oauth/authorize?client_id=" + str(a["client_id"]) +
            "&response_type=code&redirect_uri=" + REDIRECT + "&approval_prompt=force&scope=activity:read_all")


def exchange(text: str) -> str:
    """/strava 뒤에 붙인 주소(또는 code)로 토큰을 받는다. 돌려주는 값은 사람에게 보일 한 줄."""
    m = re.search(r"code=([0-9a-f]+)", text) or re.search(r"\b([0-9a-f]{30,})\b", text)
    a = app()
    if not a.get("client_id"):
        return "스트라바 앱 열쇠가 아직 없습니다"
    if not m:
        return "주소에서 code 를 못 찾았습니다 — 허락 뒤 주소창의 주소를 통째로 붙여 주세요"
    r = requests.post("https://www.strava.com/oauth/token", data={
        "client_id": a["client_id"], "client_secret": a["client_secret"], "code": m.group(1), "grant_type": "authorization_code"}, timeout=30)
    if r.status_code != 200:
        return f"토큰 받기 실패({r.status_code}) — 허락을 다시 눌러 새 주소로 해 주세요"
    j = r.json()
    if "activity:read" not in str(j.get("scope", "activity:read_all")) and "activity" not in text:
        pass
    _save(TOK, {k: j.get(k) for k in ("access_token", "refresh_token", "expires_at")} | {"athlete": (j.get("athlete") or {}).get("id")})
    return "✅ 스트라바 연결됨 — 30분마다 달리기를 가져옵니다"


def _token() -> str | None:
    t, a = _j(TOK), app()
    if not t.get("refresh_token") or not a.get("client_id"):
        return None
    if (t.get("expires_at") or 0) < time.time() + 300:
        r = requests.post("https://www.strava.com/oauth/token", data={
            "client_id": a["client_id"], "client_secret": a["client_secret"], "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
        if r.status_code != 200:
            log.warning("스트라바 토큰 갱신 실패 %s", r.status_code)
            return None
        j = r.json()
        t.update({k: j.get(k) for k in ("access_token", "refresh_token", "expires_at")})
        _save(TOK, t)
    return t.get("access_token")


def connected() -> bool:
    return bool(_j(TOK).get("refresh_token"))


def recent_runs(after_epoch: int) -> list[dict] | None:
    """after 이후 달리기 [{id, day, km, minutes}]. 연결 안 됐으면 None."""
    tok = _token()
    if not tok:
        return None
    r = requests.get("https://www.strava.com/api/v3/athlete/activities", params={"after": after_epoch, "per_page": 50},
                     headers={"Authorization": "Bearer " + tok}, timeout=30)
    if r.status_code != 200:
        log.warning("스트라바 읽기 실패 %s", r.status_code)
        return []
    out = []
    for a in r.json():
        kind = a.get("sport_type") or a.get("type")
        if kind not in ("Run", "TrailRun", "VirtualRun"):
            continue
        day = str(a.get("start_date_local", ""))[:10]
        out.append({"id": str(a["id"]), "day": day, "km": round(float(a.get("distance", 0)) / 1000, 2),
                    "minutes": round(float(a.get("moving_time", 0)) / 60, 1)})
    return out
