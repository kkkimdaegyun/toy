// game.js

window.setupGameBoard = function(players) {
    const grid = document.getElementById('casinos-grid');
    grid.innerHTML = '';
    
    // Create 6 casinos
    for (let i = 1; i <= 6; i++) {
        const panel = document.createElement('div');
        panel.className = 'casino-panel anim-fade-in';
        panel.id = `casino-${i}`;
        panel.dataset.casino = i;
        
        const header = document.createElement('div');
        header.className = 'casino-header';
        
        let diceIcon = '';
        if (gameState.gameMode === 'card') {
            diceIcon = `CARD ${i}`;
        } else {
            diceIcon = `DICE ${i}`;
        }
        
        header.innerHTML = `
            <div class="casino-number-dice">${diceIcon}</div>
            <div class="casino-total" id="casino-${i}-total">$0</div>
        `;
        
        const billsArea = document.createElement('div');
        billsArea.className = 'bills-area';
        billsArea.id = `casino-${i}-bills`;
        
        const diceArea = document.createElement('div');
        diceArea.className = 'dice-area';
        diceArea.id = `casino-${i}-dice`;
        
        panel.appendChild(header);
        panel.appendChild(billsArea);
        panel.appendChild(diceArea);
        
        // Add click listener for placement
        panel.addEventListener('click', () => {
            if (panel.classList.contains('valid-target')) {
                window.onCasinoSelect(i);
            }
        });
        
        grid.appendChild(panel);
    }
    
    window.renderPlayerPanels();
};

window.renderCasinos = function(casinoData) {
    for (let i = 1; i <= 6; i++) {
        const data = casinoData[i];
        if (!data) continue;
        
        document.getElementById(`casino-${i}-total`).innerText = formatMoney(data.total);
        
        const billsArea = document.getElementById(`casino-${i}-bills`);
        billsArea.innerHTML = '';
        
        // Sort descending
        const sortedBills = [...data.bills].sort((a,b) => b.value - a.value);
        
        sortedBills.forEach((b, idx) => {
            const billEl = document.createElement('div');
            billEl.className = `bill bill-${b.value}`;
            billEl.innerText = formatMoney(b.value);
            // stagger animation
            billEl.style.animation = `slideUp 0.3s ease-out ${idx * 0.1}s both`;
            billsArea.appendChild(billEl);
        });
    }
};

window.renderPlayerPanels = function() {
    const container = document.getElementById('players-panel');
    container.innerHTML = '';
    
    // Sort by seat
    const sortedPlayers = Object.entries(gameState.players).sort((a,b) => a[1].seat - b[1].seat);
    
    sortedPlayers.forEach(([pid, p]) => {
        const panel = document.createElement('div');
        panel.className = 'player-info';
        panel.id = `player-panel-${pid}`;
        
        const remDice = gameState.playerDice[pid] !== undefined ? gameState.playerDice[pid] : 8;
        const winAmount = gameState.winnings[pid] || 0;
        
        panel.innerHTML = `
            <div class="player-name" style="color: ${COLOR_HEX[p.color]}">${COLOR_EMOJI[p.color]} ${p.nickname}</div>
            <div class="player-stats">
                <span id="player-${pid}-rem">${gameState.gameMode === 'card' ? 'CARD' : 'DICE'} ${remDice}</span>
                <span id="player-${pid}-win" class="money-value">${formatMoney(winAmount)}</span>
            </div>
        `;
        
        container.appendChild(panel);
    });
};

