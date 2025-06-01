# server.py
import socket
import threading
import time
import uuid

HOST = "169.254.107.4" # Escucha en todas las interfaces de red disponibles
PORT = 8080

# --- Estado Global del Servidor ---
active_games = {}
games_lock = threading.Lock() # Lock para proteger el diccionario active_games

# --- Funciones de Notificación ---
def notify_players_in_game(game, message_bytes, exclude_player_id=None):
    """Notifica a todos los jugadores en una partida específica."""
    with game['lock']:
        for pid, player_info in game['clients'].items():
            if pid != exclude_player_id and player_info.get('conn'):
                try:
                    player_info['conn'].sendall(message_bytes)
                except Exception as e:
                    print(f"[GAME {game['game_id']}] Error notificando a {pid}: {e}")

# --- Lógica de Juego Separada ---

def process_2p_logic(game, player_id, command, parts):
    """Procesa la lógica para un juego de 2 jugadores."""
    conn = game['clients'][player_id]['conn']
    
    if command == "READY_SETUP":
        game['game_state']['player_setup_complete'][player_id] = True
        notify_players_in_game(game, f"MSG El oponente ha colocado sus barcos.\n".encode(), player_id)
        
        is_p1_ready = game['game_state']['player_setup_complete'].get("P1", False)
        is_p2_ready = game['game_state']['player_setup_complete'].get("P2", False)

        if is_p1_ready and is_p2_ready and not game['game_state']['game_active']:
            game['game_state']['game_active'] = True
            game['game_state']['current_turn_player_id'] = "P1"
            start_msg = f"START_GAME P1\n".encode()
            notify_players_in_game(game, start_msg)
            print(f"[GAME {game['game_id']}] Partida iniciada. Turno para P1.")

    elif command == "SHOT":
        if game['game_state']['current_turn_player_id'] != player_id:
            conn.sendall(b"MSG No es tu turno.\n")
            return
        r, c = parts[1], parts[2]
        shot_data = f"SHOT {r} {c}\n".encode()
        notify_players_in_game(game, shot_data, player_id)

    elif command == "RESULT":
        r, c, result = parts[1], parts[2], parts[3]
        original_shooter_id = "P2" if player_id == "P1" else "P1"
        
        update_msg = f"UPDATE {r} {c} {result}\n".encode()
        notify_players_in_game(game, update_msg, player_id) # Enviar a P1

        if result == 'H':
            game['game_state']['current_turn_player_id'] = original_shooter_id
        else:
            game['game_state']['current_turn_player_id'] = player_id
        
        turn_msg = f"TURN {game['game_state']['current_turn_player_id']}\n".encode()
        notify_players_in_game(game, turn_msg)

    elif command == "I_SUNK_MY_SHIP":
        # Notificar al otro jugador que hundió un barco
        payload = " ".join(parts[1:])
        sunk_msg = f"OPPONENT_SHIP_SUNK {payload}\n".encode()
        notify_players_in_game(game, sunk_msg, player_id)

    elif command == "GAME_WON":
        if game['game_state']['game_active']:
            game['game_state']['game_active'] = False
            loser_id = "P2" if player_id == "P1" else "P1"
            notify_players_in_game(game, b"GAME_OVER WIN\n", exclude_player_id=loser_id)
            notify_players_in_game(game, b"GAME_OVER LOSE\n", exclude_player_id=player_id)
            print(f"[GAME {game['game_id']}] Partida finalizada. Ganador: {player_id}")
            # El juego se eliminará cuando los jugadores se desconecten

