"""
카지노 나이트 - 사내 멀티플레이 보드게임 서버
Flask + Flask-SocketIO real-time multiplayer casino dice game.
"""
from flask import Flask, render_template, request
from flask_socketio import SocketIO, disconnect, emit, join_room, leave_room
from game.rooms import RoomManager
from game.config import *
from game.serializers import settlement_to_dict
from game.utils import get_lan_ip
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'casino-night-office-game-2024'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading', ping_timeout=60, ping_interval=25)

room_manager = RoomManager()

# Track socket-to-player mappings
sid_to_player = {}  # {sid: {'player_id': str, 'room_code': str}}
player_to_sid = {}  # {player_id: sid}
disconnected_players = {}  # {player_id: {'room_code': str, 'timestamp': float}}


@app.route('/')
def index():
    return render_template('index.html')


@app.after_request
def disable_client_cache(response):
    """Always serve the current UI to LAN players during active development."""
    if request.path == '/' or request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


def emit_room_update(room):
    """Send full room state to all players in room."""
    data = room.to_dict()
    data['player_count'] = len(room.players)
    data['is_full'] = room.is_full()
    data['available_colors'] = room.get_available_colors()
    socketio.emit('room_update', data, room=room.code)


def emit_game_state(room):
    """Send full game state to all players."""
    if room.game:
        state = room.game.get_public_state()
        socketio.emit('game_state', state, room=room.code)


def emit_log(room_code, message):
    """Send a game log message."""
    socketio.emit('game_log', {'message': message}, room=room_code)


@socketio.on('connect')
def on_connect():
    pass


@socketio.on('disconnect')
def on_disconnect():
    sid = request.sid
    if sid in sid_to_player:
        info = sid_to_player[sid]
        player_id = info['player_id']
        room_code = info['room_code']
        room = room_manager.get_room(room_code)
        
        # Mark as disconnected but don't remove
        disconnected_players[player_id] = {
            'room_code': room_code,
            'timestamp': time.time()
        }
        
        if player_id in player_to_sid:
            del player_to_sid[player_id]
        del sid_to_player[sid]
        
        if room:
            socketio.emit('player_disconnected', {
                'player_id': player_id,
                'nickname': room.players.get(player_id, {}).get('nickname', '?')
            }, room=room_code)


@socketio.on('create_room')
def on_create_room(data):
    nickname = data.get('nickname', '').strip()
    color = data.get('color', '')
    
    if not nickname or len(nickname) > 12:
        emit('error', {'message': '닉네임을 1~12자로 입력해주세요.'})
        return
    if color not in PLAYER_COLORS:
        emit('error', {'message': '올바른 색상을 선택해주세요.'})
        return
    
    player_id = f"player_{request.sid}"
    room = room_manager.create_room(player_id, nickname, color)
    
    if room is None:
        emit('error', {'message': '방을 만들 수 없습니다.'})
        return
    
    # Generate reconnect token
    token = room.generate_reconnect_token(player_id)
    
    # Track mappings
    sid_to_player[request.sid] = {'player_id': player_id, 'room_code': room.code}
    player_to_sid[player_id] = request.sid
    
    join_room(room.code)
    
    emit('room_created', {
        'room_code': room.code,
        'player_id': player_id,
        'token': token,
        'is_host': True,
        'seat': 0
    })
    
    emit_room_update(room)