window.handleTurnStart = function(data) {
    document.querySelectorAll('.player-info').forEach(p => p.classList.remove('active'));
    
    const activePanel = document.getElementById(`player-panel-${data.player_id}`);
    if (activePanel) activePanel.classList.add('active');
    
    const turnInd = document.getElementById('turn-indicator');
    turnInd.innerHTML = `<span style="color:${COLOR_HEX[data.color]}">${data.nickname}</span>님의 턴입니다.`;
    
    const btnRoll = document.getElementById('btn-roll');
    const btnDraw = document.getElementById('btn-draw');
    const currDiceArea = document.getElementById('current-dice-area');
    
    btnRoll.style.display = 'none';
    btnDraw.style.display = 'none';
    currDiceArea.innerHTML = '';
    
    // Clear all valid target highlights
    document.querySelectorAll('.casino-panel').forEach(c => c.classList.remove('valid-target'));
    
    if (data.player_id === gameState.playerId) {
        if (gameState.gameMode === 'card') {
            btnDraw.style.display = 'block';
            btnDraw.onclick = () => { btnDraw.style.display = 'none'; socket.emit('draw_cards'); };
        } else {
            btnRoll.style.display = 'block';
            btnRoll.onclick = () => { btnRoll.style.display = 'none'; socket.emit('roll_dice'); };
        }
    }
};

window.showRolledDice = function(data) {
    const currDiceArea = document.getElementById('current-dice-area');
    currDiceArea.innerHTML = '';
    
    data.results.forEach((val, idx) => {
        const d = createDiceFace(val, data.color);
        d.classList.add('anim-bounce');
        d.style.animationDelay = `${idx * 0.05}s`;
        currDiceArea.appendChild(d);
    });
    
    if (data.player_id === gameState.playerId) {
        data.valid_casinos.forEach(c => {
            const panel = document.getElementById(`casino-${c}`);
            if (panel) panel.classList.add('valid-target');
        });
        document.getElementById('turn-indicator').innerText = '배치할 카지노를 선택하세요.';
    }
};

window.showDrawnCards = function(data) {
    const currDiceArea = document.getElementById('current-dice-area');
    currDiceArea.innerHTML = '';
    
    data.results.forEach((val, idx) => {
        const c = createCardFace(val, COLOR_HEX[data.color]);
        c.classList.add('anim-bounce');
        c.style.animationDelay = `${idx * 0.05}s`;
        currDiceArea.appendChild(c);
    });
    
    if (data.player_id === gameState.playerId) {
        data.valid_casinos.forEach(c => {
            const panel = document.getElementById(`casino-${c}`);
            if (panel) panel.classList.add('valid-target');
        });
        document.getElementById('turn-indicator').innerText = '배치할 카지노를 선택하세요.';
    }
};

window.onCasinoSelect = function(casinoNum) {
    gameState.selectedCasino = casinoNum;
    socket.emit('get_placement_preview', { casino: casinoNum });
};

window.showPlacementPreview = function(data) {
    document.getElementById('preview-casino-num').innerText = data.casino;
    const content = document.getElementById('preview-content');
    
    let html = `
        <div style="text-align:center; font-size:1.2rem; margin-bottom:15px;">
            내 주사위 <strong style="color:var(--player-green);">${data.count}</strong>개를 배치합니다.
        </div>
        <div style="background:rgba(0,0,0,0.3); padding:10px; border-radius:8px;">
            <div style="margin-bottom:10px; font-weight:bold;">배치 후 예상 현황:</div>
    `;
    
    const sorted = Object.entries(data.resulting_counts).sort((a,b) => b[1].count - a[1].count);
    
    sorted.forEach(([pid, info]) => {
        let isMe = (pid === gameState.playerId) ? '(나) ' : '';
        let isTie = data.tie_players && data.tie_players.some(tp => tp.player_id === pid);
        let style = isTie ? 'text-decoration: line-through; color: var(--danger);' : '';
        let warn = isTie ? ' <span class="inline-warning">[무효 위기]</span>' : '';
        
        html += `
            <div style="display:flex; justify-content:space-between; margin-bottom:5px; padding:5px; ${pid===gameState.playerId?'background:rgba(255,255,255,0.1); border-radius:5px;':''}">
                <span style="color:${COLOR_HEX[info.color]}; font-weight:bold; ${style}">
                    ${COLOR_EMOJI[info.color]} ${info.nickname} ${isMe}
                </span>
                <span style="${style}">${info.count}개</span>
                ${warn}
            </div>
        `;
    });
    
    html += `</div>`;
    
    if (data.has_tie) {
        html += `
            <div class="tie-alert mt-20">
                경고: 현재 상태로 무효 처리되는 플레이어가 있습니다.
            </div>
        `;
    }
    
    content.innerHTML = html;
    document.getElementById('preview-overlay').classList.add('active');
    
    document.getElementById('btn-confirm-placement').onclick = () => {
        document.getElementById('preview-overlay').classList.remove('active');
        socket.emit('confirm_placement', { casino: gameState.selectedCasino });
    };
    
    document.getElementById('btn-cancel-placement').onclick = () => {
        document.getElementById('preview-overlay').classList.remove('active');
    };
};