def process_4p_logic(game, player_id, command, parts):
    """Procesa la lógica para un juego de 4 jugadores."""
    conn = game['clients'][player_id]['conn']

    if command == "TEAM_NAME_IS" and player_id in ("P1", "P3"):
        team_name = parts[1].strip()
        team_id = game['game_state']['player_teams'][player_id]
        game['game_state']['team_details'][team_id]['name'] = team_name
        print(f"[GAME {game['game_id']}] Equipo {team_id} nombrado: {team_name}")
        
        # Chequear si ambos nombres están listos
        team_a_name = game['game_state']['team_details']['TeamA']['name']
        team_b_name = game['game_state']['team_details']['TeamB']['name']
        if team_a_name and team_b_name:
            # Enviar información final a todos
            for pid_notify in game['clients']:
                my_team_id = game['game_state']['player_teams'][pid_notify]
                my_team_name = game['game_state']['team_details'][my_team_id]['name']
                opp_team_id = "TeamB" if my_team_id == "TeamA" else "TeamA"
                opp_team_name = game['game_state']['team_details'][opp_team_id]['name']
                opp_members = " ".join(game['game_state']['team_members_map'][opp_team_id])
                
                info_msg = f"TEAMS_INFO_FINAL {my_team_name.replace(' ','_')} {opp_team_name.replace(' ','_')} {opp_members}\n".encode()
                game['clients'][pid_notify]['conn'].sendall(info_msg)
            
            # Mandar a configurar a los capitanes
            # Por esto (para enviar solo a P1 y P3):
            if "P1" in game['clients'] and game['clients']['P1'].get('conn'):
                try:
                    game['clients']['P1']['conn'].sendall(b"SETUP_YOUR_BOARD\n")
                    print(f"[GAME {game['game_id']}] Sent SETUP_YOUR_BOARD to P1")
                except Exception as e:
                    print(f"[GAME {game['game_id']}] Error sending SETUP_YOUR_BOARD to P1: {e}")

            if "P3" in game['clients'] and game['clients']['P3'].get('conn'):
                try:
                    game['clients']['P3']['conn'].sendall(b"SETUP_YOUR_BOARD\n")
                    print(f"[GAME {game['game_id']}] Sent SETUP_YOUR_BOARD to P3")
                except Exception as e:
                    print(f"[GAME {game['game_id']}] Error sending SETUP_YOUR_BOARD to P3: {e}")

    # Añade un nuevo `elif` para este comando:
    elif command == "CAPTAIN_BOARD_DATA" and player_id in ("P1", "P3"):
        board_payload = " ".join(parts[1:])
        game['game_state']['captain_boards'][player_id] = board_payload
        print(f"[GAME {game['game_id']}] Received CAPTAIN_BOARD_DATA from {player_id}")
        # No es necesario notificar al compañero aquí mismo, se hará cuando el capitán envíe READY_SETUP.
    
   # Modifica el `elif` existente para "READY_SETUP" en `process_4p_logic`:
    elif command == "READY_SETUP": # Ya no solo P1 y P3, sino cualquiera de los 4.
        game['game_state']['player_setup_complete'][player_id] = True

        # Notificación de que el jugador está listo
        print(f"[GAME {game['game_id']}] Player {player_id} sent READY_SETUP. player_setup_complete: {game['game_state']['player_setup_complete']}")

        # Si el que envía READY_SETUP es un capitán (P1 o P3), enviar su tablero a su compañero (P2 o P4)
        if player_id == "P1" or player_id == "P3":
            teammate_id = "P2" if player_id == "P1" else "P4"
            team_id = game['game_state']['player_teams'][player_id]
            team_name = game['game_state']['team_details'][team_id]['name']
            notify_players_in_game(game, f"MSG El capitan de {team_name} ({player_id}) ha colocado sus barcos.\n".encode(), player_id)


            if teammate_id in game['clients'] and game['clients'][teammate_id].get('conn'):
                if player_id in game['game_state'].get('captain_boards', {}):
                    board_data_to_send = game['game_state']['captain_boards'][player_id]
                    try:
                        game['clients'][teammate_id]['conn'].sendall(f"TEAM_BOARD {board_data_to_send}\n".encode())
                        print(f"[GAME {game['game_id']}] Sent TEAM_BOARD from {player_id} to {teammate_id}")
                    except Exception as e:
                        print(f"[GAME {game['game_id']}] Error sending TEAM_BOARD to {teammate_id}: {e}")
                else:
                    print(f"[GAME {game['game_id']}] WARNING: No board data found for captain {player_id} to send to {teammate_id}")
        else: # P2 o P4 enviaron READY_SETUP (después de recibir TEAM_BOARD)
            notify_players_in_game(game, f"MSG Jugador {player_id} ha confirmado su tablero de equipo.\n".encode(), player_id)


        # Comprobar si TODOS los 4 jugadores están listos para iniciar el juego
        all_players_ready = all(game['game_state']['player_setup_complete'].get(p_id, False) for p_id in ["P1", "P2", "P3", "P4"])

        if all_players_ready and not game['game_state']['game_active']:
            game['game_state']['game_active'] = True
            game['game_state']['current_turn_index'] = 0 # turn_order = ["P1", "P3", "P2", "P4"] [cite: 69]
            turn_player = game['game_state']['turn_order'][0]
            game['game_state']['current_turn_player_id'] = turn_player

            start_msg = f"START_GAME {turn_player}\n".encode() # [cite: 45]
            notify_players_in_game(game, start_msg)
            print(f"[GAME {game['game_id']}] Partida 4P iniciada. Turno para {turn_player}.") # [cite: 46]

    elif command == "SHOT":
        if game['game_state']['current_turn_player_id'] != player_id:
            conn.sendall(b"MSG No es tu turno.\n")
            return
            
        target_id, r, c = parts[1], parts[2], parts[3]
        game['game_state']['last_shot_details'][target_id] = player_id
        
        if target_id in game['clients']:
            shot_data = f"SHOT {r} {c}\n".encode()
            game['clients'][target_id]['conn'].sendall(shot_data)

    elif command == "RESULT":
        r, c, result = parts[1], parts[2], parts[3]
        original_shooter_id = game['game_state']['last_shot_details'].get(player_id)
        
        if original_shooter_id:
            update_msg = f"UPDATE {player_id} {r} {c} {result}\n".encode()
            notify_players_in_game(game, update_msg)
            
            if result != 'H':
                current_idx = game['game_state']['current_turn_index']
                new_idx = (current_idx + 1) % game['max_players']
                game['game_state']['current_turn_index'] = new_idx
                game['game_state']['current_turn_player_id'] = game['game_state']['turn_order'][new_idx]
            else: # Hit, el turno no cambia
                game['game_state']['current_turn_player_id'] = original_shooter_id
            
            turn_msg = f"TURN {game['game_state']['current_turn_player_id']}\n".encode()
            notify_players_in_game(game, turn_msg)
    
    # ... Lógica para I_SUNK_MY_SHIP y GAME_WON de 4P ...
    elif command == "I_SUNK_MY_SHIP":
        # Notificar al equipo del tirador que hundió un barco
        original_shooter_id = game['game_state']['last_shot_details'].get(player_id)
        if not original_shooter_id: return
        
        shooter_team = game['game_state']['player_teams'][original_shooter_id]
        members_to_notify = game['game_state']['team_members_map'][shooter_team]
        
        payload = " ".join(parts[1:])
        sunk_msg = f"OPPONENT_SHIP_SUNK {player_id} {payload}\n".encode()
        for member_id in members_to_notify:
             if member_id in game['clients']:
                game['clients'][member_id]['conn'].sendall(sunk_msg)

    elif command == "GAME_WON":
        if game['game_state']['game_active']:
            game['game_state']['game_active'] = False
            winning_team_id = game['game_state']['player_teams'][player_id]
            winners = game['game_state']['team_members_map'][winning_team_id]
            losers = game['game_state']['team_members_map']["TeamB" if winning_team_id == "TeamA" else "TeamA"]

            for p_id in winners:
                if p_id in game['clients']: game['clients'][p_id]['conn'].sendall(b"GAME_OVER WIN\n")
            for p_id in losers:
                if p_id in game['clients']: game['clients'][p_id]['conn'].sendall(b"GAME_OVER LOSE\n")
            
            print(f"[GAME {game['game_id']}] Partida 4P finalizada. Ganador: Equipo {winning_team_id}")


