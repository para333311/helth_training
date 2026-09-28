"""삼성헬스 운동 가져오기 — 삼성헬스 → Health Sync → 구글 드라이브 「Health Sync 활동」 CSV → 여기(15분마다). 파라님 2026-09-28.

  토큰  ~/.volcano/uploader/token_drive.json (paracano 드라이브 토큰 · imissyou55aa · Health Sync 도 같은 계정에 쓴다)
        읽기만 한다 — 새 접근 토큰은 메모리에서만 받고 파일은 건드리지 않는다(주인은 paracano 쪽).
  파일  「RUNNING 2026.09.28 20.28 Samsung Health.csv」 한 운동 = 한 파일. 파일 이름이 중복 방지 열쇠.

스트라바 길(bot/strava.py)을 대신한다 — 연결된 적 없던 길이라 지웠다.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import os
import re
from datetime import date
from pathlib import Path

import requests

log = logging.getLogger("shealth")
TOKEN = Path(os.path.expanduser("~")) / ".volcano" / "uploader" / "token_drive.json"
FOLDER = "Health Sync 활동"
API = "https://www.googleapis.com/drive/v3/files"
RUN_TYPES = {"RUNNING", "TREADMILL"}
NAMES = {"RUNNING": "달리기", "TREADMILL": "러닝머신", "WALKING": "걷기", "CYCLING": "자전거", "HIKING": "등산",
         "SWIMMING": "수영", "STRENGTH_TRAINING": "근력운동", "WEIGHTLIFTING": "웨이트", "YOGA": "요가",
         "PILATES": "필라테스", "ROWING_MACHINE": "로잉", "ELLIPTICAL": "일립티컬", "STAIR_CLIMBING": "계단"}


def connected() -> bool:
    return TOKEN.exists()


def _access() -> str:
    t = json.loads(TOKEN.read_text(encoding="utf-8"))
    r = requests.post(t.get("token_uri") or "https://oauth2.googleapis.com/token", data={
        "client_id": t["client_id"], "client_secret": t["client_secret"],
        "refresh_token": t["refresh_token"], "grant_type": "refresh_token"}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def _num(v) -> float:
    try:
        return float(v)
    except Exception:
        return 0.0


def noise(w: dict) -> bool:
    """3분 미만 · 거리 없는 10분 미만은 워치 자동 감지 잡음."""
    return w["seconds"] < 180 or (w["km"] < 0.05 and w["seconds"] < 600)


def parse(name: str, text: str) -> dict | None:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("﻿"))))
    if not rows:
        return None
    r = rows[0]
    m = re.match(r"(\d{4})\.(\d\d)\.(\d\d) (\d\d):(\d\d)", r.get("날짜", ""))
    if not m:
        return None
    kind = (r.get("활동 유형") or "").strip()
    return {"id": name, "kind": kind, "name": NAMES.get(kind, kind.replace("_", " ").title()),
            "day": date(int(m.group(1)), int(m.group(2)), int(m.group(3))), "hm": f"{m.group(4)}:{m.group(5)}",
            "seconds": _num(r.get("경과 시간")), "km": _num(r.get("거리(km)")), "steps": int(_num(r.get("걸음"))),
            "hr": int(_num(r.get("평균 심박수"))), "kcal": int(_num(r.get("칼로리 (kcal)"))),
            "run": kind in RUN_TYPES}


def fetch(seen) -> list[dict]:
    """아직 안 본 운동들(날짜·시각 순). seen(name) -> bool."""
    tok = _access()
    h = {"Authorization": "Bearer " + tok}
    q = f"name = '{FOLDER}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    fs = requests.get(API, headers=h, params={"q": q, "fields": "files(id)"}, timeout=30).json().get("files", [])
    if not fs:
        log.warning("드라이브에 「%s」 폴더가 없다", FOLDER)
        return []
    out, page = [], None
    while True:
        p = {"q": f"'{fs[0]['id']}' in parents and name contains '.csv' and trashed = false",
             "fields": "nextPageToken, files(id,name)", "pageSize": 200}
        if page:
            p["pageToken"] = page
        j = requests.get(API, headers=h, params=p, timeout=30).json()
        for f in j.get("files", []):
            if seen(f["name"]):
                continue
            body = requests.get(f"{API}/{f['id']}", headers=h, params={"alt": "media"}, timeout=30)
            w = parse(f["name"], body.content.decode("utf-8", "replace")) if body.ok else None
            if w:
                out.append(w)
        page = j.get("nextPageToken")
        if not page:
            break
    return sorted(out, key=lambda w: (w["day"], w["hm"]))


def pace(km: float, minutes: float | None) -> str:
    if not minutes or km < 0.05:
        return ""
    s = minutes * 60 / km
    return f"{int(s // 60)}'{int(s % 60):02d}\""


def dur(minutes: float) -> str:
    s = int(round(minutes * 60))
    h, m, sec = s // 3600, s % 3600 // 60, s % 60
    return f"{h}시간 {m}분" if h else (f"{m}분 {sec}초" if m < 10 else f"{m}분")