window.updateAfterPlacement = function(data) {
    Object.entries(gameState.playerDice).forEach(([pid, remaining]) => {
        const remainingEl = document.getElementById(`player-${pid}-rem`);
        if (remainingEl) {
            remainingEl.innerText = `${gameState.gameMode === 'card' ? 'CARD' : 'DICE'} ${remaining}`;
        }
    });
    
    document.querySelectorAll('.casino-panel').forEach(c => c.classList.remove('valid-target'));
    if (data.player_id === gameState.playerId) {
        document.getElementById('current-dice-area').innerHTML = '';
    }
    
    // Check all casinos for dice counts and update visually
    for(let i=1; i<=6; i++) {
        if(gameState.casinoDice[i]) {
            renderCasinoDiceCounts(i, gameState.casinoDice[i]);
        }
    }

    const updatedCasino = document.getElementById(`casino-${data.casino}`);
    if (updatedCasino) {
        const updateToken = String(data.sequence || Date.now());
        updatedCasino.dataset.liveUpdate = updateToken;
        updatedCasino.classList.add('live-updated');

        updatedCasino.querySelector('.placement-live-label')?.remove();
        const liveLabel = document.createElement('div');
        liveLabel.className = 'placement-live-label';
        liveLabel.textContent = `${data.nickname} · ${data.count}개 배치`;
        updatedCasino.appendChild(liveLabel);

        const liveStatus = document.getElementById('live-placement-status');
        if (liveStatus) {
            liveStatus.dataset.liveUpdate = updateToken;
            liveStatus.textContent = `LIVE / ${data.nickname} → 카지노 ${data.casino} / ${data.count}개`;
        }

        setTimeout(() => {
            if (updatedCasino.dataset.liveUpdate === updateToken) {
                updatedCasino.classList.remove('live-updated');
                liveLabel.remove();
            }
            if (liveStatus && liveStatus.dataset.liveUpdate === updateToken) {
                liveStatus.textContent = '';
            }
        }, 1800);
    }
};

window.renderCasinoDiceCounts = function(casinoNum, counts) {
    const area = document.getElementById(`casino-${casinoNum}-dice`);
    area.innerHTML = '';
    
    // counts: {pid: {count, nickname, color}}
    const entries = Object.entries(counts).filter(e => e[1].count > 0);
    
    // Group by count to find ties visually
    const countMap = {};
    entries.forEach(e => {
        const c = e[1].count;
        countMap[c] = (countMap[c] || 0) + 1;
    });
    
    entries.sort((a,b) => b[1].count - a[1].count).forEach(([pid, info]) => {
        const badge = document.createElement('div');
        badge.className = 'dice-count-badge anim-bounce';
        badge.style.backgroundColor = COLOR_HEX[info.color];
        badge.innerHTML = `${info.nickname.substring(0,2)} ${info.count}`;
        
        // Tie warning
        if (countMap[info.count] > 1) {
            badge.classList.add('tie-warning');
        }
        
        area.appendChild(badge);
    });
};

window.showRoundComplete = function() {
    document.getElementById('turn-indicator').innerText = '라운드 종료! 정산을 시작합니다...';
};

