# -*- coding: utf-8 -*-
# =============================================================================
#  오타니(야구방망이) vs 은가누(맨주먹)  -  2D "링" 대결 시뮬레이터
# -----------------------------------------------------------------------------
#  실행 방법 (Windows):
#     1) 패키지 설치 :  pip install flask
#     2) 서버 실행   :  python app.py
#     3) 브라우저에서 :  http://127.0.0.1:5000  접속
#
#  필요 패키지:
#     pip install flask
#
#  - 순수 HTTP (SSL/HTTPS 미사용), 로컬 개발 전용.
#  - 두 선수는 사각 "링" 위를 (x, y) 2D 로 자유롭게 돌아다니며 싸웁니다.
#  - 시각화(브라우저 Canvas) 와 통계(서버 10,000회)는 "동일한 전투 규칙"을
#    각각 JS / Python 으로 미러링하여 구현했습니다.
#  - 캐릭터는 같은 폴더의 Ohtani.png / Ngannou.png 이미지를 사용합니다.
#    (오타니: 얼굴 이미지 + 직접 그린 유니폼 몸통 + 야구 방망이 합성)
# =============================================================================

import os
import time
import math
import random
import socket
from flask import Flask, request, jsonify, Response, send_from_directory, abort

app = Flask(__name__)
APP_DIR = os.path.dirname(os.path.abspath(__file__))

# -----------------------------------------------------------------------------
# 전투 엔진 상수 (JS 측 CONST 와 반드시 동일하게 유지) - 월드(링) 좌표계
#   월드 사각형: x in [0, WX1], y in [0, WY1]  (y가 클수록 화면 앞쪽)
# -----------------------------------------------------------------------------
DT = 1.0 / 60.0
WX1 = 760.0
WY1 = 440.0
INSET = 40.0              # 로프 안쪽 여백(이 안에서만 이동)
R_O = 24.0               # 오타니 몸 반경
R_N = 34.0               # 은가누 몸 반경
MIN_SEP = R_O + R_N      # 두 캐릭터 최소 간격
STAGGER = 0.22           # 넉백 시 은가누 경직(초)
MAX_TICKS = 1800         # 한 경기 최대 30초 -> 초과 시 HP비율 판정
KITE = 0.78              # 오타니가 유지하려는 거리 = 리치 * 0.78
ORBIT = 1.0              # 오타니 선회 방향(부호)
RETREAT_W = 1.0          # 후퇴 가중치
ORBIT_W = 0.6            # 선회(횡이동) 가중치

X0_O, Y0_O = 230.0, 250.0
X0_N, Y0_N = 540.0, 200.0

MIN_X_O = INSET + R_O; MAX_X_O = WX1 - INSET - R_O
MIN_Y_O = INSET + R_O; MAX_Y_O = WY1 - INSET - R_O
MIN_X_N = INSET + R_N; MAX_X_N = WX1 - INSET - R_N
MIN_Y_N = INSET + R_N; MAX_Y_N = WY1 - INSET - R_N


# -----------------------------------------------------------------------------
# 파라미터 기본값 (HTML 슬라이더 기본값과 동일하게 유지)
# -----------------------------------------------------------------------------
DEFAULTS = {
    # 오타니 (방망이)
    "oHp": 120.0, "oDmg": 16.0, "oSpeed": 2.4, "oAcc": 0.78,
    "oReach": 175.0, "oKnock": 70.0, "oCd": 0.55,
    # 은가누 (맨주먹)
    "nHp": 240.0, "nDmg": 38.0, "nSpeed": 3.85, "nAcc": 0.62,
    "nReach": 72.0, "nCd": 0.50,
}

# -----------------------------------------------------------------------------
# 리얼 모드 상수 (실제 데이터 기반 / JS REAL 과 동일하게 유지)
#   - 오타니 배트: 선딜 큼(telegraph)·후딜 큼·반응 느림(펀치 회피 불가), 클린샷 치명
#   - 은가누 펀치: 선딜/후딜 짧음·반응 빠름(배트 회피/슬립)·원펀치 KO·후반 지침
#   출처: Ngannou PowerKube 129,161("96마력") / Ohtani bat 75.5mph·sprint 28.1ft/s /
#         elite combat reaction ~0.15-0.2s, untrained ~0.3s, punch lands ~0.1s
# -----------------------------------------------------------------------------
REAL = {
    "O_WINDUP": 0.34, "O_RECOVER": 0.42,        # 배트 선딜/후딜(초)
    "N_WINDUP": 0.12, "N_RECOVER": 0.16, "N_FEINT_RECOVER": 0.10,
    "O_REACT": 0.32, "N_REACT": 0.18,            # 반응속도(초)
    "N_SLIP_BASE": 0.40, "O_SLIP_BASE": 0.03,    # 슬립(회피) 기본 확률
    "N_FEINT_CHANCE": 0.22, "O_BAIT_CHANCE": 0.5,
    "O_SWING_COST": 11.0, "N_PUNCH_COST": 6.0,
    "O_STAM_REGEN": 5.0, "N_STAM_REGEN": 4.0,    # 은가누 회복 느림 -> 지침
    "O_HEAD": 42.0, "O_BODY": 20.0,              # 배트 클린히트 데미지(HP 100 기준, 비KO시 누적)
    "N_HEAD": 26.0, "N_BODY": 13.0,              # 펀치 클린히트 데미지
    "KO_O": 0.80, "KO_N": 0.70,                  # 다친 상태(HP<KO_THRESH)에서 클린 헤드샷의 KO 확률(은가누 KO율 ~72% 보정)
    "KO_THRESH": 45.0,                           # 이 HP 미만으로 떨어졌을 때만 KO 발생(그 전엔 누적 데미지로 공방)
    "HEAD_CHANCE": 0.5, "STUN_TIME": 0.7, "FINISH_MULT": 1.3,
    "MAX_TICKS": 2400,                            # 40초
    "HP": 100.0,                                  # 리얼 모드 공통 durability (둘 동일)
}


def _clampf(v, lo, hi, fallback):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return fallback
    if v != v:  # NaN
        return fallback
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def sanitize_params(raw):
    raw = raw or {}
    return {
        "oHp":    _clampf(raw.get("oHp"),    10,  500, DEFAULTS["oHp"]),
        "oDmg":   _clampf(raw.get("oDmg"),    1,  100, DEFAULTS["oDmg"]),
        "oSpeed": _clampf(raw.get("oSpeed"), 0.2,  12, DEFAULTS["oSpeed"]),
        "oAcc":   _clampf(raw.get("oAcc"),    0,    1, DEFAULTS["oAcc"]),
        "oReach": _clampf(raw.get("oReach"), 60,  300, DEFAULTS["oReach"]),
        "oKnock": _clampf(raw.get("oKnock"),  0,  300, DEFAULTS["oKnock"]),
        "oCd":    _clampf(raw.get("oCd"),   0.1,    3, DEFAULTS["oCd"]),
        "nHp":    _clampf(raw.get("nHp"),    10,  800, DEFAULTS["nHp"]),
        "nDmg":   _clampf(raw.get("nDmg"),    1,  200, DEFAULTS["nDmg"]),
        "nSpeed": _clampf(raw.get("nSpeed"), 0.2,  14, DEFAULTS["nSpeed"]),
        "nAcc":   _clampf(raw.get("nAcc"),    0,    1, DEFAULTS["nAcc"]),
        "nReach": _clampf(raw.get("nReach"), 30,  200, DEFAULTS["nReach"]),
        "nCd":    _clampf(raw.get("nCd"),   0.1,    3, DEFAULTS["nCd"]),
    }


# -----------------------------------------------------------------------------
# 핵심 전투 시뮬레이션 (1회 경기, 2D) - JS의 stepSim 과 동일 로직
#   반환: (winner, ticks, hpO, hpN)
# -----------------------------------------------------------------------------
def simulate_once(p, rnd=random.random):
    hyp = math.hypot
    ox, oy = X0_O, Y0_O
    nx, ny = X0_N, Y0_N
    hpO = p["oHp"]; hpN = p["nHp"]
    maxO = hpO if hpO > 0 else 1.0
    maxN = hpN if hpN > 0 else 1.0

    oDmg = p["oDmg"]; oSpeed = p["oSpeed"]; oAcc = p["oAcc"]
    oReach = p["oReach"]; oKnock = p["oKnock"]; oCd = p["oCd"]
    nDmg = p["nDmg"]; nSpeed = p["nSpeed"]; nAcc = p["nAcc"]
    nReach = p["nReach"]; nCd = p["nCd"]

    desired = oReach * KITE
    swingT = 0.0; punchT = 0.0; stagT = 0.0
    winner = "draw"
    t = 0
    while t < MAX_TICKS:
        t += 1
        if swingT > 0.0: swingT -= DT
        if punchT > 0.0: punchT -= DT
        if stagT > 0.0: stagT -= DT

        # --- 오타니: 방망이 (사거리 안) ---
        dx = nx - ox; dy = ny - oy
        d = hyp(dx, dy)
        if d < 1e-6: d = 1e-6
        if swingT <= 0.0 and d <= oReach:
            swingT = oCd
            if rnd() < oAcc:
                hpN -= oDmg
                nx += dx / d * oKnock        # 넉백: 오타니 반대 방향
                ny += dy / d * oKnock
                if nx < MIN_X_N: nx = MIN_X_N
                elif nx > MAX_X_N: nx = MAX_X_N
                if ny < MIN_Y_N: ny = MIN_Y_N
                elif ny > MAX_Y_N: ny = MAX_Y_N
                stagT = STAGGER
                if hpN <= 0.0:
                    winner = "ohtani"; break

        # --- 오타니: 이동(후퇴 + 선회) -> 링을 돌아다님 ---
        dx = nx - ox; dy = ny - oy
        d = hyp(dx, dy)
        if d < 1e-6: d = 1e-6
        ux = dx / d; uy = dy / d           # 오타니 -> 은가누
        ax = -ux; ay = -uy                 # 멀어지는 방향
        tx = -uy * ORBIT; ty = ux * ORBIT  # 접선(선회) 방향
        if d < desired:
            mx = ax * RETREAT_W + tx * ORBIT_W
            my = ay * RETREAT_W + ty * ORBIT_W
        else:
            mx = tx; my = ty
        ml = hyp(mx, my)
        if ml > 1e-6:
            ox += mx / ml * oSpeed
            oy += my / ml * oSpeed
            if ox < MIN_X_O: ox = MIN_X_O
            elif ox > MAX_X_O: ox = MAX_X_O
            if oy < MIN_Y_O: oy = MIN_Y_O
            elif oy > MAX_Y_O: oy = MAX_Y_O

        # --- 은가누: 펀치 + 돌진 (경직 아닐 때) ---
        if stagT <= 0.0:
            dx = ox - nx; dy = oy - ny      # 은가누 -> 오타니
            d = hyp(dx, dy)
            if d < 1e-6: d = 1e-6
            if punchT <= 0.0 and d <= nReach:
                punchT = nCd
                if rnd() < nAcc:
                    hpO -= nDmg
                    if hpO <= 0.0:
                        winner = "ngannou"; break
            nx += dx / d * nSpeed
            ny += dy / d * nSpeed
            # 겹침 방지
            sx = nx - ox; sy = ny - oy
            sd = hyp(sx, sy)
            if sd < MIN_SEP:
                if sd < 1e-6:
                    sx, sy, sd = 1.0, 0.0, 1.0
                nx = ox + sx / sd * MIN_SEP
                ny = oy + sy / sd * MIN_SEP
            if nx < MIN_X_N: nx = MIN_X_N
            elif nx > MAX_X_N: nx = MAX_X_N
            if ny < MIN_Y_N: ny = MIN_Y_N
            elif ny > MAX_Y_N: ny = MAX_Y_N
    else:
        fracO = hpO / maxO
        fracN = hpN / maxN
        if fracO > fracN + 1e-6:
            winner = "ohtani"
        elif fracN > fracO + 1e-6:
            winner = "ngannou"
        else:
            winner = "draw"

    return winner, t, hpO, hpN