# --- Hilo Principal para un Jugador en una Partida ---

def handle_player_in_game(conn, game_id, player_id):
    """Bucle de escucha para un jugador que ya está en una partida."""
    game = active_games[game_id]
    print(f"[GAME {game_id}] Jugador {player_id} ({game['clients'][player_id]['addr']}) entró al bucle de juego.")

    try:
        # Si es 4P, P1 y P3 deben mandar el nombre del equipo
        if game['game_type'] == '4P' and player_id in ('P1', 'P3'):
            conn.sendall(b'REQUEST_TEAM_NAME\n')
        
        while True:
            data_bytes = conn.recv(1024)
            if not data_bytes:
                break
            
            message = data_bytes.decode().strip()
            if not message:
                continue

            parts = message.split()
            command = parts[0]
            
            # Usar el lock de la partida para procesar el comando
            with game['lock']:
                if game['game_type'] == '2P':
                    process_2p_logic(game, player_id, command, parts)
                elif game['game_type'] == '4P':
                    process_4p_logic(game, player_id, command, parts)

    except Exception as e:
        print(f"[GAME {game_id}] Error con el jugador {player_id}: {e}")
    finally:
        print(f"[GAME {game_id}] Jugador {player_id} desconectado.")
        
        with games_lock:
            if game_id in active_games:
                game = active_games[game_id]
                with game['lock']:
                    # Notificar a los demás que el jugador se fue
                    if game['game_state'].get('game_active', False):
                        notify_players_in_game(game, b"OPPONENT_LEFT\n", player_id)
                        game['game_state']['game_active'] = False

                    # Eliminar al jugador de la partida
                    if player_id in game['clients']:
                        del game['clients'][player_id]
                    
                    # Si no quedan jugadores, eliminar la partida
                    if not game['clients']:
                        del active_games[game_id]
                        print(f"[SYSTEM] Partida {game_id} cerrada por no tener jugadores.")

# --- Gestión de Conexiones Nuevas (Lobby) ---