window.showSettlement = async function(data) {
    const overlay = document.getElementById('settlement-screen');
    const content = document.getElementById('settlement-content');
    content.innerHTML = '';
    overlay.classList.add('active');
    
    // process 1 to 6
    for (let i = 1; i <= 6; i++) {
        const setData = data.settlements[i];
        if (!setData) continue;
        
        const row = document.createElement('div');
        row.className = 'settlement-row anim-slide-up';
        
        let leftCol = `<div style="font-size:1.5rem; font-weight:bold; min-width:80px;">카지노 ${i}</div>`;
        let rightCol = `<div style="display:flex; flex-direction:column; gap:5px; flex:1;">`;
        
        // Show cancelled
        if (setData.cancelled && setData.cancelled.length > 0) {
            setData.cancelled.forEach(entry => {
                const pid = typeof entry === 'string' ? entry : entry.player_id;
                const nickname = entry.nickname || (gameState.players[pid] && gameState.players[pid].nickname) || pid;
                const countInfo = setData.counts[pid];
                const countVal = countInfo ? (typeof countInfo === 'object' ? countInfo.count : countInfo) : '?';
                rightCol += `
                    <div style="color:var(--text-muted); text-decoration:line-through; font-size:0.9rem;">
                        ${nickname} 무효 (${countVal}개 동점)
                    </div>`;
            });
        }
        
        // Show payouts
        if (setData.payouts && setData.payouts.length > 0) {
            setData.payouts.forEach(po => {
                const nickname = po.nickname || (gameState.players[po.player_id] && gameState.players[po.player_id].nickname) || po.player_id;
                const color = po.color || (gameState.players[po.player_id] && gameState.players[po.player_id].color) || 'red';
                const billValue = po.bill ? po.bill.value : (po.amount || 0);
                rightCol += `
                    <div style="color:${COLOR_HEX[color]}; font-weight:bold;">
                        ${nickname} → <span class="money-value">+${formatMoney(billValue)}</span>
                    </div>`;
            });
        } else {
            rightCol += `<div style="color:var(--text-muted);">지급 대상자 없음</div>`;
        }
        
        rightCol += `</div>`;
        row.innerHTML = leftCol + rightCol;
        content.appendChild(row);
        
        // Scroll to bottom
        content.scrollTop = content.scrollHeight;
        
        // Wait 1.5s per casino for animation effect
        await sleep(1500);
    }
    
    await sleep(2000);
    overlay.classList.remove('active');
    
    // Update player panels with new winnings
    window.renderPlayerPanels();
};

window.showResults = function(data) {
    const modal = document.getElementById('results-modal');
    const rankingsEl = document.getElementById('final-rankings');
    rankingsEl.innerHTML = '';
    
    data.rankings.forEach((r, idx) => {
        const item = document.createElement('div');
        item.style.padding = '15px';
        item.style.margin = '10px 0';
        item.style.background = idx === 0 ? 'var(--surface-3)' : 'var(--surface-1)';
        item.style.border = idx === 0 ? '1px solid var(--accent)' : '1px solid var(--panel-border)';
        item.style.borderRadius = '3px';
        item.style.display = 'flex';
        item.style.justifyContent = 'space-between';
        
        item.innerHTML = `
            <div style="font-size:1.2rem; font-weight:bold; color:${COLOR_HEX[r.color]}">
                ${String(r.rank).padStart(2, '0')} / ${r.nickname}
            </div>
            <div class="money-value" style="font-size:1.1rem;">
                ${formatMoney(r.total)}
            </div>
        `;
        rankingsEl.appendChild(item);
    });
    
    document.getElementById('results-screen').classList.add('active');
    
    if (gameState.isHost) {
        document.getElementById('btn-rematch').style.display = 'inline-block';
        document.getElementById('btn-lobby').style.display = 'inline-block';
        
        document.getElementById('btn-rematch').onclick = () => socket.emit('request_rematch');
        document.getElementById('btn-lobby').onclick = () => socket.emit('return_to_lobby');
    }
};

window.showSpeechBubble = function(data) {
    const pPanel = document.getElementById(`player-panel-${data.player_id}`);
    if (!pPanel) return;
    
    const bubble = document.createElement('div');
    bubble.className = 'speech-bubble';
    bubble.innerText = data.type;
    
    const rect = pPanel.getBoundingClientRect();
    bubble.style.left = `${rect.left + rect.width/2}px`;
    bubble.style.top = `${rect.top - 20}px`;
    
    document.body.appendChild(bubble);
    setTimeout(() => bubble.remove(), 2000);
};