@socketio.on('join_room')
def on_join_room(data):
    room_code = data.get('room_code', '').strip().upper()
    nickname = data.get('nickname', '').strip()
    color = data.get('color', '')
    
    if not nickname or len(nickname) > 12:
        emit('error', {'message': '닉네임을 1~12자로 입력해주세요.'})
        return
    if color not in PLAYER_COLORS:
        emit('error', {'message': '올바른 색상을 선택해주세요.'})
        return
    if not room_code:
        emit('error', {'message': '방 코드를 입력해주세요.'})
        return
    
    existing_room = room_manager.get_room(room_code)
    if not existing_room:
        emit('error', {'message': '방을 찾을 수 없습니다.'})
        return
    
    if existing_room.is_full():
        emit('error', {'message': f'방이 꽉 찼습니다. ({MAX_PLAYERS}/{MAX_PLAYERS}명)'})
        return
    
    # Check color availability
    if color not in existing_room.get_available_colors():
        emit('error', {'message': f'{COLOR_NAMES_KR.get(color, color)} - 사용 중입니다.'})
        return
    
    # Check if game already started
    if existing_room.game and existing_room.game.phase != LOBBY:
        emit('error', {'message': '이미 게임이 진행 중입니다.'})
        return
    
    player_id = f"player_{request.sid}"
    room = room_manager.join_room(room_code, player_id, nickname, color)
    
    if room is None:
        emit('error', {'message': '방에 참가할 수 없습니다.'})
        return
    
    # Generate reconnect token
    token = room.generate_reconnect_token(player_id)
    
    # Track mappings
    sid_to_player[request.sid] = {'player_id': player_id, 'room_code': room.code}
    player_to_sid[player_id] = request.sid
    
    join_room(room.code)
    
    seat = room.players[player_id]['seat']
    
    emit('room_joined', {
        'room_code': room.code,
        'player_id': player_id,
        'token': token,
        'is_host': (player_id == room.host_id),
        'seat': seat
    })
    
    # Notify others
    socketio.emit('player_joined', {
        'player_id': player_id,
        'nickname': nickname,
        'color': color,
        'seat': seat
    }, room=room.code, skip_sid=request.sid)
    
    emit_room_update(room)


@socketio.on('reconnect_attempt')
def on_reconnect(data):
    token = data.get('token', '')
    room_code = data.get('room_code', '')
    
    room = room_manager.get_room(room_code)
    if not room:
        emit('reconnect_failed', {'message': '방을 찾을 수 없습니다.'})
        return
    
    player_id = room.get_player_by_token(token)
    if not player_id or player_id not in room.players:
        emit('reconnect_failed', {'message': '재접속에 실패했습니다.'})
        return
    
    # Update mappings
    old_sid = player_to_sid.get(player_id)
    if old_sid and old_sid != request.sid and old_sid in sid_to_player:
        socketio.emit('session_replaced', {
            'message': '같은 플레이어가 다른 탭에서 다시 연결되어 이 세션을 종료합니다.'
        }, to=old_sid)
        del sid_to_player[old_sid]
        disconnect(sid=old_sid)
    
    sid_to_player[request.sid] = {'player_id': player_id, 'room_code': room.code}
    player_to_sid[player_id] = request.sid
    
    if player_id in disconnected_players:
        del disconnected_players[player_id]
    
    join_room(room.code)
    
    player_info = room.players[player_id]
    
    emit('reconnect_success', {
        'room_code': room.code,
        'player_id': player_id,
        'is_host': (player_id == room.host_id),
        'nickname': player_info['nickname'],
        'color': player_info['color'],
        'seat': player_info['seat'],
        'has_game': room.game is not None
    })
    
    # Send current room state
    emit_room_update(room)
    
    # If game is active, send game state
    if room.game:
        emit('game_state', room.game.get_public_state())
    
    # Notify others
    socketio.emit('player_reconnected', {
        'player_id': player_id,
        'nickname': player_info['nickname']
    }, room=room.code, skip_sid=request.sid)


@socketio.on('set_game_mode')
def on_set_game_mode(data):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room:
        return
    
    if info['player_id'] != room.host_id:
        emit('error', {'message': '방장만 게임 모드를 변경할 수 있습니다.'})
        return
    
    mode = data.get('mode', 'dice')
    if mode in ('dice', 'card'):
        room.game_mode = mode
        socketio.emit('game_mode_changed', {'mode': mode}, room=room.code)
        emit_room_update(room)


