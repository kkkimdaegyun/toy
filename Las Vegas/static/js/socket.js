// socket.js
const socket = io();
window.socket = socket;

socket.on('connect', () => {
    console.log('Connected to server');
    document.getElementById('disconnect-overlay').classList.remove('active');
    
    // Attempt reconnect if session exists
    const session = loadSavedSession();
    if (session && gameState.phase === 'landing') {
        document.getElementById('loading-overlay').classList.add('active');
        document.getElementById('loading-text').innerText = '진행 중인 게임 복구 중...';
        socket.emit('reconnect_attempt', { token: session.token, room_code: session.roomCode });
    }
});

socket.on('disconnect', () => {
    console.log('Disconnected');
    document.getElementById('disconnect-overlay').classList.add('active');
});

socket.on('room_created', (data) => {
    saveSession(data.token, data.room_code);
    gameState.roomCode = data.room_code;
    gameState.playerId = data.player_id;
    gameState.isHost = data.is_host;
    gameState.seat = data.seat;
    document.getElementById('lobby-room-code').innerText = data.room_code;
    showScreen('lobby-screen');
    socket.emit('get_available_colors', { room_code: data.room_code });
});

socket.on('room_joined', (data) => {
    saveSession(data.token, data.room_code);
    gameState.roomCode = data.room_code;
    gameState.playerId = data.player_id;
    gameState.isHost = data.is_host;
    gameState.seat = data.seat;
    document.getElementById('lobby-room-code').innerText = data.room_code;
    showScreen('lobby-screen');
});

socket.on('room_update', (data) => {
    gameState.players = data.players;
    gameState.gameMode = data.game_mode;
    gameState.availableColors = data.available_colors;
    if (window.renderLobby) window.renderLobby(data);
});

socket.on('player_joined', (data) => {
    addLog(`${data.nickname}님이 입장했습니다.`);
});

socket.on('player_disconnected', (data) => {
    addLog(`${data.nickname}님의 연결이 끊어졌습니다.`);
});

socket.on('player_reconnected', (data) => {
    addLog(`${data.nickname}님이 다시 연결되었습니다.`);
});

socket.on('reconnect_success', (data) => {
    document.getElementById('loading-overlay').classList.remove('active');
    gameState.roomCode = data.room_code;
    gameState.playerId = data.player_id;
    gameState.isHost = data.is_host;
    gameState.nickname = data.nickname;
    gameState.color = data.color;
    gameState.seat = data.seat;
    document.getElementById('lobby-room-code').innerText = data.room_code;
    if (!data.has_game) {
        showScreen('lobby-screen');
    }
});

socket.on('reconnect_failed', (data) => {
    document.getElementById('loading-overlay').classList.remove('active');
    clearSession();
    console.log('Reconnect failed:', data.message);
});

socket.on('session_replaced', (data) => {
    clearSession();
    alert(data.message);
    window.location.reload();
});

socket.on('game_state', (state) => {
    restoreGameState(state);
});

socket.on('game_mode_changed', (data) => {
    gameState.gameMode = data.mode;
    if (document.getElementById('game-mode-select')) {
        document.getElementById('game-mode-select').value = data.mode;
    }
});

socket.on('game_started', (data) => {
    gameState.gameMode = data.game_mode;
    gameState.players = data.players;
    gameState.placementSequence = 0;
    // Initialise player resources
    Object.keys(gameState.players).forEach(pid => {
        gameState.playerDice[pid] = 8;
        gameState.winnings[pid] = 0;
    });
    
    // Show dealer screen
    showScreen('game-screen'); // background
    document.getElementById('dealer-screen').classList.add('active');
    document.getElementById('dealer-dice-container').innerHTML = '';
    document.getElementById('dealer-result-text').innerText = '주사위를 굴려 선을 정합니다...';
});

socket.on('dealer_roll', (data) => {
    renderDealerRoll(data);
});

function renderDealerRoll(data) {
    const container = document.getElementById('dealer-dice-container');
    container.innerHTML = '';
    
    if (data.is_reroll) {
        document.getElementById('dealer-result-text').innerText = '동점입니다! 다시 굴립니다...';
    }

    Object.entries(data.rolls).forEach(([pid, info]) => {
        const div = document.createElement('div');
        div.className = 'dealer-dice-item anim-bounce';
        
        const nameEl = document.createElement('div');
        nameEl.innerText = info.nickname;
        nameEl.style.color = COLOR_HEX[info.color];
        nameEl.style.fontWeight = 'bold';
        
        let diceEl;
        if (gameState.gameMode === 'card') {
            diceEl = createCardFace(info.roll, COLOR_HEX[info.color]);
            diceEl.style.width = '60px'; diceEl.style.height = '90px';
        } else {
            diceEl = createDiceFace(info.roll, info.color);
        }
        
        div.appendChild(nameEl);
        div.appendChild(diceEl);
        container.appendChild(div);
    });
}

