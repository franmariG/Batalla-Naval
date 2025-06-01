# server.py
import socket
import threading
import time

# Usar la IP del servidor de 4 jugadores como base
HOST = "169.254.107.4" # Asegúrate que sea la IP correcta de tu servidor
PORT = 8080

# --- Estado del Servidor (para una única partida a la vez) ---
game_lock = threading.RLock() # <--- CAMBIO IMPORTANTE: Usar RLock para permitir la re-adquisición

# Información de la partida actual
current_game = {
    "game_id": 1, # ID de partida fijo ya que solo manejamos una
    "mode": None, # 2 o 4 jugadores, se setea por el primer jugador
    "max_players": 0,
    "clients": {}, # player_id: {conn, addr, name, team_id (si 4p), last_board (si P1/P3 en 4p)}
    "player_setup_complete": {}, # player_id: bool
    "game_active": False,
    "turn_lock": threading.RLock(), # <--- CAMBIO IMPORTANTE: Usar RLock también aquí por consistencia/seguridad
    "current_turn_player_id": None,
    "turn_order": [], # Para 4 jugadores
    "current_turn_index": 0, # Para 4 jugadores
    "player_teams": {}, # P1: TeamA, etc. (solo 4p)
    "team_members_map": {}, # TeamA: [P1,P2] (solo 4p)
    "team_details": { # (solo 4p)
        "TeamA": {"name": None, "captain": "P1", "members": ["P1", "P2"]},
        "TeamB": {"name": None, "captain": "P3", "members": ["P3", "P4"]}
    },
    "last_shot_details": {} # target_id: shooter_id (solo 4p)
}

def reset_current_game_state():
    global current_game
    with game_lock:
        current_game["mode"] = None
        current_game["max_players"] = 0
        current_game["clients"].clear()
        current_game["player_setup_complete"].clear()
        current_game["game_active"] = False
        current_game["current_turn_player_id"] = None
        current_game["turn_order"] = []
        current_game["current_turn_index"] = 0
        current_game["player_teams"].clear()
        current_game["team_members_map"].clear()
        current_game["team_details"]["TeamA"]["name"] = None
        current_game["team_details"]["TeamB"]["name"] = None
        current_game["last_shot_details"].clear()
        print("INFO SERVER: Estado del juego reseteado para una nueva partida.")


def get_player_team_id(player_id):
    # No necesita lock si solo lee datos que se establecen bajo lock y no cambian frecuentemente
    # o si se accede desde un contexto que ya tiene el lock.
    # Por seguridad, podemos asumir que se llama desde un contexto con lock o que los datos son estables.
    return current_game["player_teams"].get(player_id)

def notify_players(message_bytes, target_player_ids=None, exclude_player_id=None):
    # Esta función ahora puede ser llamada de forma segura desde un hilo que ya posee game_lock
    with game_lock: 
        ids_to_notify = []
        if target_player_ids:
            ids_to_notify = target_player_ids
        else:
            ids_to_notify = list(current_game["clients"].keys())

        for pid in ids_to_notify:
            if pid == exclude_player_id:
                continue
            client_info = current_game["clients"].get(pid)
            if client_info and client_info.get('conn'):
                try:
                    client_info['conn'].sendall(message_bytes)
                except Exception as e:
                    print(f"Error notificando a {pid}: {e}")