def simulate_once_real(p, rnd=random.random):
    """리얼 모드 1경기 (상태머신). JS stepReal 과 동일 로직.
    상태: 0 ready, 1 windup, 3 recover, 4 stun.
    반환: (winner, ticks, method, hpO, hpN)  method in {punch_ko, bat_ko, decision}"""
    hyp = math.hypot
    R = REAL
    oReach = p["oReach"]; nReach = p["nReach"]
    oSpeed = p["oSpeed"]; nSpeed = p["nSpeed"]
    oAccB = p["oAcc"]; nAccB = p["nAcc"]
    odk = p["oDmg"] / 16.0; ndk = p["nDmg"] / 38.0
    oKnock = p["oKnock"]
    maxO = p["oHp"] if p["oHp"] > 0 else 1.0
    maxN = p["nHp"] if p["nHp"] > 0 else 1.0

    S = {"ox": X0_O, "oy": Y0_O, "nx": X0_N, "ny": Y0_N,
         "hpO": p["oHp"], "hpN": p["nHp"],
         "stO": 0, "tO": 0.0, "stamO": 100.0, "wuO": 0.0,
         "stN": 0, "tN": 0.0, "stamN": 100.0, "wuN": 0.0, "feintN": False}
    res = {"w": None, "m": None}

    def clamp(v, lo, hi):
        return lo if v < lo else (hi if v > hi else v)

    def hit(att):
        if att == "O":
            ax, ay, tx, ty = S["ox"], S["oy"], S["nx"], S["ny"]
            reach = oReach; accB = oAccB; head = R["O_HEAD"] * odk; body = R["O_BODY"] * odk
            defState = S["stN"]; defN = True; stam = S["stamO"]
        else:
            ax, ay, tx, ty = S["nx"], S["ny"], S["ox"], S["oy"]
            reach = nReach; accB = nAccB; head = R["N_HEAD"] * ndk; body = R["N_BODY"] * ndk
            defState = S["stO"]; defN = False; stam = S["stamN"]
        if hyp(tx - ax, ty - ay) > reach + 8:
            return False
        if defN:
            slip = R["N_SLIP_BASE"] * (0.5 + 0.5 * S["stamN"] / 100.0)
            if S["stN"] != 0:
                slip *= 0.3
            if rnd() < slip:
                return False
        else:
            if rnd() < R["O_SLIP_BASE"]:
                return False
        acc = accB * (0.6 + 0.4 * stam / 100.0)
        finishing = defState in (1, 3, 4)
        if finishing:
            acc = min(1.0, acc + 0.3)
        if rnd() >= acc:
            return False
        isHead = (rnd() < R["HEAD_CHANCE"]) or finishing
        dmg = (head if isHead else body) * (R["FINISH_MULT"] if finishing else 1.0)
        if defN:
            S["hpN"] -= dmg
            dx = S["nx"] - S["ox"]; dy = S["ny"] - S["oy"]; dl = hyp(dx, dy) or 1.0
            S["nx"] = clamp(S["nx"] + dx / dl * oKnock, MIN_X_N, MAX_X_N)
            S["ny"] = clamp(S["ny"] + dy / dl * oKnock, MIN_Y_N, MAX_Y_N)
            if S["hpN"] <= 0:                          # 누적 데미지로 다운 -> TKO
                S["hpN"] = 0.0; res["w"] = "ohtani"; res["m"] = "decision"; return True
            if isHead and S["hpN"] < R["KO_THRESH"] and rnd() < R["KO_O"]:  # 다쳤을 때만 클린 KO
                S["hpN"] = 0.0; res["w"] = "ohtani"; res["m"] = "bat_ko"; return True
            if isHead:
                S["stN"] = 4; S["tN"] = R["STUN_TIME"]; S["wuN"] = 0.0
        else:
            S["hpO"] -= dmg
            if S["hpO"] <= 0:
                S["hpO"] = 0.0; res["w"] = "ngannou"; res["m"] = "decision"; return True
            if isHead and S["hpO"] < R["KO_THRESH"] and rnd() < R["KO_N"]:
                S["hpO"] = 0.0; res["w"] = "ngannou"; res["m"] = "punch_ko"; return True
            if isHead:
                S["stO"] = 4; S["tO"] = R["STUN_TIME"]; S["wuO"] = 0.0
        return False

    t = 0
    KO = False
    while t < R["MAX_TICKS"]:
        t += 1
        # 오타니 상태
        st = S["stO"]
        if st == 0:
            S["stamO"] = min(100.0, S["stamO"] + R["O_STAM_REGEN"] * DT)
        elif st == 1:
            S["wuO"] += DT; S["tO"] -= DT
            if S["tO"] <= 0:
                if hit("O"):
                    KO = True; break
                S["stO"] = 3; S["tO"] = R["O_RECOVER"]; S["wuO"] = 0.0
        elif st == 3:
            S["tO"] -= DT
            if S["tO"] <= 0:
                S["stO"] = 0
        elif st == 4:
            S["tO"] -= DT
            if S["tO"] <= 0:
                S["stO"] = 0
        # 은가누 상태
        st = S["stN"]
        if st == 0:
            S["stamN"] = min(100.0, S["stamN"] + R["N_STAM_REGEN"] * DT)
        elif st == 1:
            S["wuN"] += DT; S["tN"] -= DT
            if S["tN"] <= 0:
                if S["feintN"]:
                    S["feintN"] = False; S["stN"] = 3; S["tN"] = R["N_FEINT_RECOVER"]; S["wuN"] = 0.0
                else:
                    if hit("N"):
                        KO = True; break
                    S["stN"] = 3; S["tN"] = R["N_RECOVER"]; S["wuN"] = 0.0
        elif st == 3:
            S["tN"] -= DT
            if S["tN"] <= 0:
                S["stN"] = 0
        elif st == 4:
            S["tN"] -= DT
            if S["tN"] <= 0:
                S["stN"] = 0

        # 오타니 AI (ready)
        if S["stO"] == 0:
            d = hyp(S["nx"] - S["ox"], S["ny"] - S["oy"])
            swing = False
            if S["stamO"] > 6 and d <= oReach:
                if S["stN"] == 1 and S["feintN"]:
                    swing = rnd() < R["O_BAIT_CHANCE"]
                elif S["stN"] in (1, 3, 4):
                    swing = True
                elif d <= oReach * 0.72:
                    swing = True
            if swing:
                wf = 1.0 + (1.0 - S["stamO"] / 100.0) * 0.4
                S["stO"] = 1; S["tO"] = R["O_WINDUP"] * wf; S["wuO"] = 0.0; S["stamO"] -= R["O_SWING_COST"]
            else:
                dx = S["nx"] - S["ox"]; dy = S["ny"] - S["oy"]; dd = hyp(dx, dy) or 1e-6
                ux = dx / dd; uy = dy / dd; ax = -ux; ay = -uy; tx = -uy; ty = ux
                des = oReach * KITE
                if dd < des:
                    mx = ax + tx * 0.6; my = ay + ty * 0.6
                else:
                    mx = tx; my = ty
                ml = hyp(mx, my) or 1e-6
                spd = oSpeed * (0.7 + 0.3 * S["stamO"] / 100.0)
                S["ox"] = clamp(S["ox"] + mx / ml * spd, MIN_X_O, MAX_X_O)
                S["oy"] = clamp(S["oy"] + my / ml * spd, MIN_Y_O, MAX_Y_O)

        # 은가누 AI (ready)
        if S["stN"] == 0:
            d = hyp(S["ox"] - S["nx"], S["oy"] - S["ny"])
            aware = (S["stO"] == 1 and S["wuO"] >= R["N_REACT"])
            if d <= nReach:
                if (not aware) and rnd() < R["N_FEINT_CHANCE"]:
                    S["stN"] = 1; S["tN"] = R["N_WINDUP"]; S["feintN"] = True; S["wuN"] = 0.0
                elif S["stamN"] > 4:
                    wf = 1.0 + (1.0 - S["stamN"] / 100.0) * 0.4
                    S["stN"] = 1; S["tN"] = R["N_WINDUP"] * wf; S["feintN"] = False; S["wuN"] = 0.0; S["stamN"] -= R["N_PUNCH_COST"]
            else:
                # 전진 압박(돌진+앵글) - 배트를 맞더라도 파고듦
                dx = S["ox"] - S["nx"]; dy = S["oy"] - S["ny"]; dd = hyp(dx, dy) or 1e-6
                ux = dx / dd; uy = dy / dd; perpx = -uy; perpy = ux
                mx = ux + perpx * 0.35; my = uy + perpy * 0.35
                ml = hyp(mx, my) or 1e-6
                spd = nSpeed * (0.7 + 0.3 * S["stamN"] / 100.0)
                nx = S["nx"] + mx / ml * spd; ny = S["ny"] + my / ml * spd
                sx = nx - S["ox"]; sy = ny - S["oy"]; sd = hyp(sx, sy)
                if sd < MIN_SEP:
                    if sd < 1e-6:
                        sx, sy, sd = 1.0, 0.0, 1.0
                    nx = S["ox"] + sx / sd * MIN_SEP; ny = S["oy"] + sy / sd * MIN_SEP
                S["nx"] = clamp(nx, MIN_X_N, MAX_X_N); S["ny"] = clamp(ny, MIN_Y_N, MAX_Y_N)

    if not KO:
        fO = S["hpO"] / maxO; fN = S["hpN"] / maxN
        if fO > fN + 1e-6:
            res["w"] = "ohtani"
        elif fN > fO + 1e-6:
            res["w"] = "ngannou"
        else:
            res["w"] = "draw"
        res["m"] = "decision"
    return res["w"], t, res["m"], S["hpO"], S["hpN"]


def run_batch(p, runs, mode="arcade"):
    try:
        runs = int(runs)
    except (TypeError, ValueError):
        runs = 10000
    if runs < 1:
        runs = 1
    if runs > 200000:
        runs = 200000

    rnd = random.random
    real = (mode == "real")
    o = n = d = 0
    tick_sum = 0
    methods = {"punch_ko": 0, "bat_ko": 0, "decision": 0}
    t0 = time.perf_counter()
    for _ in range(runs):
        if real:
            w, ticks, method, _a, _b = simulate_once_real(p, rnd)
            methods[method] = methods.get(method, 0) + 1
        else:
            w, ticks, _a, _b = simulate_once(p, rnd)
        tick_sum += ticks
        if w == "ohtani":
            o += 1
        elif w == "ngannou":
            n += 1
        else:
            d += 1
    elapsed = time.perf_counter() - t0

    out = {
        "runs": runs, "mode": mode, "ohtani": o, "ngannou": n, "draw": d,
        "ohtaniRate": round(o / runs * 100.0, 2),
        "ngannouRate": round(n / runs * 100.0, 2),
        "drawRate": round(d / runs * 100.0, 2),
        "avgSeconds": round((tick_sum / runs) * DT, 2),
        "elapsedMs": round(elapsed * 1000.0, 1),
    }
    if real:
        out["methods"] = methods
        out["koShareN"] = round(methods["punch_ko"] / n * 100.0, 1) if n > 0 else 0.0
        out["koShareO"] = round(methods["bat_ko"] / o * 100.0, 1) if o > 0 else 0.0
    return out


# -----------------------------------------------------------------------------
# 라우트
# -----------------------------------------------------------------------------
@app.route("/")
def index():
    return Response(PAGE, mimetype="text/html; charset=utf-8")


_ALLOWED_IMG = {"Ohtani.png", "Ngannou.png"}


@app.route("/img/<name>")
def img(name):
    if name not in _ALLOWED_IMG:
        abort(404)
    return send_from_directory(APP_DIR, name)


@app.route("/simulate", methods=["POST"])
def simulate():
    data = request.get_json(silent=True) or {}
    params = sanitize_params(data.get("params"))
    runs = data.get("runs", 10000)
    mode = data.get("mode", "arcade")
    if mode not in ("arcade", "real"):
        mode = "arcade"
    return jsonify(run_batch(params, runs, mode))