socket.on('dealer_result', (data) => {
    if (data.is_tie) {
        document.getElementById('dealer-result-text').innerText = `동점 발생! 재굴림 중...`;
        setTimeout(() => {
            if (gameState.isHost) socket.emit('dealer_reroll');
        }, 2000);
    } else {
        document.getElementById('dealer-result-text').innerHTML = `<span style="color:${COLOR_HEX[data.winner_color]}">${data.winner_nickname}</span>님이 선입니다! (가장 낮은 숫자)`;
        setTimeout(() => {
            document.getElementById('dealer-screen').classList.remove('active');
            if (gameState.isHost) socket.emit('setup_payouts');
        }, 2500);
    }
});

socket.on('payout_setup', (data) => {
    gameState.casinoBills = data.casinos;
    // reset dice
    gameState.casinoDice = {1:{}, 2:{}, 3:{}, 4:{}, 5:{}, 6:{}};
    if (window.setupGameBoard) window.setupGameBoard(gameState.players);
    if (window.renderCasinos) window.renderCasinos(gameState.casinoBills);
    if (window.renderPlayerPanels) window.renderPlayerPanels();
});

socket.on('turn_start', (data) => {
    gameState.currentTurn = data.player_id;
    if (window.handleTurnStart) window.handleTurnStart(data);
});

socket.on('dice_rolled', (data) => {
    gameState.currentRoll = data.results;
    gameState.validCasinos = data.valid_casinos;
    if (window.showRolledDice) window.showRolledDice(data);
    addLog(`${data.nickname}님이 주사위를 굴렸습니다.`);
});

socket.on('cards_drawn', (data) => {
    gameState.currentRoll = data.results;
    gameState.validCasinos = data.valid_casinos;
    if (window.showDrawnCards) window.showDrawnCards(data);
    addLog(`${data.nickname}님이 카드를 뽑았습니다.`);
});

socket.on('placement_preview', (data) => {
    if (window.showPlacementPreview) window.showPlacementPreview(data);
});

socket.on('placement_confirmed', (data) => {
    const sequence = Number(data.sequence || 0);
    if (sequence > 0 && sequence <= gameState.placementSequence) {
        return;
    }
    if (sequence > 0) {
        gameState.placementSequence = sequence;
    }

    // Apply the server snapshot atomically before the following turn_start
    // event arrives. The previous code overwrote this casino with undefined
    // when casino_counts was absent, making the board appear one turn late.
    if (data.all_player_remaining) {
        gameState.playerDice = { ...data.all_player_remaining };
    } else {
        gameState.playerDice[data.player_id] = data.remaining;
    }

    if (data.all_casino_dice) {
        gameState.casinoDice = data.all_casino_dice;
    } else if (data.casino_counts) {
        gameState.casinoDice[data.casino] = data.casino_counts;
    }
    
    if (window.updateAfterPlacement) window.updateAfterPlacement(data);
    addLog(`${data.nickname}님이 카지노 ${data.casino}에 ${data.count}개를 배치했습니다.`);
});

socket.on('player_finished', (data) => {
    addLog(`${data.nickname}님이 주사위를 모두 사용했습니다.`);
});

socket.on('round_complete', () => {
    if (window.showRoundComplete) window.showRoundComplete();
    setTimeout(() => {
        if (gameState.isHost) socket.emit('do_settlement');
    }, 2000);
});

socket.on('settlement_data', (data) => {
    // Server sends absolute winnings values
    if (data.winnings) {
        gameState.winnings = data.winnings;
    }
    if (window.showSettlement) window.showSettlement(data);
});

socket.on('game_over', (data) => {
    if (window.showResults) window.showResults(data);
});

socket.on('reaction', (data) => {
    if (window.showSpeechBubble) window.showSpeechBubble(data);
});

socket.on('game_log', (data) => {
    addLog(data.message);
});

socket.on('error', (data) => {
    alert(data.message);
});

socket.on('rematch_started', () => {
    document.getElementById('results-screen').classList.remove('active');
    // Reset game state for new round
    Object.keys(gameState.players).forEach(pid => {
        gameState.playerDice[pid] = 8;
        gameState.winnings[pid] = 0;
    });
    gameState.casinoDice = {1:{}, 2:{}, 3:{}, 4:{}, 5:{}, 6:{}};
    gameState.casinoBills = {};
    gameState.selectedCasino = null;
    gameState.currentRoll = [];
    gameState.validCasinos = [];
    gameState.placementSequence = 0;
    
    // Dealer screen will be shown by dealer_roll event
    document.getElementById('dealer-screen').classList.add('active');
    document.getElementById('dealer-dice-container').innerHTML = '';
    document.getElementById('dealer-result-text').innerText = '새 게임! 선을 정합니다...';
    addLog("새 게임이 시작되었습니다.");
});

socket.on('return_to_lobby', () => {
    document.getElementById('results-screen').classList.remove('active');
    showScreen('lobby-screen');
});

socket.on('available_colors', (data) => {
    gameState.availableColors = data.colors;
    updateColorPicker();
});

