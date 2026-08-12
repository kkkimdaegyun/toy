// app.js
const gameState = {
    roomCode: null, playerId: null, nickname: null, color: null,
    isHost: false, seat: -1, gameMode: 'dice',
    players: {}, casinoBills: {}, casinoDice: {},
    playerDice: {}, winnings: {}, currentTurn: null,
    currentRoll: [], validCasinos: [], selectedCasino: null, placementSequence: 0,
    phase: 'landing', serverPhase: null,
    availableColors: ['red', 'orange', 'yellow', 'green']
};

const COLOR_NAMES = {red: '빨강', orange: '주황', yellow: '노랑', green: '초록'};
const COLOR_EMOJI = {red: 'R', orange: 'O', yellow: 'Y', green: 'G'};
const COLOR_HEX = {red: '#c58686', orange: '#c6a06f', yellow: '#c4b56f', green: '#7fa88e'};

function showScreen(name) {
    // Hide all base screens
    document.querySelectorAll('.screen:not(.overlay)').forEach(s => s.classList.remove('active'));
    
    // Hide overlays if switching base screens (except specifically called overlays)
    if (name === 'landing-screen' || name === 'lobby-screen' || name === 'game-screen') {
        document.querySelectorAll('.overlay').forEach(s => s.classList.remove('active'));
    }
    
    const target = document.getElementById(name);
    if (target) {
        target.classList.add('active');
        gameState.phase = name.replace('-screen', '');
    }
}

function formatMoney(v) {
    if (v >= 10000) return '$' + (v / 10000) + '만';
    return '$' + v.toLocaleString();
}

function openGuide() {
    document.getElementById('guide-modal').style.display = 'flex';
}

function closeGuide() {
    document.getElementById('guide-modal').style.display = 'none';
}

function getUrlParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

function loadSavedSession() {
    // sessionStorage survives a refresh but is isolated per tab. Using
    // localStorage here caused a new tab to steal the active host session.
    const token = sessionStorage.getItem('lv_token');
    const roomCode = sessionStorage.getItem('lv_room');
    if (token && roomCode) {
        return { token, roomCode };
    }
    return null;
}

function saveSession(token, roomCode) {
    sessionStorage.setItem('lv_token', token);
    sessionStorage.setItem('lv_room', roomCode);
    // Remove session data written by older versions of the client.
    localStorage.removeItem('lv_token');
    localStorage.removeItem('lv_room');
}

function clearSession() {
    sessionStorage.removeItem('lv_token');
    sessionStorage.removeItem('lv_room');
    localStorage.removeItem('lv_token');
    localStorage.removeItem('lv_room');
}

document.addEventListener('DOMContentLoaded', () => {
    const roomParam = getUrlParam('room');
    if (roomParam) {
        document.getElementById('room-code-input').value = roomParam;
    }
    
    // Pre-fill random nickname if empty for quick testing
    const adjectives = ['빠른', '멋진', '졸린', '화난', '행복한', '용감한', '똑똑한'];
    const nouns = ['호랑이', '토끼', '거북이', '강아지', '고양이', '독수리', '돌고래'];
    if (!document.getElementById('nickname-input').value) {
        const randAdj = adjectives[Math.floor(Math.random() * adjectives.length)];
        const randNoun = nouns[Math.floor(Math.random() * nouns.length)];
        document.getElementById('nickname-input').value = `${randAdj}${randNoun}`;
    }

    // Reaction buttons
    document.querySelectorAll('.reaction-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const type = btn.dataset.type;
            if (window.socket) {
                window.socket.emit('send_reaction', { type });
            }
        });
    });
});
