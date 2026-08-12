"""Friendly Korean game errors.

Every message here is shown directly to a player, so keep the tone warm and
never blame them.
"""


class GameError(Exception):
    """A rule violation the player should be told about, in Korean."""

    def __init__(self, message: str, code: str = "error"):
        super().__init__(message)
        self.message = message
        self.code = code


# --- reusable messages ------------------------------------------------------
ROOM_NOT_FOUND = "방을 찾을 수 없습니다."
ROOM_FULL = "방이 가득 찼습니다."
NICKNAME_TAKEN = "이미 사용 중인 닉네임입니다."
NICKNAME_EMPTY = "닉네임을 입력해주세요."
NICKNAME_LONG = "닉네임은 12자까지 가능합니다."
CHARACTER_TAKEN = "이 캐릭터는 다른 플레이어가 사용 중입니다."
CHARACTER_INVALID = "캐릭터를 선택해주세요."
NOT_HOST = "방장만 할 수 있습니다."
NOT_ENOUGH_PLAYERS = "2명 이상이어야 게임을 시작할 수 있습니다."
GAME_ALREADY_STARTED = "이미 게임이 진행 중입니다."
CANNOT_BET_NOW = "지금은 베팅할 수 없습니다."
NOT_YOUR_TURN = "아직 내 차례가 아닙니다."
ALREADY_FOLDED = "이미 다이한 상태입니다."
NOT_IN_ROUND = "이번 판에 참여하고 있지 않습니다."
NOT_ENOUGH_CHIPS = "칩이 부족합니다."
MAX_RAISE_REACHED = "레이즈는 한 라운드에 3번까지 가능합니다."
CANNOT_CHECK = "지금은 체크할 수 없습니다. 콜 또는 다이를 선택해주세요."
CANNOT_DISCARD_NOW = "지금은 카드를 버릴 수 없습니다."
CARD_NOT_YOURS = "내 카드가 아닙니다."
LOAN_MAX = "대출은 2번까지만 가능합니다."
LOAN_NOT_NOW = "지금은 대출을 받을 수 없습니다."
REACTION_TOO_FAST = "잠시 후에 다시 눌러주세요."
DISCONNECTED = "잠시 연결이 끊겼습니다."
UNKNOWN_ACTION = "알 수 없는 동작입니다."
NOT_ENOUGH_FUNDED = "참가비를 낼 수 있는 사람이 2명 이상이어야 합니다."
