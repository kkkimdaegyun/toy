"""
마피아 게임 엔진
================
온라인 마피아 게임의 핵심 로직을 담당하는 모듈.
Phase 관리, 역할 배정, 밤/낮 액션, 투표, 승리 조건 등을 처리한다.
"""

from __future__ import annotations

import asyncio
import json
import random
import secrets
import string
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import WebSocket

# ──────────────────────────────────────────────
# 상수: 캐릭터 목록 (최대 12명)
# ──────────────────────────────────────────────
CHARACTERS: list[dict[str, str]] = [
    {"id": "wolf", "emoji": "🐺", "name": "늑대"},
    {"id": "fox", "emoji": "🦊", "name": "여우"},
    {"id": "cat", "emoji": "🐱", "name": "고양이"},
    {"id": "rabbit", "emoji": "🐰", "name": "토끼"},
    {"id": "bear", "emoji": "🐻", "name": "곰"},
    {"id": "lion", "emoji": "🦁", "name": "사자"},
    {"id": "frog", "emoji": "🐸", "name": "개구리"},
    {"id": "penguin", "emoji": "🐧", "name": "펭귄"},
    {"id": "dog", "emoji": "🐶", "name": "강아지"},
    {"id": "owl", "emoji": "🦉", "name": "부엉이"},
    {"id": "tiger", "emoji": "🐯", "name": "호랑이"},
    {"id": "panda", "emoji": "🐼", "name": "판다"},
]

CHARACTER_MAP: dict[str, dict[str, str]] = {c["id"]: c for c in CHARACTERS}


# ──────────────────────────────────────────────
# Enum: 게임 페이즈 / 역할
# ──────────────────────────────────────────────
class Phase(str, Enum):
    LOBBY = "lobby"
    NIGHT = "night"
    DAY_RESULT = "day_result"
    DISCUSSION = "discussion"
    VOTE = "vote"
    VOTE_RESULT = "vote_result"
    GAME_OVER = "game_over"


class Role(str, Enum):
    MAFIA = "mafia"
    DOCTOR = "doctor"
    POLICE = "police"
    CITIZEN = "citizen"


# ──────────────────────────────────────────────
# Player 클래스
# ──────────────────────────────────────────────
@dataclass
class Player:
    """개별 플레이어 상태를 관리한다."""

    ws: WebSocket
    character_id: str
    character: dict[str, str]
    role: Role | None = None
    alive: bool = True
    night_action_target: str | None = None  # 밤 행동 대상 (character_id)
    vote_target: str | None = None  # 투표 대상 (character_id)
    self_save_used: bool = False  # 의사: 자가 치료 1회 제한

    def to_public_dict(self) -> dict[str, Any]:
        """클라이언트에 공개되는 플레이어 정보."""
        return {
            "character_id": self.character_id,
            "emoji": self.character["emoji"],
            "name": self.character["name"],
            "alive": self.alive,
        }


