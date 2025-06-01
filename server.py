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
team_members_map = {"TeamA": ["P1", "P2"], "TeamB": ["P3", "P4"]}
turn_order = ["P1", "P3", "P2", "P4"]
current_turn_index = 0
current_turn_player_id = None

last_shot_details = {}  # {"P3": "P1"} significa que P1 disparó a P3

# NUEVA ESTRUCTURA PARA DETALLES DE EQUIPO
team_details = {
    "TeamA": {"name": None, "captain": "P1", "members": ["P1", "P2"]},
    "TeamB": {"name": None, "captain": "P3", "members": ["P3", "P4"]}
}
# Lock para proteger el acceso a team_details si múltiples hilos lo modifican (aunque aquí P1 y P3 son específicos)
team_details_lock = threading.Lock()

def get_player_team_id(player_id): # Renombrado para claridad
    return player_teams.get(player_id)

def get_opposing_team_members(player_id):
    sender_team = get_player_team_id(player_id)
    return [pid for tid, members in team_members_map.items() if tid != sender_team for pid in members]

def notify_players(message_bytes, target_player_ids=None, exclude_player_id=None):
    ids_to_notify = []
    if target_player_ids:
        ids_to_notify = target_player_ids
    else:
        ids_to_notify = list(clients.keys())

    for pid in ids_to_notify:
        if pid == exclude_player_id:
            continue
        client_info = clients.get(pid)
        if client_info and client_info.get('conn'):
            try:
                client_info['conn'].sendall(message_bytes)
            except Exception as e:
                print(f"Error notifying {pid}: {e}")

