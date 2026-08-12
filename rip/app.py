"""
퇴사자 사이버 묘지 (R.I.P. - Resign In Peace)
=============================================
먼저 떠난 동료들을 묘비로 기리고,
내가 마지막으로 퇴사하는 날 '최후의 버튼'으로 서버를 영면에 들게 하는
슬프고도 웃긴 토이 프로젝트의 백엔드.

- Framework: FastAPI (가볍고 빠르고, 무엇보다 죽기 좋음)
- DB: SQLite
- 보안: HTTPS 없음. 순수 HTTP. 우리는 떠날 사람들이니까.
"""

import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

# Windows 콘솔(cp949)에서도 한글/이모지 출력이 깨지거나 죽지 않도록 UTF-8 강제
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Windows 콘솔 출력 코드페이지를 UTF-8(65001)로 — 배너 한글이 깨지지 않도록
if sys.platform == "win32":
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# 경로 설정
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# DATA_DIR 는 Docker 볼륨으로 마운트할 수 있게 환경변수로 분리.
# (서버는 죽어도 묘비 기록은 남아야 하니까... 추억은 영원히)
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "graveyard.db"


# ---------------------------------------------------------------------------
# DB 유틸
# ---------------------------------------------------------------------------
def init_db() -> None:
    """묘지(테이블)를 처음 한 번 조성한다."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS graves (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,          -- 이름 / 닉네임
                job         TEXT NOT NULL,          -- 직무
                resign_date TEXT NOT NULL,          -- 퇴사일 (YYYY-MM-DD)
                tags        TEXT NOT NULL DEFAULT '',  -- 특징/키워드 (#태그 형태)
                epitaph     TEXT NOT NULL DEFAULT '',  -- 묘비명 / 한 줄 평
                editor      TEXT NOT NULL DEFAULT '',  -- 기록/수정한 사람 (수정자)
                icon        TEXT NOT NULL DEFAULT '',  -- 묘비 아이콘 (✝ / 🌱 / 🕊️)
                created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        # 기존 DB 호환: 예전 버전 DB 에 없는 컬럼이 있으면 추가한다.
        cols = [r[1] for r in conn.execute("PRAGMA table_info(graves)").fetchall()]
        for col in ("editor", "icon"):
            if col not in cols:
                conn.execute(f"ALTER TABLE graves ADD COLUMN {col} TEXT NOT NULL DEFAULT ''")
        # 만든 사람(크레딧) 명단 — 처음 등장한 순서대로 누적(추가 전용)
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS credits (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL UNIQUE,
                created_at  TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
            """
        )
        # 기존 묘비 기록자(editor)들을 첫 등장 순서로 크레딧에 채워 넣는다.
        conn.execute(
            """
            INSERT OR IGNORE INTO credits (name)
            SELECT TRIM(editor) FROM graves
             WHERE TRIM(editor) <> ''
             GROUP BY TRIM(editor)
             ORDER BY MIN(id)
            """
        )
        conn.commit()


@contextmanager
def get_db():
    """요청마다 커넥션을 열고 닫는 단순한 컨텍스트 매니저."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def add_credit(conn, name: str) -> None:
    """만든 사람(크레딧)을 명단에 추가한다 (이미 있으면 무시 — 추가 전용)."""
    name = (name or "").strip()
    if name:
        conn.execute("INSERT OR IGNORE INTO credits (name) VALUES (?)", (name,))


# ---------------------------------------------------------------------------
# 입력 모델
# ---------------------------------------------------------------------------
class GraveIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=30)
    job: str = Field(..., min_length=1, max_length=40)
    resign_date: str = Field(..., min_length=1, max_length=20)
    tags: str = Field(default="", max_length=200)
    epitaph: str = Field(default="", max_length=200)
    editor: str = Field(default="", max_length=30)  # 기록/수정한 사람 (수정자)
    icon: str = Field(default="", max_length=8)      # 묘비 아이콘 (✝ / 🌱 / 🕊️)

    @field_validator("name", "job", "resign_date")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("필수 항목은 비워둘 수 없습니다.")
        return v

    @field_validator("tags", "epitaph", "editor")
    @classmethod
    def strip_optional(cls, v: str) -> str:
        return v.strip()

    @field_validator("icon")
    @classmethod
    def valid_icon(cls, v: str) -> str:
        # 정해진 3개 아이콘만 허용, 그 외(또는 빈 값)는 '' → 화면에서 기본(✝)로 표시
        v = (v or "").strip()
        return v if v in {"✝", "🌱", "🕊️"} else ""


# ---------------------------------------------------------------------------
# 앱
# ---------------------------------------------------------------------------
app = FastAPI(
    title="퇴사자 사이버 묘지",
    description="Resign In Peace 🪦",
    version="1.0.0-RIP",
)


# 모듈이 로드되는 즉시 묘지를 조성한다.
# (uvicorn 의 lifespan 이든, 직접 import 든 상관없이 테이블 존재를 보장)
init_db()


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    """묘지 정문(메인 페이지)."""
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/graves")
def list_graves() -> list[dict]:
    """안장된 모든 퇴사자 목록 (최근 퇴사 순)."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM graves ORDER BY resign_date DESC, id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/api/graves", status_code=201)