# =============================================================================
#  프론트엔드 (HTML + CSS + JS) - 단일 문자열로 내장
#  ※ 따옴표 충돌을 막기 위해 내부에서는 큰따옴표(") 만 사용합니다.
# =============================================================================
PAGE = r'''<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>오타니(방망이) vs 은가누(맨주먹) - 2D 링 대결 시뮬레이터</title>
<style>
  :root{
    --bg:#0b1020; --panel:#141b30; --panel2:#1b2340; --line:#2a3556;
    --ink:#e8edf7; --muted:#9aa7c7; --o:#38bdf8; --n:#f87171; --acc:#fbbf24;
  }
  *{box-sizing:border-box;}
  body{ margin:0; background:#0b1020; color:var(--ink);
    font-family:"Segoe UI","Malgun Gothic","맑은 고딕",system-ui,sans-serif; }
  .wrap{max-width:1180px; margin:0 auto; padding:18px 16px 60px;}
  h1{font-size:22px; margin:6px 0 2px; letter-spacing:.5px;}
  h1 .o{color:var(--o);} h1 .n{color:var(--n);} h1 .vs{color:var(--acc);}
  .sub{color:var(--muted); font-size:13px; margin:0 0 16px;}
  .stage{ position:relative; background:#070b16; border:1px solid var(--line);
    border-radius:14px; overflow:hidden; box-shadow:0 10px 40px rgba(0,0,0,.45); }
  canvas{display:block; width:100%; height:auto;}
  .controls{display:flex; flex-wrap:wrap; gap:10px; margin:14px 0;}
  button{ cursor:pointer; border:1px solid var(--line); background:var(--panel2);
    color:var(--ink); padding:10px 16px; border-radius:10px; font-size:14px;
    font-weight:600; transition:.15s; user-select:none; }
  button:hover{border-color:#3c4d7d; background:#222c52; transform:translateY(-1px);}
  button:active{transform:translateY(0);}
  button.primary{background:linear-gradient(180deg,#2563eb,#1e40af); border-color:#3b82f6;}
  button.danger{background:linear-gradient(180deg,#b45309,#92400e); border-color:#d97706;}
  button:disabled{opacity:.5; cursor:not-allowed; transform:none;}
  .grid{display:grid; grid-template-columns:1fr 1fr; gap:16px; margin-top:6px;}
  @media(max-width:820px){ .grid{grid-template-columns:1fr;} }
  .card{background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px;}
  .card h2{margin:0 0 12px; font-size:16px; display:flex; align-items:center; gap:8px;}
  .dot{width:12px; height:12px; border-radius:50%; display:inline-block;}
  .dot.o{background:var(--o);} .dot.n{background:var(--n);}
  .slider{margin:11px 0;}
  .slider .row{display:flex; justify-content:space-between; font-size:13px; margin-bottom:4px;}
  .slider .val{color:var(--acc); font-weight:700;}
  input[type=range]{width:100%; accent-color:#3b82f6;}
  .o-card input[type=range]{accent-color:var(--o);}
  .n-card input[type=range]{accent-color:var(--n);}
  .stats{margin-top:16px;}
  .runsbox{display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-bottom:12px;}
  .runsbox input{width:120px; padding:9px 10px; border-radius:8px; border:1px solid var(--line);
    background:var(--panel2); color:var(--ink); font-size:14px;}
  .result{display:none;}
  .result.show{display:block;}
  .bar{height:30px; border-radius:8px; background:var(--panel2); overflow:hidden; display:flex; margin:8px 0;}
  .bar > span{display:flex; align-items:center; justify-content:flex-end; padding:0 10px;
    font-size:12px; font-weight:700; color:#06101f; white-space:nowrap; min-width:0;}
  .seg-o{background:linear-gradient(90deg,#0ea5e9,#7dd3fc);}
  .seg-n{background:linear-gradient(90deg,#ef4444,#fca5a5);}
  .seg-d{background:linear-gradient(90deg,#64748b,#94a3b8);}
  .resgrid{display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:12px;}
  .rcell{background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:12px; text-align:center;}
  .rcell .big{font-size:24px; font-weight:800;}
  .rcell .lbl{font-size:12px; color:var(--muted); margin-top:3px;}
  .rcell.o .big{color:var(--o);} .rcell.n .big{color:var(--n);} .rcell.d .big{color:var(--muted);}
  .meta{color:var(--muted); font-size:12px; margin-top:10px;}
  .legend{display:flex; gap:16px; flex-wrap:wrap; color:var(--muted); font-size:12px; margin-top:10px;}
  .spin{display:none; align-items:center; gap:10px; color:var(--muted); font-size:13px;}
  .spin.show{display:flex;}
  .spinner{width:16px; height:16px; border:3px solid #2a3556; border-top-color:#3b82f6;
    border-radius:50%; animation:sp .8s linear infinite;}
  @keyframes sp{to{transform:rotate(360deg);}}
  .foot{color:var(--muted); font-size:12px; margin-top:26px; line-height:1.6;}
  .modebar{display:flex; align-items:center; gap:8px; margin:14px 0 0; flex-wrap:wrap;}
  .modelbl{color:var(--muted); font-size:13px; font-weight:700; margin-right:2px;}
  button.mode{background:var(--panel2); border:1px solid var(--line); padding:9px 14px;}
  button.mode.active{background:linear-gradient(180deg,#7f1d1d,#991b1b); border-color:#ef4444; color:#fff;}
  button.mode.arc.active{background:linear-gradient(180deg,#1e40af,#1d4ed8); border-color:#3b82f6;}
  .modenote{color:var(--acc); font-size:12px; margin-left:4px; flex-basis:100%;}
  .logwrap{margin-top:12px; background:var(--panel); border:1px solid var(--line); border-radius:12px; overflow:hidden; display:none;}
  .logwrap.show{display:block;}
  .logttl{padding:8px 12px; font-weight:700; font-size:13px; background:var(--panel2); border-bottom:1px solid var(--line);}
  .log{height:128px; overflow-y:auto; padding:8px 12px; font-size:12.5px; line-height:1.65;
       font-family:Consolas,"D2Coding","Malgun Gothic",monospace;}
  .logline{color:#cbd5e1; border-bottom:1px dashed rgba(120,140,200,.10); padding:1px 0;}
  .methods{display:none; grid-template-columns:repeat(3,1fr); gap:10px; margin-top:10px;}
  .methods.show{display:grid;}
  .mcell{background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:10px; text-align:center;}
  .mcell .big{font-size:18px; font-weight:800;}
  .mcell.p .big{color:var(--n);} .mcell.b .big{color:var(--o);} .mcell.d .big{color:var(--muted);}
  .mcell .lbl{font-size:11px; color:var(--muted); margin-top:3px;}
  .card.locked{opacity:.5;}
  .card.locked input[type=range]{cursor:not-allowed;}
  .card.locked .val{opacity:.7;}
  .lockbadge{display:none; font-size:11px; color:var(--acc); margin-left:auto; font-weight:700;}
  .card.locked .lockbadge{display:inline;}
  /* 미니뷰(PIP): 창 크기에 맞춰 경기 화면만 비율 유지하며 꽉 차게 */
  .pipbar{display:none; position:fixed; top:8px; right:8px; gap:6px; z-index:20; opacity:.3; transition:opacity .2s;}
  .pipbar:hover{opacity:1;}
  .pipbtn{padding:5px 9px; font-size:12px; font-weight:700; background:rgba(20,27,48,.88);
    border:1px solid var(--line); border-radius:7px; color:var(--ink); cursor:pointer;}
  .pipbtn:hover{background:#222c52;}
  body.pip{overflow:hidden; background:#000;}
  body.pip .wrap{max-width:none; margin:0; padding:0;}
  body.pip .wrap > *:not(.stage):not(.pipbar){display:none !important;}
  body.pip .stage{position:fixed; inset:0; border:0; border-radius:0; box-shadow:none; background:#000;}
  body.pip .stage canvas{width:100%; height:100%; object-fit:contain;}
  body.pip .pipbar{display:flex;}
  .reccard{display:flex; align-items:center; gap:14px; flex-wrap:wrap; margin-top:12px; padding:10px 14px;
    background:var(--panel); border:1px solid var(--line); border-radius:12px; font-size:13px;}
  .recttl{font-weight:700; color:var(--ink);}
  .recline{color:var(--muted);}
  .recreset{margin-left:auto; padding:6px 12px; font-size:12px;}
</style>
</head>
<body>
<div class="wrap">
  <h1>⚾ <span class="o">오타니</span> <span class="vs">VS</span> <span class="n">은가누</span> 🥊 <span style="font-size:14px;color:var(--muted)">2D 링 대결 시뮬레이터</span></h1>
  <p class="sub">사각 링 위를 <b>2D로 돌아다니며</b> 싸웁니다 · 긴 리치+넉백의 <b style="color:var(--o)">오타니</b> vs 압도적 맷집+돌진 한 방의 <b style="color:var(--n)">은가누</b></p>

  <div class="stage">
    <canvas id="cv" width="920" height="560"></canvas>
  </div>

  <div class="modebar">
    <span class="modelbl">전투 모드</span>
    <button id="mArcade" class="mode arc active">⚾ 아케이드</button>
    <button id="mReal" class="mode">🥊 리얼 (실제 스탯)</button>
    <span id="modeNote" class="modenote"></span>
  </div>

  <div class="controls">
    <button id="btnStart" class="primary">▶ 경기 시작 / 다시하기</button>
    <button id="btnPause">⏸ 일시정지</button>
    <button id="btnReset" class="danger">↻ 파라미터 초기화</button>
    <button id="btnPip">🔍 미니뷰(PIP)</button>
  </div>

  <div class="reccard">
    <span class="recttl">📋 전적</span>
    <span id="recArc" class="recline"></span>
    <span id="recReal" class="recline"></span>
    <button id="btnRecReset" class="recreset">전적 초기화</button>
  </div>

  <div id="logwrap" class="logwrap">
    <div class="logttl">📣 실시간 해설 </div>
    <div id="log" class="log"></div>
  </div>

  <div class="grid">
    <div class="card o-card">
      <h2><span class="dot o"></span> 오타니 (야구 방망이) <span class="lockbadge">🔒 실제 스탯 고정</span></h2>
      <div class="slider"><div class="row"><span>체력 (HP)</span><span class="val" id="v_oHp"></span></div>
        <input type="range" id="oHp" min="10" max="500" step="5"></div>
      <div class="slider"><div class="row"><span>데미지</span><span class="val" id="v_oDmg"></span></div>
        <input type="range" id="oDmg" min="1" max="100" step="1"></div>
      <div class="slider"><div class="row"><span>이동 속도</span><span class="val" id="v_oSpeed"></span></div>
        <input type="range" id="oSpeed" min="0.2" max="12" step="0.05"></div>
      <div class="slider"><div class="row"><span>명중률</span><span class="val" id="v_oAcc"></span></div>
        <input type="range" id="oAcc" min="0" max="100" step="1"></div>
      <div class="slider"><div class="row"><span>리치 (사거리)</span><span class="val" id="v_oReach"></span></div>
        <input type="range" id="oReach" min="60" max="300" step="5"></div>
      <div class="slider"><div class="row"><span>넉백 (밀어내기)</span><span class="val" id="v_oKnock"></span></div>
        <input type="range" id="oKnock" min="0" max="300" step="5"></div>
      <div class="slider"><div class="row"><span>공격 쿨다운 (초)</span><span class="val" id="v_oCd"></span></div>
        <input type="range" id="oCd" min="0.1" max="3" step="0.05"></div>
    </div>

    <div class="card n-card">
      <h2><span class="dot n"></span> 은가누 (맨주먹) <span class="lockbadge">🔒 실제 스탯 고정</span></h2>
      <div class="slider"><div class="row"><span>체력 (HP)</span><span class="val" id="v_nHp"></span></div>
        <input type="range" id="nHp" min="10" max="800" step="5"></div>
      <div class="slider"><div class="row"><span>데미지</span><span class="val" id="v_nDmg"></span></div>
        <input type="range" id="nDmg" min="1" max="200" step="1"></div>
      <div class="slider"><div class="row"><span>이동 속도 (돌진)</span><span class="val" id="v_nSpeed"></span></div>
        <input type="range" id="nSpeed" min="0.2" max="14" step="0.05"></div>
      <div class="slider"><div class="row"><span>명중률</span><span class="val" id="v_nAcc"></span></div>
        <input type="range" id="nAcc" min="0" max="100" step="1"></div>
      <div class="slider"><div class="row"><span>리치 (사거리)</span><span class="val" id="v_nReach"></span></div>
        <input type="range" id="nReach" min="30" max="200" step="2"></div>
      <div class="slider"><div class="row"><span>공격 쿨다운 (초)</span><span class="val" id="v_nCd"></span></div>
        <input type="range" id="nCd" min="0.1" max="3" step="0.05"></div>
    </div>
  </div>

  <div class="card stats">
    <h2>📊 통계 시뮬레이션 (시각화 없이 고속 반복)</h2>
    <div class="runsbox">
      <label>반복 횟수</label>
      <input type="number" id="runs" value="10000" min="1" max="200000" step="1000">
      <button id="btnSim" class="primary">📊 시뮬레이션 실행</button>
      <div class="spin" id="spin"><div class="spinner"></div> 서버에서 계산 중...</div>
    </div>
    <div class="result" id="result">
      <div class="bar" id="bar">
        <span class="seg-o" id="seg_o"></span>
        <span class="seg-n" id="seg_n"></span>
        <span class="seg-d" id="seg_d"></span>
      </div>
      <div class="resgrid">
        <div class="rcell o"><div class="big" id="r_o">-</div><div class="lbl">오타니 승</div></div>
        <div class="rcell n"><div class="big" id="r_n">-</div><div class="lbl">은가누 승</div></div>
        <div class="rcell d"><div class="big" id="r_d">-</div><div class="lbl">무승부</div></div>
      </div>
      <div class="methods" id="methods">
        <div class="mcell p"><div class="big" id="m_punch">-</div><div class="lbl">은가누 펀치 KO</div></div>
        <div class="mcell b"><div class="big" id="m_bat">-</div><div class="lbl">오타니 배트 KO</div></div>
        <div class="mcell d"><div class="big" id="m_dec">-</div><div class="lbl">판정/TKO(누적)</div></div>
      </div>
      <div class="meta" id="r_meta"></div>
    </div>
    <div class="legend">
      <span><b style="color:var(--ink)">규칙:</b> 30초(1800틱) 초과 시 남은 HP 비율로 판정 · 통계는 현재 슬라이더 값 그대로 서버(Python)에서 계산됩니다.</span>
    </div>
  </div>

  <div class="foot">
    Tip: 오타니는 링을 <b>빙빙 돌며 거리</b>를 벌리고 넉백으로 은가누를 떼어낼 때 강합니다. 코너에 몰려 클린치되면
    은가누의 한 방에 무너집니다. · 시각화와 통계는 동일한 전투 규칙(JS↔Python 미러링)을 사용합니다.
  </div>

  <div id="pipbar" class="pipbar">
    <button id="pipMode" class="pipbtn">🥊 리얼</button>
    <button id="pipPause" class="pipbtn">⏸</button>
    <button id="pipExit" class="pipbtn">✕ 닫기</button>
  </div>
</div>

<script>
// ===========================================================================
//  전투 엔진 상수 (Python 측 상수와 반드시 동일) - 월드 좌표계
// ===========================================================================
var CONST = {
  DT: 1/60, WX1: 760, WY1: 440, INSET: 40,
  R_O: 24, R_N: 34, MIN_SEP: 24+34, STAGGER: 0.22, MAX_TICKS: 1800,
  KITE: 0.78, ORBIT: 1.0, RETREAT_W: 1.0, ORBIT_W: 0.6,
  X0_O: 230, Y0_O: 250, X0_N: 540, Y0_N: 200,
  MIN_X_O: 40+24, MAX_X_O: 760-40-24, MIN_Y_O: 40+24, MAX_Y_O: 440-40-24,
  MIN_X_N: 40+34, MAX_X_N: 760-40-34, MIN_Y_N: 40+34, MAX_Y_N: 440-40-34,
  SWING_DUR: 0.24, PUNCH_DUR: 0.26, AUTO_RESTART: 2.4
};

var DEFAULTS = {
  oHp:120, oDmg:16, oSpeed:2.4, oAcc:78, oReach:175, oKnock:70, oCd:0.55,
  nHp:240, nDmg:38, nSpeed:3.85, nAcc:62, nReach:72, nCd:0.50
};

// 리얼 모드 상수 (Python REAL 과 동일하게 유지)
var REAL = {
  O_WINDUP:0.34, O_RECOVER:0.42,
  N_WINDUP:0.12, N_RECOVER:0.16, N_FEINT_RECOVER:0.10,
  O_REACT:0.32, N_REACT:0.18,
  N_SLIP_BASE:0.40, O_SLIP_BASE:0.03,
  N_FEINT_CHANCE:0.22, O_BAIT_CHANCE:0.5,
  O_SWING_COST:11, N_PUNCH_COST:6,
  O_STAM_REGEN:5, N_STAM_REGEN:4,
  O_HEAD:42, O_BODY:20, N_HEAD:26, N_BODY:13,
  KO_O:0.80, KO_N:0.70, KO_THRESH:45,
  HEAD_CHANCE:0.5, STUN_TIME:0.7, FINISH_MULT:1.3,
  MAX_TICKS:2400, HP:100
};
// 리얼 모드 고정 프리셋(HP 동일 + 실제 명중률 등) - 슬라이더 표시/엔진 입력값
var REAL_PRESET = { oHp:100, nHp:100, oDmg:16, nDmg:38, oSpeed:2.4, nSpeed:3.85,
  oAcc:60, nAcc:40, oReach:175, oKnock:70, oCd:0.55, nReach:72, nCd:0.50 };
var mode = "arcade";   // "arcade" | "real"

// 전적(누적 승패) - 모드별, localStorage 영구 저장
var RECORD_KEY="ovn_record_v1";
function blankRec(){ return {ohtani:0, ngannou:0, draw:0, streakWho:null, streak:0}; }
function loadRecord(){ try{ var r=JSON.parse(localStorage.getItem(RECORD_KEY)); if(r&&r.arcade&&r.real) return r; }catch(e){} return {arcade:blankRec(), real:blankRec()}; }
var record = loadRecord();
function saveRecord(){ try{ localStorage.setItem(RECORD_KEY, JSON.stringify(record)); }catch(e){} }
function recordResult(winner){
  var r=record[mode]; if(!r) return;
  if(winner==="ohtani") r.ohtani++; else if(winner==="ngannou") r.ngannou++; else r.draw++;
  if(winner==="draw"){ r.streakWho=null; r.streak=0; }
  else if(r.streakWho===winner) r.streak++; else { r.streakWho=winner; r.streak=1; }
  saveRecord(); updateRecordDOM();
}
function updateRecordDOM(){
  function line(label, x){ return label+"  오타니 "+x.ohtani+" : "+x.ngannou+" 은가누"+(x.draw?(" · 무 "+x.draw):"")+"  ("+(x.ohtani+x.ngannou+x.draw)+"전)"; }
  var aEl=document.getElementById("recArc"), rEl=document.getElementById("recReal");
  if(aEl) aEl.textContent=line("⚾ 아케이드", record.arcade);
  if(rEl) rEl.textContent=line("🥊 리얼", record.real);
}

var SLIDERS = ["oHp","oDmg","oSpeed","oAcc","oReach","oKnock","oCd",
               "nHp","nDmg","nSpeed","nAcc","nReach","nCd"];

function fmt(id, v){
  if(id==="oAcc"||id==="nAcc") return Math.round(v)+"%";
  if(id==="oCd"||id==="nCd")   return Number(v).toFixed(2)+"s";
  if(id==="oSpeed"||id==="nSpeed") return Number(v).toFixed(2);
  if(id==="oReach"||id==="nReach"||id==="oKnock") return Math.round(v)+"px";
  return Math.round(v);
}
function setSlider(id, v){
  var el=document.getElementById(id); el.value=v;
  document.getElementById("v_"+id).textContent=fmt(id,v);
}
function bindSliders(){
  SLIDERS.forEach(function(id){
    var el=document.getElementById(id);
    el.addEventListener("input", function(){
      document.getElementById("v_"+id).textContent=fmt(id, el.value);
    });
  });
}
function resetParams(){ SLIDERS.forEach(function(id){ setSlider(id, DEFAULTS[id]); }); }
function applyPreset(pre){ SLIDERS.forEach(function(id){ if(pre[id]!==undefined) setSlider(id, pre[id]); }); }

function readCfg(){
  function g(id){ return parseFloat(document.getElementById(id).value); }
  return {
    oHp:g("oHp"), oDmg:g("oDmg"), oSpeed:g("oSpeed"), oAcc:g("oAcc")/100,
    oReach:g("oReach"), oKnock:g("oKnock"), oCd:g("oCd"),
    nHp:g("nHp"), nDmg:g("nDmg"), nSpeed:g("nSpeed"), nAcc:g("nAcc")/100,
    nReach:g("nReach"), nCd:g("nCd")
  };
}

// ===========================================================================
//  시뮬레이션 1틱 (Python simulate_once 와 동일 로직 + 시각효과) - 2D
// ===========================================================================
function newState(c){
  return {
    ox:CONST.X0_O, oy:CONST.Y0_O, nx:CONST.X0_N, ny:CONST.Y0_N,
    hpO:c.oHp, hpN:c.nHp, maxO:c.oHp, maxN:c.nHp,
    swingT:0, punchT:0, stagT:0, t:0, over:false, winner:null, winnerKO:false,
    swingAnim:0, punchAnim:0, faceO:1, faceN:-1,
    particles:[], dmgNums:[], dust:[], shocks:[], texts:[], shake:0,
    intro:1.3, koTimer:0, hitStop:0,
    flashO:0, flashN:0, recoilOx:0, recoilOy:0, headSnap:0,
    dispO:1, dispN:1, chipO:1, chipN:1, overT:0,
    pOx:CONST.X0_O, pOy:CONST.Y0_O, pNx:CONST.X0_N, pNy:CONST.Y0_N,
    // 리얼 모드 상태머신 (0 ready,1 windup,3 recover,4 stun)
    foS:0, foT:0, foStam:100, foWu:0,
    fnS:0, fnT:0, fnStam:100, fnWu:0, fnFeint:false,
    log:[], recorded:false
  };
}
function endFight(s,w,ko){ s.winner=w; s.over=true; s.winnerKO=!!ko; s.koTimer = ko?1.0:0; }

function stepSim(s, c){
  if(s.over) return;
  var K=CONST; s.t++;
  if(s.swingT>0) s.swingT-=K.DT;
  if(s.punchT>0) s.punchT-=K.DT;
  if(s.stagT>0)  s.stagT -=K.DT;
  // (swingAnim/punchAnim/shake 등 시각 타이머는 updateEffects에서 실시간 감쇠)

  var desired = c.oReach*K.KITE;
  var dx,dy,d;

  // --- 오타니: 방망이 ---
  dx=s.nx-s.ox; dy=s.ny-s.oy; d=Math.hypot(dx,dy); if(d<1e-6) d=1e-6;
  if(s.swingT<=0 && d<=c.oReach){
    s.swingT=c.oCd; s.swingAnim=K.SWING_DUR;
    if(Math.random()<c.oAcc){
      s.hpN-=c.oDmg;
      s.nx+=dx/d*c.oKnock; s.ny+=dy/d*c.oKnock;
      s.nx=clamp(s.nx,K.MIN_X_N,K.MAX_X_N); s.ny=clamp(s.ny,K.MIN_Y_N,K.MAX_Y_N);
      s.stagT=K.STAGGER;
      hitFx(s, s.nx, s.ny, "#fde047", 22); spawnDmg(s,s.nx,s.ny,c.oDmg,"o");
      spawnShock(s, s.nx, s.ny, "#fde047", 70); spawnText(s, s.nx, s.ny, "깡!", "#fde047");
      s.flashN=0.13; s.hitStop=Math.max(s.hitStop,0.05); s.shake=Math.max(s.shake,0.16);
      if(s.hpN<=0){ endFight(s,"ohtani",true); s.shake=0.42; spawnText(s,s.nx,s.ny,"💥","#fde047"); return; }
    }
  }

  // --- 오타니: 이동(후퇴 + 선회) ---
  dx=s.nx-s.ox; dy=s.ny-s.oy; d=Math.hypot(dx,dy); if(d<1e-6) d=1e-6;
  var ux=dx/d, uy=dy/d, ax=-ux, ay=-uy, tx=-uy*K.ORBIT, ty=ux*K.ORBIT, mx,my;
  if(d<desired){ mx=ax*K.RETREAT_W+tx*K.ORBIT_W; my=ay*K.RETREAT_W+ty*K.ORBIT_W; }
  else { mx=tx; my=ty; }
  var ml=Math.hypot(mx,my);
  if(ml>1e-6){
    s.ox+=mx/ml*c.oSpeed; s.oy+=my/ml*c.oSpeed;
    s.ox=clamp(s.ox,K.MIN_X_O,K.MAX_X_O); s.oy=clamp(s.oy,K.MIN_Y_O,K.MAX_Y_O);
  }

  // --- 은가누: 펀치 + 돌진 ---
  if(s.stagT<=0){
    dx=s.ox-s.nx; dy=s.oy-s.ny; d=Math.hypot(dx,dy); if(d<1e-6) d=1e-6;
    if(s.punchT<=0 && d<=c.nReach){
      s.punchT=c.nCd; s.punchAnim=K.PUNCH_DUR;
      if(Math.random()<c.nAcc){
        s.hpO-=c.nDmg;
        hitFx(s, s.ox, s.oy, "#fca5a5", 28); spawnDmg(s,s.ox,s.oy,c.nDmg,"n");
        spawnShock(s, s.ox, s.oy, "#fecaca", 96); spawnText(s, s.ox, s.oy, "퍽!", "#f87171");
        s.flashO=0.16; s.headSnap=0.22; s.hitStop=Math.max(s.hitStop,0.09); s.shake=Math.max(s.shake,0.3);
        var rdx=s.ox-s.nx, rdy=s.oy-s.ny, rl=Math.hypot(rdx,rdy)||1;
        s.recoilOx=rdx/rl*16; s.recoilOy=rdy/rl*16;
        if(s.hpO<=0){ endFight(s,"ngannou",true); s.shake=0.5; spawnText(s,s.ox,s.oy,"💥","#f87171"); return; }
      }
    }
    s.nx+=dx/d*c.nSpeed; s.ny+=dy/d*c.nSpeed;
    var sx=s.nx-s.ox, sy=s.ny-s.oy, sd=Math.hypot(sx,sy);
    if(sd<K.MIN_SEP){ if(sd<1e-6){sx=1;sy=0;sd=1;} s.nx=s.ox+sx/sd*K.MIN_SEP; s.ny=s.oy+sy/sd*K.MIN_SEP; }
    s.nx=clamp(s.nx,K.MIN_X_N,K.MAX_X_N); s.ny=clamp(s.ny,K.MIN_Y_N,K.MAX_Y_N);
  }

  // 바라보는 방향(화면 x 기준)
  s.faceO = (s.nx>=s.ox)?1:-1;
  s.faceN = (s.ox<=s.nx)?-1:1;

  if(!s.over && s.t>=K.MAX_TICKS){
    var fO=s.hpO/s.maxO, fN=s.hpN/s.maxN;
    if(fO>fN+1e-6) endFight(s,"ohtani");
    else if(fN>fO+1e-6) endFight(s,"ngannou");
    else endFight(s,"draw");
  }
}
function clamp(v,lo,hi){ return v<lo?lo:(v>hi?hi:v); }

// ===========================================================================
//  실시간 해설 로그
// ===========================================================================
function pushLog(s, txt){
  s.log.push(txt); if(s.log.length>80) s.log.shift();
  var el=document.getElementById("log");
  if(el){
    var line=document.createElement("div"); line.className="logline";
    line.textContent="["+(s.t/60).toFixed(1)+"s] "+txt;
    el.appendChild(line);
    while(el.childNodes.length>80) el.removeChild(el.firstChild);
    el.scrollTop=el.scrollHeight;
  }
}
function clearLog(){ var el=document.getElementById("log"); if(el) el.innerHTML=""; }

// ===========================================================================
//  리얼 모드 1틱 (Python simulate_once_real 과 동일 로직 + 해설/연출)
//  상태: 0 ready, 1 windup, 3 recover, 4 stun
// ===========================================================================
function stepReal(s, c){
  if(s.over) return;
  var K=CONST, R=REAL; s.t++;
  var odk=c.oDmg/16, ndk=c.nDmg/38;

  function hit(att){
    var ax,ay,tx,ty,reach,accB,head,body,defState,defN,stam;
    if(att==="O"){ ax=s.ox;ay=s.oy;tx=s.nx;ty=s.ny; reach=c.oReach; accB=c.oAcc; head=R.O_HEAD*odk; body=R.O_BODY*odk; defState=s.fnS; defN=true; stam=s.foStam; }
    else { ax=s.nx;ay=s.ny;tx=s.ox;ty=s.oy; reach=c.nReach; accB=c.nAcc; head=R.N_HEAD*ndk; body=R.N_BODY*ndk; defState=s.foS; defN=false; stam=s.fnStam; }
    if(Math.hypot(tx-ax,ty-ay) > reach+8){ pushLog(s, att==="O"?"오타니 풀스윙 — 헛스윙!":"은가누 펀치 — 허공!"); return false; }
    if(defN){
      var slip=R.N_SLIP_BASE*(0.5+0.5*s.fnStam/100); if(s.fnS!==0) slip*=0.3;
      if(Math.random()<slip){ pushLog(s,"은가누 슬립! 배트 회피"); spawnText(s,s.nx,s.ny,"슬립!","#93c5fd"); return false; }
    } else { if(Math.random()<R.O_SLIP_BASE){ pushLog(s,"오타니 가까스로 회피!"); return false; } }
    var acc=accB*(0.6+0.4*stam/100);
    var finishing=(defState===1||defState===3||defState===4);
    if(finishing) acc=Math.min(1,acc+0.3);
    if(Math.random()>=acc){ pushLog(s, att==="O"?"오타니 빗맞음":"은가누 빗맞음"); return false; }
    var isHead=(Math.random()<R.HEAD_CHANCE)||finishing;
    var dmg=(isHead?head:body)*(finishing?R.FINISH_MULT:1);
    if(defN){
      s.hpN-=dmg;
      var dx=s.nx-s.ox,dy=s.ny-s.oy,dl=Math.hypot(dx,dy)||1;
      s.nx=clamp(s.nx+dx/dl*c.oKnock,K.MIN_X_N,K.MAX_X_N); s.ny=clamp(s.ny+dy/dl*c.oKnock,K.MIN_Y_N,K.MAX_Y_N);
      hitFx(s,s.nx,s.ny,"#fde047",isHead?22:14); spawnDmg(s,s.nx,s.ny,dmg,"o");
      spawnShock(s,s.nx,s.ny,"#fde047",isHead?80:55); spawnText(s,s.nx,s.ny,isHead?"깡!":"퍽","#fde047");
      s.flashN=0.13; s.hitStop=Math.max(s.hitStop,isHead?0.06:0.04); s.shake=Math.max(s.shake,isHead?0.22:0.12);
      pushLog(s, isHead?("오타니 배트 헤드 적중 "+Math.round(dmg)):("오타니 배트 바디 "+Math.round(dmg)));
      if(s.hpN<=0){ s.hpN=0; s.dispN=0; s.chipN=0; endFight(s,"ohtani",false); s.shake=0.42; pushLog(s,"🏆 은가누 다운 — 오타니 TKO 승!"); return true; }
      if(isHead && s.hpN<R.KO_THRESH && Math.random()<R.KO_O){
        s.hpN=0; s.dispN=0; s.chipN=0; spawnShock(s,s.nx,s.ny,"#fde047",100); spawnText(s,s.nx,s.ny,"깡!💥","#fde047");
        s.flashN=0.16; s.hitStop=Math.max(s.hitStop,0.1); s.shake=0.5;
        endFight(s,"ohtani",true); pushLog(s,"💥 오타니 풀스윙 헤드 직격 — 은가누 K.O.!! 🏆"); return true;
      }
      if(isHead){ s.fnS=4; s.fnT=R.STUN_TIME; s.fnWu=0; pushLog(s,"은가누 휘청! (스턴)"); }
    } else {
      s.hpO-=dmg;
      hitFx(s,s.ox,s.oy,"#fca5a5",isHead?24:16); spawnDmg(s,s.ox,s.oy,dmg,"n");
      spawnShock(s,s.ox,s.oy,"#fecaca",isHead?84:55); spawnText(s,s.ox,s.oy,isHead?"퍽!":"턱","#f87171");
      s.flashO=0.14; s.headSnap=0.2; s.hitStop=Math.max(s.hitStop,isHead?0.07:0.05); s.shake=Math.max(s.shake,isHead?0.26:0.14);
      var rdx=s.ox-s.nx,rdy=s.oy-s.ny,rl=Math.hypot(rdx,rdy)||1; s.recoilOx=rdx/rl*14; s.recoilOy=rdy/rl*14;
      pushLog(s, isHead?("은가누 펀치 헤드 적중 "+Math.round(dmg)):("은가누 바디블로 "+Math.round(dmg)));
      if(s.hpO<=0){ s.hpO=0; s.dispO=0; s.chipO=0; endFight(s,"ngannou",false); s.shake=0.45; pushLog(s,"🏆 오타니 다운 — 은가누 TKO 승!"); return true; }
      if(isHead && s.hpO<R.KO_THRESH && Math.random()<R.KO_N){
        s.hpO=0; s.dispO=0; s.chipO=0; spawnShock(s,s.ox,s.oy,"#fecaca",104); spawnText(s,s.ox,s.oy,"퍽!💥","#f87171");
        s.flashO=0.18; s.headSnap=0.24; s.hitStop=Math.max(s.hitStop,0.11); s.shake=0.55;
        endFight(s,"ngannou",true); pushLog(s,"💥 은가누 강펀치 헤드 직격 — 오타니 K.O.!! 🏆"); return true;
      }
      if(isHead){ s.foS=4; s.foT=R.STUN_TIME; s.foWu=0; pushLog(s,"오타니 휘청! (스턴)"); }
    }
    return false;
  }

  // ---- 상태머신: 오타니 ----
  var st=s.foS;
  if(st===0){ s.foStam=Math.min(100,s.foStam+R.O_STAM_REGEN*K.DT); }
  else if(st===1){ s.foWu+=K.DT; s.foT-=K.DT; if(s.foT<=0){ if(hit("O")) return; s.swingAnim=K.SWING_DUR; s.foS=3; s.foT=R.O_RECOVER; s.foWu=0; } }
  else if(st===3){ s.foT-=K.DT; if(s.foT<=0) s.foS=0; }
  else if(st===4){ s.foT-=K.DT; if(s.foT<=0) s.foS=0; }
  // ---- 상태머신: 은가누 ----
  st=s.fnS;
  if(st===0){ s.fnStam=Math.min(100,s.fnStam+R.N_STAM_REGEN*K.DT); }
  else if(st===1){ s.fnWu+=K.DT; s.fnT-=K.DT; if(s.fnT<=0){ if(s.fnFeint){ s.fnFeint=false; s.fnS=3; s.fnT=R.N_FEINT_RECOVER; s.fnWu=0; } else { if(hit("N")) return; s.punchAnim=K.PUNCH_DUR; s.fnS=3; s.fnT=R.N_RECOVER; s.fnWu=0; } } }
  else if(st===3){ s.fnT-=K.DT; if(s.fnT<=0) s.fnS=0; }
  else if(st===4){ s.fnT-=K.DT; if(s.fnT<=0) s.fnS=0; }

  // ---- 오타니 AI (ready) ----
  if(s.foS===0){
    var d=Math.hypot(s.nx-s.ox,s.ny-s.oy), swing=false;
    if(s.foStam>6 && d<=c.oReach){
      if(s.fnS===1 && s.fnFeint) swing=Math.random()<R.O_BAIT_CHANCE;
      else if(s.fnS===1||s.fnS===3||s.fnS===4) swing=true;
      else if(d<=c.oReach*0.72) swing=true;
    }
    if(swing){
      var wf=1+(1-s.foStam/100)*0.4;
      pushLog(s, (s.fnS===1&&s.fnFeint)?"은가누 페인트… 오타니 낚여 풀스윙!":"오타니 배트 풀스윙 장전!");
      s.foS=1; s.foT=R.O_WINDUP*wf; s.foWu=0; s.foStam-=R.O_SWING_COST;
    } else {
      var dx=s.nx-s.ox,dy=s.ny-s.oy,dd=Math.hypot(dx,dy)||1e-6;
      var ux=dx/dd,uy=dy/dd,ax=-ux,ay=-uy,tx=-uy,ty=ux,mx,my;
      var des=c.oReach*K.KITE;
      if(dd<des){ mx=ax+tx*0.6; my=ay+ty*0.6; } else { mx=tx; my=ty; }
      var ml=Math.hypot(mx,my)||1e-6, spd=c.oSpeed*(0.7+0.3*s.foStam/100);
      s.ox=clamp(s.ox+mx/ml*spd,K.MIN_X_O,K.MAX_X_O); s.oy=clamp(s.oy+my/ml*spd,K.MIN_Y_O,K.MAX_Y_O);
    }
  }
  // ---- 은가누 AI (ready) ----
  if(s.fnS===0){
    var d2=Math.hypot(s.ox-s.nx,s.oy-s.ny);
    var aware=(s.foS===1 && s.foWu>=R.N_REACT);
    if(d2<=c.nReach){
      if(!aware && Math.random()<R.N_FEINT_CHANCE){ s.fnS=1; s.fnT=R.N_WINDUP; s.fnFeint=true; s.fnWu=0; pushLog(s,"은가누 페인트로 견제"); }
      else if(s.fnStam>4){ var wf2=1+(1-s.fnStam/100)*0.4; s.fnS=1; s.fnT=R.N_WINDUP*wf2; s.fnFeint=false; s.fnWu=0; s.fnStam-=R.N_PUNCH_COST; pushLog(s, aware?"은가누 카운터 펀치!":"은가누 강펀치 노림!"); }
    } else {
      // 전진 압박 - 배트를 맞더라도 파고듦
      var dx3=s.ox-s.nx,dy3=s.oy-s.ny,dd3=Math.hypot(dx3,dy3)||1e-6;
      var ux3=dx3/dd3,uy3=dy3/dd3,px3=-uy3,py3=ux3;
      var mx3=ux3+px3*0.35,my3=uy3+py3*0.35,ml3=Math.hypot(mx3,my3)||1e-6,spd3=c.nSpeed*(0.7+0.3*s.fnStam/100);
      var nnx=s.nx+mx3/ml3*spd3, nny=s.ny+my3/ml3*spd3;
      var sx=nnx-s.ox,sy=nny-s.oy,sd=Math.hypot(sx,sy);
      if(sd<K.MIN_SEP){ if(sd<1e-6){sx=1;sy=0;sd=1;} nnx=s.ox+sx/sd*K.MIN_SEP; nny=s.oy+sy/sd*K.MIN_SEP; }
      s.nx=clamp(nnx,K.MIN_X_N,K.MAX_X_N); s.ny=clamp(nny,K.MIN_Y_N,K.MAX_Y_N);
    }
  }

  s.faceO=(s.nx>=s.ox)?1:-1; s.faceN=(s.ox<=s.nx)?-1:1;

  if(!s.over && s.t>=R.MAX_TICKS){
    var fO=s.hpO/s.maxO, fN=s.hpN/s.maxN;
    if(fO>fN+1e-6) endFight(s,"ohtani",false); else if(fN>fO+1e-6) endFight(s,"ngannou",false); else endFight(s,"draw",false);
    pushLog(s,"시간 종료 — 판정");
  }
}

// ===========================================================================
//  좌표 투영 (월드 -> 화면)  : 사각 링 원근감
// ===========================================================================
var PROJ = { BACK_Y:175, FRONT_Y:505, BACK_HW:250, FRONT_HW:400, CX:460,
             BACK_S:0.60, FRONT_S:1.05 };
function project(wx, wy){
  var ty = wy/CONST.WY1;
  var hw = PROJ.BACK_HW + ty*(PROJ.FRONT_HW-PROJ.BACK_HW);
  return {
    x: PROJ.CX + (wx-CONST.WX1/2)/(CONST.WX1/2)*hw,
    y: PROJ.BACK_Y + ty*(PROJ.FRONT_Y-PROJ.BACK_Y),
    s: PROJ.BACK_S + ty*(PROJ.FRONT_S-PROJ.BACK_S),
    ty: ty
  };
}

// ===========================================================================
//  이미지 로딩 + 가공 (흰 배경 제거 / 얼굴 원형 크롭) - 같은 출처라 안전
// ===========================================================================
var sprN=null;   // 은가누: {canvas, w, h}
var whiteN=null; // 은가누 흰색 실루엣(피격 플래시용)
var headO=null;  // 오타니 얼굴: canvas(원형)
(function loadImages(){
  var imgN=new Image();
  imgN.onload=function(){ try{ sprN=removeWhiteBg(imgN); whiteN=makeWhite(sprN.canvas); }catch(e){} };
  imgN.src="/img/Ngannou.png";
  var imgO=new Image();
  imgO.onload=function(){ try{ headO=makeFace(imgO); }catch(e){} };
  imgO.src="/img/Ohtani.png";
})();
function makeWhite(src){
  var c=document.createElement("canvas"); c.width=src.width; c.height=src.height;
  var x=c.getContext("2d"); x.drawImage(src,0,0);
  x.globalCompositeOperation="source-in"; x.fillStyle="#ffffff"; x.fillRect(0,0,c.width,c.height);
  return c;
}

function removeWhiteBg(img){
  var W=img.naturalWidth, H=img.naturalHeight;
  var c=document.createElement("canvas"); c.width=W; c.height=H;
  var x=c.getContext("2d"); x.drawImage(img,0,0);
  var id=x.getImageData(0,0,W,H), d=id.data;
  var seen=new Uint8Array(W*H), stack=[];
  function white(k){ var i=k*4; return d[i]>234 && d[i+1]>234 && d[i+2]>234; }
  function seed(ix,iy){ var k=iy*W+ix; if(!seen[k] && white(k)){ seen[k]=1; stack.push(k); } }
  for(var px=0;px<W;px++){ seed(px,0); seed(px,H-1); }
  for(var py=0;py<H;py++){ seed(0,py); seed(W-1,py); }
  while(stack.length){
    var k=stack.pop(), ix=k%W, iy=(k/W)|0; d[k*4+3]=0;
    if(ix>0){ var a=k-1; if(!seen[a]&&white(a)){seen[a]=1;stack.push(a);} }
    if(ix<W-1){ var b=k+1; if(!seen[b]&&white(b)){seen[b]=1;stack.push(b);} }
    if(iy>0){ var e=k-W; if(!seen[e]&&white(e)){seen[e]=1;stack.push(e);} }
    if(iy<H-1){ var f=k+W; if(!seen[f]&&white(f)){seen[f]=1;stack.push(f);} }
  }
  x.putImageData(id,0,0);
  // 콘텐츠 영역 트림
  var minx=W,miny=H,maxx=0,maxy=0, found=false;
  for(var yy=0;yy<H;yy++) for(var xx=0;xx<W;xx++){
    if(d[(yy*W+xx)*4+3]>10){ found=true;
      if(xx<minx)minx=xx; if(xx>maxx)maxx=xx; if(yy<miny)miny=yy; if(yy>maxy)maxy=yy; }
  }
  if(!found){ return {canvas:c, w:W, h:H}; }
  var tw=maxx-minx+1, th=maxy-miny+1;
  var t=document.createElement("canvas"); t.width=tw; t.height=th;
  t.getContext("2d").drawImage(c, minx,miny,tw,th, 0,0,tw,th);
  return {canvas:t, w:tw, h:th};
}

function makeFace(img){
  var w=img.naturalWidth, h=img.naturalHeight;
  var cx=w*0.46, cy=h*0.40, r=w*0.40;
  var S=256, out=document.createElement("canvas"); out.width=S; out.height=S;
  var x=out.getContext("2d");
  x.save(); x.beginPath(); x.arc(S/2,S/2,S/2-2,0,Math.PI*2); x.closePath(); x.clip();
  x.drawImage(img, cx-r, cy-r, 2*r, 2*r, 0,0,S,S);
  x.restore();
  return out;
}

// ===========================================================================
//  효과
// ===========================================================================
function hitFx(s, wx, wy, color, n){
  var p=project(wx,wy), bx=p.x, by=p.y-70*p.s;
  for(var i=0;i<n;i++){
    var a=Math.random()*Math.PI*2, sp=1.5+Math.random()*4.5;
    s.particles.push({x:bx,y:by,vx:Math.cos(a)*sp,vy:Math.sin(a)*sp-1.5,life:1,color:color,r:2+Math.random()*2.5});
  }
  for(var j=0;j<6;j++){
    s.dust.push({x:p.x+(Math.random()*30-15),y:p.y,vx:(Math.random()*2-1)*1.2,vy:-Math.random()*1.2,life:1,r:3+Math.random()*4});
  }
}
function spawnDmg(s, wx, wy, val, who){
  var p=project(wx,wy);
  s.dmgNums.push({x:p.x,y:p.y-95*p.s,val:Math.round(val),who:who,life:1});
}
function spawnShock(s, wx, wy, color, maxR){
  var p=project(wx,wy);
  s.shocks.push({x:p.x, y:p.y-70*p.s, r:6, maxR:maxR*p.s, life:1, color:color});
}
function spawnText(s, wx, wy, txt, color){
  var p=project(wx,wy);
  s.texts.push({x:p.x+(Math.random()*24-12), y:p.y-120*p.s, txt:txt, color:color, life:1, scale:0.2});
}
function clamp01(v){ return v<0?0:(v>1?1:v); }
function footDust(s, px, py, x, y){
  var mv=Math.hypot(x-px, y-py);
  if(mv>1.6 && Math.random()<0.4){
    var p=project(x,y);
    s.dust.push({x:p.x+(Math.random()*14-7), y:p.y, vx:(Math.random()*2-1)*0.8, vy:-Math.random()*0.8, life:0.7, r:2+Math.random()*3});
  }
}
function updateEffects(s, dt){
  if(!dt) dt=1/60;
  var f=dt*60;
  for(var i=s.dust.length-1;i>=0;i--){ var d=s.dust[i]; d.x+=d.vx*f;d.y+=d.vy*f;d.vy+=0.08*f;d.life-=0.03*f; if(d.life<=0)s.dust.splice(i,1); }
  for(var j=s.particles.length-1;j>=0;j--){ var p=s.particles[j]; p.x+=p.vx*f;p.y+=p.vy*f;p.vy+=0.22*f;p.life-=0.035*f; if(p.life<=0)s.particles.splice(j,1); }
  for(var k=s.dmgNums.length-1;k>=0;k--){ var n=s.dmgNums[k]; n.y-=0.9*f;n.life-=0.018*f; if(n.life<=0)s.dmgNums.splice(k,1); }
  for(var q=s.shocks.length-1;q>=0;q--){ var sk=s.shocks[q]; sk.r+=(sk.maxR-sk.r)*Math.min(1,0.22*f); sk.life-=0.05*f; if(sk.life<=0)s.shocks.splice(q,1); }
  for(var u=s.texts.length-1;u>=0;u--){ var tx=s.texts[u]; tx.scale+=(1-tx.scale)*Math.min(1,0.3*f); tx.y-=0.5*f; tx.life-=0.02*f; if(tx.life<=0)s.texts.splice(u,1); }
  // 시각 타이머 실시간 감쇠
  if(s.swingAnim>0){ s.swingAnim-=dt; if(s.swingAnim<0)s.swingAnim=0; }
  if(s.punchAnim>0){ s.punchAnim-=dt; if(s.punchAnim<0)s.punchAnim=0; }
  if(s.shake>0){ s.shake-=dt; if(s.shake<0)s.shake=0; }
  if(s.flashO>0){ s.flashO-=dt; if(s.flashO<0)s.flashO=0; }
  if(s.flashN>0){ s.flashN-=dt; if(s.flashN<0)s.flashN=0; }
  if(s.headSnap>0){ s.headSnap-=dt; if(s.headSnap<0)s.headSnap=0; }
  var decay=Math.pow(0.78,f); s.recoilOx*=decay; s.recoilOy*=decay;
  // HP 바 보간 + 칩 데미지
  var tO=Math.max(0,s.hpO/s.maxO), tN=Math.max(0,s.hpN/s.maxN);
  s.dispO+=(tO-s.dispO)*Math.min(1,0.25*f); s.dispN+=(tN-s.dispN)*Math.min(1,0.25*f);
  s.chipO+=(s.dispO-s.chipO)*Math.min(1,0.05*f); s.chipN+=(s.dispN-s.chipN)*Math.min(1,0.05*f);
  // 발먼지(시각 전용)
  footDust(s, s.pOx, s.pOy, s.ox, s.oy); footDust(s, s.pNx, s.pNy, s.nx, s.ny);
  s.pOx=s.ox; s.pOy=s.oy; s.pNx=s.nx; s.pNy=s.ny;
}

// ===========================================================================
//  렌더링
// ===========================================================================
var cv=document.getElementById("cv"), ctx=cv.getContext("2d"), W=cv.width, H=cv.height;

function rrect(x,y,w,h,r){
  ctx.beginPath(); ctx.moveTo(x+r,y);
  ctx.arcTo(x+w,y,x+w,y+h,r); ctx.arcTo(x+w,y+h,x,y+h,r);
  ctx.arcTo(x,y+h,x,y,r); ctx.arcTo(x,y,x+w,y,r); ctx.closePath();
}

// 4 코너(월드 사각형) 화면 좌표
function ringCorners(){
  return {
    BL:project(0,0), BR:project(CONST.WX1,0),
    FL:project(0,CONST.WY1), FR:project(CONST.WX1,CONST.WY1)
  };
}

function drawArena(){
  var g=ctx.createLinearGradient(0,0,0,H);
  g.addColorStop(0,"#0c1024"); g.addColorStop(.55,"#0a0f20"); g.addColorStop(1,"#070b16");
  ctx.fillStyle=g; ctx.fillRect(0,0,W,H);
  // 관중석 점
  for(var i=0;i<160;i++){
    var x=(i*53%W), y=20+(i*37%120);
    ctx.fillStyle = i%3===0 ? "rgba(120,140,200,.16)" : "rgba(90,110,170,.10)";
    ctx.fillRect(x,y,4,4);
  }
  // 스포트라이트
  var sl=ctx.createRadialGradient(W/2,40,40, W/2,200,520);
  sl.addColorStop(0,"rgba(120,150,230,.10)"); sl.addColorStop(1,"rgba(0,0,0,0)");
  ctx.fillStyle=sl; ctx.fillRect(0,0,W,H);
}

function drawMat(C){
  // 링 바닥(트라페조이드)
  ctx.beginPath();
  ctx.moveTo(C.BL.x,C.BL.y); ctx.lineTo(C.BR.x,C.BR.y);
  ctx.lineTo(C.FR.x,C.FR.y); ctx.lineTo(C.FL.x,C.FL.y); ctx.closePath();
  var mg=ctx.createLinearGradient(0,C.BL.y,0,C.FL.y);
  mg.addColorStop(0,"#23314f"); mg.addColorStop(1,"#152038");
  ctx.fillStyle=mg; ctx.fill();
  ctx.lineWidth=3; ctx.strokeStyle="rgba(150,180,240,.35)"; ctx.stroke();
  // 가운데 로고/라인
  ctx.save();
  ctx.beginPath();
  ctx.moveTo(C.BL.x,C.BL.y); ctx.lineTo(C.BR.x,C.BR.y);
  ctx.lineTo(C.FR.x,C.FR.y); ctx.lineTo(C.FL.x,C.FL.y); ctx.closePath(); ctx.clip();
  var mid=project(CONST.WX1/2, CONST.WY1/2);
  ctx.globalAlpha=0.16; ctx.fillStyle="#cdd9ff";
  ctx.font="bold 60px Segoe UI"; ctx.textAlign="center"; ctx.textBaseline="middle";
  ctx.fillText("VS", mid.x, mid.y);
  ctx.globalAlpha=1; ctx.textBaseline="alphabetic"; ctx.textAlign="left";
  ctx.restore();
}

function postTop(corner, ph){ return {x:corner.x, y:corner.y-ph}; }
function ropesBetween(a, pha, b, phb){
  var fr=[0.34,0.58,0.84];
  ctx.lineWidth=3; ctx.strokeStyle="#e2e8f0";
  for(var i=0;i<fr.length;i++){
    ctx.beginPath();
    ctx.moveTo(a.x, a.y-pha*fr[i]);
    ctx.lineTo(b.x, b.y-phb*fr[i]);
    ctx.stroke();
  }
}
function drawPost(corner, ph, color){
  ctx.fillStyle="#0b1020";
  rrect(corner.x-5, corner.y-ph, 10, ph, 4); ctx.fill();
  ctx.fillStyle=color; // 코너 패드
  rrect(corner.x-7, corner.y-ph, 14, 18, 5); ctx.fill();
  ctx.fillStyle="rgba(255,255,255,.15)";
  rrect(corner.x-7, corner.y-ph+18, 14, 8, 3); ctx.fill();
}

var BPH=72, FPH=120; // back/front 포스트 높이
function drawRopesBack(C){
  // 뒤쪽 + 좌우 로프 (선수보다 먼저)
  ropesBetween(C.BL,BPH, C.BR,BPH);   // 뒤
  ropesBetween(C.BL,BPH, C.FL,FPH);   // 좌
  ropesBetween(C.BR,BPH, C.FR,FPH);   // 우
  drawPost(C.BL,BPH,"#ef4444"); drawPost(C.BR,BPH,"#3b82f6");
}
function drawRopesFront(C){
  ropesBetween(C.FL,FPH, C.FR,FPH);   // 앞 (선수 위로)
  drawPost(C.FL,FPH,"#3b82f6"); drawPost(C.FR,FPH,"#ef4444");
}

function drawShadow(p, rad){
  ctx.fillStyle="rgba(0,0,0,.38)";
  ctx.beginPath(); ctx.ellipse(p.x, p.y, rad, rad*0.32, 0,0,Math.PI*2); ctx.fill();
}

// ---- 오타니: 그린 유니폼 몸통 + 얼굴 이미지 머리(좌우 반전 보정) + 방망이 ----
function drawOhtani(s, c){
  var p=project(s.ox, s.oy), k=p.s, face=s.faceO;
  var rx=s.recoilOx||0, ry=(s.recoilOy||0)*0.3;
  var breathe=1+Math.sin(s.t*0.12)*0.02;
  drawShadow({x:p.x, y:p.y}, 30*k);

  // ===== 몸통/다리/뒷팔 (face로 좌우 반전) =====
  ctx.save();
  ctx.translate(p.x+rx, p.y+ry);
  ctx.scale(face*k, k);
  ctx.strokeStyle="#cbd5e1"; ctx.lineWidth=11; ctx.lineCap="round";
  ctx.beginPath(); ctx.moveTo(-9,-56); ctx.lineTo(-11,0); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(9,-56); ctx.lineTo(11,0); ctx.stroke();
  ctx.save(); ctx.translate(0,-56); ctx.scale(1,breathe); ctx.translate(0,56);
  var bg=ctx.createLinearGradient(0,-120,0,-56);
  bg.addColorStop(0,"#f8fafc"); bg.addColorStop(1,"#dbe4f0");
  ctx.fillStyle=bg; rrect(-22,-120,44,66,11); ctx.fill();
  ctx.strokeStyle="#1d4ed8"; ctx.lineWidth=2.5; rrect(-22,-120,44,66,11); ctx.stroke();
  ctx.fillStyle="#1d4ed8"; ctx.fillRect(-2,-118,4,60);
  ctx.font="bold 16px Segoe UI"; ctx.fillStyle="#1e3a8a"; ctx.textAlign="center";
  ctx.fillText("17", 0, -84); ctx.textAlign="left";
  if(s.flashO>0){ ctx.globalAlpha=clamp01(s.flashO/0.16)*0.7; ctx.fillStyle="#ffffff"; rrect(-22,-120,44,66,11); ctx.fill(); ctx.globalAlpha=1; }
  ctx.restore();
  ctx.strokeStyle="#e8eef7"; ctx.lineWidth=8; ctx.lineCap="round";
  ctx.beginPath(); ctx.moveTo(-14,-112); ctx.lineTo(-24,-92); ctx.stroke();
  ctx.restore();

  // ===== 머리(얼굴 이미지, 좌우 반전 보정 + 헤드스냅) =====
  ctx.save();
  var snap=(s.headSnap>0? clamp01(s.headSnap/0.22):0);
  ctx.translate(p.x+rx + face*snap*9, p.y+ry);
  ctx.rotate(face*snap*0.28);
  var hr=27*k, headY=-(132*k);
  if(headO){
    ctx.save();
    ctx.beginPath(); ctx.arc(0, headY, hr, 0, Math.PI*2); ctx.closePath(); ctx.clip();
    if(face<0){ ctx.translate(0,headY); ctx.scale(-1,1); ctx.translate(0,-headY); } // 항상 상대를 바라봄
    ctx.drawImage(headO, -hr, headY-hr, hr*2, hr*2);
    if(s.flashO>0){ ctx.globalAlpha=clamp01(s.flashO/0.16)*0.6; ctx.fillStyle="#ffffff"; ctx.fillRect(-hr,headY-hr,hr*2,hr*2); ctx.globalAlpha=1; }
    ctx.restore();
    ctx.lineWidth=2.5*k; ctx.strokeStyle="#0b1020";
    ctx.beginPath(); ctx.arc(0, headY, hr, 0, Math.PI*2); ctx.stroke();
    // 다저스 모자(돔 + 상대 방향 챙 + 로고)
    ctx.fillStyle="#1e3a8a";
    ctx.beginPath(); ctx.arc(0, headY-hr*0.42, hr*0.98, Math.PI, 0); ctx.fill();
    ctx.beginPath(); ctx.ellipse(face*hr*0.78, headY-hr*0.52, hr*0.72, hr*0.24, 0, 0, Math.PI*2); ctx.fill();
    ctx.fillStyle="#ffffff"; ctx.beginPath(); ctx.arc(0, headY-hr*0.62, hr*0.12, 0, Math.PI*2); ctx.fill();
  } else {
    ctx.fillStyle="#f1c9a5"; ctx.beginPath(); ctx.arc(0, headY, hr, 0, Math.PI*2); ctx.fill();
  }
  ctx.restore();

  // ===== 방망이(스윙 + 다중 잔상) =====
  ctx.save();
  ctx.translate(p.x+rx, p.y+ry);
  var handX=face*10*k, handY=-96*k;
  var prog=(CONST.SWING_DUR - s.swingAnim)/CONST.SWING_DUR;
  var rest = face>0 ? -2.35 : (Math.PI+2.35);
  var hit  = face>0 ? 0.5   : (Math.PI-0.5);
  var batLen=c.oReach*0.9*k;
  if(s.swingAnim>0){
    for(var ti=3;ti>=1;ti--){
      var ee=clamp01(prog - ti*0.07), aa=rest+(hit-rest)*(ee*ee);
      var bxx=handX+Math.cos(aa)*batLen, byy=handY+Math.sin(aa)*batLen;
      ctx.strokeStyle="rgba(253,224,71,"+(0.05*(4-ti))+")"; ctx.lineWidth=16*k; ctx.lineCap="round";
      ctx.beginPath(); ctx.moveTo(handX,handY); ctx.lineTo(bxx,byy); ctx.stroke();
    }
  }
  var ang = rest;
  if(s.swingAnim>0){ var e=clamp01(prog); ang = rest+(hit-rest)*(e*e); }
  var bx=handX+Math.cos(ang)*batLen, by=handY+Math.sin(ang)*batLen;
  var grd=ctx.createLinearGradient(handX,handY,bx,by);
  grd.addColorStop(0,"#7c4a18"); grd.addColorStop(1,"#d29a4a");
  ctx.strokeStyle=grd; ctx.lineCap="round"; ctx.lineWidth=6*k;
  ctx.beginPath(); ctx.moveTo(handX,handY); ctx.lineTo(bx,by); ctx.stroke();
  ctx.lineWidth=10*k;
  ctx.beginPath(); ctx.moveTo(handX+(bx-handX)*0.55,handY+(by-handY)*0.55); ctx.lineTo(bx,by); ctx.stroke();
  ctx.strokeStyle="#e8eef7"; ctx.lineWidth=7*k;
  ctx.beginPath(); ctx.moveTo(face*8*k,-108*k); ctx.lineTo(handX,handY); ctx.stroke();
  ctx.restore();
}

// ---- 은가누: 전신 이미지 + (장전->폭발 전진->회복) 펀치 런지 + 모션블러 + 피격 플래시 ----
function drawNgannou(s, c){
  var p=project(s.nx, s.ny), k=p.s, face=s.faceN;
  var bob=Math.sin(s.t*0.16+1)*2*k;
  drawShadow({x:p.x, y:p.y}, 36*k);
  // 런지: 살짝 뒤로 장전 -> 폭발적으로 전진 -> 회복
  var lunge=0, lean=0;
  if(s.punchAnim>0){
    var prog=clamp01((CONST.PUNCH_DUR - s.punchAnim)/CONST.PUNCH_DUR);
    if(prog<0.22){ lunge=-(prog/0.22)*10; }
    else if(prog<0.5){ lunge=((prog-0.22)/0.28)*44; }
    else { lunge=44*(1-(prog-0.5)/0.5); }
    lean=(lunge/44)*0.14;
  }
  var op=project(s.ox,s.oy);
  var ddx=op.x-p.x, ddy=op.y-p.y, dl=Math.hypot(ddx,ddy)||1;
  var lx=(ddx/dl)*lunge*k, ly=(ddy/dl)*lunge*0.45*k;
  var H0=216*k, w0=H0*(sprN? (sprN.w/sprN.h) : 0.66);
  function blit(img, ox2, oy2, alpha){
    ctx.save(); ctx.globalAlpha=alpha;
    ctx.translate(p.x+ox2, p.y+oy2+bob); ctx.scale(face,1); ctx.rotate(-face*lean);
    if(img){ ctx.drawImage(img, -w0/2, -H0, w0, H0); }
    else { ctx.fillStyle="#b91c1c"; rrect(-26*k,-150*k,52*k,150*k,14*k); ctx.fill();
           ctx.fillStyle="#6b3f2a"; ctx.beginPath(); ctx.arc(0,-168*k,16*k,0,Math.PI*2); ctx.fill(); }
    ctx.restore();
  }
  var img = sprN? sprN.canvas : null;
  if(s.punchAnim>0 && lunge>6){ blit(img, lx*0.5, ly*0.5, 0.16); blit(img, lx*0.78, ly*0.78, 0.28); }
  blit(img, lx, ly, 1);
  if(s.flashN>0 && whiteN){ blit(whiteN, lx, ly, clamp01(s.flashN/0.13)*0.9); }
}

function drawHpBars(s){
  drawBar(24, 24, 360, s.dispO, s.chipO, "#38bdf8", "오타니", Math.max(0,Math.round(s.hpO)), false);
  drawBar(W-24-360, 24, 360, s.dispN, s.chipN, "#f87171", "은가누", Math.max(0,Math.round(s.hpN)), true);
  // 타이머
  ctx.fillStyle="rgba(0,0,0,.5)"; rrect(W/2-54,18,108,32,9); ctx.fill();
  ctx.strokeStyle="rgba(251,191,36,.5)"; ctx.lineWidth=1.5; rrect(W/2-54,18,108,32,9); ctx.stroke();
  ctx.fillStyle="#fbbf24"; ctx.font="bold 19px Segoe UI"; ctx.textAlign="center";
  ctx.fillText((s.t/60).toFixed(1)+"s", W/2, 41); ctx.textAlign="left";
}
function drawBar(x,y,w,ratio,chip,color,name,hp,right){
  var h=22;
  ctx.fillStyle="rgba(0,0,0,.55)"; rrect(x-2,y-2,w+4,h+4,7); ctx.fill();
  ctx.fillStyle="#0a1226"; rrect(x,y,w,h,6); ctx.fill();
  ctx.save(); rrect(x,y,w,h,6); ctx.clip();
  // 칩(지연) 바 - 최근 받은 피해 표시
  ctx.fillStyle="rgba(255,210,120,.55)";
  if(right) ctx.fillRect(x+w*(1-chip), y, w*chip, h); else ctx.fillRect(x, y, w*chip, h);
  // 메인 바 (+ 위험시 빨강)
  ctx.fillStyle = ratio<0.28 ? "#ef4444" : color;
  if(right) ctx.fillRect(x+w*(1-ratio), y, w*ratio, h); else ctx.fillRect(x, y, w*ratio, h);
  // 광택
  ctx.fillStyle="rgba(255,255,255,.16)";
  if(right) ctx.fillRect(x+w*(1-ratio), y, w*ratio, h*0.42); else ctx.fillRect(x, y, w*ratio, h*0.42);
  ctx.restore();
  ctx.fillStyle="#fff"; ctx.font="bold 14px Segoe UI"; ctx.textAlign = right?"right":"left";
  ctx.fillText(name+"   "+hp, right? x+w : x, y-7); ctx.textAlign="left";
}

function drawWinner(s){
  ctx.fillStyle="rgba(5,9,20,.62)"; ctx.fillRect(0,0,W,H);
  var name,color,emo;
  if(s.winner==="ohtani"){ name="오타니 승리!"; color="#38bdf8"; emo="⚾"; }
  else if(s.winner==="ngannou"){ name="은가누 승리!"; color="#f87171"; emo="🥊"; }
  else { name="무승부"; color="#cbd5e1"; emo="🤝"; }
  ctx.textAlign="center";
  ctx.font="50px Segoe UI"; ctx.fillText(emo, W/2, H/2-46);
  ctx.fillStyle=color; ctx.font="bold 46px Segoe UI"; ctx.fillText(name, W/2, H/2+10);
  ctx.fillStyle="#9aa7c7"; ctx.font="15px Segoe UI";
  ctx.fillText("오타니 HP "+Math.max(0,Math.round(s.hpO))+"  /  은가누 HP "+Math.max(0,Math.round(s.hpN))
               +"   ·   "+(s.t/60).toFixed(1)+"s", W/2, H/2+44);
  var remain=Math.max(0, CONST.AUTO_RESTART-(s.overT||0));
  ctx.fillStyle="#fbbf24";
  ctx.fillText("잠시 후 자동으로 다음 경기 시작...  ("+remain.toFixed(1)+"s)", W/2, H/2+72);
  ctx.textAlign="left";
}

function drawIntro(s){
  var a=clamp01(s.intro/1.3);
  ctx.globalAlpha=Math.min(1,a*1.6);
  ctx.textAlign="center";
  var sc=1.0+(1-a)*0.45;
  ctx.save(); ctx.translate(W/2,H/2-16); ctx.scale(sc,sc);
  ctx.font="bold 66px Segoe UI"; ctx.lineWidth=8; ctx.strokeStyle="#0b1020";
  ctx.strokeText("FIGHT!",0,0); ctx.fillStyle="#fbbf24"; ctx.fillText("FIGHT!",0,0);
  ctx.restore(); ctx.globalAlpha=1; ctx.textAlign="left";
}
function drawKO(s){
  ctx.fillStyle="rgba(120,10,10,.32)"; ctx.fillRect(0,0,W,H);
  var prog=1-clamp01(s.koTimer/1.0), sc=0.5+prog*1.1;
  ctx.save(); ctx.translate(W/2,H/2); ctx.scale(sc,sc); ctx.rotate(-0.06);
  ctx.font="bold 112px Segoe UI"; ctx.textAlign="center"; ctx.lineWidth=12; ctx.strokeStyle="#0b1020";
  ctx.strokeText("K.O.!",0,0); ctx.fillStyle="#f87171"; ctx.fillText("K.O.!",0,0);
  ctx.restore(); ctx.textAlign="left";
}

// ---- 리얼 모드 전용 연출 ----
function chargeAura(p, color, prog){
  ctx.save(); ctx.globalAlpha=0.2+0.4*prog; ctx.strokeStyle=color; ctx.lineWidth=2.5+3*prog;
  ctx.beginPath(); ctx.ellipse(p.x, p.y, (22+22*prog)*p.s, (8+8*prog)*p.s, 0,0,Math.PI*2); ctx.stroke();
  ctx.globalAlpha=1; ctx.restore();
}
function stunStars(p, t){
  ctx.save(); ctx.fillStyle="#fde047"; ctx.font="bold "+Math.round(15*p.s)+"px Segoe UI"; ctx.textAlign="center";
  for(var i=0;i<3;i++){ var a=t*0.2+i*2.094; ctx.fillText("★", p.x+Math.cos(a)*22*p.s, p.y-150*p.s+Math.sin(a)*6*p.s); }
  ctx.textAlign="left"; ctx.restore();
}
function drawRealOverlays(s){
  if(s.foS===1) chargeAura(project(s.ox,s.oy), "#fde047", clamp01(s.foWu/REAL.O_WINDUP));
  if(s.fnS===1 && !s.fnFeint) chargeAura(project(s.nx,s.ny), "#f87171", clamp01(s.fnWu/REAL.N_WINDUP));
  if(s.foS===4) stunStars(project(s.ox,s.oy), s.t);
  if(s.fnS===4) stunStars(project(s.nx,s.ny), s.t);
}
function drawStam(x,y,w,r,color,right){
  ctx.fillStyle="rgba(0,0,0,.45)"; rrect(x,y,w,8,3); ctx.fill();
  ctx.save(); rrect(x,y,w,8,3); ctx.clip(); ctx.fillStyle=color;
  if(right) ctx.fillRect(x+w*(1-r),y,w*r,8); else ctx.fillRect(x,y,w*r,8);
  ctx.restore();
  ctx.fillStyle="#9aa7c7"; ctx.font="9px Segoe UI"; ctx.textAlign=right?"right":"left";
  ctx.fillText("STAMINA "+Math.round(r*100), right?x+w:x, y-2); ctx.textAlign="left";
}
function drawStaminaBars(s){
  drawStam(24, 52, 200, Math.max(0,s.foStam/100), "#38bdf8", false);
  drawStam(W-24-200, 52, 200, Math.max(0,s.fnStam/100), "#f87171", true);
}
// 전적(누적 승패) 캔버스 표시 - PIP에서도 보임
function drawRecord(s){
  var r=record[mode]; if(!r) return;
  var cx=W/2, y=54, w=300;
  ctx.fillStyle="rgba(0,0,0,.45)"; rrect(cx-w/2, y, w, 26, 8); ctx.fill();
  ctx.font="bold 15px Segoe UI"; ctx.textBaseline="middle"; ctx.textAlign="left";
  var x=cx-w/2+14;
  ctx.fillStyle="#9aa7c7"; ctx.fillText("전적 ", x, y+13); x+=ctx.measureText("전적 ").width;
  var sO="오타니 "+r.ohtani; ctx.fillStyle="#38bdf8"; ctx.fillText(sO, x, y+13); x+=ctx.measureText(sO).width;
  ctx.fillStyle="#e8edf7"; ctx.fillText(" : ", x, y+13); x+=ctx.measureText(" : ").width;
  ctx.fillStyle="#f87171"; ctx.fillText(r.ngannou+" 은가누", x, y+13);
  ctx.textBaseline="alphabetic"; ctx.textAlign="left";
  if(r.streak>=2 && r.streakWho){
    ctx.font="bold 12px Segoe UI"; ctx.textAlign="center";
    ctx.fillStyle=(r.streakWho==="ohtani")?"#38bdf8":"#f87171";
    ctx.fillText((r.streakWho==="ohtani"?"오타니":"은가누")+" "+r.streak+"연승 🔥", cx, y+42);
    ctx.textAlign="left";
  }
}

function render(s, c){
  ctx.setTransform(1,0,0,1,0,0);
  ctx.clearRect(0,0,W,H);
  var sh=(s.shake>0)?s.shake/0.2:0; if(sh>1)sh=1;
  if(sh>0) ctx.translate((Math.random()*2-1)*11*sh,(Math.random()*2-1)*7*sh);
  var C=ringCorners();
  drawArena();
  drawMat(C);
  drawRopesBack(C);
  // 바닥 먼지
  for(var i=0;i<s.dust.length;i++){ var d=s.dust[i]; ctx.globalAlpha=Math.max(0,d.life)*0.5;
    ctx.fillStyle="#b8c4e0"; ctx.beginPath(); ctx.arc(d.x,d.y,d.r,0,Math.PI*2); ctx.fill(); }
  ctx.globalAlpha=1;
  // 선수(깊이 정렬: 뒤=작은 y 먼저)
  if(s.oy<=s.ny){ drawOhtani(s,c); drawNgannou(s,c); }
  else { drawNgannou(s,c); drawOhtani(s,c); }
  if(mode==="real") drawRealOverlays(s);
  // 충격파 링
  for(var q=0;q<s.shocks.length;q++){ var w2=s.shocks[q]; ctx.globalAlpha=Math.max(0,w2.life)*0.8;
    ctx.strokeStyle=w2.color; ctx.lineWidth=5*Math.max(0.2,w2.life);
    ctx.beginPath(); ctx.arc(w2.x,w2.y,w2.r,0,Math.PI*2); ctx.stroke(); }
  ctx.globalAlpha=1;
  // 파티클
  for(var j=0;j<s.particles.length;j++){ var p=s.particles[j]; ctx.globalAlpha=Math.max(0,p.life);
    ctx.fillStyle=p.color; ctx.beginPath(); ctx.arc(p.x,p.y,p.r,0,Math.PI*2); ctx.fill(); }
  ctx.globalAlpha=1;
  // 데미지 숫자(외곽선)
  for(var m=0;m<s.dmgNums.length;m++){ var n=s.dmgNums[m]; ctx.globalAlpha=Math.max(0,n.life);
    ctx.font="bold "+(n.who==="o"?22:26)+"px Segoe UI"; ctx.textAlign="center";
    ctx.lineWidth=3.5; ctx.strokeStyle="rgba(0,0,0,.6)"; ctx.strokeText("-"+n.val,n.x,n.y);
    ctx.fillStyle=n.who==="o"?"#fde047":"#f87171"; ctx.fillText("-"+n.val, n.x, n.y); }
  ctx.globalAlpha=1; ctx.textAlign="left";
  // 임팩트 텍스트(깡!/퍽!/💥)
  for(var u=0;u<s.texts.length;u++){ var tt=s.texts[u]; ctx.globalAlpha=Math.max(0,tt.life);
    ctx.save(); ctx.translate(tt.x,tt.y); ctx.scale(tt.scale,tt.scale); ctx.rotate(-0.12);
    ctx.font="bold 40px Segoe UI"; ctx.textAlign="center"; ctx.lineWidth=6; ctx.strokeStyle="#0b1020";
    ctx.strokeText(tt.txt,0,0); ctx.fillStyle=tt.color; ctx.fillText(tt.txt,0,0); ctx.restore(); }
  ctx.globalAlpha=1; ctx.textAlign="left";
  drawRopesFront(C);
  ctx.setTransform(1,0,0,1,0,0);
  // 비네트
  var vg=ctx.createRadialGradient(W/2,H/2,H*0.42, W/2,H/2,H*0.98);
  vg.addColorStop(0,"rgba(0,0,0,0)"); vg.addColorStop(1,"rgba(0,0,0,.42)");
  ctx.fillStyle=vg; ctx.fillRect(0,0,W,H);
  drawHpBars(s);
  if(mode==="real") drawStaminaBars(s);
  drawRecord(s);
  if(s.intro>0) drawIntro(s);
  if(s.over){ if(s.winnerKO && s.koTimer>0) drawKO(s); else drawWinner(s); }
}

// ===========================================================================
//  루프 (고정 timestep)
// ===========================================================================
var state=null, cfg=null, running=false, acc=0, last=0;
function loop(now){
  if(!last) last=now;
  var dtms=now-last; last=now; if(dtms>200) dtms=200;
  var dt=dtms/1000;
  if(state){
    if(running && !state.over){
      if(state.intro>0){ state.intro-=dt; }            // FIGHT! 인트로 동안 대기
      else if(state.hitStop>0){ state.hitStop-=dt; acc=0; }  // 타격 순간 프리즈
      else {
        acc+=dt; var steps=0;
        var stepFn = (mode==="real") ? stepReal : stepSim;
        while(acc>=CONST.DT && steps<8){
          stepFn(state,cfg); acc-=CONST.DT; steps++;
          if(state.hitStop>0){ acc=0; break; }          // 이번 틱에 타격 발생 -> 프리즈
          if(state.over) break;
        }
      }
    }
    if(state.over && !state.recorded){ state.recorded=true; recordResult(state.winner); }
    if(state.over && running){
      if(state.koTimer>0){ state.koTimer-=dt; }
      else { state.overT+=dt; if(state.overT>=CONST.AUTO_RESTART){ startFight(); } }
    }
    updateEffects(state, dt);
    render(state,cfg);
  }
  requestAnimationFrame(loop);
}
function startFight(){
  cfg=readCfg(); state=newState(cfg); running=true; acc=0; last=0; setPauseLabel();
  clearLog();
  if(mode==="real") pushLog(state, "⚔️ 경기 시작 — 실제 스탯 기반 리얼 모드");
}
function setPauseLabel(){
  document.getElementById("btnPause").textContent = running?"⏸ 일시정지":"▶ 재개";
  var pp=document.getElementById("pipPause"); if(pp) pp.textContent = running?"⏸":"▶";
}

// ===========================================================================
//  통계
// ===========================================================================
function runStats(){
  var btn=document.getElementById("btnSim"), spin=document.getElementById("spin");
  var runs=parseInt(document.getElementById("runs").value,10)||10000;
  if(runs<1)runs=1; if(runs>200000)runs=200000;
  btn.disabled=true; spin.classList.add("show");
  document.getElementById("result").classList.remove("show");
  fetch("/simulate",{method:"POST",headers:{"Content-Type":"application/json"},
    body:JSON.stringify({runs:runs, mode:mode, params:readCfg()})})
  .then(function(r){return r.json();})
  .then(function(d){ showStats(d); })
  .catch(function(e){ alert("시뮬레이션 오류: "+e); })
  .finally(function(){ btn.disabled=false; spin.classList.remove("show"); });
}
function showStats(d){
  document.getElementById("r_o").textContent=d.ohtani.toLocaleString()+"  ("+d.ohtaniRate+"%)";
  document.getElementById("r_n").textContent=d.ngannou.toLocaleString()+"  ("+d.ngannouRate+"%)";
  document.getElementById("r_d").textContent=d.draw.toLocaleString()+"  ("+d.drawRate+"%)";
  var so=document.getElementById("seg_o"),sn=document.getElementById("seg_n"),sd=document.getElementById("seg_d");
  so.style.width=d.ohtaniRate+"%"; sn.style.width=d.ngannouRate+"%"; sd.style.width=d.drawRate+"%";
  so.textContent=d.ohtaniRate>=8?"오타니 "+d.ohtaniRate+"%":"";
  sn.textContent=d.ngannouRate>=8?"은가누 "+d.ngannouRate+"%":"";
  sd.textContent=d.drawRate>=8?"무 "+d.drawRate+"%":"";
  var mEl=document.getElementById("methods");
  if(d.methods){
    document.getElementById("m_punch").textContent=d.methods.punch_ko.toLocaleString();
    document.getElementById("m_bat").textContent=d.methods.bat_ko.toLocaleString();
    document.getElementById("m_dec").textContent=d.methods.decision.toLocaleString();
    mEl.classList.add("show");
  } else { mEl.classList.remove("show"); }
  var mlabel=(d.mode==="real")?"리얼":"아케이드";
  var meta="["+mlabel+"] "+d.runs.toLocaleString()+"회 · 평균 경기시간 "+d.avgSeconds+"s · 서버 계산 "+d.elapsedMs+"ms";
  if(d.koShareN!==undefined) meta+=" · 은가누 승리 중 KO "+d.koShareN+"% (실제 72%)";
  document.getElementById("r_meta").textContent=meta;
  document.getElementById("result").classList.add("show");
}

// ===========================================================================
//  초기화
// ===========================================================================
function setMode(m){
  mode=m;
  var locked=(m==="real");
  document.getElementById("mArcade").classList.toggle("active", m==="arcade");
  document.getElementById("mReal").classList.toggle("active", m==="real");
  document.getElementById("logwrap").classList.toggle("show", locked);
  // 리얼 모드: 실제 스탯 프리셋(HP 동일) 적용 + 슬라이더 잠금 / 아케이드: 자유 조절
  if(locked) applyPreset(REAL_PRESET); else resetParams();
  SLIDERS.forEach(function(id){ document.getElementById(id).disabled = locked; });
  document.getElementById("btnReset").disabled = locked;
  var oc=document.querySelector(".o-card"), nc=document.querySelector(".n-card");
  if(oc) oc.classList.toggle("locked", locked);
  if(nc) nc.classList.toggle("locked", locked);
  document.getElementById("modeNote").textContent = locked
    ? "실제 스탯 기반 · HP 동일(100:100) · 명중률·반응속도 실측 · KO는 실제 KO율(은가누 72%) 확률로 발생 · 🔒 고정"
    : "밸런스 ~50:50, HP 주고받는 아케이드 대결 · 슬라이더 자유 조절";
  var pm=document.getElementById("pipMode"); if(pm) pm.textContent = locked?"🥊 리얼":"⚾ 아케이드";
  startFight();
}
function setPip(on){ document.body.classList.toggle("pip", on); }

bindSliders(); resetParams(); requestAnimationFrame(loop);
document.getElementById("btnStart").addEventListener("click", startFight);
document.getElementById("btnPause").addEventListener("click", function(){
  if(!state) return; if(state.over){ startFight(); return; } running=!running; setPauseLabel();
});
document.getElementById("btnReset").addEventListener("click", function(){ resetParams(); startFight(); });
document.getElementById("btnSim").addEventListener("click", runStats);
document.getElementById("mArcade").addEventListener("click", function(){ setMode("arcade"); });
document.getElementById("mReal").addEventListener("click", function(){ setMode("real"); });
document.getElementById("btnPip").addEventListener("click", function(){ setPip(true); });
document.getElementById("pipExit").addEventListener("click", function(){ setPip(false); });
document.getElementById("pipPause").addEventListener("click", function(){
  if(!state) return; if(state.over){ startFight(); return; } running=!running; setPauseLabel();
});
document.getElementById("pipMode").addEventListener("click", function(){ setMode(mode==="real"?"arcade":"real"); });
// 캔버스 더블클릭으로 PIP 토글
document.getElementById("cv").addEventListener("dblclick", function(){ setPip(!document.body.classList.contains("pip")); });
document.getElementById("btnRecReset").addEventListener("click", function(){
  if(confirm("전적을 모두 초기화할까요?")){ record={arcade:blankRec(), real:blankRec()}; saveRecord(); updateRecordDOM(); }
});
updateRecordDOM();
setMode("arcade");
</script>
</body>
</html>'''


def _lan_ip():
    """같은 네트워크에서 접속할 때 쓸 내 PC의 LAN IP를 알아낸다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip


if __name__ == "__main__":
    ip = _lan_ip()
    print("=" * 64)
    print("  오타니(방망이) vs 은가누(맨주먹) 2D 링 대결 시뮬레이터")
    print("  내 PC에서:        http://127.0.0.1:5000")
    print("  같은 Wi-Fi/공유기: http://%s:5000   <- 이 주소를 공유하세요" % ip)
    print("  (순수 HTTP / 종료: Ctrl+C / 같은 네트워크 기기만 접속 가능)")
    print("=" * 64)
    # 0.0.0.0 = 모든 네트워크 인터페이스에 바인딩 -> 같은 네트워크의 다른 기기에서 접속 가능
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
