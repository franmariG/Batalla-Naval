# server.py

import socket
import threading
import json
import time
import random
import sys

HOST = '0.0.0.0'  # Listen on all available interfaces
PORT = 6789
GRID_SIZE = 10
SHIPS_CONFIG = [ # (Name, Size)
    ("Carrier", 5), ("Battleship", 4), ("Cruiser", 3),
    ("Submarine", 3), ("Destroyer", 2)
]

# Game Room and Player Management
game_rooms = {}  # {room_id: GameRoom_instance}
next_room_id = 0
next_player_id = 0 # Global player ID to ensure uniqueness across rooms

class Player:
    def __init__(self, sock, addr, player_id):
        self.socket = sock
        self.address = addr
        self.player_id = player_id
        self.board = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] # 0=empty, 1=ship
        self.ship_coords = {} # {ship_name: [(r,c), ...]}
        self.ships_placed_count = 0
        self.is_ready = False # Ready for game to start (all ships placed)
        self.active_in_game = True # Still has ships floating
        self.ships_sunk = 0

class GameRoom:
    def __init__(self, room_id, num_players_expected):
        self.room_id = room_id
        self.num_players_expected = num_players_expected
        self.players = {}  # {player_id: Player_instance}
        self.player_threads = {} # {player_id: thread_instance}
        self.game_state = "WAITING"  # WAITING, SETUP, PLAYING, FINISHED
        self.player_turn_order = [] # List of player_ids in order of turns
        self.current_turn_idx = -1
        self.lock = threading.Lock()

    def add_player(self, player, thread):
        with self.lock:
            if len(self.players) < self.num_players_expected and self.game_state == "WAITING":
                self.players[player.player_id] = player
                self.player_threads[player.player_id] = thread
                print(f"[Room {self.room_id}] Player {player.player_id} joined. {len(self.players)}/{self.num_players_expected}")
                
                self.broadcast_wait_update()

                if len(self.players) == self.num_players_expected:
                    self.start_game_setup()
                return True
            else: # Room full or game already started
                self.send_to_player(player.player_id, {"type": "ERROR", "message": "Room is full or game in progress.", "fatal": True})
                return False
    
    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.players:
                player = self.players.pop(player_id)
                self.player_threads.pop(player_id, None)
                print(f"[Room {self.room_id}] Player {player_id} disconnected/left.")

                if self.game_state != "WAITING" and self.game_state != "FINISHED":
                    # Player disconnected mid-game
                    player.active_in_game = False # Mark as inactive
                    self.broadcast({"type": "PLAYER_DEFEATED", "player_id": player_id, "reason": "disconnected"})
                    
                    # Check if this ends the game
                    active_players_left = [p for p in self.players.values() if p.active_in_game]
                    if len(active_players_left) <= 1:
                        winner = active_players_left[0].player_id if active_players_left else None
                        self.end_game(winner)
                    elif self.player_turn_order[self.current_turn_idx] == player_id: # If it was their turn
                        self.next_turn() # Advance turn
                
                elif self.game_state == "WAITING": # Player left before game start
                    self.broadcast_wait_update() # Update remaining players
                
                # If room becomes empty, it could be cleaned up by main server thread (optional)
            # else:
                # print(f"[Room {self.room_id}] Attempted to remove non-existent player {player_id}")


    def broadcast_wait_update(self):
        for p_id, player_obj in self.players.items():
            self.send_to_player(p_id, {
                "type": "WAIT_UPDATE",
                "your_id": p_id,
                "current_players": len(self.players),
                "expected_players": self.num_players_expected
            })

    def start_game_setup(self):
        self.game_state = "SETUP"
        self.player_turn_order = list(self.players.keys())
        random.shuffle(self.player_turn_order)
        print(f"[Room {self.room_id}] Starting setup. Turn order: {self.player_turn_order}")

        all_pids = list(self.players.keys())
        for p_id in self.players:
            self.send_to_player(p_id, {
                "type": "GAME_START",
                "your_id": p_id,
                "all_player_ids": all_pids, # All players in the game
                "player_turn_order": self.player_turn_order # For client info if needed
            })
            # Client will implicitly go to SETUP_SHIPS state from this
    
    def handle_place_ship(self, player_id, data):
        with self.lock:
            if self.game_state != "SETUP" or player_id not in self.players:
                return
            
            player = self.players[player_id]
            if player.ships_placed_count >= len(SHIPS_CONFIG):
                self.send_to_player(player_id, {"type": "SHIP_PLACEMENT_INVALID", "player_id": player_id, "reason": "All ships already placed."})
                return

            ship_name = data['ship_name']
            ship_size = data['size']
            row, col = data['row'], data['col']
            orientation = data['orientation']

            # Validate placement (bounds, overlap)
            temp_ship_coords = []
            valid = True
            for i in range(ship_size):
                r, c = row, col
                if orientation == 'H': c += i
                else: r += i

                if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE):
                    valid = False; break
                if player.board[r][c] == 1: # Overlap
                    valid = False; break
                temp_ship_coords.append((r, c))
            
            if valid:
                for r, c in temp_ship_coords:
                    player.board[r][c] = 1 # Mark as ship
                player.ship_coords[ship_name] = temp_ship_coords
                player.ships_placed_count += 1
                self.send_to_player(player_id, {"type": "SHIP_PLACEMENT_SUCCESS", "player_id": player_id, "ship_coords": temp_ship_coords})
                
                # print(f"[Room {self.room_id}] Player {player_id} placed {ship_name}")
                # Player client will send "FINISH_SETUP" when they are done with all ships.
            else:
                self.send_to_player(player_id, {"type": "SHIP_PLACEMENT_INVALID", "player_id": player_id, "reason": "Invalid position (bounds or overlap)."})

    def handle_finish_setup(self, player_id):
        with self.lock:
            if player_id not in self.players or self.game_state != "SETUP": return
            
            player = self.players[player_id]
            if player.ships_placed_count < len(SHIPS_CONFIG):
                self.send_to_player(player_id, {"type": "ERROR", "message": "Not all ships placed yet."})
                return

            player.is_ready = True
            print(f"[Room {self.room_id}] Player {player_id} finished setup.")

            # Check if all players are ready
            if all(p.is_ready for p in self.players.values()):
                self.start_playing_phase()

    def start_playing_phase(self):
        self.game_state = "PLAYING"
        self.current_turn_idx = 0
        print(f"[Room {self.room_id}] All players ready. Starting game. First turn: {self.player_turn_order[self.current_turn_idx]}")
        self.broadcast_turn_info()

    def broadcast_turn_info(self):
        if self.game_state != "PLAYING" or self.current_turn_idx == -1: return

        current_player_id_turn = self.player_turn_order[self.current_turn_idx]
        self.broadcast({"type": "UPDATE_TURN", "player_id_turn": current_player_id_turn})
        print(f"[Room {self.room_id}] Turn: Player {current_player_id_turn}")

    def handle_attack(self, attacker_id, data):
        with self.lock:
            if self.game_state != "PLAYING" or attacker_id != self.player_turn_order[self.current_turn_idx]:
                self.send_to_player(attacker_id, {"type": "ERROR", "message": "Not your turn or game not active."})
                return

            target_player_id = data['target_player_id']
            row, col = data['row'], data['col']

            if target_player_id not in self.players or not self.players[target_player_id].active_in_game:
                self.send_to_player(attacker_id, {"type": "ERROR", "message": "Invalid target player."})
                return
            
            if target_player_id == attacker_id:
                self.send_to_player(attacker_id, {"type": "ERROR", "message": "Cannot attack yourself."})
                return

            target_player = self.players[target_player_id]
            
            # Check if already attacked this cell (optional, client should prevent but server validates)
            # For simplicity, we'll allow re-attacking but it's usually a wasted turn.
            # Client board state will show hit/miss.

            result_type = "MISS"
            sunk_ship_details = None

            if target_player.board[row][col] == 1: # It's a hit on a ship part
                target_player.board[row][col] = 2 # Mark as hit (server-side, 2 could mean 'hit ship part')
                result_type = "HIT"
                
                # Check if this hit sunk a ship
                for ship_name, coords in target_player.ship_coords.items():
                    if (row, col) in coords: # This hit is part of this ship
                        is_sunk = True
                        for r_ship, c_ship in coords:
                            if target_player.board[r_ship][c_ship] == 1: # Still a floating part
                                is_sunk = False
                                break
                        if is_sunk:
                            result_type = "SUNK"
                            target_player.ships_sunk += 1
                            sunk_ship_details = {"name": ship_name, "coords": coords}
                            print(f"[Room {self.room_id}] Player {attacker_id} SUNK {ship_name} of Player {target_player_id}")
                            break 
            
            # elif target_player.board[row][col] == 0: # Miss on empty water
                # target_player.board[row][col] = 3 # Mark as miss (server-side, 3 could mean 'missed water')
            
            # Broadcast result
            attack_msg = {
                "type": "ATTACK_RESULT",
                "attacker_id": attacker_id,
                "target_player_id": target_player_id,
                "row": row, "col": col,
                "result": result_type
            }
            if sunk_ship_details:
                attack_msg["sunk_ship_name"] = sunk_ship_details["name"]
                attack_msg["sunk_ship_coords"] = sunk_ship_details["coords"]
            self.broadcast(attack_msg)

            print(f"[Room {self.room_id}] Player {attacker_id} attacks Player {target_player_id} at ({row},{col}): {result_type}")

            # Check if target player is defeated
            if result_type == "SUNK" and target_player.ships_sunk == len(SHIPS_CONFIG):
                target_player.active_in_game = False
                self.broadcast({"type": "PLAYER_DEFEATED", "player_id": target_player_id})
                print(f"[Room {self.room_id}] Player {target_player_id} has been defeated.")

                # Check for game over
                active_players_left = [p for p in self.players.values() if p.active_in_game]
                if len(active_players_left) <= 1:
                    winner = active_players_left[0].player_id if active_players_left else None # Winner or draw
                    self.end_game(winner)
                    return # Game ended, no next turn

            # If game not over, proceed to next turn
            self.next_turn()

    def next_turn(self):
        if self.game_state != "PLAYING": return

        # Find next active player
        num_total_players = len(self.player_turn_order)
        for i in range(1, num_total_players + 1):
            next_idx = (self.current_turn_idx + i) % num_total_players
            next_player_id = self.player_turn_order[next_idx]
            if self.players[next_player_id].active_in_game:
                self.current_turn_idx = next_idx
                self.broadcast_turn_info()
                return
        
        # Should not happen if game over condition is checked correctly before calling next_turn
        print(f"[Room {self.room_id}] Error: Could not find next active player for turn.")
        self.end_game(None) # No winner, something went wrong

    def end_game(self, winner_id):
        self.game_state = "FINISHED"
        self.broadcast({"type": "GAME_OVER", "winner_id": winner_id})
        print(f"[Room {self.room_id}] Game Over. Winner: {winner_id if winner_id is not None else 'Draw/None'}")
        # Optionally, close all player sockets in this room after a delay or message.
        # For now, clients will disconnect or menu will take over. Room can be cleaned up.

    def broadcast(self, message_dict, exclude_player_id=None):
        message_json = json.dumps(message_dict) + '\n'
        for p_id, player_obj in self.players.items():
            if p_id != exclude_player_id:
                try:
                    player_obj.socket.sendall(message_json.encode('utf-8'))
                except socket.error as e:
                    print(f"Error broadcasting to Player {p_id}: {e}")
                    # self.remove_player(p_id) # Consider removing on send error

    def send_to_player(self, player_id, message_dict):
        if player_id in self.players:
            message_json = json.dumps(message_dict) + '\n'
            try:
                self.players[player_id].socket.sendall(message_json.encode('utf-8'))
            except socket.error as e:
                print(f"Error sending to Player {player_id}: {e}")
                # self.remove_player(player_id)