# ──────────────────────────────────────────────
# Room 클래스
# ──────────────────────────────────────────────
class Room:
    """하나의 게임 방을 관리한다."""

    def __init__(
        self,
        room_id: str,
        host_ws: WebSocket,
        config: dict[str, int],
    ) -> None:
        self.room_id: str = room_id
        self.host_ws: WebSocket = host_ws
        self.config: dict[str, int] = config  # {mafia, doctor, police}

        self.players: dict[str, Player] = {}  # character_id → Player
        self.ws_to_character: dict[int, str] = {}  # id(ws) → character_id

        self.phase: Phase = Phase.LOBBY
        self.round_number: int = 0
        self.phase_timer_task: asyncio.Task[None] | None = None

        # 밤 투표 (마피아끼리), 낮 투표
        self.mafia_votes: dict[str, str] = {}  # mafia_char_id → target_char_id
        self.day_votes: dict[str, str] = {}  # voter_char_id → target_char_id

        # 이전 판 마피아 기록 (연속 마피아 방지)
        self.last_mafia_chars: set[str] = set()

    # ── 유틸 프로퍼티 ──

    @property
    def alive_players(self) -> dict[str, Player]:
        """생존 플레이어만 반환."""
        return {cid: p for cid, p in self.players.items() if p.alive}

    @property
    def alive_mafia(self) -> dict[str, Player]:
        """생존 마피아만 반환."""
        return {
            cid: p
            for cid, p in self.players.items()
            if p.alive and p.role == Role.MAFIA
        }

    @property
    def alive_non_mafia(self) -> dict[str, Player]:
        """생존 시민 팀만 반환."""
        return {
            cid: p
            for cid, p in self.players.items()
            if p.alive and p.role != Role.MAFIA
        }

    def min_players(self) -> int:
        """최소 플레이어 수: 설정된 특수 역할 + 시민 최소 1명."""
        return self.config["mafia"] + self.config["doctor"] + self.config["police"] + 1

    # ── 통신 ──

    async def broadcast(
        self,
        data: dict[str, Any],
        alive_only: bool = False,
        role_filter: Role | None = None,
        exclude_ws: WebSocket | None = None,
    ) -> None:
        """조건에 맞는 플레이어들에게 메시지를 전송한다."""
        msg = json.dumps(data, ensure_ascii=False)
        for player in self.players.values():
            if alive_only and not player.alive:
                continue
            if role_filter is not None and player.role != role_filter:
                continue
            if exclude_ws is not None and player.ws is exclude_ws:
                continue
            try:
                await player.ws.send_text(msg)
            except Exception:
                pass  # 연결 끊긴 플레이어 무시

    async def send_to(self, character_id: str, data: dict[str, Any]) -> None:
        """특정 캐릭터에게 메시지를 전송한다."""
        player = self.players.get(character_id)
        if player:
            try:
                await player.ws.send_text(json.dumps(data, ensure_ascii=False))
            except Exception:
                pass

    async def send_to_ws(self, ws: WebSocket, data: dict[str, Any]) -> None:
        """특정 WebSocket에 메시지를 전송한다."""
        try:
            await ws.send_text(json.dumps(data, ensure_ascii=False))
        except Exception:
            pass

    # ── 역할 배정 ──

    def assign_roles(self) -> None:
        """설정에 따라 무작위로 역할을 배정한다. (연속 마피아 방지 + 암호학적 난수 적용)"""
        sys_rand = secrets.SystemRandom()
        all_ids = list(self.players.keys())
        mafia_count = min(self.config["mafia"], len(all_ids))

        # 지난 판에 마피아였던 캐릭터 제외 후보군 우선 추출
        non_last_mafia = [cid for cid in all_ids if cid not in self.last_mafia_chars]
        if len(non_last_mafia) >= mafia_count:
            mafia_ids = sys_rand.sample(non_last_mafia, mafia_count)
        else:
            mafia_ids = non_last_mafia[:]
            remaining_for_mafia = [cid for cid in all_ids if cid not in mafia_ids]
            needed = mafia_count - len(mafia_ids)
            mafia_ids.extend(sys_rand.sample(remaining_for_mafia, needed))

        for cid in mafia_ids:
            self.players[cid].role = Role.MAFIA

        self.last_mafia_chars = set(mafia_ids)

        # 나머지 플레이어들에게 의사, 경찰, 시민 배정
        remaining_ids = [cid for cid in all_ids if cid not in mafia_ids]
        sys_rand.shuffle(remaining_ids)

        idx = 0
        for _ in range(self.config["doctor"]):
            if idx < len(remaining_ids):
                self.players[remaining_ids[idx]].role = Role.DOCTOR
                idx += 1
        for _ in range(self.config["police"]):
            if idx < len(remaining_ids):
                self.players[remaining_ids[idx]].role = Role.POLICE
                idx += 1
        while idx < len(remaining_ids):
            self.players[remaining_ids[idx]].role = Role.CITIZEN
            idx += 1

    # ── 승리 조건 확인 ──

    def check_win(self) -> str | None:
        """
        승리 조건 확인.
        - 마피아 전원 사망 → 'citizen'
        - 마피아 수 >= 시민 팀 수 → 'mafia'
        """
        mafia_count = len(self.alive_mafia)
        non_mafia_count = len(self.alive_non_mafia)

        if mafia_count == 0:
            return "citizen"
        if mafia_count >= non_mafia_count:
            return "mafia"
        return None

    # ── 게임 흐름 ──

    _ROLE_DISPLAY: dict[Role, str] = {
        Role.MAFIA: "🔪 마피아",
        Role.DOCTOR: "💊 의사",
        Role.POLICE: "🔍 경찰",
        Role.CITIZEN: "👤 시민",
    }

    async def start_game(self) -> None:
        """게임 시작: 역할 배정 → 개별 통지 → 밤 페이즈 진입."""
        self.assign_roles()

        # 마피아 동료 목록 (마피아에게만 공개)
        mafia_allies = [
            {"character_id": cid, "emoji": p.character["emoji"], "name": p.character["name"]}
            for cid, p in self.players.items()
            if p.role == Role.MAFIA
        ]

        all_players = [p.to_public_dict() for p in self.players.values()]

        # 각 플레이어에게 역할 통지 (프론트엔드 game_started 메시지)
        for cid, player in self.players.items():
            allies = mafia_allies if player.role == Role.MAFIA else []
            await self.send_to(cid, {
                "type": "game_started",
                "role": player.role.value if player.role else None,
                "role_display": self._ROLE_DISPLAY.get(player.role, "👤 시민"),
                "mafia_allies": allies,
                "players": all_players,
            })

        # 3초 대기 (역할 확인 시간)
        await asyncio.sleep(3)
        await self.start_night()

    async def start_night(self) -> None:
        """밤 페이즈 시작."""
        self.round_number += 1
        self.phase = Phase.NIGHT

        # 밤 행동 초기화
        self.mafia_votes.clear()
        for player in self.players.values():
            player.night_action_target = None

        # 공통 알림
        await self.broadcast({
            "type": "phase_change",
            "phase": Phase.NIGHT.value,
            "round": self.round_number,
            "timer": 30,
        })

        # 역할별 프롬프트 전송
        alive_non_mafia_list = [
            p.to_public_dict() for p in self.alive_non_mafia.values()
        ]
        alive_players_list = [
            p.to_public_dict() for p in self.alive_players.values()
        ]

        for cid, player in self.alive_players.items():
            if player.role == Role.MAFIA:
                await self.send_to(cid, {
                    "type": "night_action_prompt",
                    "action_type": "mafia",
                    "message": "제거할 대상을 선택하세요.",
                    "targets": alive_non_mafia_list,
                })
            elif player.role == Role.DOCTOR:
                targets = alive_players_list
                if player.self_save_used:
                    targets = [t for t in targets if t["character_id"] != cid]
                await self.send_to(cid, {
                    "type": "night_action_prompt",
                    "action_type": "doctor",
                    "message": "보호할 대상을 선택하세요." + (" (자기 보호 1회 사용됨)" if player.self_save_used else ""),
                    "targets": targets,
                })
            elif player.role == Role.POLICE:
                targets = [
                    p.to_public_dict()
                    for c, p in self.alive_players.items()
                    if c != cid
                ]
                await self.send_to(cid, {
                    "type": "night_action_prompt",
                    "action_type": "police",
                    "message": "조사할 대상을 선택하세요.",
                    "targets": targets,
                })
            # 시민은 별도 프롬프트 없음

        # 30초 타이머
        self._cancel_timer()
        self.phase_timer_task = asyncio.create_task(self._night_timer())

    async def _night_timer(self) -> None:
        """밤 타이머: 30초 후 자동 진행."""
        await asyncio.sleep(30)
        if self.phase == Phase.NIGHT:
            await self.resolve_night()

    async def handle_night_action(self, character_id: str, target_id: str) -> None:
        """밤 행동 처리."""
        player = self.players.get(character_id)
        if not player or not player.alive or self.phase != Phase.NIGHT:
            return

        player.night_action_target = target_id
        target_p = self.players.get(target_id)
        target_name_str = f"{target_p.character['emoji']} {target_p.character['name']}" if target_p else target_id

        if player.role == Role.MAFIA:
            self.mafia_votes[character_id] = target_id
            # 마피아 동료에게 투표 알림 + 마피아 채팅방에 메시지 표시
            await self.broadcast(
                {
                    "type": "mafia_action_update",
                    "from": f"{player.character['emoji']} {player.character['name']}",
                    "target": target_id,
                },
                alive_only=True,
                role_filter=Role.MAFIA,
            )
            await self.broadcast(
                {
                    "type": "mafia_chat",
                    "from": "📢 마피아 지목",
                    "message": f"{player.character['emoji']} {player.character['name']}님이 {target_name_str}을(를) 습격 대상으로 지목했습니다.",
                },
                alive_only=True,
                role_filter=Role.MAFIA,
            )
        elif player.role == Role.DOCTOR:
            # 자가 치료 제한 확인
            if target_id == character_id:
                if player.self_save_used:
                    await self.send_to(character_id, {
                        "type": "error",
                        "message": "자가 치료는 1회만 가능합니다.",
                    })
                    player.night_action_target = None
                    return
                player.self_save_used = True
            await self.send_to(character_id, {
                "type": "system_chat",
                "message": f"💊 {target_name_str}을(를) 보호 대상으로 지목했습니다.",
            })
        elif player.role == Role.POLICE:
            await self.send_to(character_id, {
                "type": "system_chat",
                "message": f"🔍 {target_name_str}을(를) 조사 대상으로 지목했습니다.",
            })

        # 모든 행동 완료 확인
        if self._all_night_actions_done():
            self._cancel_timer()
            await self.resolve_night()

    def _all_night_actions_done(self) -> bool:
        """모든 생존 역할자가 밤 행동을 완료했는지 확인."""
        for cid, player in self.alive_players.items():
            if player.role == Role.CITIZEN:
                continue  # 시민은 밤 행동 없음
            if player.night_action_target is None:
                return False
        return True

    async def resolve_night(self) -> None:
        """밤 결과 처리: 마피아 투표 집계, 의사 보호, 경찰 조사."""
        self.phase = Phase.DAY_RESULT

        # ── 마피아 대상 결정 (다수결, 동률 시 랜덤) ──
        kill_target: str | None = None
        if self.mafia_votes:
            vote_counts: dict[str, int] = {}
            for target in self.mafia_votes.values():
                vote_counts[target] = vote_counts.get(target, 0) + 1
            max_votes = max(vote_counts.values())
            top_targets = [t for t, c in vote_counts.items() if c == max_votes]
            kill_target = random.choice(top_targets)
        else:
            # 마피아가 아무도 투표하지 않으면 랜덤 시민 팀 대상
            non_mafia_ids = list(self.alive_non_mafia.keys())
            if non_mafia_ids:
                kill_target = random.choice(non_mafia_ids)

        # ── 의사 보호 확인 ──
        doctor_saved = False
        for cid, player in self.alive_players.items():
            if player.role == Role.DOCTOR and player.night_action_target == kill_target:
                doctor_saved = True
                break

        # ── 경찰 조사 결과 (비공개) ──
        for cid, player in self.alive_players.items():
            if player.role == Role.POLICE and player.night_action_target:
                target_player = self.players.get(player.night_action_target)
                if target_player:
                    is_mafia = target_player.role == Role.MAFIA
                    target_name = f"{target_player.character['emoji']} {target_player.character['name']}"
                    result_msg = (
                        f"{target_name}은(는) 마피아입니다! 🚨"
                        if is_mafia
                        else f"{target_name}은(는) 마피아가 아닙니다. ✅"
                    )
                    await self.send_to(cid, {
                        "type": "police_result",
                        "target": player.night_action_target,
                        "is_mafia": is_mafia,
                        "message": result_msg,
                    })
                    await self.send_to(cid, {
                        "type": "system_chat",
                        "message": f"[경찰 조사 결과] {result_msg}",
                    })

        # ── 사망 처리 ──
        killed_player_info: dict[str, Any] | None = None
        if kill_target and not doctor_saved:
            victim = self.players.get(kill_target)
            if victim and victim.alive:
                victim.alive = False
                killed_player_info = victim.to_public_dict()

        # ── 결과 메시지 생성 ──
        if doctor_saved and kill_target is not None:
            result_msg = f"☀️ 아침이 밝았습니다. 어젯밤 누군가 습격당했지만 의사의 활약으로 살아남았습니다!"
        elif killed_player_info:
            victim = self.players.get(kill_target, None)
            if victim:
                result_msg = f"☀️ 아침이 밝았습니다. 어젯밤 {victim.character['emoji']} {victim.character['name']}이(가) 사망했습니다."
            else:
                result_msg = "☀️ 아침이 밝았습니다."
        else:
            result_msg = "☀️ 아침이 밝았습니다. 어젯밤은 아무 일도 일어나지 않았습니다."

        await self.broadcast({
            "type": "night_result",
            "message": result_msg,
            "round": self.round_number,
            "killed": killed_player_info,
            "saved": doctor_saved and kill_target is not None,
            "players": [p.to_public_dict() for p in self.players.values()],
        })
        await self.broadcast({
            "type": "system_chat",
            "message": result_msg,
        })

        # 승리 조건 확인
        winner = self.check_win()
        if winner:
            await self.end_game(winner)
            return

        # 토론 페이즈로 진입
        await asyncio.sleep(3)
        await self.start_discussion()

    async def start_discussion(self) -> None:
        """토론 페이즈 시작."""
        self.phase = Phase.DISCUSSION
        disc_time = self.config.get("discussion_time", 60)
        disc_msg = f"💬 토론 시간이 되었습니다. ({disc_time}초간 자유롭게 대화하세요)"

        await self.broadcast({
            "type": "phase_change",
            "phase": Phase.DISCUSSION.value,
            "round": self.round_number,
            "timer": disc_time,
            "message": disc_msg,
            "alive_players": [p.to_public_dict() for p in self.alive_players.values()],
        })
        await self.broadcast({
            "type": "system_chat",
            "message": disc_msg,
        })

        self._cancel_timer()
        self.phase_timer_task = asyncio.create_task(self._discussion_timer(disc_time))

    async def _discussion_timer(self, duration: int) -> None:
        """토론 타이머 후 투표로 전환."""
        await asyncio.sleep(duration)
        if self.phase == Phase.DISCUSSION:
            await self.start_vote()

    async def start_vote(self) -> None:
        """투표 페이즈 시작 (20초)."""
        self.phase = Phase.VOTE
        self.day_votes.clear()

        targets = [p.to_public_dict() for p in self.alive_players.values()]

        vote_msg = "🗳️ 투표 시간이 되었습니다. 의심되는 사람을 선택하세요. (20초)"
        await self.broadcast({
            "type": "phase_change",
            "phase": Phase.VOTE.value,
            "round": self.round_number,
            "timer": 20,
            "message": vote_msg,
            "targets": targets,
        })
        await self.broadcast({
            "type": "system_chat",
            "message": vote_msg,
        })

        self._cancel_timer()
        self.phase_timer_task = asyncio.create_task(self._vote_timer())

    async def _vote_timer(self) -> None:
        """투표 타이머: 20초 후 자동 집계."""
        await asyncio.sleep(20)
        if self.phase == Phase.VOTE:
            await self.resolve_vote()

    async def handle_vote(self, character_id: str, target_id: str) -> None:
        """투표 처리."""
        player = self.players.get(character_id)
        if not player or not player.alive or self.phase != Phase.VOTE:
            return
        if character_id in self.day_votes:
            return  # 이미 투표함

        self.day_votes[character_id] = target_id
        player.vote_target = target_id

        # 누가 투표했는지만 알림 (누구에게 했는지는 비공개)
        msg_cast = f"🗳️ {player.character['emoji']} {player.character['name']}님이 투표했습니다 ({len(self.day_votes)}/{len(self.alive_players)})"
        await self.broadcast({
            "type": "vote_cast",
            "voter": player.to_public_dict(),
            "vote_count": len(self.day_votes),
            "total_alive": len(self.alive_players),
        })
        await self.broadcast({
            "type": "system_chat",
            "message": msg_cast,
        })

        # 전원 투표 완료 확인
        if len(self.day_votes) >= len(self.alive_players):
            self._cancel_timer()
            await self.resolve_vote()

    async def resolve_vote(self) -> None:
        """투표 결과 집계 및 처리."""
        self.phase = Phase.VOTE_RESULT

        # 득표 집계
        vote_counts: dict[str, int] = {}
        for target in self.day_votes.values():
            vote_counts[target] = vote_counts.get(target, 0) + 1

        # 투표 상세 (공개)
        vote_details: list[dict[str, Any]] = []
        for voter_id, target_id in self.day_votes.items():
            voter = self.players[voter_id]
            target = self.players[target_id]
            vote_details.append({
                "voter": voter.to_public_dict(),
                "target": target.to_public_dict(),
            })

        eliminated: dict[str, Any] | None = None
        eliminated_role: str | None = None

        if vote_counts:
            max_votes = max(vote_counts.values())
            top_targets = [t for t, c in vote_counts.items() if c == max_votes]

            if len(top_targets) == 1:
                target_id = top_targets[0]
                target_player = self.players[target_id]
                target_player.alive = False
                eliminated = target_player.to_public_dict()
                eliminated_role = target_player.role.value if target_player.role else None

        # 결과 메시지 생성
        if eliminated:
            role_display = self._ROLE_DISPLAY.get(Role(eliminated_role), "👤 시민") if eliminated_role else ""
            ep = self.players.get(top_targets[0])
            if ep:
                vote_msg = f"⚖️ 투표 결과 {ep.character['emoji']} {ep.character['name']}이(가) 추방되었습니다. (역할: {role_display})"
            else:
                vote_msg = "⚖️ 투표 결과 한 명이 추방되었습니다."
        elif vote_counts:
            vote_msg = "⚖️ 투표가 동률입니다. 아무도 추방되지 않았습니다."
        else:
            vote_msg = "⚖️ 아무도 투표하지 않았습니다."

        await self.broadcast({
            "type": "vote_result",
            "message": vote_msg,
            "round": self.round_number,
            "vote_details": vote_details,
            "eliminated": eliminated,
            "eliminated_role": eliminated_role,
            "players": [p.to_public_dict() for p in self.players.values()],
        })
        await self.broadcast({
            "type": "system_chat",
            "message": vote_msg,
        })

        # 승리 조건 확인
        winner = self.check_win()
        if winner:
            await asyncio.sleep(3)
            await self.end_game(winner)
            return

        # 다음 밤으로
        await asyncio.sleep(3)
        await self.start_night()

    async def broadcast_dead_chat(self, data: dict[str, Any]) -> None:
        """사망한 플레이어들에게만 브로드캐스트 (영매/유령 채팅)."""
        tasks = []
        for player in self.players.values():
            if not player.alive:
                tasks.append(self.send_to_ws(player.ws, data))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def end_game(self, winner: str) -> None:
        """게임 종료: 모든 역할 공개."""
        self._cancel_timer()
        self.phase = Phase.GAME_OVER

        winner_msg = "🎉 시민 팀 승리!" if winner == "citizen" else "😈 마피아 팀 승리!"

        # 전체 역할 공개
        all_roles = [
            {
                **player.to_public_dict(),
                "role": player.role.value if player.role else None,
                "role_display": self._ROLE_DISPLAY.get(player.role, "👤 시민") if player.role else "👤 시민",
            }
            for player in self.players.values()
        ]

        await self.broadcast({
            "type": "game_over",
            "winner": winner,
            "message": winner_msg,
            "players": all_roles,
        })
        await self.broadcast({
            "type": "system_chat",
            "message": f"🏆 [게임 종료] {winner_msg}",
        })

    # ── 내부 유틸 ──

    def _cancel_timer(self) -> None:
        """진행 중인 타이머를 취소한다."""
        if self.phase_timer_task and not self.phase_timer_task.done():
            self.phase_timer_task.cancel()
        self.phase_timer_task = None


