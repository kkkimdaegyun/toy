# Number Code

Number Code is an original, real-time LAN board game for 2–4 players. Players see the colours of every tile but only their own hidden numbers. Take turns guessing opponents’ tiles and be the last player with an unrevealed tile.

It uses one Python server, Flask, Flask-SocketIO, vanilla HTML/CSS/JavaScript, and no runtime internet services. It is not affiliated with any commercial board-game brand.

## Install and run (Windows)

From this folder, install the host-only dependencies once:

```powershell
py -m pip install -r requirements.txt
```

Then always start the game with exactly:

```powershell
py app.py
```

The terminal prints both `http://127.0.0.1:5000` and, when detected, a LAN address such as `http://192.168.0.32:5000`. Open the LAN address on the host or send it to coworkers on the same network. Everyone else only needs Chrome or Edge.

If the LAN address is not printed, run `ipconfig` and use the IPv4 Address for the active network adapter with port `5000`.

## How to play

1. Enter a nickname and create a room.
2. Copy the invite link and have 1–3 coworkers join it.
3. The host starts the match. Each player receives four tiles and the first player immediately draws a fifth tile.
4. On your turn, select a hidden opponent tile, choose 0–11, and confirm the guess.
5. A correct guess reveals that opponent tile. Continue guessing or end your turn to keep your drawn tile hidden.
6. A wrong guess reveals the tile you drew and advances the turn. If the deck is empty, a random unrevealed tile belonging to the guessing player is revealed instead.
7. A player is eliminated when all their tiles are revealed. The final remaining player wins.

The host can start another round with the same players or return the room to its lobby after a match.

## Privacy and real-time design

The Python server owns the deck, turn order, tile values, guesses, reveals, elimination, and winning state. Browsers send only intentions. Every Socket.IO state update is generated separately for its recipient:

- Your tiles include values, whether revealed or not.
- Opponent tiles include values only after those tiles are publically revealed.
- No full room/game object is broadcast to every browser.

A browser refresh reconnects its saved player using a server-issued token in `localStorage`. A disconnected current player pauses the game until that player returns; reconnecting does not draw another tile.

## Project structure

```text
app.py                 Flask app and Socket.IO handlers
game/models.py         Tile, player, and room data models
game/engine.py         Server-authoritative rules and sanitized views
game/rooms.py          Room, nickname, socket, and reconnect management
game/utils.py          Sorting and LAN IPv4 detection helpers
templates/index.html   Single-page game shell
static/css/style.css   Offline board-game visual design
static/js/*.js         Socket connection, UI state, and board rendering
tests/test_engine.py   Rule, reset, and privacy tests
```

## Testing

Run the core rules tests with:

```powershell
py -m unittest discover -s tests -v
```

The tests cover tile creation/uniqueness, colour ordering, deals, correct and incorrect guesses, drawn-tile penalties, voluntary end turns, turn skipping, elimination, winner detection, game reset, and hidden opponent-value sanitization.

## LAN troubleshooting

Windows Defender Firewall may ask to allow Python to communicate on networks. Allow it on **Private networks** when appropriate for your company environment. If coworkers cannot open the invite link, check that they are on the same LAN, the displayed IPv4 address and port are correct, firewall rules allow Python/port 5000, and the company network does not use client isolation.

This is an in-memory private-network MVP: rooms are lost if the server restarts, there is no permanent leave/remove flow, and there is no turn timer. It intentionally keeps disconnected players and pauses their active turn so a refresh cannot change game state.