def handle_lobby_connection(conn, addr):
    """Maneja la primera conexión de un cliente para listar, crear o unirse a una partida."""
    try:
        request = conn.recv(1024).decode().strip()
        parts = request.split()
        command = parts[0]

        if command == "LIST_GAMES":
            with games_lock:
                available_games = []
                for gid, game in active_games.items():
                    # Solo listar partidas que no estén llenas
                    if len(game['clients']) < game['max_players']:
                        game_info = f"{gid}|{game.get('game_name','Partida sin nombre')}|{game['game_type']}|{len(game['clients'])}|{game['max_players']}"
                        available_games.append(game_info)
                response = "GAMES_LIST " + ";".join(available_games)
                conn.sendall(response.encode())
            conn.close()

        elif command == "CREATE_GAME":
            game_type = parts[1] # 2P o 4P
            game_name = " ".join(parts[2:])
            game_id = str(uuid.uuid4())[:6]

            # Crear el estado inicial según el tipo de juego
            initial_game_state = {}
            if game_type == '2P':
                initial_game_state = {
                    "player_setup_complete": {"P1": False, "P2": False},
                    "game_active": False,
                    "current_turn_player_id": None
                }
            elif game_type == '4P':
                initial_game_state = {
                    "player_setup_complete": {p: False for p in ["P1", "P2", "P3", "P4"]},
                    "game_active": False,
                    "player_teams": {"P1": "TeamA", "P2": "TeamA", "P3": "TeamB", "P4": "TeamB"},
                    "team_members_map": {"TeamA": ["P1", "P2"], "TeamB": ["P3", "P4"]},
                    "turn_order": ["P1", "P3", "P2", "P4"],
                    "current_turn_index": 0,
                    "current_turn_player_id": None,
                    "last_shot_details": {},
                    "team_details": {
                        "TeamA": {"name": None, "captain": "P1"},
                        "TeamB": {"name": None, "captain": "P3"}
                    },
                    "captain_boards": {} # <--- AÑADIR ESTA LÍNEA
                }

            new_game = {
                "game_id": game_id,
                "game_type": game_type,
                "max_players": 2 if game_type == '2P' else 4,
                "game_name": game_name,
                "clients": {},
                "game_state": initial_game_state,
                "lock": threading.Lock()
            }

            with games_lock:
                active_games[game_id] = new_game
            
            # Unir al creador a la partida
            join_game_logic(conn, addr, game_id)

        elif command == "JOIN_GAME":
            game_id = parts[1]
            join_game_logic(conn, addr, game_id)

    except Exception as e:
        print(f"Error en el lobby con {addr}: {e}")
        conn.close()

def join_game_logic(conn, addr, game_id):
    with games_lock:
        if game_id not in active_games:
            conn.sendall(b"ERROR Game not found\n")
            conn.close()
            return

        game = active_games[game_id]
        
        with game['lock']:
            if len(game['clients']) >= game['max_players']:
                conn.sendall(b"ERROR Game is full\n")
                conn.close()
                return

            # Asignar el siguiente ID de jugador disponible
            player_id = ""
            for i in range(1, game['max_players'] + 1):
                pid_candidate = f"P{i}"
                if pid_candidate not in game['clients']:
                    player_id = pid_candidate
                    break
            
            game['clients'][player_id] = {'conn': conn, 'addr': addr}
            
            # Enviar al jugador su ID y el tipo de juego
            conn.sendall(f"JOIN_SUCCESS {player_id} {game['game_type']}\n".encode())
            print(f"Jugador {addr} se unió a la partida {game_id} como {player_id}.")

            # Si la partida se llena, notificar a todos para que empiecen
            if len(game['clients']) == game['max_players']:
                notify_players_in_game(game, f"MSG Todos los jugadores ({game['max_players']}) se han conectado. Preparando partida...\n".encode())

    # Iniciar el hilo de juego para este jugador
    thread = threading.Thread(target=handle_player_in_game, args=(conn, game_id, player_id), daemon=True)
    thread.start()


# --- Bucle Principal del Servidor ---
def start_server():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(10)
    print(f"Servidor unificado de Batalla Naval escuchando en {HOST}:{PORT}")

    while True:
        try:
            conn, addr = server_socket.accept()
            print(f"Nueva conexión del lobby: {addr}")
            # Cada nueva conexión se maneja en el lobby primero
            lobby_thread = threading.Thread(target=handle_lobby_connection, args=(conn, addr), daemon=True)
            lobby_thread.start()
        except Exception as e:
            print(f"Error aceptando conexiones: {e}")
            break

if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        while server_thread.is_alive():
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor (Ctrl+C)...")
    finally:
        print("Servidor principal finalizando.")