# --- Client Handler Thread ---
def client_thread_function(client_socket, client_address):
    global next_player_id, game_rooms, next_room_id
    
    current_player_id = -1
    current_room = None
    player_obj = None

    try:
        # Initial message from client: JOIN_GAME
        initial_data = client_socket.recv(1024).decode('utf-8').strip()
        if not initial_data:
            print(f"No initial data from {client_address}. Closing.")
            client_socket.close()
            return
            
        msg = json.loads(initial_data)
        
        if msg['type'] == 'JOIN_GAME':
            mode = msg['mode'] # 2 or 4
            
            with threading.Lock(): # Protect global next_player_id and room assignment
                current_player_id = next_player_id
                next_player_id += 1
                player_obj = Player(client_socket, client_address, current_player_id)

                # Find or create a room for this mode
                found_room = False
                for room in game_rooms.values():
                    if room.num_players_expected == mode and len(room.players) < mode and room.game_state == "WAITING":
                        current_room = room
                        found_room = True
                        break
                
                if not found_room:
                    room_id = f"room_{next_room_id}"
                    next_room_id += 1
                    current_room = GameRoom(room_id, mode)
                    game_rooms[room_id] = current_room
                
            if not current_room.add_player(player_obj, threading.current_thread()):
                # Failed to add player (e.g. room became full just as we checked)
                print(f"Failed to add Player {current_player_id} to room. Closing connection.")
                client_socket.close()
                return
        else:
            print(f"Unexpected initial message from {client_address}: {msg}. Closing.")
            client_socket.close()
            return

        # Main loop for this client
        socket_buffer = ""
        while True:
            try:
                data = client_socket.recv(2048)
                if not data: # Connection closed by client
                    break 
                
                socket_buffer += data.decode('utf-8')
                
                while '\n' in socket_buffer:
                    message_json, socket_buffer = socket_buffer.split('\n', 1)
                    if message_json:
                        client_msg = json.loads(message_json)
                        # print(f"SERVER RECV from P{current_player_id}: {client_msg}") # Debug

                        if client_msg["type"] == "PLACE_SHIP":
                            current_room.handle_place_ship(current_player_id, client_msg)
                        elif client_msg["type"] == "FINISH_SETUP":
                            current_room.handle_finish_setup(current_player_id)
                        elif client_msg["type"] == "ATTACK":
                            current_room.handle_attack(current_player_id, client_msg)
                        elif client_msg["type"] == "LEAVE_GAME":
                            print(f"Player {current_player_id} explicitly sent LEAVE_GAME.")
                            raise ConnectionResetError # Treat as disconnect
                        # Add other message types as needed

            except BlockingIOError: # Should not happen with blocking sockets in thread
                time.sleep(0.01) # Just in case, though unlikely
                continue
            except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError):
                print(f"Player {current_player_id} ({client_address}) disconnected.")
                break
            except json.JSONDecodeError:
                print(f"Invalid JSON from Player {current_player_id}: '{message_json[:100]}...'") # Print first 100 chars
                socket_buffer = "" # Clear buffer to prevent re-parsing bad data
            except Exception as e:
                print(f"Error processing message from Player {current_player_id}: {e}")
                import traceback
                traceback.print_exc()
                break # Critical error with this client's messages

    finally:
        if current_room and current_player_id != -1:
            current_room.remove_player(current_player_id)
        
        # Clean up empty finished rooms (optional, could be a periodic task)
        if current_room and not current_room.players and current_room.game_state == "FINISHED":
            with threading.Lock(): # Protect game_rooms dictionary
                if current_room.room_id in game_rooms and not game_rooms[current_room.room_id].players:
                    print(f"Cleaning up empty finished room: {current_room.room_id}")
                    del game_rooms[current_room.room_id]
        
        client_socket.close()
        print(f"Closed connection for Player {current_player_id} from {client_address}")