def handle_client_connection(conn, addr):
    global current_game
    player_id = None
    initial_player_info_processed = False

    try:
        conn.settimeout(10.0) 
        initial_data_bytes = conn.recv(1024)
        conn.settimeout(None) 

        if not initial_data_bytes:
            print(f"Conexión de {addr} cerrada sin datos iniciales.")
            conn.close()
            return

        initial_msg = initial_data_bytes.decode().strip()
        print(f"DEBUG SERVER: Mensaje inicial de {addr}: '{initial_msg}'")
        parts = initial_msg.split()
        command = parts[0]

        requested_mode = 0
        player_name_temp = None

        if command == "PLAYER_INITIAL_INFO":
            if len(parts) >= 2:
                try:
                    requested_mode = int(parts[1])
                    if requested_mode not in [2, 4]:
                        raise ValueError("Modo inválido")
                    if requested_mode == 2 and len(parts) >= 3:
                        player_name_temp = " ".join(parts[2:])
                    elif requested_mode == 4: 
                        pass
                except ValueError:
                    print(f"ERROR SERVER: PLAYER_INITIAL_INFO malformado o modo inválido de {addr}: {initial_msg}")
                    conn.sendall(b"MSG Error: Informacion inicial invalida.\n")
                    conn.close()
                    return
            else:
                print(f"ERROR SERVER: PLAYER_INITIAL_INFO incompleto de {addr}: {initial_msg}")
                conn.sendall(b"MSG Error: Informacion inicial incompleta.\n")
                conn.close()
                return
        else:
            print(f"ERROR SERVER: Mensaje inicial inesperado de {addr}: {initial_msg}")
            conn.sendall(b"MSG Error: Protocolo inicial incorrecto.\n")
            conn.close()
            return

        with game_lock:
            if current_game["mode"] is None: # Primer jugador (P1)
                current_game["mode"] = requested_mode
                current_game["max_players"] = requested_mode
                if requested_mode == 2:
                    current_game["player_setup_complete"] = {"P1": False, "P2": False}
                    player_id = "P1"
                else: # requested_mode == 4
                    current_game["player_setup_complete"] = {"P1": False, "P2": False, "P3": False, "P4": False}
                    current_game["player_teams"] = {"P1": "TeamA", "P2": "TeamA", "P3": "TeamB", "P4": "TeamB"} 
                    current_game["team_members_map"] = {"TeamA": ["P1", "P2"], "TeamB": ["P3", "P4"]} 
                    current_game["turn_order"] = ["P1", "P3", "P2", "P4"] 
                    current_game["team_details"] = { 
                        "TeamA": {"name": None, "captain": "P1", "members": ["P1", "P2"]},
                        "TeamB": {"name": None, "captain": "P3", "members": ["P3", "P4"]}
                    }
                    player_id = "P1"
                
                current_game["clients"][player_id] = {'conn': conn, 'addr': addr}
                if player_name_temp and requested_mode == 2:
                     current_game["clients"][player_id]['name'] = player_name_temp
                elif requested_mode == 2:
                     current_game["clients"][player_id]['name'] = f"Jugador {player_id}"
                
                # ----- INICIO DE LA MODIFICACIÓN -----
                if requested_mode == 4:
                    # Asignar 'team_id' también para P1 en modo 4 jugadores
                    current_game["clients"][player_id]['team_id'] = get_player_team_id(player_id)
                # ----- FIN DE LA MODIFICACIÓN -----
                
                # player_setup_complete[player_id] es implicitamente False por la inicialización general
                # No es necesario current_game["player_setup_complete"][player_id] = False aquí de nuevo
                print(f"INFO SERVER: Jugador {player_id} ({addr}) conectado. Juego configurado para {current_game['mode']} jugadores.")

            elif requested_mode == current_game["mode"]: 
                if len(current_game["clients"]) < current_game["max_players"]:
                    for i in range(1, current_game["max_players"] + 1):
                        pid_candidate = f"P{i}"
                        if pid_candidate not in current_game["clients"]:
                            player_id = pid_candidate
                            break
                    
                    if player_id:
                        current_game["clients"][player_id] = {'conn': conn, 'addr': addr}
                        if player_name_temp and requested_mode == 2:
                            current_game["clients"][player_id]['name'] = player_name_temp
                        elif requested_mode == 2: 
                            current_game["clients"][player_id]['name'] = f"Jugador {player_id}"
                        
                        # player_setup_complete[player_id] es implicitamente False
                        if current_game["mode"] == 4:
                             current_game["clients"][player_id]['team_id'] = get_player_team_id(player_id) # get_player_team_id no usa lock
                        print(f"INFO SERVER: Jugador {player_id} ({addr}) conectado.")
                    else: 
                        print(f"ERROR SERVER: No se pudo asignar ID a {addr} aunque hay espacio.")
                        conn.sendall(b"MSG Error: No se pudo asignar ID de jugador.\n")
                        conn.close()
                        return
                else:
                    print(f"WARN SERVER: Conexión de {addr} rechazada, partida llena ({len(current_game['clients'])}/{current_game['max_players']}).")
                    conn.sendall(b"MSG Servidor actualmente lleno.\n")
                    conn.close()
                    return
            else: 
                print(f"WARN SERVER: Conexión de {addr} rechazada. Modo solicitado ({requested_mode}) no coincide con modo actual ({current_game['mode']}).")
                conn.sendall(b"MSG Error: El modo de juego solicitado no coincide con la partida actual.\n")
                conn.close()
                return
        
        initial_player_info_processed = True
        conn.sendall(f"PLAYER_ID {player_id}\n".encode()) 
        time.sleep(0.1)

        if current_game["mode"] == 4:
            player_client_info = current_game["clients"][player_id] # Accedido después del lock, seguro
            is_captain = (player_id == current_game["team_details"]["TeamA"]["captain"] or \
                          player_id == current_game["team_details"]["TeamB"]["captain"]) 
            if is_captain:
                try:
                    conn.sendall(b"REQUEST_TEAM_NAME\n") 
                    print(f"DEBUG SERVER [{player_id}]: Enviado REQUEST_TEAM_NAME.")
                    conn.settimeout(60.0)
                    team_name_msg_bytes = conn.recv(1024) 
                    conn.settimeout(None)
                    if team_name_msg_bytes:
                        team_name_msg = team_name_msg_bytes.decode().strip()
                        if team_name_msg.startswith("TEAM_NAME_IS "): 
                            team_name_payload = team_name_msg[len("TEAM_NAME_IS "):].strip() 
                            if team_name_payload:
                                # Usar game_lock en lugar de turn_lock para consistencia si team_details es parte del estado general del juego
                                with game_lock: 
                                    # Asumiendo player_client_info['team_id'] se asignó antes o es seguro de leer
                                    # Esto debería ser current_game["clients"][player_id]['team_id']
                                    # que fue asignado bajo game_lock anteriormente.
                                    player_team_id_for_name = current_game["clients"][player_id].get('team_id', get_player_team_id(player_id))

                                    current_game["team_details"][player_team_id_for_name]['name'] = team_name_payload 
                                print(f"INFO SERVER [{player_id}]: Nombre para {player_team_id_for_name} establecido a '{team_name_payload}'.")
                except socket.timeout:
                    print(f"WARN SERVER [{player_id}]: Timeout esperando TEAM_NAME_IS.") 
                except Exception as e:
                    print(f"ERROR SERVER [{player_id}]: Procesando TEAM_NAME_IS: {e}") 
                
                with game_lock: # Asegurar acceso a team_details
                    player_team_id_check = current_game["clients"][player_id].get('team_id', get_player_team_id(player_id))
                    if not current_game["team_details"][player_team_id_check]['name']:
                        default_team_name = f"Equipo_{player_team_id_check[-1]}" 
                        current_game["team_details"][player_team_id_check]['name'] = default_team_name 
                        print(f"INFO SERVER [{player_id}]: Usando nombre de equipo por defecto '{default_team_name}' para {player_team_id_check}.")

        wait_loops = 0
        max_wait_total = 120 
        condition_to_wait = True
        while condition_to_wait:
            with game_lock: 
                num_clients = len(current_game["clients"])
                all_ready_for_setup = (num_clients == current_game["max_players"])
                if current_game["mode"] == 4:
                    all_ready_for_setup = all_ready_for_setup and \
                                          current_game["team_details"]["TeamA"]["name"] and \
                                          current_game["team_details"]["TeamB"]["name"]
                condition_to_wait = not all_ready_for_setup
            
            if not condition_to_wait:
                break

            wait_loops += 1
            if player_id not in current_game["clients"] or not current_game["clients"][player_id].get('conn'):
                print(f"DEBUG SERVER [{player_id}]: Desconectado mientras esperaba a otros/nombres.")
                return
            
            if wait_loops > max_wait_total:
                print(f"ERROR SERVER [{player_id}]: Timeout general esperando jugadores/nombres. Terminando hilo de espera.")
                if current_game["mode"] == 4:
                    with game_lock: # Proteger acceso a team_details
                        if not current_game["team_details"]["TeamA"]["name"]: current_game["team_details"]["TeamA"]["name"] = "Equipo Alfa" 
                        if not current_game["team_details"]["TeamB"]["name"]: current_game["team_details"]["TeamB"]["name"] = "Equipo Bravo" 
                break 
            
            # Leer estado de los nombres de equipo bajo lock para evitar race conditions en el mensaje de espera
            msg_espera_extra_4p = ""
            if current_game["mode"] == 4:
                with game_lock:
                    status_team_A = current_game['team_details']['TeamA']['name'] or "Pendiente" 
                    status_team_B = current_game['team_details']['TeamB']['name'] or "Pendiente" 
                msg_espera_extra_4p = f". Nombres Equipo A: {status_team_A}, Equipo B: {status_team_B}"
            
            msg_espera_str = f"MSG Esperando jugadores ({num_clients}/{current_game['max_players']}){msg_espera_extra_4p}"
            
            try:
                if wait_loops % 5 == 0 or wait_loops == 1:
                    conn.sendall(f"{msg_espera_str}\n".encode()) 
            except socket.error:
                return 
            time.sleep(1)

        # Enviar información de oponentes/equipos
        # Acceder a current_game["clients"] y current_game["team_details"] necesita game_lock
        with game_lock:
            if current_game["mode"] == 2:
                other_id = "P2" if player_id == "P1" else "P1"
                opponent_name = "EsperandoOponente" # Default
                # Esperar nombre del oponente es problemático aquí si el otro hilo aún no lo seteó.
                # Es mejor que el nombre se setee cuando el jugador se conecta.
                # Lo que está en current_game["clients"][other_id]['name'] debería ser lo correcto.
                if other_id in current_game["clients"] and 'name' in current_game["clients"][other_id]:
                    opponent_name = current_game["clients"][other_id]['name']
                conn.sendall(f"OPPONENT_NAME {opponent_name}\n".encode())

            elif current_game["mode"] == 4:
                my_team_id_final = current_game["clients"][player_id]['team_id'] 
                my_team_name_final = current_game["team_details"][my_team_id_final]['name'] 
                opponent_team_id_final = "TeamB" if my_team_id_final == "TeamA" else "TeamA" 
                opponent_team_name_final = current_game["team_details"][opponent_team_id_final]['name'] 
                opponent_member_ids = current_game["team_details"][opponent_team_id_final]['members'] 
                opponent_ids_payload = " ".join(opponent_member_ids) 
                teams_info_final_msg = f"TEAMS_INFO_FINAL {my_team_name_final.replace(' ', '_')} {opponent_team_name_final.replace(' ', '_')} {opponent_ids_payload}\n" 
                conn.sendall(teams_info_final_msg.encode()) 

        # Enviar SETUP_YOUR_BOARD
        send_setup_board = False
        if current_game["mode"] == 2:
            send_setup_board = True
        elif current_game["mode"] == 4 and player_id in ("P1", "P3"): 
            send_setup_board = True
        
        # player_setup_complete se accede aquí, idealmente bajo lock si hay riesgo de modificación concurrente.
        # Sin embargo, en este punto, solo se lee para el player_id actual.
        # Y len(clients) también.
        is_player_setup_done = False
        num_connected_clients = 0
        with game_lock: # Asegurar lectura consistente
            is_player_setup_done = current_game["player_setup_complete"].get(player_id, False)
            num_connected_clients = len(current_game["clients"])

        if send_setup_board and num_connected_clients == current_game["max_players"] and not is_player_setup_done:
            conn.sendall(b"SETUP_YOUR_BOARD\n") 
            print(f"DEBUG [{player_id}]: Enviado SETUP_YOUR_BOARD.")
        
        while True:
            data_bytes = conn.recv(1024) 
            if not data_bytes:
                print(f"Jugador {player_id} desconectado (recv vacío).") 
                break
            
            data_decoded_full_message = data_bytes.decode()
            messages_received = data_decoded_full_message.split('\n') 

            for data_single_message in messages_received:
                data = data_single_message.strip() 
                if not data: 
                    continue
                
                # Mantener los logs de depuración anteriores aquí si se desea
                print(f"DEBUG SERVER [{player_id}]: Datos: '{data}'")
                parts = data.split() 
                if not parts: continue
                command = parts[0] 

                if command == "READY_SETUP": 
                    print(f"DEBUG SERVER [{player_id}]: Entrando en procesar READY_SETUP. game_active actual: {current_game.get('game_active')}")
                    with game_lock: # game_lock es RLock, re-adquisición es segura
                        print(f"DEBUG SERVER [{player_id}]: READY_SETUP - game_lock adquirido.")
                        can_send_ready = False
                        if current_game["mode"] == 2: can_send_ready = True
                        elif current_game["mode"] == 4 and player_id in ("P1", "P3"): can_send_ready = True

                        cond1_not_can_send = not can_send_ready
                        cond2_pid_not_in_setup = player_id not in current_game.get("player_setup_complete", {})
                        cond3_game_active = current_game.get("game_active", False) 
                        
                        print(f"DEBUG SERVER [{player_id}]: READY_SETUP validación -> not_can_send:{cond1_not_can_send}, pid_not_in_setup:{cond2_pid_not_in_setup}, game_active:{cond3_game_active}")

                        if cond1_not_can_send or cond2_pid_not_in_setup or cond3_game_active: 
                            print(f"DEBUG SERVER [{player_id}]: READY_SETUP ignorado debido a condiciones de validación.")
                            continue
                        
                        print(f"DEBUG SERVER [{player_id}]: READY_SETUP - Validación pasada. Procediendo a marcar como listo.")
                        current_game["player_setup_complete"][player_id] = True 
                        
                        player_name_for_msg = current_game.get("clients", {}).get(player_id, {}).get('name', player_id)
                        print(f"DEBUG SERVER [{player_id}]: Marcado como listo. player_setup_complete ahora es: {current_game['player_setup_complete']}")
                        
                        if current_game["mode"] == 2:
                            status_msg_for_other = f"MSG El jugador {player_name_for_msg} ha terminado.\n" 
                            notify_players(status_msg_for_other.encode(), exclude_player_id=player_id) 
                        elif current_game["mode"] == 4:
                            my_team_id_for_msg = get_player_team_id(player_id) 
                            my_team_name_for_msg = current_game["team_details"].get(my_team_id_for_msg, {}).get('name', f"Equipo {my_team_id_for_msg}") 
                            notify_players(
                                f"MSG El capitan del {my_team_name_for_msg} ({player_id}) ha terminado.\n".encode(), 
                                exclude_player_id=player_id
                            )
                        try:
                            conn.sendall(b"MSG Esperando que el oponente/otros terminen...\n") 
                        except socket.error: 
                            print(f"DEBUG SERVER [{player_id}]: Socket error al enviar 'MSG Esperando...' después de READY_SETUP. Terminando hilo.")
                            break # Este break sale del for data_single_message, luego podría salir del while True

                        all_set_up = False
                        if current_game["mode"] == 2:
                            all_set_up = current_game["player_setup_complete"].get("P1", False) and \
                                         current_game["player_setup_complete"].get("P2", False) 
                        elif current_game["mode"] == 4:
                            all_set_up = current_game["player_setup_complete"].get("P1", False) and \
                                         current_game["player_setup_complete"].get("P3", False) 
                        
                        print(f"DEBUG SERVER [{player_id}]: Chequeo all_set_up: {all_set_up}. game_active: {current_game['game_active']}")
                        if all_set_up and not current_game["game_active"]: 
                             print(f"DEBUG SERVER [{player_id}]: all_set_up es True y game_active es False. Intentando iniciar juego.")
                             # Usar current_game["turn_lock"] que también es RLock
                             with current_game["turn_lock"]: 
                                if not current_game["game_active"]: # Doble chequeo, crucial
                                    current_game["game_active"] = True 
                                    
                                    if current_game["mode"] == 4: 
                                        for team_leader, teammate in [("P1", "P2"), ("P3", "P4")]: 
                                            if team_leader in current_game["clients"] and teammate in current_game["clients"]:
                                                leader_info = current_game["clients"][team_leader]
                                                board_to_send = leader_info.get('last_board') 
                                                if board_to_send:
                                                    teammate_conn_obj = current_game["clients"][teammate].get('conn')
                                                    if teammate_conn_obj:
                                                        try:
                                                            teammate_conn_obj.sendall(f"TEAM_BOARD {board_to_send}\n".encode()) 
                                                            print(f"DEBUG SERVER: Enviado TEAM_BOARD de {team_leader} a {teammate}")
                                                        except Exception as e_tb:
                                                            print(f"Error enviando TEAM_BOARD a {teammate}: {e_tb}")

                                    if current_game["mode"] == 2:
                                        current_game["current_turn_player_id"] = "P1" 
                                    elif current_game["mode"] == 4:
                                        current_game["current_turn_index"] = 0 
                                        current_game["current_turn_player_id"] = current_game["turn_order"][0] 
                                        current_game["last_shot_details"].clear() 

                                    start_msg = f"START_GAME {current_game['current_turn_player_id']}\n".encode() 
                                    notify_players(start_msg) # notify_players usa game_lock, seguro con RLock
                                    print(f"INFO SERVER: Juego iniciado. Turno para: {current_game['current_turn_player_id']}")
                                else: 
                                    print(f"DEBUG SERVER [{player_id}]: Juego YA ESTABA activo bajo turn_lock. No se reinicia.")
                        # Fin del if all_set_up
                    # Fin del with game_lock para READY_SETUP

                elif command == "TEAM_BOARD_DATA": 
                    if current_game["mode"] == 4 and player_id in ("P1", "P3"):
                        with game_lock: # Proteger escritura en current_game
                            board_payload = " ".join(parts[1:]) 
                            current_game["clients"][player_id]['last_board'] = board_payload.strip() 
                        print(f"DEBUG [{player_id}]: Recibido TEAM_BOARD_DATA. Length: {len(board_payload)}")
                    # No necesita `continue` explícito si no hay más lógica para este comando en el bucle

                elif command == "SHOT": 
                    # Lógica de SHOT (acceso a current_game, turn_lock)
                    # ... (código original de SHOT) ...
                    if not current_game.get("game_active") or current_game.get("current_turn_player_id") != player_id:
                        try: conn.sendall(b"MSG No es tu turno o juego no activo.\n"); continue
                        except: break
                    
                    if current_game["mode"] == 2:
                        try:
                            r, c = parts[1], parts[2]
                            target_opponent_id = "P2" if player_id == "P1" else "P1"
                            # notify_players usa game_lock
                            notify_players(f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id])
                            print(f"[{player_id}] disparo a ({r},{c}). Enviando al oponente.")
                        except IndexError:
                             print(f"ERROR [{player_id}]: SHOT malformado (2P) - {data}")
                             continue # Continuar con el siguiente mensaje en el buffer
                    
                    elif current_game["mode"] == 4:
                        try:
                            target_opponent_id_shot = parts[1]
                            r, c = parts[2], parts[3]
                            
                            with game_lock: # Para leer team_id y last_shot_details
                                target_client_info = current_game["clients"].get(target_opponent_id_shot)
                                if not target_client_info or get_player_team_id(target_opponent_id_shot) == get_player_team_id(player_id):
                                    try: conn.sendall(b"MSG Oponente invalido.\n"); continue
                                    except: break
                                current_game["last_shot_details"][target_opponent_id_shot] = player_id
                            
                            notify_players(f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id_shot])
                            print(f"DEBUG [{player_id}]: {player_id} disparo a {target_opponent_id_shot} en ({r},{c})")
                        except IndexError:
                            print(f"ERROR [{player_id}]: SHOT malformado (4P) - {data}")
                            continue
                
                elif command == "RESULT": 
                    # Lógica de RESULT (acceso a current_game, turn_lock)
                    # ... (código original de RESULT) ...
                    if not current_game.get("game_active"): continue
                    try:
                        r_res, c_res, result_char = parts[1], parts[2], parts[3]
                    except IndexError:
                        print(f"ERROR [{player_id}]: RESULT malformado - {data}")
                        continue

                    if current_game["mode"] == 2:
                        original_shooter_id = "P2" if player_id == "P1" else "P1"
                        notify_players(f"UPDATE {r_res} {c_res} {result_char}\n".encode(), target_player_ids=[original_shooter_id])
                        
                        with current_game["turn_lock"]:
                            if not current_game.get("game_active"): continue # Chequeo doble
                            if result_char == 'H':
                                current_game["current_turn_player_id"] = original_shooter_id
                                notify_players(b"YOUR_TURN_AGAIN\n", target_player_ids=[original_shooter_id])
                                notify_players(b"OPPONENT_TURN_MSG\n", target_player_ids=[player_id])
                            else: # Miss 'M'
                                current_game["current_turn_player_id"] = player_id
                                notify_players(b"YOUR_TURN_AGAIN\n", target_player_ids=[player_id])
                                notify_players(b"OPPONENT_TURN_MSG\n", target_player_ids=[original_shooter_id])
                            print(f"INFO SERVER (2P): Turno para {current_game['current_turn_player_id']}")
                    
                    elif current_game["mode"] == 4:
                        original_shooter_id = None
                        with game_lock: # Para leer last_shot_details
                            original_shooter_id = current_game["last_shot_details"].get(player_id)
                        
                        if not original_shooter_id or original_shooter_id not in current_game.get("clients", {}):
                            continue
                        
                        notify_players(f"UPDATE {player_id} {r_res} {c_res} {result_char}\n".encode())
                        print(f"DEBUG SERVER (4P): Enviado UPDATE a todos: {f'UPDATE {player_id} {r_res} {c_res} {result_char}'}")

                        with current_game["turn_lock"]:
                            if not current_game.get("game_active"): continue
                            if result_char == 'H':
                                current_game["current_turn_player_id"] = original_shooter_id
                            else: # Miss
                                current_game["current_turn_index"] = (current_game["current_turn_index"] + 1) % current_game["max_players"]
                                current_game["current_turn_player_id"] = current_game["turn_order"][current_game["current_turn_index"]]
                            
                            notify_players(f"TURN {current_game['current_turn_player_id']}\n".encode())
                            print(f"INFO SERVER (4P): Turno para {current_game['current_turn_player_id']}.")

                elif command == "I_SUNK_MY_SHIP": 
                    # ... (código original de I_SUNK_MY_SHIP, asegurar locks si es necesario para leer last_shot_details) ...
                    if not current_game.get("game_active"): continue
                    try:
                        ship_name = parts[1]
                        coords_str_payload = " ".join(parts[2:])

                        if current_game["mode"] == 2:
                            shooter_player_id = "P2" if player_id == "P1" else "P1"
                            notify_players(f"OPPONENT_SHIP_SUNK {ship_name} {coords_str_payload}\n".encode(), target_player_ids=[shooter_player_id])
                        
                        elif current_game["mode"] == 4:
                            original_shooter_id_sunk = None
                            with game_lock: # Para leer last_shot_details
                                original_shooter_id_sunk = current_game["last_shot_details"].get(player_id)
                            
                            if not original_shooter_id_sunk or original_shooter_id_sunk not in current_game.get("clients",{}):
                                continue
                            
                            shooter_team_id = get_player_team_id(original_shooter_id_sunk) # No necesita lock si player_teams es estable
                            if not shooter_team_id: continue

                            members_to_notify_sunk = []
                            with game_lock: # Para leer team_members_map
                                members_to_notify_sunk = current_game["team_members_map"].get(shooter_team_id, [])
                            
                            notify_players(f"OPPONENT_SHIP_SUNK {player_id} {ship_name} {coords_str_payload}\n".encode(), target_player_ids=members_to_notify_sunk)
                            print(f"INFO SERVER: Notificado a equipo {shooter_team_id} que hundieron {ship_name} de {player_id}.")

                    except Exception as e:
                        print(f"Error procesando I_SUNK_MY_SHIP: {e} - Data: {data}")
                        continue
                
                elif command == "GAME_WON": 
                    # ... (código original de GAME_WON, asegurar locks para current_game["game_active"] y notificaciones) ...
                    # El current_game["turn_lock"] ya está siendo usado.
                    # notify_players usa game_lock, lo cual es seguro con RLock.
                    if current_game.get("game_active"):
                        winner_proposer_id = player_id
                        
                        with current_game["turn_lock"]:
                            if not current_game.get("game_active"):
                                print(f"DEBUG SERVER [{player_id}]: GAME_WON pero juego ya inactivo en lock.")
                                break # Salir del bucle de mensajes si el juego terminó por otra razón
                            current_game["game_active"] = False
                            current_game["current_turn_player_id"] = None

                        if current_game["mode"] == 2:
                            loser_id = "P2" if winner_proposer_id == "P1" else "P1"
                            print(f"INFO (2P): Procesando GAME_WON. Ganador: {winner_proposer_id}, Perdedor: {loser_id}.")
                            notify_players(b"GAME_OVER WIN\n", target_player_ids=[winner_proposer_id])
                            notify_players(b"GAME_OVER LOSE\n", target_player_ids=[loser_id])
                        
                        elif current_game["mode"] == 4:
                            winning_team_id = get_player_team_id(winner_proposer_id)
                            if not winning_team_id: continue
                            
                            with game_lock: # Para leer team_members_map
                                winners = current_game["team_members_map"].get(winning_team_id, [])
                                losing_team_id = "TeamB" if winning_team_id == "TeamA" else "TeamA"
                                losers = current_game["team_members_map"].get(losing_team_id, [])
                            
                            print(f"INFO (4P): Fin de juego. Ganadores: Equipo {winning_team_id}. Perdedores: Equipo {losing_team_id}.")
                            for p_win_id in winners: notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_win_id])
                            for p_lose_id in losers: notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_lose_id])
                        
                        time.sleep(0.5)
                        break # Salir del bucle de mensajes, el juego terminó para este jugador.
                    else:
                        print(f"WARN SERVER [{player_id}]: GAME_WON ignorado, juego no activo.")

                # Aquí terminaba el `for data_single_message in messages_received:`
                # Si un `break` ocurrió dentro del for, sale aquí.
            # Aquí termina el `while True:` si el `break` interno lo gatilló (ej. socket error, GAME_WON)
            # o si `if not data_bytes:` fue verdadero.

    except ConnectionResetError: 
        print(f"Jugador {player_id or addr} ha reseteado la conexion.") 
    except socket.timeout:
        print(f"Socket timeout para {player_id or addr}.")
    except socket.error as e: 
        # Solo loguear si era relevante o no era la desconexión esperada
        if current_game.get("game_active", False) or not initial_player_info_processed:
             if isinstance(e, ConnectionResetError) or (hasattr(e, 'winerror') and e.winerror == 10054): # Común en Windows
                 print(f"Jugador {player_id or addr} cerró la conexión (socket error detectado).")
             else:
                 print(f"Error de socket con {player_id or addr}: {e}")
    except Exception as e: 
        print(f"Error inesperado con el jugador {player_id or addr}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"Limpiando para el jugador {player_id or addr}.") 
        was_game_active_before_leaving = False
        # Acceder a game_active bajo lock para evitar race condition
        with game_lock:
            was_game_active_before_leaving = current_game.get("game_active", False)
        
        if conn and conn.fileno() != -1: 
            try: conn.shutdown(socket.SHUT_RDWR) 
            except: pass
            try: conn.close() 
            except: pass

        player_left_id_final = player_id 
        
        with game_lock: 
            if player_id and player_id in current_game["clients"]:
                del current_game["clients"][player_id] 
                print(f"Jugador {player_id} eliminado de 'clients'. Clientes restantes: {list(current_game['clients'].keys())}") 

            # Si el jugador se fue DURANTE un juego activo, notificar al/los otro(s) y terminar el juego.
            if was_game_active_before_leaving and player_left_id_final: 
                game_truly_ended_by_this_dc = False
                # Usar turn_lock para modificar el estado del juego activo
                with current_game["turn_lock"]:
                    if current_game["game_active"]: 
                        current_game["game_active"] = False 
                        current_game["current_turn_player_id"] = None 
                        game_truly_ended_by_this_dc = True
                
                if game_truly_ended_by_this_dc:
                    print(f"INFO SERVER: Jugador {player_left_id_final} se fue durante partida activa.") 
                    if current_game["mode"] == 2:
                        other_player_id_on_dc = "P1" if player_left_id_final == "P2" else "P2"
                        # Clientes restantes se leen bajo game_lock (hecho por notify_players)
                        if other_player_id_on_dc in current_game["clients"]: # Chequear si el otro aún está
                            notify_players(b"OPPONENT_LEFT\n", target_player_ids=[other_player_id_on_dc]) 
                            notify_players(b"GAME_OVER WIN\n", target_player_ids=[other_player_id_on_dc])
                    
                    elif current_game["mode"] == 4:
                        losing_team_id_on_dc = get_player_team_id(player_left_id_final) 
                        winning_team_id_on_dc = "TeamB" if losing_team_id_on_dc == "TeamA" else "TeamA" 
                        print(f"INFO SERVER: Equipo {losing_team_id_on_dc} pierde por desconexion de {player_left_id_final}. Gana Equipo {winning_team_id_on_dc}.") 
                        
                        msg_dc_broadcast = f"OPPONENT_TEAM_LEFT El jugador {player_left_id_final} del equipo {losing_team_id_on_dc} se ha desconectado. Su equipo pierde.\n".encode() 
                        
                        # Leer mapas de equipo bajo game_lock
                        winners_on_dc = current_game["team_members_map"].get(winning_team_id_on_dc, []) 
                        losers_team_members_on_dc = current_game["team_members_map"].get(losing_team_id_on_dc, [])
                        
                        # Filtrar los perdedores que todavía están conectados
                        # current_game["clients"] se accede dentro de notify_players (que tiene game_lock)
                        # O podemos construir la lista de IDs aquí bajo el lock actual.
                        
                        # Notificar a los ganadores
                        for p_id_notify_win in winners_on_dc:
                             if p_id_notify_win in current_game["clients"]: # Asegurarse que el ganador sigue conectado
                                notify_players(msg_dc_broadcast, target_player_ids=[p_id_notify_win])
                                notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_id_notify_win])
                        
                        # Notificar a los miembros restantes del equipo perdedor
                        for p_id_notify_lose in losers_team_members_on_dc:
                            if p_id_notify_lose != player_left_id_final and p_id_notify_lose in current_game["clients"]:
                                notify_players(msg_dc_broadcast, target_player_ids=[p_id_notify_lose])
                                notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_id_notify_lose])
                                
            if not current_game["clients"]: 
                print("Todos los jugadores se han desconectado. Reseteando estado del servidor.") 
                reset_current_game_state() 
        
        print(f"Fin de handle_client_connection para {player_id or addr}.") 