# ──────────────────────────────────────────────
# GameManager 클래스
# ──────────────────────────────────────────────
class GameManager:
    """모든 게임 방을 관리하는 매니저."""

    def __init__(self) -> None:
        self.rooms: dict[str, Room] = {}  # room_id → Room
        self.ws_to_room: dict[int, str] = {}  # id(ws) → room_id
        self.lobby_connections: set[WebSocket] = set()  # 대기방 광장 접속자 목록
        self.global_chat_history: list[dict[str, Any]] = []  # 광장 채팅 기록 보관


    def _generate_room_id(self) -> str:
        """중복 없는 4자리 방 코드 생성."""
        while True:
            room_id = "".join(random.choices(string.digits, k=4))
            if room_id not in self.rooms:
                return room_id

    def create_room(
        self,
        host_ws: WebSocket,
        config: dict[str, int],
        character_id: str,
        requested_room_id: str = "",
    ) -> Room:
        """새 방을 생성하고 방장을 참가시킨다."""
        if requested_room_id and len(requested_room_id) == 4 and requested_room_id.isdigit() and requested_room_id not in self.rooms:
            room_id = requested_room_id
        else:
            room_id = self._generate_room_id()
        room = Room(room_id=room_id, host_ws=host_ws, config=config)
        self.rooms[room_id] = room

        # 방장을 플레이어로 등록
        character = CHARACTER_MAP[character_id]
        player = Player(ws=host_ws, character_id=character_id, character=character)
        room.players[character_id] = player
        room.ws_to_character[id(host_ws)] = character_id
        self.ws_to_room[id(host_ws)] = room_id

        return room

    def get_room(self, room_id: str) -> Room | None:
        """방 ID로 Room 객체를 반환한다."""
        return self.rooms.get(room_id)

    def get_room_info(self, room_id: str) -> dict[str, Any] | None:
        """방 정보 조회 (캐릭터 선택 화면용)."""
        room = self.rooms.get(room_id)
        if not room:
            return None
        return {
            "taken_characters": list(room.players.keys()),
            "player_count": len(room.players),
            "config": room.config,
        }

    def get_player_room(self, ws: WebSocket) -> tuple[Room | None, str | None]:
        """WebSocket으로 해당 플레이어의 방과 캐릭터 ID를 반환한다."""
        room_id = self.ws_to_room.get(id(ws))
        if not room_id:
            return None, None
        room = self.rooms.get(room_id)
        if not room:
            return None, None
        character_id = room.ws_to_character.get(id(ws))
        return room, character_id

    def join_room(
        self, ws: WebSocket, room_id: str, character_id: str
    ) -> tuple[bool, str]:
        """플레이어를 방에 참가시킨다. (성공 여부, 메시지) 반환."""
        room = self.rooms.get(room_id)
        if not room:
            return False, "존재하지 않는 방입니다."
        if room.phase != Phase.LOBBY:
            return False, "이미 게임이 진행 중입니다."
        if character_id not in CHARACTER_MAP:
            return False, "유효하지 않은 캐릭터입니다."
        if character_id in room.players:
            return False, "이미 선택된 캐릭터입니다."
        if len(room.players) >= 12:
            return False, "방이 가득 찼습니다. (최대 12명)"

        character = CHARACTER_MAP[character_id]
        if len(room.players) == 0:
            room.host_ws = ws
        player = Player(ws=ws, character_id=character_id, character=character)
        room.players[character_id] = player
        room.ws_to_character[id(ws)] = character_id
        self.ws_to_room[id(ws)] = room_id

        return True, "참가 성공!"

    def remove_player(self, ws: WebSocket) -> tuple[Room | None, str | None]:
        """플레이어를 방에서 제거한다. (Room, character_id) 반환."""
        room_id = self.ws_to_room.pop(id(ws), None)
        if not room_id:
            return None, None

        room = self.rooms.get(room_id)
        if not room:
            return None, None

        character_id = room.ws_to_character.pop(id(ws), None)
        if not character_id:
            return None, None

        # 로비 상태에서만 플레이어 제거 (게임 중엔 유지)
        if room.phase == Phase.LOBBY:
            room.players.pop(character_id, None)

            # 방장 이전 (방은 새로고침 F5 대응으로 유지)
            if room.players and room.host_ws is ws:
                new_host = next(iter(room.players.values()))
                room.host_ws = new_host.ws

        return room, character_id

    def connect_lobby(self, ws: WebSocket) -> None:
        """대기방 광장에 접속한 클라이언트 등록."""
        self.lobby_connections.add(ws)

    def disconnect_ws(self, ws: WebSocket) -> tuple[Room | None, str | None]:
        """클라이언트 연결 해제 처리 (로비 광장 및 참여 중인 방)."""
        self.lobby_connections.discard(ws)
        return self.remove_player(ws)

    async def broadcast_lobby_chat(self, sender: str, content: str) -> None:
        """대기방 진입 전 자유 채팅방(광장) 메시지 브로드캐스트."""
        data = {
            "type": "global_chat",
            "sender": sender,
            "content": content,
            "user_count": len(self.lobby_connections),
        }
        self.global_chat_history.append(data)
        if len(self.global_chat_history) > 100:
            self.global_chat_history.pop(0)
        raw = json.dumps(data, ensure_ascii=False)
        tasks = []
        to_remove = set()
        for ws in self.lobby_connections:
            try:
                tasks.append(ws.send_text(raw))
            except Exception:
                to_remove.add(ws)
        for ws in to_remove:
            self.lobby_connections.discard(ws)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_lobby_count(self) -> None:
        """대기방 광장 접속 인원 수 브로드캐스트."""
        data = {
            "type": "lobby_count",
            "user_count": len(self.lobby_connections),
        }
        raw = json.dumps(data, ensure_ascii=False)
        tasks = []
        to_remove = set()
        for ws in self.lobby_connections:
            try:
                tasks.append(ws.send_text(raw))
            except Exception:
                to_remove.add(ws)
        for ws in to_remove:
            self.lobby_connections.discard(ws)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def get_room_list(self) -> list[dict[str, Any]]:
        """로비에 표시할 개설된 방 목록 반환."""
        result = []
        for r_id, room in self.rooms.items():
            result.append({
                "room_id": r_id,
                "player_count": len(room.players),
                "min_players": room.min_players(),
                "phase": room.phase.value,
                "config": room.config,
            })
        return result

    async def broadcast_room_list(self) -> None:
        """대기방 광장 접속자들에게 현재 개설된 방 목록 브로드캐스트."""
        data = {
            "type": "room_list",
            "rooms": self.get_room_list(),
        }
        raw = json.dumps(data, ensure_ascii=False)
        tasks = []
        to_remove = set()
        for ws in self.lobby_connections:
            try:
                tasks.append(ws.send_text(raw))
            except Exception:
                to_remove.add(ws)
        for ws in to_remove:
            self.lobby_connections.discard(ws)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