function addLog(msg) {
    const logEl = document.getElementById('log-messages');
    if (!logEl) return;
    const div = document.createElement('div');
    div.className = 'log-msg anim-fade-in';
    
    const time = new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit', second:'2-digit'});
    div.innerHTML = `<span style="color:#aaa">[${time}]</span> ${msg}`;
    
    logEl.appendChild(div);
    logEl.parentElement.scrollTop = logEl.parentElement.scrollHeight;
}

function restoreGameState(state) {
    gameState.serverPhase = state.phase;
    gameState.placementSequence = Number(state.placement_sequence || 0);
    gameState.gameMode = state.game_mode;
    gameState.players = state.players || {};
    gameState.currentTurn = state.current_player;
    gameState.currentRoll = state.current_roll || [];
    gameState.winnings = state.winnings || {};
    gameState.selectedCasino = null;

    gameState.playerDice = {};
    Object.entries(state.player_dice || {}).forEach(([pid, resource]) => {
        gameState.playerDice[pid] = resource.remaining;
    });

    gameState.casinoBills = {};
    Object.entries(state.casino_bills || {}).forEach(([casino, bills]) => {
        gameState.casinoBills[casino] = {
            bills,
            total: bills.reduce((sum, bill) => sum + bill.value, 0)
        };
    });

    gameState.casinoDice = {};
    for (let casino = 1; casino <= 6; casino++) {
        const rawCounts = (state.casino_dice || {})[casino] || {};
        const enriched = {};
        Object.entries(rawCounts).forEach(([pid, count]) => {
            const player = gameState.players[pid];
            if (player) {
                enriched[pid] = {
                    count,
                    nickname: player.nickname,
                    color: player.color
                };
            }
        });
        gameState.casinoDice[casino] = enriched;
    }

    showScreen('game-screen');
    if (window.setupGameBoard) window.setupGameBoard(gameState.players);
    if (window.renderCasinos) window.renderCasinos(gameState.casinoBills);
    if (window.renderPlayerPanels) window.renderPlayerPanels();
    for (let casino = 1; casino <= 6; casino++) {
        if (window.renderCasinoDiceCounts) {
            window.renderCasinoDiceCounts(casino, gameState.casinoDice[casino]);
        }
    }

    if (state.phase === 'DEALER_ROLL' || state.phase === 'DEALER_TIE_REROLL' || state.phase === 'PAYOUT_SETUP') {
        const dealer = document.getElementById('dealer-screen');
        dealer.classList.add('active');
        const rolls = {};
        Object.entries(state.dealer_rolls || {}).forEach(([pid, roll]) => {
            const player = gameState.players[pid];
            if (player) {
                rolls[pid] = { roll, nickname: player.nickname, color: player.color };
            }
        });
        if (Object.keys(rolls).length > 0) {
            renderDealerRoll({ rolls, is_reroll: state.phase === 'DEALER_TIE_REROLL' });
        }
        document.getElementById('dealer-result-text').innerText =
            state.phase === 'PAYOUT_SETUP' ? '게임판을 준비하고 있습니다...' : '선 정하기를 복구했습니다.';
    }

    if (state.phase === 'DEALER_TIE_REROLL' && gameState.isHost) {
        setTimeout(() => socket.emit('dealer_reroll'), 300);
    } else if (state.phase === 'PAYOUT_SETUP' && gameState.isHost) {
        setTimeout(() => socket.emit('setup_payouts'), 300);
    } else if (state.phase === 'ROUND_COMPLETE' && gameState.isHost) {
        if (window.showRoundComplete) window.showRoundComplete();
        setTimeout(() => socket.emit('do_settlement'), 300);
    }

    if (state.current_player && ['TURN_WAITING', 'DICE_ROLLING', 'CARD_DRAWING', 'PLACEMENT_SELECTION'].includes(state.phase)) {
        const player = gameState.players[state.current_player];
        if (player && window.handleTurnStart) {
            window.handleTurnStart({
                player_id: state.current_player,
                nickname: player.nickname,
                color: player.color,
                remaining: gameState.playerDice[state.current_player]
            });
        }

        if (gameState.currentRoll.length > 0 && player) {
            const rollData = {
                player_id: state.current_player,
                nickname: player.nickname,
                color: player.color,
                results: gameState.currentRoll,
                valid_casinos: [...new Set(gameState.currentRoll)].sort()
            };
            gameState.validCasinos = rollData.valid_casinos;
            if (gameState.gameMode === 'card' && window.showDrawnCards) {
                window.showDrawnCards(rollData);
            } else if (window.showRolledDice) {
                window.showRolledDice(rollData);
            }
        }
    }

    if (state.phase === 'GAME_OVER' && window.showResults) {
        const sorted = Object.entries(gameState.winnings).sort((a, b) => b[1] - a[1]);
        const rankings = sorted.map(([pid, total], index) => {
            const player = gameState.players[pid];
            let rank = index + 1;
            if (index > 0 && total === sorted[index - 1][1]) {
                rank = sorted.slice(0, index).findIndex((entry) => entry[1] === total) + 1;
            }
            return {
                player_id: pid,
                nickname: player.nickname,
                color: player.color,
                total,
                rank
            };
        });
        window.showResults({ rankings });
    }
}