def handle_client_connection(conn, player_id, initial_bytes_from_start_server=None): # initial_bytes_from_start_server para claridad
    global game_active, current_turn_player_id, player_setup_complete, clients, current_turn_index, last_shot_details, team_details
    
    player_client_info = clients.get(player_id)
    if not player_client_info:
        print(f"Error: No se encontró información del cliente para {player_id} al inicio de handle_client_connection.")
        try: conn.close()
        except: pass
        return
    
    print(f"Jugador {player_id} ({clients[player_id]['addr']}) conectado.")
    
    # Asignar team_id al cliente para referencia futura
    player_client_info['team_id'] = get_player_team_id(player_id)

    # Ya no procesamos PLAYER_NAME individual aquí desde initial_bytes_from_start_server
    # initial_bytes_from_start_server es usado principalmente por start_server para el comando LIST_GAMES

    
    try:
        conn.settimeout(None) # Quitar timeout si venía de start_server
        conn.sendall(f"PLAYER_ID {player_id}\n".encode())
        print(f"DEBUG SERVER [{player_id}]: Enviado PLAYER_ID.")
        time.sleep(0.1)

        # Solicitar nombre de equipo si es capitán (P1 o P3)
        is_captain = (player_id == team_details["TeamA"]["captain"] or player_id == team_details["TeamB"]["captain"])
        
        if is_captain:
            try:
                conn.sendall(b"REQUEST_TEAM_NAME\n")
                print(f"DEBUG SERVER [{player_id}]: Enviado REQUEST_TEAM_NAME.")
                
                conn.settimeout(60.0) # Timeout para que el capitán ingrese el nombre
                team_name_msg_bytes = conn.recv(1024)
                conn.settimeout(None)

                if team_name_msg_bytes:
                    team_name_msg = team_name_msg_bytes.decode().strip()
                    if team_name_msg.startswith("TEAM_NAME_IS "):
                        team_name_payload = team_name_msg[len("TEAM_NAME_IS "):].strip()
                        if team_name_payload:
                            with team_details_lock:
                                current_player_team_id = player_client_info['team_id']
                                team_details[current_player_team_id]['name'] = team_name_payload
                            print(f"INFO SERVER [{player_id}]: Nombre para {current_player_team_id} establecido a '{team_name_payload}'.")
                        else:
                            print(f"WARN SERVER [{player_id}]: TEAM_NAME_IS recibido con payload vacío.")
                    else:
                        print(f"WARN SERVER [{player_id}]: Mensaje inesperado en lugar de TEAM_NAME_IS: {team_name_msg}")
                else:
                    print(f"WARN SERVER [{player_id}]: No se recibió TEAM_NAME_IS (bytes vacíos).")
            except socket.timeout:
                print(f"WARN SERVER [{player_id}]: Timeout esperando TEAM_NAME_IS.")
            except Exception as e:
                print(f"ERROR SERVER [{player_id}]: Procesando TEAM_NAME_IS: {e}")
            
            # Si el nombre del equipo no se estableció, usar uno por defecto
            with team_details_lock:
                current_player_team_id_check = player_client_info['team_id']
                if not team_details[current_player_team_id_check]['name']:
                    default_team_name = f"Equipo_{current_player_team_id_check[-1]}" # Equipo_A o Equipo_B
                    team_details[current_player_team_id_check]['name'] = default_team_name
                    print(f"INFO SERVER [{player_id}]: Usando nombre de equipo por defecto '{default_team_name}' para {current_player_team_id_check}.")

         # Esperar a que todos los jugadores estén conectados Y AMBOS NOMBRES DE EQUIPO ESTÉN LISTOS
        wait_loops = 0
        max_wait_team_names = 70 # Segundos
        print(f"DEBUG SERVER [{player_id}]: Entrando a bucle de espera de jugadores/nombres de equipo.")
        while len(clients) < MAX_PLAYERS or \
              not team_details["TeamA"]["name"] or \
              not team_details["TeamB"]["name"]:
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'): 
                print(f"DEBUG SERVER [{player_id}]: Desconectado mientras esperaba jugadores/nombres de equipo.")
                return
            
            # Enviar mensaje de espera al cliente actual
            # Esto evita spam si un capitán tarda mucho y los otros ya están esperando.
            if wait_loops % 5 == 0 or wait_loops == 1 : # Enviar al inicio y luego cada 5s
                status_team_A = team_details["TeamA"]["name"] or "Pendiente"
                status_team_B = team_details["TeamB"]["name"] or "Pendiente"
                msg_espera = f"MSG Esperando jugadores ({len(clients)}/{MAX_PLAYERS}). Nombres Equipo A: {status_team_A}, Equipo B: {status_team_B}\n"
                try:
                    conn.sendall(msg_espera.encode())
                except socket.error:
                    print(f"DEBUG SERVER [{player_id}]: Desconectado al enviar MSG de espera detallado.")
                    return

            if wait_loops > max_wait_team_names:
                print(f"ERROR SERVER [{player_id}]: Timeout general esperando jugadores/nombres de equipo. Terminando hilo.")
                # Asignar nombres por defecto si alguno falta para no bloquear indefinidamente
                with team_details_lock:
                    if not team_details["TeamA"]["name"]: team_details["TeamA"]["name"] = "Equipo Alfa"
                    if not team_details["TeamB"]["name"]: team_details["TeamB"]["name"] = "Equipo Bravo"
                break # Salir del bucle y continuar con nombres por defecto
            time.sleep(1)
        
        print(f"DEBUG SERVER [{player_id}]: Salió del bucle de espera. TeamA: '{team_details['TeamA']['name']}', TeamB: '{team_details['TeamB']['name']}'.")

        # Enviar información final de equipos
        my_team_id_final = player_client_info['team_id']
        my_team_name_final = team_details[my_team_id_final]['name']
        opponent_team_id_final = "TeamB" if my_team_id_final == "TeamA" else "TeamA"
        opponent_team_name_final = team_details[opponent_team_id_final]['name']
        
        # Obtener los IDs de los miembros del equipo oponente
        opponent_member_ids = team_details[opponent_team_id_final]['members'] # Lista como ['P3', 'P4']
        opponent_ids_payload = " ".join(opponent_member_ids) # String como "P3 P4"
        
        teams_info_final_msg = f"TEAMS_INFO_FINAL {my_team_name_final.replace(' ', '_')} {opponent_team_name_final.replace(' ', '_')} {opponent_ids_payload}\n"
        try:
            conn.sendall(teams_info_final_msg.encode())
            print(f"DEBUG SERVER [{player_id}]: Enviado TEAMS_INFO_FINAL: Mi Equipo='{my_team_name_final}', Oponente='{opponent_team_name_final}', IDs Oponentes='{opponent_ids_payload}'.")
        except Exception as e:
            print(f"Error enviando TEAMS_INFO_FINAL a {player_id}: {e}")
            return # No se puede continuar si esto falla

        # Solo P1 y P3 colocan barcos
        # Lógica de SETUP_YOUR_BOARD (como la tenías, para P1 y P3)
        if len(clients) == MAX_PLAYERS and not player_setup_complete.get(player_id, False):
            if player_id in ("P1", "P3"): # Solo P1 y P3 (capitanes) colocan para su equipo
                try:
                    conn.sendall(b"SETUP_YOUR_BOARD\n")
                    print(f"DEBUG [{player_id}]: Enviado SETUP_YOUR_BOARD.")
                except Exception as e:
                    print(f"ERROR SERVER [{player_id}]: Fallo al enviar SETUP_YOUR_BOARD: {e}")
                    return
    except socket.error as e:
        print(f"Error de socket inicial con {player_id}: {e}")
        return
    try:
        while True:
            data_bytes = conn.recv(1024)
            if not data_bytes:
                print(f"Jugador {player_id} desconectado (recv vacío).")
                break 
           
            data_decoded_full_message = data_bytes.decode() # Decodificar una vez
            
            # Procesar múltiples mensajes si llegaron juntos
            messages_received = data_decoded_full_message.split('\n')

            for data_single_message in messages_received:
                data = data_single_message.strip()
                if not data:
                    continue

                print(f"DEBUG [{player_id}]: Datos decodificados: '{data}'")
                parts = data.split()
                if not parts: # Chequeo extra por si una línea era solo \n y strip la dejó vacía
                    continue
                command = parts[0]
                print(f"DEBUG [{player_id}]: Comando extraído: '{command}'")

            
            # data = data_bytes.decode().strip() # strip() es importante
            # if not data: # Ignorar mensajes vacíos después de strip()
            #     print(f"DEBUG [{player_id}]: Mensaje vacío recibido y ignorado.")
            #     continue

            # Ya no necesitamos esto aquí, el nombre de equipo se gestionó antes
            # if data.startswith("PLAYER_NAME "):
            #     player_name = data[len("PLAYER_NAME "):].strip()
            #     clients[player_id]['name'] = player_name
            #     print(f"Nombre recibido de {player_id}: {player_name}")
            #     continue

            # print(f"DEBUG [{player_id}]: Datos decodificados: '{data}'")
            # parts = data.split()
            # command = parts[0]
            # print(f"DEBUG [{player_id}]: Comando extraído: '{command}'")

            # --- Procesamiento de Comandos ---
            # Solo P1 y P3 pueden enviar READY_SETUP
            if command == "READY_SETUP":
                if player_id not in ("P1", "P3") or player_id not in player_setup_complete or game_active:
                    print(f"DEBUG [{player_id}]: READY_SETUP ignorado. PID: {player_id}, En Setup: {player_id in player_setup_complete}, GameActive: {game_active}")
                    continue
                # player_setup_complete[player_id] = True
                # notify_players(
                #     f"MSG El jugador {clients[player_id].get('name', player_id)} ha terminado de colocar sus barcos.\n".encode(),
                #     exclude_player_id=player_id
                # )
                player_setup_complete[player_id] = True
                
                my_team_id_for_msg = get_player_team_id(player_id)
                my_team_name_for_msg = team_details.get(my_team_id_for_msg, {}).get('name', f"Equipo {my_team_id_for_msg}")
                notify_players(
                    f"MSG El capitán del {my_team_name_for_msg} ({player_id}) ha terminado de colocar sus barcos.\n".encode(),
                    exclude_player_id=player_id
                )
                try:
                    conn.sendall(b"MSG Esperando que los demas oponentes terminen la configuracion...\n")
                except socket.error:
                    break
                all_captains_ready = player_setup_complete.get("P1", False) and player_setup_complete.get("P3", False) # [cite: 62]
                    
                    # **** START ENHANCED DEBUGGING BLOCK ****
                print(f"DEBUG SERVER [{player_id}]: READY_SETUP received. P1_ready={player_setup_complete.get('P1', False)}, P3_ready={player_setup_complete.get('P3', False)}, game_active={game_active}")

                if all_captains_ready and not game_active:
                    print(f"DEBUG SERVER [{player_id}]: All captains READY and game NOT active. Preparing to send TEAM_BOARDs and start game.")
                    
                    # --- Enviar el tablero de P1 a P2 y el de P3 a P4 ---
                    for team_leader, teammate in [("P1", "P2"), ("P3", "P4")]: # [cite: 62]
                        print(f"DEBUG SERVER [{player_id}]: Processing TEAM_BOARD for {team_leader} -> {teammate}")
                        
                        if team_leader not in clients:
                            print(f"DEBUG SERVER [{player_id}]: COND_FAIL: {team_leader} not in clients. Skipping TEAM_BOARD for this pair.")
                            continue
                        if teammate not in clients:
                            print(f"DEBUG SERVER [{player_id}]: COND_FAIL: {teammate} not in clients. Skipping TEAM_BOARD for this pair.")
                            continue
                        
                        client_info_leader = clients.get(team_leader)
                        if not client_info_leader:
                            print(f"DEBUG SERVER [{player_id}]: COND_FAIL: Could not get client_info for {team_leader}. Skipping TEAM_BOARD for this pair.")
                            continue

                        board_info = client_info_leader.get('last_board') # [cite: 63]
                        if not board_info:
                            print(f"DEBUG SERVER [{player_id}]: COND_FAIL: board_info for {team_leader} is None or empty. Skipping TEAM_BOARD for this pair.")
                            continue
                            
                        print(f"DEBUG SERVER [{player_id}]: Checks passed for {team_leader} -> {teammate}. Board info length: {len(board_info)}. Teammate client info: {clients.get(teammate)}")
                        
                        teammate_conn = clients.get(teammate, {}).get('conn')
                        if not teammate_conn:
                            print(f"DEBUG SERVER [{player_id}]: COND_FAIL: Teammate {teammate} has no valid 'conn' object. Cannot send TEAM_BOARD.")
                            continue
                                
                        try:
                            teammate_conn.sendall(f"TEAM_BOARD {board_info}\n".encode()) # [cite: 64]
                            print(f"DEBUG SERVER [{player_id}]: Successfully sent TEAM_BOARD from {team_leader} to {teammate}")
                        except Exception as e:
                            print(f"Error sending TEAM_BOARD to {teammate} from {team_leader}: {e}") # [cite: 65]
                    # **** END ENHANCED DEBUGGING BLOCK ****
                    with turn_lock:
                        if not game_active: # Doble chequeo dentro del lock
                            game_active = True
                            current_turn_index = 0
                            current_turn_player_id = turn_order[current_turn_index]
                            last_shot_details.clear()
                            print(f"INFO SERVER: Juego iniciando. Turno para {current_turn_player_id}.")
                            notify_players(f"START_GAME {current_turn_player_id}\n".encode())
                        else:
                            print(f"DEBUG [{player_id}]: Juego ya activo cuando se intentó iniciar con READY_SETUP.")
                elif not all_captains_ready:
                    print(f"DEBUG SERVER [{player_id}]: Not all captains ready yet. P1: {player_setup_complete.get('P1', False)}, P3: {player_setup_complete.get('P3', False)}")
                elif game_active:
                     print(f"DEBUG SERVER [{player_id}]: All captains ready, but game is already active. No action taken for TEAM_BOARD/START_GAME here.")
            elif command == "SHOT":
                if not game_active or current_turn_player_id != player_id:
                    try: conn.sendall(b"MSG No es tu turno o el juego no ha comenzado.\n"); continue
                    except: break
                try:
                    target_opponent_id = parts[1]
                    r, c = parts[2], parts[3]
                except IndexError:
                    print(f"ERROR [{player_id}]: SHOT malformado - {data}")
                    continue
                
                target_client_info = clients.get(target_opponent_id)
                if not target_client_info or get_player_team_id(target_opponent_id) == get_player_team_id(player_id):
                    try: conn.sendall(b"MSG Oponente invalido o companero de equipo.\n"); continue
                    except: break
                    
                last_shot_details[target_opponent_id] = player_id # Quién disparó a quién
                notify_players(f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id])
                print(f"DEBUG [{player_id}]: {player_id} disparó a {target_opponent_id} en ({r},{c})")
            
            elif command == "RESULT":
                if not game_active:
                    continue
                try:
                    r_res, c_res, result_char = parts[1], parts[2], parts[3]
                except IndexError:
                    print(f"ERROR [{player_id}]: RESULT malformado - {data}")
                    continue
                
                original_shooter_id = last_shot_details.get(player_id) 
                if not original_shooter_id or original_shooter_id not in clients:
                    print(f"WARN [{player_id}]: No se encontró original_shooter_id para RESULT o ya no está. last_shot_details: {last_shot_details}")
                    continue
                # --- LÓGICA MODIFICADA PARA NOTIFICAR A TODOS ---

                # `player_id` es el ID del jugador que fue "objetivo" del disparo (ej. P3)
                # `original_shooter_id` es el ID del que disparó (ej. P1)

                 # Notificar a todos los jugadores sobre el resultado del disparo.
                # El cliente interpretará 'player_id' como el jugador del equipo cuyo tablero se actualiza.
                update_message = f"UPDATE {player_id} {r_res} {c_res} {result_char}\n".encode()
                notify_players(update_message)
                print(f"DEBUG SERVER: Enviado UPDATE a todos: {update_message.decode().strip()}")

                # La lógica de turnos permanece igual
                with turn_lock:
                    if not game_active: continue # Chequeo dentro del lock
                    if result_char == 'H':
                        current_turn_player_id = original_shooter_id # El que disparó sigue jugando
                    else: # 'M' o cualquier otra cosa que no sea 'H'
                        current_turn_index = (current_turn_index + 1) % MAX_PLAYERS
                        current_turn_player_id = turn_order[current_turn_index]
                        
                    # Notificar de quién es el turno
                    turn_msg = f"TURN {current_turn_player_id}\n".encode()
                    notify_players(turn_msg)
                    print(f"INFO SERVER: Turno cambiado a {current_turn_player_id}.")
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
                    
                    # player_id es el jugador cuyo barco fue hundido.
                    # Necesitamos notificar al equipo del jugador que HIZO el disparo.
                    original_shooter_id = last_shot_details.get(player_id)
                    if not original_shooter_id or original_shooter_id not in clients:
                        print(f"WARN [{player_id}]: No se encontró original_shooter_id para I_SUNK_MY_SHIP. last_shot_details: {last_shot_details}")
                        continue
                    
                    # --- LÓGICA MODIFICADA PARA NOTIFICAR A TODO EL EQUIPO ---
                    
                    # Identificar el equipo del jugador que disparó
                    shooter_team_id = get_player_team_id(original_shooter_id)
                    if not shooter_team_id:
                        continue
                    
                    # Obtener a todos los miembros de ese equipo para notificarles
                    members_to_notify = team_members_map.get(shooter_team_id, [])

                    # El mensaje OPPONENT_SHIP_SUNK debe llevar el ID del JUGADOR cuyo barco fue hundido (player_id)
                    # para que el equipo atacante sepa de qué oponente era el barco.
                    notification_msg_str = f"OPPONENT_SHIP_SUNK {player_id} {ship_name} {coords_str_payload}\n"
                    notify_players(notification_msg_str.encode(), target_player_ids=members_to_notify)
                    print(f"INFO SERVER: Notificado a equipo {shooter_team_id} que hundieron {ship_name} de {player_id}.")

                except Exception as e:
                    print(f"Error procesando I_SUNK_MY_SHIP: {e} - Data: {data}")
                    continue
            elif command == "GAME_WON":
                if game_active:
                    winner_proposer_id = player_id # El jugador que envía GAME_WON
                    winning_team_id = get_player_team_id(winner_proposer_id)
                    if not winning_team_id:
                        print(f"WARN [{player_id}]: GAME_WON recibido de jugador sin equipo válido.")
                        continue
                    with turn_lock:
                        if game_active:# Chequeo final
                            game_active = False
                            current_turn_player_id = None
                            
                            winners = team_members_map.get(winning_team_id, [])
                            # Determinar equipo perdedor
                            losing_team_id = "TeamB" if winning_team_id == "TeamA" else "TeamA"
                            losers = team_members_map.get(losing_team_id, [])

                            print(f"INFO SERVER: Fin de juego. Ganadores: Equipo {winning_team_id} ({winners}). Perdedores: Equipo {losing_team_id} ({losers}).")

                            for p_win_id in winners:
                                if p_win_id in clients:
                                    notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_win_id])
                            for p_lose_id in losers:
                                if p_lose_id in clients:
                                    notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_lose_id])
                            # No necesitamos break aquí, el hilo del ganador puede terminar naturalmente.
                            # Los hilos de los perdedores también.
                        else:
                             print(f"DEBUG SERVER [{player_id}]: GAME_WON procesado, pero juego ya estaba inactivo.")
                else:
                    print(f"WARN SERVER [{player_id}]: GAME_WON ignorado, juego no activo.")
            
            elif command == "TEAM_BOARD_DATA":
                    # parts[0] es "TEAM_BOARD_DATA"
                    # parts[1:] debería ser el payload, unido por espacios.
                    if len(parts) > 1:
                        board_payload = " ".join(parts[1:]) # Reconstruye el payload a partir de las partes
                    else:
                        board_payload = "" # No había payload
                    
                    clients[player_id]['last_board'] = board_payload.strip() # strip() por si acaso
                    print(f"DEBUG [{player_id}]: Recibido y guardado TEAM_BOARD_DATA. Original 'data': '{data}'. Payload procesado: '{board_payload}'. Length: {len(clients[player_id]['last_board'])}")
                    continue
            
    except Exception as e:
        print(f"Error inesperado con el jugador {player_id}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"DEBUG SERVER [{player_id}]: Entrando al finally de handle_client_connection.")
        was_game_active_before_leaving = game_active
        
        # Cerrar conexión
        if conn and conn.fileno() != -1:
            try: conn.shutdown(socket.SHUT_RDWR)
            except: pass
            try: conn.close()
            except: pass
            
        player_left_id_final = None
        if player_id in clients:
            player_left_id_final = player_id
            # NO remover de clients aquí si quieres que otros hilos vean que se fue
            # Pero sí marcarlo como 'desconectado' o con conn=None.
            # Por ahora, lo removemos para simplificar, pero puede afectar la notificación a otros.
            print(f"DEBUG SERVER [{player_id}]: Removiendo {player_id} de clients.")
            del clients[player_id]
            print(f"Jugador {player_id} eliminado. Clientes restantes: {list(clients.keys())}")
        
        # Si el juego estaba activo y un jugador se va, el equipo del jugador que se fue pierde.
        if was_game_active_before_leaving and player_left_id_final:
            print(f"INFO SERVER: Jugador {player_left_id_final} se fue durante partida activa.")
            losing_team_id_on_dc = get_player_team_id(player_left_id_final)
            winning_team_id_on_dc = None
            if losing_team_id_on_dc == "TeamA": winning_team_id_on_dc = "TeamB"
            elif losing_team_id_on_dc == "TeamB": winning_team_id_on_dc = "TeamA"

            game_truly_ended_by_this_dc = False
            with turn_lock:
                if game_active: # Si OTRO hilo no lo puso a False ya
                    game_active = False
                    current_turn_player_id = None
                    game_truly_ended_by_this_dc = True
            
            if game_truly_ended_by_this_dc and winning_team_id_on_dc:
                print(f"INFO SERVER: Equipo {losing_team_id_on_dc} pierde por desconexión de {player_left_id_final}. Gana Equipo {winning_team_id_on_dc}.")
                msg_bytes_dc = f"OPPONENT_TEAM_LEFT El jugador {player_left_id_final} (Equipo {losing_team_id_on_dc}) se ha desconectado. Su equipo pierde.\n".encode()
                
                winners_on_dc = team_members_map.get(winning_team_id_on_dc, [])
                # No notificar al que se fue. Los restantes del equipo perdedor sí.
                losers_still_connected_on_dc = [pid for pid in team_members_map.get(losing_team_id_on_dc, []) if pid in clients and pid != player_left_id_final]

                for p_id_notify in list(clients.keys()): # Notificar a los que quedan
                    if p_id_notify in winners_on_dc:
                        notify_players(msg_bytes_dc, target_player_ids=[p_id_notify])
                        notify_players(b"GAME_OVER WIN\n", target_player_ids=[p_id_notify])
                    elif p_id_notify in losers_still_connected_on_dc : # No notificar al que se fue
                        notify_players(msg_bytes_dc, target_player_ids=[p_id_notify])
                        notify_players(b"GAME_OVER LOSE\n", target_player_ids=[p_id_notify])
            else:
                if not game_truly_ended_by_this_dc :
                     print(f"DEBUG SERVER [{player_id}]: Juego ya había terminado cuando {player_left_id_final} se fue.")


        if not clients: # Si este fue el último cliente
            print("Todos los jugadores se han desconectado. Reseteando estado del servidor.")
            player_setup_complete = {pid_key: False for pid_key in player_setup_complete}
            with turn_lock: # Asegurar que estas variables se actualizan de forma segura
                game_active = False 
                current_turn_player_id = None
                current_turn_index = 0
            last_shot_details.clear()
            team_details["TeamA"]["name"] = None # Resetear nombres de equipo
            team_details["TeamB"]["name"] = None
        
        print(f"Fin de handle_client_connection para {player_id}.")

def get_available_games():
    games = []
    # Solo mostrar una "partida" si no está llena
    if len(clients) < MAX_PLAYERS:
        # Usar nombre de TeamA si P1 está y lo ha puesto, sino un default
        team_a_name_display = "Equipo Alfa (Esperando capitán)"
        if "P1" in clients and team_details["TeamA"]["name"]:
            team_a_name_display = team_details["TeamA"]["name"]
        elif not team_details["TeamA"]["name"] and "P1" in clients : # P1 conectado pero no ha nombrado
             team_a_name_display = f"{clients['P1'].get('id','P1')} esperando para nombrar Equipo A..."
        elif not team_details["TeamA"]["name"] and not "P1" in clients: # Nadie de Team A
             team_a_name_display = "Esperando Capitán Equipo A"


        games.append({
            "nombre_creador": team_a_name_display, 
            "id": 1, # ID de partida fijo por ahora
            "jugadores_conectados": len(clients), 
            "max_jugadores": MAX_PLAYERS
        })
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
    global clients, player_setup_complete, game_active, current_turn_player_id, current_turn_index, team_details
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        server_socket.bind((HOST, PORT))
    except OSError as e:
        print(f"Error al enlazar el socket en {HOST}:{PORT} - {e}")
        return
    
    server_socket.listen(MAX_PLAYERS + 2) # Un par extra para peticiones de lista
    print(f"Servidor de Batalla Naval (4 jugadores) escuchando en {HOST}:{PORT}")
    
    player_ids_available = [f"P{i+1}" for i in range(MAX_PLAYERS)]
    
    while True:
        # Resetear nombres de equipo si no hay clientes, para la siguiente partida.
        if not clients:
            with team_details_lock:
                team_details["TeamA"]["name"] = None
                team_details["TeamB"]["name"] = None
            player_setup_complete = {pid_key: False for pid_key in player_setup_complete} # Resetear setup
            game_active = False # Asegurarse que el juego no esté activo
            current_turn_player_id = None
            current_turn_index = 0
            last_shot_details.clear()
            
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
            initial_bytes_for_handler = None # Bytes que se pasarán al handler del juego
             # Intentar leer un primer mensaje para ver si es LIST_GAMES
            # o el inicio de una conexión de juego (que podría ser PLAYER_NAME)
            try:
                conn.settimeout(0.5) # Timeout corto para no bloquear si es una conexión de juego lenta
                peek_bytes = conn.recv(1024) 
                conn.settimeout(None) # Quitar timeout

                if peek_bytes:
                    decoded_peek = peek_bytes.decode().strip()
                    if decoded_peek == "LIST_GAMES": # [cite: 90]
                        print(f"DEBUG SERVER: Recibida petición LIST_GAMES de {addr}.")
                        handle_list_games_request(conn) # Esta función cierra la conexión
                        continue # Volver a esperar otra conexión
                    else:
                        # No era LIST_GAMES, así que estos bytes son para el handler del juego
                        initial_bytes_for_handler = peek_bytes 
                        print(f"DEBUG SERVER: Conexión de juego de {addr}. Bytes iniciales pasados al handler: '{decoded_peek[:50]}...'")
                else:
                    # No se recibió nada, podría ser una conexión fallida o un ping silencioso.
                    # Si no se reciben bytes, initial_bytes_for_handler permanecerá None.
                    # El handle_client_connection se encargará si es None.
                    print(f"DEBUG SERVER: Conexión de {addr} sin bytes iniciales (o recv vacío después de timeout corto).")

            except socket.timeout: # El timeout de 0.5s expiró, es una conexión de juego normal sin datos inmediatos
                conn.settimeout(None)
                print(f"DEBUG SERVER: Timeout corto para peek_bytes de {addr}. Asumiendo conexión de juego.")
                # initial_bytes_for_handler sigue siendo None
            except Exception as e:
                print(f"Error en pre-handle de conexión (peek_bytes) para {addr}: {e}")
                try: conn.close()
                except: pass
                continue # No procesar esta conexión
            
            # Asignar Player ID si hay slots
            assigned_player_id = None
            for pid_candidate in player_ids_available:
                if pid_candidate not in clients:
                    assigned_player_id = pid_candidate # [cite: 91]
                    break
                
            if assigned_player_id:
                print(f"DEBUG SERVER: Asignando ID {assigned_player_id} a {addr}.")
                player_setup_complete[assigned_player_id] = False # Resetear setup para el nuevo jugador
                clients[assigned_player_id] = {'conn': conn, 'addr': addr} # 'team_id' se añade en handle_client
                
                # Pasar initial_bytes_for_handler al hilo. Si es None, el handler lo gestionará.
                # PERO, ya no vamos a usar initial_bytes para el nombre de equipo en handle_client_connection.
                # El P1/P3 enviarán su nombre DESPUÉS de recibir REQUEST_TEAM_NAME.
                # Por lo tanto, initial_bytes_for_handler no es estrictamente necesario para la lógica de nombres de equipo.
                thread = threading.Thread(target=handle_client_connection, args=(conn, assigned_player_id, None), daemon=True) # Pasamos None para initial_bytes
                thread.start()
                
                if len(clients) == MAX_PLAYERS:
                    print(f"{MAX_PLAYERS} jugadores conectados. Esperando nombres de equipo y configuración.") # [cite: 93]
            else:
                print(f"Conexión de {addr} rechazada, servidor lleno.")
                try:
                    conn.sendall(b"MSG Servidor actualmente lleno. Intenta mas tarde.\n") # Añadir \n
                    conn.close()
                except: pass
        else: # Servidor lleno (MAX_PLAYERS conectados)
            time.sleep(1) 
            # Aquí se podría añadir lógica para remover clientes "zombie" si no responden después de un tiempo
    
    if server_socket: # [cite: 94]
        server_socket.close()
    print("Bucle principal del servidor terminado.")

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