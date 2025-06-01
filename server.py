# server.py
import socket
import threading
import time

HOST = "169.254.107.4"
PORT = 8080
MAX_PLAYERS = 4

# --- Estado del Servidor ---
clients = {}  # {'P1': {...}, ...}
player_setup_complete = {"P1": False, "P2": False, "P3": False, "P4": False}
game_active = False
turn_lock = threading.Lock()

# Equipos y turnos
player_teams = {"P1": "TeamA", "P2": "TeamA", "P3": "TeamB", "P4": "TeamB"}
team_members = {"TeamA": ["P1", "P2"], "TeamB": ["P3", "P4"]}
turn_order = ["P1", "P3", "P2", "P4"]
current_turn_index = 0
current_turn_player_id = None

last_shot_details = {}  # {"P3": "P1"} significa que P1 disparó a P3

def get_player_team(player_id):
    return player_teams.get(player_id)

def get_opposing_team_members(player_id):
    sender_team = get_player_team(player_id)
    return [pid for tid, members in team_members.items() if tid != sender_team for pid in members]

def notify_players(message_bytes, target_player_ids=None, exclude_player_id=None):
    ids = target_player_ids if target_player_ids else list(clients.keys())
    for pid in ids:
        if pid == exclude_player_id:
            continue
        if pid in clients and clients[pid].get('conn'):
            try:
                clients[pid]['conn'].sendall(message_bytes)
            except Exception as e:
                print(f"Error notifying {pid}: {e}")