def create_grave(grave: GraveIn) -> dict:
    """새 묘비를 세운다 (한 명의 퇴사를 기록한다)."""
    with get_db() as conn:
        cur = conn.execute(
            """
            INSERT INTO graves (name, job, resign_date, tags, epitaph, editor, icon)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (grave.name, grave.job, grave.resign_date, grave.tags, grave.epitaph, grave.editor, grave.icon),
        )
        new_id = cur.lastrowid
        row = conn.execute("SELECT * FROM graves WHERE id = ?", (new_id,)).fetchone()
        # 기록자를 크레딧(만든 사람) 명단에 추가
        add_credit(conn, grave.editor)
    return dict(row)


@app.put("/api/graves/{grave_id}")
def update_grave(grave_id: int, grave: GraveIn) -> dict:
    """기존 묘비 내용을 수정한다 (수정자 이름 포함)."""
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE graves
               SET name = ?, job = ?, resign_date = ?, tags = ?, epitaph = ?, editor = ?, icon = ?
             WHERE id = ?
            """,
            (
                grave.name,
                grave.job,
                grave.resign_date,
                grave.tags,
                grave.epitaph,
                grave.editor,
                grave.icon,
                grave_id,
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="그런 묘비는 없습니다.")
        row = conn.execute("SELECT * FROM graves WHERE id = ?", (grave_id,)).fetchone()
        # 수정자를 크레딧(만든 사람) 명단에 추가
        add_credit(conn, grave.editor)
    return dict(row)


@app.delete("/api/graves/{grave_id}", status_code=204)
def delete_grave(grave_id: int):
    """묘비 철거 (잘못 새겼을 때 — 파묘)."""
    with get_db() as conn:
        cur = conn.execute("DELETE FROM graves WHERE id = ?", (grave_id,))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="그런 묘비는 없습니다.")
    return JSONResponse(status_code=204, content=None)


@app.get("/api/credits")
def list_credits() -> list:
    """이 묘지를 만든 사람들 명단 (처음 등장한 순서대로)."""
    with get_db() as conn:
        rows = conn.execute("SELECT name FROM credits ORDER BY id").fetchall()
    return [r["name"] for r in rows]


def _lan_ips() -> list:
    """같은 네트워크의 동료에게 공유할 이 컴퓨터의 LAN IP 목록."""
    import socket

    ips = set()
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))  # 실제 패킷은 안 나감 — 라우팅용 로컬 IP만 얻음
        ips.add(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None):
            ip = info[4][0]
            if "." in ip and not ip.startswith("127."):
                ips.add(ip)
    except Exception:
        pass
    return sorted(ips)


if __name__ == "__main__":
    # 로컬에서 Docker 없이 바로 실행할 때를 위한 진입점 (python app.py).
    # HTTPS 없음. 순수 HTTP. 같은 네트워크(LAN)의 동료도 접속 가능.
    import threading
    import webbrowser

    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")  # 0.0.0.0 = 같은 네트워크의 동료도 접속 가능
    port = int(os.environ.get("PORT", 8000))

    print("=" * 64)
    print("  🪦  퇴사자 사이버 묘지  (Resign In Peace)")
    print("=" * 64)
    print(f"  이 컴퓨터에서      :  http://localhost:{port}")
    for ip in _lan_ips():
        print(f"  같은 네트워크 동료 :  http://{ip}:{port}")
    print(f"  기록 파일          :  {DB_PATH}")
    print("-" * 64)
    print("  · 등록한 묘비는 위 SQLite 파일에 영구 저장됩니다 (껐다 켜도 유지).")
    print(f"  · 같은 와이파이/랜의 동료는 위 'http://<IP>:{port}' 주소로 접속해")
    print("    묘비를 보거나 추가할 수 있습니다.")
    print("  · Windows 방화벽 허용 창이 뜨면 '액세스 허용'을 눌러야 동료가 접속됩니다.")
    print("  · 종료: 이 창에서 Ctrl + C  (기록은 유지)")
    print("=" * 64)

    # 서버가 뜬 직후 브라우저 자동 열기 (OPEN_BROWSER=0 으로 끌 수 있음)
    if os.environ.get("OPEN_BROWSER", "1") != "0":
        threading.Timer(1.5, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    uvicorn.run(
        "app:app",
        host=host,
        port=port,
        reload=False,  # reload=True 면 서버가 부활해버려서 '최후의 버튼'이 무력화됨
    )