def get_formatted_available_games():
    global current_game
    games_output = []
    with game_lock: 
        if current_game["mode"] is None: 
            pass
        elif len(current_game["clients"]) < current_game["max_players"]:
            game_name = f"Partida de {current_game['mode']}J" # Simplificado
            if "P1" in current_game["clients"] and 'name' in current_game["clients"]["P1"]:
                 if current_game["mode"] == 2:
                     game_name = f"{current_game['clients']['P1']['name']} esperando..."
                 elif current_game["mode"] == 4:
                     team_a_name_temp = current_game["team_details"]["TeamA"]["name"]
                     if team_a_name_temp:
                         game_name = f"Equipo: {team_a_name_temp}"
                     else:
                         game_name = f"Cap. {current_game['clients']['P1']['name']} creando..."
            elif current_game["mode"] == 4: # Si P1 no está, pero es modo 4J
                game_name = "Esperando Cap. TeamA"

            games_output.append({ 
                "nombre_creador": game_name,
                "id": current_game["game_id"], 
                "jugadores_conectados": len(current_game["clients"]), 
                "max_jugadores": current_game["max_players"] 
            })
    return games_output


def handle_list_games_request(conn_list): 
    games_data = get_formatted_available_games() 
    games_str_parts = []
    for g in games_data:
        games_str_parts.append(f"{g['nombre_creador']}|{g['id']}|{g['jugadores_conectados']}|{g['max_jugadores']}") 
    games_str = ";".join(games_str_parts)
    try:
        conn_list.sendall(f"GAMES_LIST {games_str}\n".encode()) 
    except Exception as e:
        print(f"Error enviando GAMES_LIST: {e}") 
    finally:
        try: conn_list.shutdown(socket.SHUT_RDWR) 
        except: pass
        conn_list.close() 

