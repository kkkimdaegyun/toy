"""Central tunable configuration for 숫자 섯다.

Every number a game designer might want to tweak lives here.
Nothing in this module imports from the rest of the package.
"""

# --- table size -------------------------------------------------------------
MIN_PLAYERS = 2
MAX_PLAYERS = 6

# --- chips ------------------------------------------------------------------
STARTING_CHIPS = 300_000
BASE_UNIT = 10_000          # "1단위"

ANTE = BASE_UNIT            # 참가비
BET_AMOUNT = BASE_UNIT      # opening 베팅
RAISE_INCREMENT = BASE_UNIT  # 레이즈 step
MAX_RAISES = 3              # 레이즈 per betting phase

# --- loans (virtual, playful) ----------------------------------------------
LOAN_AMOUNT = 100_000
LOAN_INTEREST_RATE = 0.10           # 선이자 10%
LOAN_INTEREST = int(LOAN_AMOUNT * LOAN_INTEREST_RATE)   # 10,000
LOAN_NET = LOAN_AMOUNT - LOAN_INTEREST                  # 90,000
MAX_LOANS = 2
PENALTY_LOAN_INDEX = 2      # taking the Nth loan sets automatic_last_place

# --- identity ---------------------------------------------------------------
NICKNAME_MAX_LEN = 12
NICKNAME_MIN_LEN = 1
ROOM_CODE_LEN = 4
# Unambiguous alphabet: no O/0, I/1, etc.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

# --- deck -------------------------------------------------------------------
CARD_NUMBERS = list(range(10))   # 0..9  (0 == 장 / 10)
COPIES_PER_NUMBER = 2
DECK_SIZE = len(CARD_NUMBERS) * COPIES_PER_NUMBER   # 20

CARDS_FIRST_DEAL = 2
CARDS_SECOND_DEAL = 1
FINAL_HAND_SIZE = 2

# --- housekeeping -----------------------------------------------------------
LOG_MAX_ENTRIES = 60
REACTION_COOLDOWN_SEC = 2.0
ROOM_IDLE_TTL_SEC = 60 * 60 * 6     # empty rooms are reaped after 6h

# --- phases -----------------------------------------------------------------
PHASE_LOBBY = "LOBBY"
PHASE_ANTE = "ANTE"
PHASE_DEAL2 = "DEAL2"
PHASE_BET1 = "BET1"
PHASE_DEAL3 = "DEAL3"
PHASE_DISCARD = "DISCARD"
PHASE_BET2 = "BET2"
PHASE_SHOWDOWN = "SHOWDOWN"
PHASE_ROUND_END = "ROUND_END"
PHASE_FINISHED = "FINISHED"

PHASE_LABELS = {
    PHASE_LOBBY: "대기실",
    PHASE_ANTE: "참가비",
    PHASE_DEAL2: "카드 2장 배분",
    PHASE_BET1: "1차 베팅",
    PHASE_DEAL3: "세 번째 카드",
    PHASE_DISCARD: "카드 버리기",
    PHASE_BET2: "2차 베팅",
    PHASE_SHOWDOWN: "카드 공개",
    PHASE_ROUND_END: "판 결과",
    PHASE_FINISHED: "게임 종료",
}

# Ordered flow shown in the on-screen progress strip.
PHASE_FLOW = [
    PHASE_ANTE,
    PHASE_DEAL2,
    PHASE_BET1,
    PHASE_DEAL3,
    PHASE_DISCARD,
    PHASE_BET2,
    PHASE_SHOWDOWN,
    PHASE_ROUND_END,
]

# Phases in which a player may choose 다이 (including out of turn).
DAI_ALLOWED_PHASES = frozenset({
    PHASE_DEAL2,
    PHASE_BET1,
    PHASE_DEAL3,
    PHASE_DISCARD,
    PHASE_BET2,
})

BETTING_PHASES = frozenset({PHASE_BET1, PHASE_BET2})

# --- characters -------------------------------------------------------------
# Themes only; the artwork itself is original and lives in static/js/characters.js
CHARACTERS = [
    {"id": "bear", "name": "곰돌"},
    {"id": "cat", "name": "냥이"},
    {"id": "dog", "name": "멍이"},
    {"id": "rabbit", "name": "토깽"},
    {"id": "fox", "name": "여우"},
    {"id": "panda", "name": "판다"},
    {"id": "penguin", "name": "펭구"},
    {"id": "chick", "name": "삐약"},
    {"id": "frog", "name": "개굴"},
    {"id": "robot", "name": "로봇"},
    {"id": "alien", "name": "외계"},
    {"id": "ghost", "name": "유령"},
]
CHARACTER_IDS = frozenset(c["id"] for c in CHARACTERS)

# --- quick reactions --------------------------------------------------------
REACTIONS = [
    {"key": "kk", "text": "ㅋㅋ"},
    {"key": "heok", "text": "헉"},
    {"key": "good", "text": "굿"},
    {"key": "go", "text": "가자!"},
    {"key": "pity", "text": "아쉽다"},
    {"key": "cool", "text": "😎"},
]
REACTION_KEYS = frozenset(r["key"] for r in REACTIONS)
REACTION_TEXT = {r["key"]: r["text"] for r in REACTIONS}

# --- server -----------------------------------------------------------------
DEFAULT_PORT = 3949
DEFAULT_HOST = "0.0.0.0"