# --- Main Server Execution ---
if __name__ == "__main__":
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow reusing address quickly
    try:
        server_socket.bind((HOST, PORT))
    except socket.error as e:
        print(f"Error binding server socket: {e}")
        sys.exit(1)
    
    server_socket.listen(5) # Max queued connections
    print(f"Server listening on {HOST}:{PORT}")

    try:
        while True:
            client_sock, client_addr = server_socket.accept()
            # client_sock.setblocking(True) # Sockets are blocking by default
            print(f"Accepted connection from {client_addr}")
            
            thread = threading.Thread(target=client_thread_function, args=(client_sock, client_addr))
            thread.daemon = True # Allow main program to exit even if threads are running
            thread.start()
            # Note: We don't store the main thread objects here unless we need to join() them,
            # but player_threads in GameRoom stores them for specific players.
    except KeyboardInterrupt:
        print("Server shutting down...")
    finally:
        for room_id, room in list(game_rooms.items()): # Iterate over a copy for safe deletion
            room.broadcast({"type": "SERVER_SHUTDOWN", "message": "Server is shutting down."})
            # Give a moment for messages to go out
            time.sleep(0.2)
            for p_id, player in list(room.players.items()): # Iterate over a copy
                player.socket.close()
            # Optionally clear rooms more explicitly if needed
            if room_id in game_rooms: del game_rooms[room_id]

        server_socket.close()
        print("Server socket closed.")