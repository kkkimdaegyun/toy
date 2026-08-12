// lobby.js

document.getElementById('color-picker').addEventListener('click', (e) => {
    if (e.target.classList.contains('color-btn') && !e.target.classList.contains('disabled')) {
        document.querySelectorAll('.color-btn').forEach(b => b.classList.remove('selected'));
        e.target.classList.add('selected');
        gameState.color = e.target.dataset.color;
    }
});

function updateColorPicker() {
    const avail = gameState.availableColors || ['red', 'orange', 'yellow', 'green'];
    document.querySelectorAll('.color-btn').forEach(btn => {
        const color = btn.dataset.color;
        if (avail.includes(color)) {
            btn.classList.remove('disabled');
        } else {
            btn.classList.add('disabled');
            if (btn.classList.contains('selected')) {
                btn.classList.remove('selected');
                gameState.color = null;
            }
        }
    });
}

document.getElementById('btn-create-room').addEventListener('click', () => {
    const nick = document.getElementById('nickname-input').value.trim();
    if (!nick) return alert('닉네임을 입력하세요.');
    if (!gameState.color) return alert('색상을 선택하세요.');
    
    gameState.nickname = nick;
    socket.emit('create_room', { nickname: nick, color: gameState.color });
});

document.getElementById('btn-join-room').addEventListener('click', () => {
    const nick = document.getElementById('nickname-input').value.trim();
    const code = document.getElementById('room-code-input').value.trim().toUpperCase();
    
    if (!nick) return alert('닉네임을 입력하세요.');
    if (!code) return alert('방 코드를 입력하세요.');
    if (!gameState.color) return alert('색상을 선택하세요.');
    
    gameState.nickname = nick;
    socket.emit('join_room', { room_code: code, nickname: nick, color: gameState.color });
});

document.getElementById('btn-copy-link').addEventListener('click', () => {
    const url = `${window.location.origin}/?room=${gameState.roomCode}`;
    navigator.clipboard.writeText(url).then(() => {
        const btn = document.getElementById('btn-copy-link');
        btn.innerText = '복사 완료';
        setTimeout(() => btn.innerText = '초대 링크 복사', 2000);
    });
});

document.getElementById('btn-start').addEventListener('click', () => {
    socket.emit('start_game');
});

document.getElementById('game-mode-select').addEventListener('change', (e) => {
    if (gameState.isHost) {
        socket.emit('set_game_mode', { mode: e.target.value });
    }
});

window.renderLobby = function(data) {
    const players = data.players; // {pid: {nickname, color, seat}}
    
    // Update color picker
    updateColorPicker();

    // Show host controls
    if (gameState.isHost) {
        document.getElementById('host-controls').style.display = 'flex';
    }

    const container = document.getElementById('lobby-players');
    container.innerHTML = '';
    
    let playerCount = Object.keys(players).length;

    // Show all four available seats even though the game can start with two.
    for (let i = 0; i < 4; i++) {
        const slot = document.createElement('div');
        slot.className = 'player-slot';
        
        // Find player in this seat
        const playerEntry = Object.entries(players).find(([pid, p]) => p.seat === i);
        
        if (playerEntry) {
            const [pid, p] = playerEntry;
            slot.classList.add('occupied');
            slot.style.borderColor = COLOR_HEX[p.color];
            
            let hostHtml = (pid === data.host_id) ? '<div class="crown">HOST</div>' : '';
            slot.innerHTML = `
                ${hostHtml}
                <div class="player-color-mark" style="color: ${COLOR_HEX[p.color]}">${COLOR_EMOJI[p.color]}</div>
                <div style="font-weight: bold; color: ${COLOR_HEX[p.color]}">${p.nickname}</div>
                ${pid === gameState.playerId ? '(나)' : ''}
            `;
        } else {
            slot.innerHTML = `<div style="color: var(--text-muted);">빈 자리</div>`;
        }
        
        container.appendChild(slot);
    }
    
    // Update buttons
    const btnStart = document.getElementById('btn-start');
    const startStatus = document.getElementById('start-status');
    
    if (gameState.isHost) {
        btnStart.style.display = 'block';
        // Keep the button clickable so the server can return a useful reason
        // instead of making the UI look broken.
        btnStart.disabled = false;
        btnStart.innerText = '게임 시작';
        startStatus.style.display = 'block';
        if (playerCount < 2) {
            startStatus.className = 'start-status waiting';
            startStatus.innerText = `한 명 더 필요합니다. (${playerCount}/4)`;
        } else {
            startStatus.className = 'start-status can-start';
            startStatus.innerText = `${playerCount}명 입장 완료 · 바로 시작할 수 있습니다.`;
        }
    } else {
        btnStart.style.display = 'none';
        startStatus.style.display = 'block';
        startStatus.className = 'start-status waiting';
        startStatus.innerText = playerCount < 2
            ? '다른 플레이어를 기다리는 중입니다.'
            : '방장이 게임을 시작할 수 있습니다.';
    }
};