def handle_client_connection(conn, player_id, initial_bytes=None):
    global game_active, current_turn_player_id, player_setup_complete, clients, current_turn_index, last_shot_details
    print(f"Jugador {player_id} ({clients[player_id]['addr']}) conectado.")
    try:
        # ELIMINA el bloque try/except que leía con timeout.
        # Lo reemplazamos con el procesamiento del 'initial_bytes' que recibimos.

        # NUEVO BLOQUE para procesar los bytes iniciales
        if initial_bytes:
            initial_msg = initial_bytes.decode().strip()
            if initial_msg.startswith("PLAYER_NAME "):
                player_name = initial_msg[len("PLAYER_NAME "):].strip()
                clients[player_id]['name'] = player_name
                print(f"Nombre recibido de {player_id}: {player_name}") # ¡Esto ahora debería funcionar!
            else:
                # Si el primer mensaje no es el nombre, asignamos uno por defecto
                clients[player_id]['name'] = f"Jugador {player_id}"
        else:
            # Si no hubo bytes iniciales (no debería pasar), asignamos por defecto
            clients[player_id]['name'] = f"Jugador {player_id}"

        conn.settimeout(None) # Nos aseguramos que el timeout se quite
        conn.sendall(f"PLAYER_ID {player_id}\n".encode()) # <-- Añadido \n
        time.sleep(0.1)

        # Esperar a que ambos jugadores estén conectados y tengan nombre
        wait_loops = 0
        while len(clients) < MAX_PLAYERS or not all('name' in c for c in clients.values()):
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'): 
                return
            if not game_active:
                conn.sendall(b"MSG Esperando a todos los jugadores...\n")
            time.sleep(1)

        # Enviar info de equipos y oponentes
        my_team = get_player_team(player_id)
        teammate_id = next((tid for tid in team_members[my_team] if tid != player_id), None)
        teammate_name = clients[teammate_id]['name'] if teammate_id and teammate_id in clients else "N/A"
        opponents_info = []
        for opp_id in get_opposing_team_members(player_id):
            opp_name = clients[opp_id]['name'] if opp_id in clients else f"Jugador_{opp_id}"
            opponents_info.append(f"{opp_id} {opp_name}")
        team_info_msg = f"TEAM_INFO {teammate_id or 'NONE'} {teammate_name} {' '.join(opponents_info)}\n"
        try:
            conn.sendall(team_info_msg.encode())
        except Exception as e:
            print(f"Error enviando TEAM_INFO a {player_id}: {e}")

        if player_id not in clients or not clients[player_id].get('conn'):
            return

        # Solo P1 y P3 colocan barcos
        if len(clients) == MAX_PLAYERS and not player_setup_complete.get(player_id, False):
            if player_id in ("P1", "P3"):
                conn.sendall(b"SETUP_YOUR_BOARD\n")
                print(f"DEBUG [{player_id}]: Enviado SETUP_YOUR_BOARD.")
    except socket.error as e:
        print(f"Error de socket inicial con {player_id}: {e}")
        return
    try:
        while True:
            data_bytes = conn.recv(1024)
            if not data_bytes:
                print(f"Jugador {player_id} desconectado (recv vacío).")
                break 
            
            data = data_bytes.decode().strip() # strip() es importante
            if not data: # Ignorar mensajes vacíos después de strip()
                print(f"DEBUG [{player_id}]: Mensaje vacío recibido y ignorado.")
                continue

            # Nuevo: Si el cliente envía el nombre después de la conexión inicial
            if data.startswith("PLAYER_NAME "):
                player_name = data[len("PLAYER_NAME "):].strip()
                clients[player_id]['name'] = player_name
                print(f"Nombre recibido de {player_id}: {player_name}")
                continue

            print(f"DEBUG [{player_id}]: Datos decodificados: '{data}'")
            parts = data.split()
            command = parts[0]
            print(f"DEBUG [{player_id}]: Comando extraído: '{command}'")

            # --- Procesamiento de Comandos ---
            # Solo P1 y P3 pueden enviar READY_SETUP
            if command == "READY_SETUP":
                if player_id not in ("P1", "P3") or player_id not in player_setup_complete or game_active:
                    continue
                player_setup_complete[player_id] = True
                notify_players(
                    f"MSG El jugador {clients[player_id].get('name', player_id)} ha terminado de colocar sus barcos.\n".encode(),
                    exclude_player_id=player_id
                )
                try:
                    conn.sendall(b"MSG Esperando que los demas oponentes terminen la configuracion...\n")
                except socket.error:
                    break
                # Solo P1 y P3 deben estar listos para iniciar el juego
                all_ready = player_setup_complete["P1"] and player_setup_complete["P3"]
                if all_ready and not game_active:
                    # --- Enviar el tablero de P1 a P2 y el de P3 a P4 ---
                    for team_leader, teammate in [("P1", "P2"), ("P3", "P4")]:
                        if team_leader in clients and teammate in clients:
                            board_info = clients[team_leader].get('last_board')
                            if board_info:
                                try:
                                    clients[teammate]['conn'].sendall(f"TEAM_BOARD {board_info}\n".encode())
                                except Exception as e:
                                    print(f"Error enviando TEAM_BOARD a {teammate}: {e}")
                    with turn_lock:
                        if not game_active:
                            game_active = True
                            current_turn_index = 0
                            current_turn_player_id = turn_order[current_turn_index]
                            last_shot_details.clear()
                            notify_players(f"START_GAME {current_turn_player_id}\n".encode())
            elif command == "SHOT":
                if not game_active or current_turn_player_id != player_id:
                    try: conn.sendall(b"MSG No es tu turno o el juego no ha comenzado.\n"); continue
                    except: break
                try:
                    target_opponent_id = parts[1]
                    r, c = parts[2], parts[3]
                except IndexError:
                    continue
                if target_opponent_id not in clients or get_player_team(target_opponent_id) == get_player_team(player_id):
                    try: conn.sendall(b"MSG Oponente invalido.\n"); continue
                    except: break
                last_shot_details[target_opponent_id] = player_id
                notify_players(f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id])
            elif command == "RESULT":
                if not game_active:
                    continue
                try:
                    r_res, c_res, result_char = parts[1], parts[2], parts[3]
                except IndexError:
                    continue
                original_shooter_id = last_shot_details.get(player_id)
                if not original_shooter_id or original_shooter_id not in clients:
                    continue
                notify_players(
                    f"UPDATE {player_id} {r_res} {c_res} {result_char}\n".encode(),
                    target_player_ids=[original_shooter_id]
                )
                # --- LÓGICA MODIFICADA PARA NOTIFICAR A TODOS ---

                # `player_id` es el ID del jugador que fue "objetivo" del disparo (ej. P3)
                # `original_shooter_id` es el ID del que disparó (ej. P1)

                # Notificamos a todos los jugadores. El mensaje UPDATE lleva el ID
                # del equipo afectado, para que cada cliente sepa qué tablero actualizar.
                update_message = f"UPDATE {player_id} {r_res} {c_res} {result_char}\n".encode()
                notify_players(update_message) # Envía a todos los clientes conectados

                # La lógica de turnos permanece igual
                with turn_lock:
                    if not game_active:
                        continue
                    if result_char == 'H':
                        current_turn_player_id = original_shooter_id
                    else:
                        current_turn_index = (current_turn_index + 1) % MAX_PLAYERS
                        current_turn_player_id = turn_order[current_turn_index]
                    # Notificar de quién es el turno
                    turn_msg = f"TURN {current_turn_player_id}\n".encode()
                    notify_players(turn_msg)
                    # for pid in clients:
                    #     if pid == current_turn_player_id:
                    #         notify_players(b"YOUR_TURN_AGAIN\n", target_player_ids=[pid])
                    #     else:
                    #         notify_players(b"OPPONENT_TURN_MSG\n", target_player_ids=[pid])
            elif command == "I_SUNK_MY_SHIP":
                if not game_active:
                    continue
                try:
                    ship_name = parts[1]
                    coords_str_payload = " ".join(parts[2:])
                    original_shooter_id = last_shot_details.get(player_id)
                    if not original_shooter_id or original_shooter_id not in clients:
                        continue
                    # --- LÓGICA MODIFICADA PARA NOTIFICAR A TODO EL EQUIPO ---
                    
                    # Identificar el equipo del jugador que disparó
                    shooter_team_id = get_player_team(original_shooter_id)
                    if not shooter_team_id:
                        continue
                    
                    # Obtener a todos los miembros de ese equipo para notificarles
                    members_to_notify = team_members.get(shooter_team_id, [])

                    # Crear el mensaje de notificación
                    notification_msg = f"OPPONENT_SHIP_SUNK {player_id} {ship_name} {coords_str_payload}\n"
                    
                    # Enviar el mensaje a todos los miembros del equipo atacante
                    notify_players(notification_msg.encode(), target_player_ids=members_to_notify)

                except Exception as e:
                    print(f"Error procesando I_SUNK_MY_SHIP: {e}")
                    continue
            elif command == "GAME_WON":
                if game_active:
                    winner_proposer_id = player_id
                    winning_team_id = get_player_team(winner_proposer_id)
                    if not winning_team_id:
                        continue
                    with turn_lock:
                        if game_active:
                            game_active = False
                            current_turn_player_id = None
                            winners = team_members.get(winning_team_id, [])
                            losers = [pid for tid, members in team_members.items() if tid != winning_team_id for pid in members]
                            for p_win_id in winners:
                                if p_win_id in clients:
                                    notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_win_id])
                            for p_lose_id in losers:
                                if p_lose_id in clients:
                                    notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_lose_id])
                            time.sleep(0.5)
                            break
            elif command == "TEAM_BOARD_DATA":
                board_payload = data[len("TEAM_BOARD_DATA "):]
                clients[player_id]['last_board'] = board_payload
                continue
    except Exception as e:
        print(f"Error inesperado con el jugador {player_id}: {e}")
    finally:
        was_game_active_before_leaving = game_active
        if conn and conn.fileno() != -1:
            try: conn.shutdown(socket.SHUT_RDWR)
            except: pass
            try: conn.close()
            except: pass
        player_left_id = None
        if player_id in clients:
            player_left_id = player_id
            del clients[player_id]
        if was_game_active_before_leaving and player_left_id:
            losing_team_id = get_player_team(player_left_id)
            winning_team_id = None
            if losing_team_id == "TeamA": winning_team_id = "TeamB"
            elif losing_team_id == "TeamB": winning_team_id = "TeamA"
            game_ended_due_to_disconnect = False
            with turn_lock:
                if game_active:
                    game_active = False
                    current_turn_player_id = None
                    game_ended_due_to_disconnect = True
            if game_ended_due_to_disconnect and winning_team_id:
                msg_bytes = f"OPPONENT_TEAM_LEFT El jugador {player_left_id} se ha desconectado. Su equipo pierde.\n".encode()
                winners = team_members.get(winning_team_id, [])
                losers = team_members.get(losing_team_id, [])
                for p_id_notify in list(clients.keys()):
                    if p_id_notify in winners:
                        notify_players(msg_bytes, target_player_ids=[p_id_notify])
                        notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_id_notify])
                    elif p_id_notify in losers and p_id_notify != player_left_id:
                        notify_players(msg_bytes, target_player_ids=[p_id_notify])
                        notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_id_notify])
        if not clients:
            player_setup_complete = {pid: False for pid in player_setup_complete}
            with turn_lock:
                game_active = False
                current_turn_player_id = None
                current_turn_index = 0
                last_shot_details.clear()