@socketio.on('start_game')
def on_start_game(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        emit('error', {'message': '세션이 만료되었습니다. 페이지를 새로고침해 다시 연결해주세요.'})
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room:
        return
    
    if info['player_id'] != room.host_id:
        emit('error', {'message': '방장만 게임을 시작할 수 있습니다.'})
        return
    
    if room.game and room.game.phase != LOBBY:
        emit('error', {'message': '이미 게임이 시작되었습니다.'})
        return
    
    player_count = len(room.players)
    if player_count < MIN_PLAYERS:
        emit('error', {'message': f'최소 {MIN_PLAYERS}명이 모여야 게임을 시작할 수 있습니다.'})
        return
    if player_count > MAX_PLAYERS:
        emit('error', {'message': f'최대 {MAX_PLAYERS}명까지 게임에 참여할 수 있습니다.'})
        return
    
    # Create and start game
    game = room.create_game()
    game.start_game()
    
    emit_log(room.code, '게임을 시작합니다.')
    emit_log(room.code, '선 정하기를 시작합니다.')
    
    # Do dealer roll
    rolls = game.do_dealer_roll()
    
    # Build roll data with nicknames
    roll_data = {}
    for pid, roll in rolls.items():
        nickname = game.players[pid]['nickname']
        color = game.players[pid]['color']
        roll_data[pid] = {'roll': roll, 'nickname': nickname, 'color': color}
        emit_log(room.code, f'{nickname}님: {roll}')
    
    socketio.emit('game_started', {
        'game_mode': game.game_mode,
        'players': game.players
    }, room=room.code)
    
    socketio.emit('dealer_roll', {'rolls': roll_data}, room=room.code)
    
    # Resolve - check for winner or tie
    winner, reroll_list = game.resolve_dealer()
    
    if winner:
        nickname = game.players[winner]['nickname']
        emit_log(room.code, f'{nickname}님이 선입니다.')
        socketio.emit('dealer_result', {
            'winner_id': winner,
            'winner_nickname': game.players[winner]['nickname'],
            'winner_color': game.players[winner]['color'],
            'is_tie': False,
            'reroll_players': []
        }, room=room.code)
    else:
        names = ', '.join(game.players[pid]['nickname'] + '님' for pid in reroll_list)
        emit_log(room.code, f'최저 숫자가 동률입니다! {names}이 다시 굴립니다.')
        socketio.emit('dealer_result', {
            'winner_id': None,
            'is_tie': True,
            'reroll_players': [
                {'player_id': pid, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
                for pid in reroll_list
            ]
        }, room=room.code)


@socketio.on('dealer_reroll')
def on_dealer_reroll(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    if game.phase != DEALER_TIE_REROLL:
        return
    
    rolls = game.do_dealer_roll()
    
    roll_data = {}
    for pid, roll in rolls.items():
        nickname = game.players[pid]['nickname']
        color = game.players[pid]['color']
        roll_data[pid] = {'roll': roll, 'nickname': nickname, 'color': color}
        emit_log(room.code, f'{nickname}님: {roll}')
    
    socketio.emit('dealer_roll', {'rolls': roll_data, 'is_reroll': True}, room=room.code)
    
    winner, reroll_list = game.resolve_dealer()
    
    if winner:
        nickname = game.players[winner]['nickname']
        emit_log(room.code, f'{nickname}님이 선입니다.')
        socketio.emit('dealer_result', {
            'winner_id': winner,
            'winner_nickname': game.players[winner]['nickname'],
            'winner_color': game.players[winner]['color'],
            'is_tie': False,
            'reroll_players': []
        }, room=room.code)
    else:
        names = ', '.join(game.players[pid]['nickname'] + '님' for pid in reroll_list)
        emit_log(room.code, f'최저 숫자가 동률입니다! {names}이 다시 굴립니다.')
        socketio.emit('dealer_result', {
            'winner_id': None,
            'is_tie': True,
            'reroll_players': [
                {'player_id': pid, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
                for pid in reroll_list
            ]
        }, room=room.code)


@socketio.on('setup_payouts')
def on_setup_payouts(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    if game.phase != PAYOUT_SETUP:
        return
    
    casino_bills = game.setup_payouts()
    
    emit_log(room.code, '카지노 배당금을 배치합니다.')
    
    # Send bills for each casino for animation
    payout_data = {}
    for casino_num in range(1, NUM_CASINOS + 1):
        bills = casino_bills.get(casino_num, [])
        total = sum(b.value for b in bills)
        payout_data[str(casino_num)] = {
            'bills': [b.to_dict() for b in bills],
            'total': total
        }
    
    socketio.emit('payout_setup', {'casinos': payout_data}, room=room.code)
    
    # Send turn start for first player
    current = game.get_current_player()
    if current:
        nickname = game.players[current]['nickname']
        pd = game.player_dice[current]
        remaining = pd.remaining
        emit_log(room.code, f'{nickname}님의 차례입니다.')
        socketio.emit('turn_start', {
            'player_id': current,
            'nickname': game.players[current]['nickname'],
            'color': game.players[current]['color'],
            'remaining': remaining
        }, room=room.code)


@socketio.on('roll_dice')
def on_roll_dice(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    player_id = info['player_id']
    
    if player_id != game.get_current_player():
        emit('error', {'message': '현재 차례가 아닙니다.'})
        return
    
    if game.phase != TURN_WAITING:
        emit('error', {'message': '주사위를 굴릴 수 없는 상태입니다.'})
        return
    
    results = game.do_roll()
    
    nickname = game.players[player_id]['nickname']
    emit_log(room.code, f'{nickname}님이 주사위를 굴렸습니다.')
    
    valid_casinos = game.get_valid_casinos(player_id)
    
    socketio.emit('dice_rolled', {
        'player_id': player_id,
        'results': results,
        'valid_casinos': valid_casinos,
        'nickname': game.players[player_id]['nickname'],
        'color': game.players[player_id]['color']
    }, room=room.code)
    
    game.phase = PLACEMENT_SELECTION


@socketio.on('draw_cards')
def on_draw_cards(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    player_id = info['player_id']
    
    if player_id != game.get_current_player():
        emit('error', {'message': '현재 차례가 아닙니다.'})
        return
    
    if game.phase != TURN_WAITING:
        emit('error', {'message': '카드를 뽑을 수 없는 상태입니다.'})
        return
    
    results = game.do_card_draw()
    
    nickname = game.players[player_id]['nickname']
    emit_log(room.code, f'{nickname}님이 카드를 뽑았습니다.')
    
    valid_casinos = game.get_valid_casinos(player_id)
    
    socketio.emit('cards_drawn', {
        'player_id': player_id,
        'results': results,
        'valid_casinos': valid_casinos,
        'nickname': game.players[player_id]['nickname'],
        'color': game.players[player_id]['color']
    }, room=room.code)
    
    game.phase = PLACEMENT_SELECTION


@socketio.on('get_placement_preview')
def on_get_preview(data):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    player_id = info['player_id']
    casino_number = data.get('casino', 0)
    
    if player_id != game.get_current_player():
        return
    
    preview = game.get_placement_preview(player_id, casino_number)
    
    # Add player nicknames/colors to preview
    enriched_counts = {}
    for pid, count in preview.get('resulting_counts', {}).items():
        if pid in game.players:
            enriched_counts[pid] = {
                'count': count,
                'nickname': game.players[pid]['nickname'],
                'color': game.players[pid]['color']
            }
    preview['resulting_counts'] = enriched_counts
    
    # Enrich tie players
    enriched_ties = []
    for pid in preview.get('tie_players', []):
        if pid in game.players:
            enriched_ties.append({
                'player_id': pid,
                'nickname': game.players[pid]['nickname'],
                'color': game.players[pid]['color']
            })
    preview['tie_players'] = enriched_ties
    
    emit('placement_preview', preview)


@socketio.on('confirm_placement')
def on_confirm_placement(data):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    player_id = info['player_id']
    casino_number = data.get('casino', 0)
    
    # Validate
    valid, error_msg = game.validate_placement(player_id, casino_number)
    if not valid:
        emit('error', {'message': error_msg})
        return
    
    nickname = game.players[player_id]['nickname']
    color = game.players[player_id]['color']
    
    # Do placement
    placed = game.do_placement(player_id, casino_number)
    
    emit_log(room.code, f'{nickname}님이 카지노 {casino_number}에 주사위 {placed}개를 배치했습니다.')
    
    # Get updated casino counts for ALL casinos
    all_casino_dice_enriched = {}
    for cn in range(1, 7):
        counts_for_casino = {}
        for pid, c in game.casino_dice[cn].items():
            if pid in game.players:
                counts_for_casino[pid] = {
                    'count': c,
                    'nickname': game.players[pid]['nickname'],
                    'color': game.players[pid]['color']
                }
        all_casino_dice_enriched[str(cn)] = counts_for_casino
    
    remaining = game.player_dice[player_id].remaining
    
    # Build player dice remaining for all players
    all_player_remaining = {}
    for pid in game.players:
        all_player_remaining[pid] = game.player_dice[pid].remaining
    
    socketio.emit('placement_confirmed', {
        'player_id': player_id,
        'nickname': nickname,
        'color': color,
        'casino': casino_number,
        'count': placed,
        'sequence': game.placement_sequence,
        'remaining': remaining,
        'casino_counts': all_casino_dice_enriched[str(casino_number)],
        'all_casino_dice': all_casino_dice_enriched,
        'all_player_remaining': all_player_remaining,
        'winnings': game.winnings
    }, room=room.code)
    
    # Check if player has finished
    if remaining == 0:
        emit_log(room.code, f'{nickname}님이 주사위를 모두 사용했습니다.')
        socketio.emit('player_finished', {
            'player_id': player_id,
            'nickname': nickname
        }, room=room.code)
    
    # Check game phase
    if game.phase == ROUND_COMPLETE:
        emit_log(room.code, '모든 주사위 배치가 완료되었습니다!')
        socketio.emit('round_complete', {}, room=room.code)
    elif game.phase == TURN_WAITING:
        # Next turn
        current = game.get_current_player()
        if current:
            next_nickname = game.players[current]['nickname']
            next_remaining = game.player_dice[current].remaining
            emit_log(room.code, f'{next_nickname}님의 차례입니다.')
            socketio.emit('turn_start', {
                'player_id': current,
                'nickname': game.players[current]['nickname'],
                'color': game.players[current]['color'],
                'remaining': next_remaining
            }, room=room.code)


@socketio.on('do_settlement')
def on_do_settlement(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    game = room.game
    if game.phase != ROUND_COMPLETE:
        return
    
    emit_log(room.code, '정산을 시작합니다.')
    
    results = game.do_settlement()
    
    # Send settlement results casino by casino
    settlement_data = {}
    for casino_num in range(1, NUM_CASINOS + 1):
        res = results[casino_num]
        
        enriched = settlement_to_dict(res)
        
        # Add player names to counts
        enriched_counts = {}
        for pid, count in res['counts'].items():
            if pid in game.players:
                enriched_counts[pid] = {
                    'count': count,
                    'nickname': game.players[pid]['nickname'],
                    'color': game.players[pid]['color']
                }
        enriched['counts'] = enriched_counts
        
        # Add names to ties
        enriched_ties = []
        for count_val, pids in res['ties']:
            tie_info = {
                'count': count_val,
                'players': [
                    {'player_id': pid, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
                    for pid in pids if pid in game.players
                ]
            }
            enriched_ties.append(tie_info)
        enriched['ties'] = enriched_ties
        
        # Add names to cancelled
        enriched_cancelled = [
            {'player_id': pid, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
            for pid in res['cancelled'] if pid in game.players
        ]
        enriched['cancelled'] = enriched_cancelled
        
        # Add names to eligible
        enriched_eligible = [
            {'player_id': pid, 'count': count, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
            for pid, count in res['eligible'] if pid in game.players
        ]
        enriched['eligible'] = enriched_eligible
        
        # Add names to payouts
        enriched_payouts = []
        for pid, bill in res['payouts']:
            if pid in game.players:
                enriched_payouts.append({
                    'player_id': pid,
                    'nickname': game.players[pid]['nickname'],
                    'color': game.players[pid]['color'],
                    'bill': bill.to_dict()
                })
        enriched['payouts'] = enriched_payouts
        
        settlement_data[str(casino_num)] = enriched
        
        # Log
        emit_log(room.code, f'카지노 {casino_num} 정산을 시작합니다.')
        for tie_info in enriched_ties:
            names = '과 '.join(p['nickname'] for p in tie_info['players'])
            emit_log(room.code, f'{names}이(가) {tie_info["count"]}개로 동률입니다. 무효 처리됩니다.')
        for payout in enriched_payouts:
            emit_log(room.code, f'{payout["nickname"]}님이 ${payout["bill"]["value"]:,}을 획득했습니다.')
        if not enriched_payouts and not enriched_eligible:
            emit_log(room.code, '동률로 인해 지급 대상이 없습니다.')
    
    socketio.emit('settlement_data', {
        'settlements': settlement_data,
        'winnings': game.winnings
    }, room=room.code)
    
    # Send game over
    rankings = game.get_rankings()
    winners = game.get_winner()
    
    socketio.emit('game_over', {
        'rankings': rankings,
        'winners': winners,
        'winnings': game.winnings,
        'is_joint_win': len(winners) > 1
    }, room=room.code)
    
    emit_log(room.code, '게임이 종료되었습니다!')
    for r in rankings:
        emit_log(room.code, f'{r["rank"]}위 {r["nickname"]}님 - ${r["total"]:,}')


@socketio.on('request_rematch')
def on_request_rematch(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room or not room.game:
        return
    
    if info['player_id'] != room.host_id:
        emit('error', {'message': '방장만 재시작할 수 있습니다.'})
        return
    
    game = room.game
    game.reset_for_rematch()
    
    emit_log(room.code, '새 게임을 시작합니다!')
    emit_log(room.code, '선 정하기를 시작합니다.')
    
    # New dealer roll
    rolls = game.do_dealer_roll()
    
    roll_data = {}
    for pid, roll in rolls.items():
        nickname = game.players[pid]['nickname']
        color = game.players[pid]['color']
        roll_data[pid] = {'roll': roll, 'nickname': nickname, 'color': color}
        emit_log(room.code, f'{nickname}님: {roll}')
    
    socketio.emit('rematch_started', {}, room=room.code)
    socketio.emit('dealer_roll', {'rolls': roll_data}, room=room.code)
    
    winner, reroll_list = game.resolve_dealer()
    
    if winner:
        nickname = game.players[winner]['nickname']
        emit_log(room.code, f'{nickname}님이 선입니다.')
        socketio.emit('dealer_result', {
            'winner_id': winner,
            'winner_nickname': game.players[winner]['nickname'],
            'winner_color': game.players[winner]['color'],
            'is_tie': False,
            'reroll_players': []
        }, room=room.code)
    else:
        names = ', '.join(game.players[pid]['nickname'] + '님' for pid in reroll_list)
        emit_log(room.code, f'최저 숫자가 동률입니다! {names}이 다시 굴립니다.')
        socketio.emit('dealer_result', {
            'winner_id': None,
            'is_tie': True,
            'reroll_players': [
                {'player_id': pid, 'nickname': game.players[pid]['nickname'], 'color': game.players[pid]['color']}
                for pid in reroll_list
            ]
        }, room=room.code)


@socketio.on('return_to_lobby')
def on_return_to_lobby(data=None):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room:
        return
    
    if info['player_id'] != room.host_id:
        emit('error', {'message': '방장만 로비로 돌아갈 수 있습니다.'})
        return
    
    room.game = None
    
    socketio.emit('return_to_lobby', {}, room=room.code)
    emit_room_update(room)


@socketio.on('send_reaction')
def on_send_reaction(data):
    sid = request.sid
    info = sid_to_player.get(sid)
    if not info:
        return
    
    room = room_manager.get_room(info['room_code'])
    if not room:
        return
    
    player_id = info['player_id']
    reaction_type = data.get('type', '')
    
    valid_reactions = ['ㅋㅋ', '헉', '굿', '가자!', '아깝다', '😎']
    if reaction_type not in valid_reactions:
        return
    
    nickname = ''
    color = ''
    if room.game and player_id in room.game.players:
        nickname = room.game.players[player_id]['nickname']
        color = room.game.players[player_id]['color']
    elif player_id in room.players:
        nickname = room.players[player_id]['nickname']
        color = room.players[player_id]['color']
    
    socketio.emit('reaction', {
        'player_id': player_id,
        'nickname': nickname,
        'color': color,
        'type': reaction_type
    }, room=room.code)


@socketio.on('get_available_colors')
def on_get_colors(data):
    room_code = data.get('room_code', '').strip().upper()
    room = room_manager.get_room(room_code)
    if room:
        emit('available_colors', {'colors': room.get_available_colors()})
    else:
        emit('available_colors', {'colors': PLAYER_COLORS[:]})


if __name__ == "__main__":
    lan_ip = get_lan_ip()
    
    print("\n" + "=" * 50)
    print("   카지노 나이트 - 사내 멀티플레이")
    print("=" * 50)
    print()
    print("내 PC:")
    print(f"  http://127.0.0.1:1336")
    print()
    if lan_ip and lan_ip != "127.0.0.1":
        print("사내 접속 주소:")
        print(f"  http://{lan_ip}:1336")
    else:
        print("사내 접속 주소:")
        print("  ipconfig 명령어에서 IPv4 주소를 확인해주세요.")
    print()
    print("게임 서버가 실행되었습니다.")
    print("=" * 50)
    print()
    
    socketio.run(
        app,
        host="0.0.0.0",
        port=1336,
        debug=True,
        allow_unsafe_werkzeug=True
    )