def start_server():
    global current_game
    reset_current_game_state() 

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM) 
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) 
    try:
        server_socket.bind((HOST, PORT)) 
    except OSError as e:
        print(f"Error al enlazar el socket en {HOST}:{PORT} - {e}") 
        return
        
    server_socket.listen(5) 
    print(f"Servidor Unificado de Batalla Naval escuchando en {HOST}:{PORT}") 
    
    active_threads = []
    try:
        while True:
            try:
                conn, addr = server_socket.accept() 
            except OSError: 
                print("Socket del servidor cerrado. Terminando bucle de aceptación.") 
                break
            except Exception as e:
                print(f"Error aceptando conexión: {e}") 
                continue

            initial_peek_bytes = None
            is_list_request = False
            try:
                conn.settimeout(0.2)  
                initial_peek_bytes = conn.recv(1024, socket.MSG_PEEK) 
                conn.settimeout(None) 
                if initial_peek_bytes:
                    decoded_peek = initial_peek_bytes.decode().strip()
                    if decoded_peek.startswith("LIST_GAMES"): 
                        is_list_request = True
                        conn.recv(len(initial_peek_bytes)) 
                        print(f"DEBUG SERVER: Recibida petición LIST_GAMES de {addr}.") 
                        # No crear hilo para LIST_GAMES, manejar directamente
                        handle_list_games_request(conn) 
                        continue 
            except socket.timeout: 
                conn.settimeout(None)
            except Exception as e: 
                print(f"Error en peek de conexión de {addr}: {e}") 
                conn.close()
                continue
            
            print(f"INFO SERVER: Nueva conexión de juego de {addr}")
            thread = threading.Thread(target=handle_client_connection, args=(conn, addr), daemon=True) 
            thread.start()
            active_threads.append(thread)
            
            # Limpiar hilos terminados (opcional, pero buena práctica)
            active_threads = [t for t in active_threads if t.is_alive()]

    except KeyboardInterrupt:
        print("\nDeteniendo el servidor (Ctrl+C)...")
    finally:
        if server_socket:
            server_socket.close()
        print("Esperando que los hilos de cliente terminen...")
        for t in active_threads:
            if t.is_alive():
                t.join(timeout=1.0) # Dar un poco de tiempo para que los hilos terminen
        print("Servidor principal finalizando.")


# if __name__ == "__main__":
#     # No es necesario un hilo separado para start_server si la lógica de finalización está en start_server
#     start_server()


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True) # [cite: 718, 990]
    server_thread.start() # [cite: 718, 990]
    print("Presiona Ctrl+C para detener el servidor.") # [cite: 718, 990]
    try:
        while server_thread.is_alive(): # [cite: 718, 990]
            time.sleep(1)
    except KeyboardInterrupt: # [cite: 719, 990]
        print("\nDeteniendo el servidor (Ctrl+C)...") # [cite: 719, 990]
    finally:
        print("Servidor principal finalizando.") # [cite: 719, 990]