def get_available_games():
    games = []
    if len(clients) < MAX_PLAYERS:
        creator_name = "Esperando jugadores..."
        if "P1" in clients and 'name' in clients["P1"]:
            creator_name = clients["P1"]['name']
        elif clients:
            first_client_id = next(iter(clients))
            creator_name = clients[first_client_id].get('name', f"Jugador {first_client_id}")
        games.append({"nombre_creador": creator_name, "id": 1, "jugadores_conectados": len(clients), "max_jugadores": MAX_PLAYERS})
    return games

def handle_list_games_request(conn):
    games = get_available_games()
    games_str_parts = []
    for g in games:
        games_str_parts.append(f"{g['nombre_creador']}|{g['id']}|{g['jugadores_conectados']}|{g['max_jugadores']}")
    games_str = ";".join(games_str_parts)
    try:
        conn.sendall(f"GAMES_LIST {games_str}\n".encode())
    except Exception as e:
        print(f"Error enviando GAMES_LIST: {e}")
    finally:
        try: conn.shutdown(socket.SHUT_RDWR)
        except: pass
        conn.close()

def start_server():
    global clients, player_setup_complete, game_active, current_turn_player_id, current_turn_index
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
    except OSError as e:
        print(f"Error al enlazar el socket en {HOST}:{PORT} - {e}")
        return
    server_socket.listen(MAX_PLAYERS + 2)
    print(f"Servidor de Batalla Naval (4 jugadores) escuchando en {HOST}:{PORT}")
    player_ids_available = [f"P{i+1}" for i in range(MAX_PLAYERS)]
    while True:
        if len(clients) < MAX_PLAYERS:
            if not clients:
                print("Servidor listo y esperando jugadores...")
            try:
                conn, addr = server_socket.accept()
            except OSError:
                print("Socket del servidor cerrado. Terminando bucle de aceptación.")
                break
            except Exception as e:
                print(f"Error aceptando conexión: {e}")
                continue
            initial_bytes = None
            try:
                conn.settimeout(0.5)
                initial_bytes = conn.recv(1024)
                conn.settimeout(None)
            except socket.timeout:
                conn.settimeout(None)
                conn.close()
                continue
            except Exception as e:
                conn.close()
                continue
            if initial_bytes:
                first_msg = initial_bytes.decode().strip()
                if first_msg == "LIST_GAMES":
                    handle_list_games_request(conn)
                    continue
            assigned_player_id = None
            for pid_candidate in player_ids_available:
                if pid_candidate not in clients:
                    assigned_player_id = pid_candidate
                    break
            if assigned_player_id:
                player_setup_complete[assigned_player_id] = False
                clients[assigned_player_id] = {'conn': conn, 'addr': addr}
                thread = threading.Thread(target=handle_client_connection, args=(conn, assigned_player_id, initial_bytes), daemon=True)
                thread.start()
                if len(clients) == MAX_PLAYERS:
                    print(f"{MAX_PLAYERS} jugadores conectados. La fase de configuracion comenzara para cada uno.")
            else:
                try:
                    conn.sendall(b"MSG Servidor actualmente lleno. Intenta mas tarde.\n")
                    conn.close()
                except: pass
        else:
            time.sleep(1)
    if server_socket:
        server_socket.close()

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