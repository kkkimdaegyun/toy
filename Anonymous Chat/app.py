"""
마피아 게임 서버
================
FastAPI + WebSocket 기반 온라인 마피아 게임 서버.
클라이언트 메시지를 받아 GameManager에 위임한다.
"""

from __future__ import annotations

import asyncio
import html
import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from game import CHARACTERS, GameManager, Phase, Role

app = FastAPI()
gm = GameManager()


@app.on_event("startup")
async def startup_event() -> None:
    async def _periodic_lobby_broadcast() -> None:
        while True:
            await asyncio.sleep(3)
            await gm.broadcast_lobby_count()

    asyncio.create_task(_periodic_lobby_broadcast())


# ──────────────────────────────────────────────
# HTTP 라우트
# ──────────────────────────────────────────────

@app.get("/")
async def index() -> HTMLResponse:
    """메인 페이지 제공."""
    html_path = Path(__file__).parent / "index.html"
    return HTMLResponse(html_path.read_text(encoding="utf-8"))


# ──────────────────────────────────────────────
# WebSocket 핸들러
# ──────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    gm.connect_lobby(ws)
    for msg in gm.global_chat_history:
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            pass
    await gm.broadcast_lobby_count()
    await gm.broadcast_room_list()

    try:
        while True:
            raw = await ws.receive_text()
            data: dict[str, Any] = json.loads(raw)
            action = data.get("action", "")

            # ── 로비 광장 자유 채팅 ──
            if action == "global_chat":
                sender = str(data.get("sender", "익명"))[:20]
                content = str(data.get("content", ""))[:300]
                if content.strip():
                    await gm.broadcast_lobby_chat(sender or "익명", content)
                continue

            # ── 방 생성 ──
            if action == "create_room":
                config = data.get("config", {})
                config = {
                    "mafia": max(1, min(4, int(config.get("mafia", 1)))),
                    "doctor": max(0, min(2, int(config.get("doctor", 0)))),
                    "police": max(0, min(2, int(config.get("police", 0)))),
                    "discussion_time": max(15, min(300, int(config.get("discussion_time", 60)))),
                }
                character_id = data.get("character_id", "")
                requested_room_id = str(data.get("room_id", "")).strip()

                room = gm.create_room(ws, config, character_id, requested_room_id=requested_room_id)
                await room.send_to_ws(ws, {
                    "type": "room_created",
                    "room_id": room.room_id,
                    "is_host": True,
                    "config": room.config,
                    "players": [p.to_public_dict() for p in room.players.values()],
                    "min_players": room.min_players(),
                })
                await gm.broadcast_lobby_chat(
                    "📢 시스템",
                    f"🎉 [새 게임방 개설] 방 번호 {room.room_id} 개설! 클릭하여 바로 방 코드 입력 (마피아 {room.config['mafia']}명 방)"
                )
                await gm.broadcast_room_list()

            # ── 방 정보 조회 ──
            elif action == "get_room_info":
                room_id = data.get("room_id", "")
                info = gm.get_room_info(room_id)
                if info:
                    await _send_ws(ws, {
                        "type": "room_info",
                        "room_id": room_id,
                        **info,
                    })
                else:
                    await _send_ws(ws, {
                        "type": "error",
                        "message": "존재하지 않는 방입니다.",
                    })

            # ── 방 참가 ──
            elif action == "join_room":
                room_id = data.get("room_id", "")
                character_id = data.get("character_id", "")
                success, message = gm.join_room(ws, room_id, character_id)

                if success:
                    room = gm.get_room(room_id)
                    if room:
                        # 참가자에게 방 정보 전송
                        await room.send_to_ws(ws, {
                            "type": "room_joined",
                            "room_id": room_id,
                            "is_host": room.host_ws is ws,
                            "players": [p.to_public_dict() for p in room.players.values()],
                            "config": room.config,
                            "min_players": room.min_players(),
                        })
                        # 다른 플레이어들에게 알림
                        player = room.players[character_id]
                        await room.broadcast(
                            {
                                "type": "player_joined",
                                "player": player.to_public_dict(),
                                "player_count": len(room.players),
                                "min_players": room.min_players(),
                            },
                            exclude_ws=ws,
                        )
                        await gm.broadcast_room_list()
                else:
                    await _send_ws(ws, {"type": "error", "message": message})

            # ── 게임 시작 ──
            elif action == "start_game":
                room, char_id = gm.get_player_room(ws)
                if not room:
                    await _send_ws(ws, {"type": "error", "message": "방에 참가하지 않았습니다."})
                    continue
                if room.host_ws is not ws:
                    await _send_ws(ws, {"type": "error", "message": "방장만 게임을 시작할 수 있습니다."})
                    continue
                if len(room.players) < room.min_players():
                    await _send_ws(ws, {
                        "type": "error",
                        "message": f"최소 {room.min_players()}명이 필요합니다. (현재 {len(room.players)}명)",
                    })
                    continue
                await room.start_game()
                await gm.broadcast_room_list()

            # ── 채팅 (토론/로비/사망자) ──
            elif action in ("chat", "dead_chat"):
                room, char_id = gm.get_player_room(ws)
                if not room or not char_id:
                    continue
                player = room.players.get(char_id)
                if not player:
                    continue

                content = str(data.get("content", ""))[:500]
                if not content.strip():
                    continue

                if not player.alive and room.phase != Phase.LOBBY:
                    # 사망자끼리의 유령 채팅방
                    await room.broadcast_dead_chat({
                        "type": "dead_chat",
                        "character": player.to_public_dict(),
                        "content": content,
                    })
                elif player.alive and room.phase in (Phase.DISCUSSION, Phase.LOBBY):
                    await room.broadcast({
                        "type": "chat",
                        "character": player.to_public_dict(),
                        "content": content,
                    })

            # ── 마피아 채팅 (밤) ──
            elif action == "mafia_chat":
                room, char_id = gm.get_player_room(ws)
                if not room or not char_id:
                    continue
                if room.phase != Phase.NIGHT:
                    continue
                player = room.players.get(char_id)
                if not player or not player.alive or player.role != Role.MAFIA:
                    continue

                content = str(data.get("content", ""))[:500]
                if not content.strip():
                    continue

                await room.broadcast(
                    {
                        "type": "mafia_chat",
                        "from": f"{player.character['emoji']} {player.character['name']}",
                        "message": content,
                    },
                    alive_only=True,
                    role_filter=Role.MAFIA,
                )

            # ── 밤 행동 ──
            elif action == "night_action":
                room, char_id = gm.get_player_room(ws)
                if not room or not char_id:
                    continue
                if room.phase != Phase.NIGHT:
                    continue

                target = data.get("target", "")
                await room.handle_night_action(char_id, target)

            # ── 투표 ──
            elif action == "vote":
                room, char_id = gm.get_player_room(ws)
                if not room or not char_id:
                    continue
                if room.phase != Phase.VOTE:
                    continue

                target = data.get("target", "")
                await room.handle_vote(char_id, target)

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        # 연결 해제 처리
        room, char_id = gm.disconnect_ws(ws)
        await gm.broadcast_lobby_count()
        await gm.broadcast_room_list()
        if room and char_id and room.phase == Phase.LOBBY:
            await room.broadcast({
                "type": "player_left",
                "character_id": char_id,
                "player_count": len(room.players),
                "min_players": room.min_players(),
            })


async def _send_ws(ws: WebSocket, data: dict[str, Any]) -> None:
    """WebSocket에 JSON 메시지를 안전하게 전송한다."""
    try:
        await ws.send_text(json.dumps(data, ensure_ascii=False))
    except Exception:
        pass


# ──────────────────────────────────────────────
# 엔트리 포인트
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    print("[Mafia Game Server] http://0.0.0.0:2638")
    uvicorn.run("app:app", host="0.0.0.0", port=2638, reload=False)
