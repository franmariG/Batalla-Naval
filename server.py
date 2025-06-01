# server.py
import socket
import threading
import time

# Usar la IP del servidor de 4 jugadores como base
HOST = "169.254.107.4" # Asegúrate que sea la IP correcta de tu servidor
PORT = 8080

# active_games almacenará el estado de todas las partidas activas.
# La clave será el game_id, el valor será el diccionario del estado de la partida.
active_games = {}
games_list_lock = threading.RLock() # Lock para acceder/modificar active_games
next_game_id = 1
game_id_lock = threading.Lock() # Lock para la generación segura de next_game_id

def get_new_game_id():
    global next_game_id
    with game_id_lock:
        new_id = next_game_id
        next_game_id += 1
        return new_id
    
# Esta función crea la estructura inicial para una nueva partida.
def create_new_game_state_template(requested_mode):
    game_state = {
        "game_id": 0, # Se establecerá cuando se añada a active_games
        "mode": requested_mode,
        "max_players": requested_mode,
        "clients": {}, # player_id: {conn, addr, name, team_id (si 4p), last_board (si P1/P3 en 4p)}
        "player_setup_complete": {}, # player_id: bool
        "game_active": False,
        "turn_lock": threading.RLock(), # Lock específico para los turnos de esta partida
        "current_turn_player_id": None,
        "turn_order": [],
        "current_turn_index": 0,
        "player_teams": {},
        "team_members_map": {},
        "team_details": {
            "TeamA": {"name": None, "captain": "P1", "members": ["P1", "P2"]},
            "TeamB": {"name": None, "captain": "P3", "members": ["P3", "P4"]}
        },
        "last_shot_details": {},
        "game_specific_lock": threading.RLock() # Lock para el estado general de esta partida
    }
    if requested_mode == 2:
        game_state["player_setup_complete"] = {"P1": False, "P2": False}
    elif requested_mode == 4:
        game_state["player_setup_complete"] = {"P1": False, "P2": False, "P3": False, "P4": False}
        game_state["player_teams"] = {"P1": "TeamA", "P2": "TeamA", "P3": "TeamB", "P4": "TeamB"}
        game_state["team_members_map"] = {"TeamA": ["P1", "P2"], "TeamB": ["P3", "P4"]}
        game_state["turn_order"] = ["P1", "P3", "P2", "P4"]
    return game_state

# Función para obtener el team_id dentro del contexto de una partida específica
def get_player_team_id_from_game(game_state_dict, player_id_in_game):
    return game_state_dict["player_teams"].get(player_id_in_game)


# Modificar notify_players para que opere sobre una partida específica
def notify_players_in_game(game_state_dict, message_bytes, target_player_ids=None, exclude_player_id=None):
    # Se usará game_state_dict["game_specific_lock"] internamente si es necesario para leer game_state_dict["clients"]
    # o se asume que quien llama ya tiene el lock.
    # Por simplicidad, asumimos que game_state_dict["clients"] se accede bajo un lock adecuado.
    
    # game_specific_lock debe usarse aquí para leer game_state_dict["clients"] de forma segura
    with game_state_dict["game_specific_lock"]:
        ids_to_notify = []
        if target_player_ids:
            ids_to_notify = target_player_ids
        else:
            ids_to_notify = list(game_state_dict["clients"].keys())

        for pid in ids_to_notify:
            if pid == exclude_player_id:
                continue
            client_info = game_state_dict["clients"].get(pid)
            if client_info and client_info.get('conn'):
                try:
                    client_info['conn'].sendall(message_bytes)
                except Exception as e:
                    print(f"Error notificando a {pid} en partida {game_state_dict.get('game_id', 'N/A')}: {e}")


def handle_client_connection(conn, addr):
    assigned_player_id = None
    assigned_game_id = None
    current_game_state_ref = None # Referencia al diccionario de la partida actual

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

        if command == "CREATE_GAME":
            if len(parts) >= 2:
                try:
                    requested_mode = int(parts[1])
                    if requested_mode not in [2, 4]: raise ValueError("Modo inválido")
                    if requested_mode == 2 and len(parts) >= 3:
                        player_name_temp = " ".join(parts[2:]).replace("_", " ")
                except ValueError:
                    print(f"ERROR SERVER: CREATE_GAME malformado de {addr}: {initial_msg}")
                    conn.sendall(b"MSG Error: Informacion inicial invalida.\n")
                    conn.close()
                    return

                assigned_game_id = get_new_game_id()
                current_game_state_ref = create_new_game_state_template(requested_mode)
                current_game_state_ref["game_id"] = assigned_game_id
                
                assigned_player_id = "P1" # El creador es P1 en su partida
                current_game_state_ref["clients"][assigned_player_id] = {'conn': conn, 'addr': addr}
                if requested_mode == 2:
                    current_game_state_ref["clients"][assigned_player_id]['name'] = player_name_temp if player_name_temp else f"Jugador {assigned_player_id}"
                elif requested_mode == 4: # Asignar team_id al capitán P1
                    current_game_state_ref["clients"][assigned_player_id]['team_id'] = get_player_team_id_from_game(current_game_state_ref, assigned_player_id)

                with games_list_lock:
                    active_games[assigned_game_id] = current_game_state_ref
                
                print(f"INFO SERVER: Jugador {assigned_player_id} ({addr}) creó Partida ID: {assigned_game_id} (Modo {requested_mode}).")

            else: # CREATE_GAME malformado
                conn.sendall(b"MSG Error: Comando CREATE_GAME incompleto.\n")
                conn.close()
                return

        elif command == "JOIN_GAME":
            if len(parts) >= 3: # JOIN_GAME <game_id> <mode> [name_if_2p]
                try:
                    target_game_id = int(parts[1])
                    requested_mode = int(parts[2]) # <--- ASEGÚRATE QUE ESTA LÍNEA ESTÉ ASÍ
                    
                    if requested_mode not in [2, 4]: # Añadir validación
                        print(f"ERROR SERVER: JOIN_GAME modo inválido ({requested_mode}) de {addr}: {initial_msg}")
                        conn.sendall(b"MSG Error: Modo para unirse invalido.\n")
                        conn.close()
                        return
                    
                    if len(parts) >= 4 and requested_mode == 2 : # Nombre opcional para 2J
                         player_name_temp = " ".join(parts[3:]).replace("_", " ")

                except ValueError:
                    print(f"ERROR SERVER: JOIN_GAME malformado de {addr}: {initial_msg}")
                    conn.sendall(b"MSG Error: Informacion para unirse invalida.\n")
                    conn.close()
                    return

                with games_list_lock: # Para buscar en active_games
                    if target_game_id not in active_games:
                        conn.sendall(b"MSG Error: Partida no encontrada.\n")
                        conn.close()
                        return
                    current_game_state_ref = active_games[target_game_id]
                
                # Ahora, usar el lock específico de la partida para modificarla
                with current_game_state_ref["game_specific_lock"]:
                    if len(current_game_state_ref["clients"]) >= current_game_state_ref["max_players"]:
                        conn.sendall(b"MSG Partida llena.\n")
                        conn.close()
                        return # Importante retornar para no seguir procesando este cliente para esta partida

                    # Asignar Px al jugador que se une
                    for i in range(1, current_game_state_ref["max_players"] + 1):
                        pid_candidate = f"P{i}"
                        if pid_candidate not in current_game_state_ref["clients"]:
                            assigned_player_id = pid_candidate
                            break
                    
                    if not assigned_player_id: # No debería ocurrir si el chequeo de 'llena' es correcto
                        conn.sendall(b"MSG Error: No se pudo asignar ID en la partida.\n")
                        conn.close()
                        return

                    current_game_state_ref["clients"][assigned_player_id] = {'conn': conn, 'addr': addr}
                    if current_game_state_ref["mode"] == 2:
                        current_game_state_ref["clients"][assigned_player_id]['name'] = player_name_temp if player_name_temp else f"Jugador {assigned_player_id}"
                    if current_game_state_ref["mode"] == 4:
                        current_game_state_ref["clients"][assigned_player_id]['team_id'] = get_player_team_id_from_game(current_game_state_ref, assigned_player_id)
                    
                    assigned_game_id = target_game_id
                    print(f"INFO SERVER: Jugador {assigned_player_id} ({addr}) se unió a Partida ID: {assigned_game_id}.")
            else: # JOIN_GAME malformado
                conn.sendall(b"MSG Error: Comando JOIN_GAME incompleto.\n")
                conn.close()
                return
        else:
            print(f"ERROR SERVER: Mensaje inicial inesperado de {addr}: {initial_msg}")
            conn.sendall(b"MSG Error: Protocolo inicial incorrecto.\n")
            conn.close()
            return

        # Enviar PLAYER_ID y GAME_ID al cliente
        conn.sendall(f"PLAYER_ID {assigned_player_id} {assigned_game_id}\n".encode())
        time.sleep(0.1)
        # ----- INICIO DE LA LÓGICA DE PARTIDA (ADAPTAR EXTENSAMENTE) -----
        # Todas las referencias a `current_game` deben ser `current_game_state_ref`
        # Todos los `game_lock` deben ser `current_game_state_ref["game_specific_lock"]`
        # Todos los `turn_lock` deben ser `current_game_state_ref["turn_lock"]`
        # `notify_players` debe ser `notify_players_in_game(current_game_state_ref, ...)`
        
        initial_player_info_processed = True
        conn.sendall(f"PLAYER_ID {assigned_player_id}\n".encode()) 
        time.sleep(0.1)

        if current_game_state_ref["mode"] == 4:
            player_client_info = current_game_state_ref["clients"][assigned_player_id] # Accedido después del lock, seguro
            is_captain = (assigned_player_id == current_game_state_ref["team_details"]["TeamA"]["captain"] or \
                          assigned_player_id == current_game_state_ref["team_details"]["TeamB"]["captain"]) 
            if is_captain:
                try:
                    conn.sendall(b"REQUEST_TEAM_NAME\n") 
                    print(f"DEBUG SERVER [{assigned_player_id}]: Enviado REQUEST_TEAM_NAME.")
                    conn.settimeout(60.0)
                    team_name_msg_bytes = conn.recv(1024) 
                    conn.settimeout(None)
                    if team_name_msg_bytes:
                        team_name_msg = team_name_msg_bytes.decode().strip()
                        if team_name_msg.startswith("TEAM_NAME_IS "): 
                            team_name_payload = team_name_msg[len("TEAM_NAME_IS "):].strip() 
                            if team_name_payload:
                                with current_game_state_ref["game_specific_lock"]: 
                                    player_team_id_for_name = current_game_state_ref["clients"][assigned_player_id].get('team_id', get_player_team_id_from_game(current_game_state_ref, assigned_player_id))

                                    current_game_state_ref["team_details"][player_team_id_for_name]['name'] = team_name_payload 
                                print(f"INFO SERVER [{assigned_player_id}]: Nombre para {player_team_id_for_name} establecido a '{team_name_payload}'.")
                except socket.timeout:
                    print(f"WARN SERVER [{assigned_player_id}]: Timeout esperando TEAM_NAME_IS.") 
                except Exception as e:
                    print(f"ERROR SERVER [{assigned_player_id}]: Procesando TEAM_NAME_IS: {e}") 
                
                with current_game_state_ref["game_specific_lock"]: # Asegurar acceso a team_details
                    player_team_id_check = current_game_state_ref["clients"][assigned_player_id].get('team_id', get_player_team_id_from_game(current_game_state_ref, assigned_player_id))
                    if not current_game_state_ref["team_details"][player_team_id_check]['name']:
                        default_team_name = f"Equipo_{player_team_id_check[-1]}" 
                        current_game_state_ref["team_details"][player_team_id_check]['name'] = default_team_name 
                        print(f"INFO SERVER [{assigned_player_id}]: Usando nombre de equipo por defecto '{default_team_name}' para {player_team_id_check}.")

        # --- NUEVA Fase Consolidada de Espera y Señalización de Configuración ---
        setup_signal_sent_to_this_client = False 
        # Una bandera en game_state["clients"][assigned_player_id]['got_setup_prompt'] puede rastrear si se enviaron OPPONENT_NAME/TEAMS_INFO y SETUP_YOUR_BOARD.
        # Inicializa esta bandera cuando el cliente se añade a game_state.
        # Ejemplo: current_game_state_ref["clients"][assigned_player_id]['got_setup_prompt'] = False

        wait_for_global_readiness_loops = 0
        # Puedes ajustar este timeout. Es el tiempo máximo que un cliente esperará si la partida nunca se llena.
        MAX_GLOBAL_WAIT_LOOPS = 180 # ej., 180 segundos (3 minutos)

        while not setup_signal_sent_to_this_client and wait_for_global_readiness_loops < MAX_GLOBAL_WAIT_LOOPS:
            game_is_globally_ready_now = False
            num_current_clients = 0
            is_this_client_still_connected = False # Renombrado para claridad

            with current_game_state_ref["game_specific_lock"]:
                if assigned_player_id not in current_game_state_ref["clients"]:
                    print(f"DEBUG SERVER [{assigned_player_id}]: Cliente desconectado durante espera de disponibilidad global.")
                    return # Salir del manejador si el cliente ya no está en el estado del juego

                is_this_client_still_connected = True # Todavía en el diccionario de clientes
                num_current_clients = len(current_game_state_ref["clients"])
                
                # Verificar condición de disponibilidad global
                ready_check = (num_current_clients == current_game_state_ref["max_players"])
                if current_game_state_ref["mode"] == 4:
                    all_team_names_set = current_game_state_ref["team_details"]["TeamA"]["name"] and \
                                         current_game_state_ref["team_details"]["TeamB"]["name"]
                    ready_check = ready_check and all_team_names_set
                game_is_globally_ready_now = ready_check
                
                # Verificar si este cliente ya recibió su indicación de configuración
                # Es mejor usar una bandera específica para esto en lugar de player_setup_complete
                # Asumamos una nueva bandera: current_game_state_ref["clients"][assigned_player_id].get('setup_prompt_sent', False)
                # Asegúrate de que esta bandera se inicialice a False cuando un jugador se une.
                # Para este ejemplo, lo simularemos con setup_signal_sent_to_this_client por simplicidad,
                # pero una bandera persistente en game_state es mejor.

            if game_is_globally_ready_now:
                with current_game_state_ref["game_specific_lock"]: # Readquirir el lock para modificación/envío seguro
                    # Verificar si este cliente aún necesita la indicación de configuración
                    # Esta verificación debería usar una bandera persistente. Por ahora, dependemos de la condición del bucle.

                    # Determinar si este cliente es un "jugador de configuración" (P1/P2 para 2J, P1/P3 para 4J)
                    is_primary_setup_player = (current_game_state_ref["mode"] == 2) or \
                                              (current_game_state_ref["mode"] == 4 and assigned_player_id in ("P1", "P3"))

                    if is_primary_setup_player:
                        # Enviar OPPONENT_NAME / TEAMS_INFO_FINAL primero
                        if current_game_state_ref["mode"] == 2:
                            other_id = "P2" if assigned_player_id == "P1" else "P1"
                            # Asegurar que el cliente other_id exista y tenga un nombre, o usar predeterminado
                            opponent_name = current_game_state_ref.get("clients", {}).get(other_id, {}).get('name', "Oponente")
                            conn.sendall(f"OPPONENT_NAME {opponent_name.replace(' ', '_')}\n".encode()) # 
                        elif current_game_state_ref["mode"] == 4: # P1 o P3 (capitanes)
                            my_team_id_final = current_game_state_ref["clients"][assigned_player_id]['team_id']
                            my_team_name_final = current_game_state_ref["team_details"][my_team_id_final]['name'] or f"Equipo_{my_team_id_final[-1]}"
                            opponent_team_id_final = "TeamB" if my_team_id_final == "TeamA" else "TeamA"
                            opponent_team_name_final = current_game_state_ref["team_details"][opponent_team_id_final]['name'] or f"Equipo_{opponent_team_id_final[-1]}"
                            opponent_member_ids = current_game_state_ref["team_members_map"].get(opponent_team_id_final, [])
                            opponent_ids_payload = " ".join(opponent_member_ids)
                            teams_info_final_msg = f"TEAMS_INFO_FINAL {my_team_name_final.replace(' ', '_')} {opponent_team_name_final.replace(' ', '_')} {opponent_ids_payload}\n" # 
                            conn.sendall(teams_info_final_msg.encode())
                        
                        conn.sendall(b"SETUP_YOUR_BOARD\n") # 
                        print(f"DEBUG SERVER [{assigned_player_id}]: Enviado OPPONENT_NAME/TEAMS_INFO_FINAL y SETUP_YOUR_BOARD (partida globalmente lista).")
                        # Marcar que este cliente ha recibido la indicación para prevenir reenvío (idealmente usando una bandera persistente)
                        # current_game_state_ref["clients"][assigned_player_id]['setup_prompt_sent'] = True
                        setup_signal_sent_to_this_client = True # Salir del bucle de espera de este manejador
                    
                    elif current_game_state_ref["mode"] == 4 and assigned_player_id in ("P2", "P4"):
                        # Jugadores no capitanes en modo 4J (P2, P4) necesitan TEAMS_INFO_FINAL y luego esperar TEAM_BOARD
                        my_team_id_final = current_game_state_ref["clients"][assigned_player_id]['team_id']
                        my_team_name_final = current_game_state_ref["team_details"][my_team_id_final]['name'] or f"Equipo_{my_team_id_final[-1]}"
                        opponent_team_id_final = "TeamB" if my_team_id_final == "TeamA" else "TeamA"
                        opponent_team_name_final = current_game_state_ref["team_details"][opponent_team_id_final]['name'] or f"Equipo_{opponent_team_id_final[-1]}"
                        opponent_member_ids = current_game_state_ref["team_members_map"].get(opponent_team_id_final, [])
                        opponent_ids_payload = " ".join(opponent_member_ids)
                        teams_info_final_msg = f"TEAMS_INFO_FINAL {my_team_name_final.replace(' ', '_')} {opponent_team_name_final.replace(' ', '_')} {opponent_ids_payload}\n" # 
                        conn.sendall(teams_info_final_msg.encode())
                        print(f"DEBUG SERVER [{assigned_player_id}]: Enviado TEAMS_INFO_FINAL. Esperando TEAM_BOARD del capitán.")
                        # Marcar indicación enviada y salir del bucle de espera para este manejador
                        # current_game_state_ref["clients"][assigned_player_id]['setup_prompt_sent'] = True
                        setup_signal_sent_to_this_client = True 
                # Fin de la sección crítica con lock
            else:
                # La partida aún no está globalmente lista. Enviar un mensaje de espera.
                msg_parts = [f"MSG Esperando jugadores ({num_current_clients}/{current_game_state_ref['max_players']})"]
                if current_game_state_ref["mode"] == 4:
                    # Acceder de forma segura a los nombres de los equipos para el mensaje de estado
                    team_a_name_status = "Pendiente"
                    team_b_name_status = "Pendiente"
                    with current_game_state_ref["game_specific_lock"]:
                         team_a_name_status = current_game_state_ref["team_details"]["TeamA"]["name"] or "Pendiente"
                         team_b_name_status = current_game_state_ref["team_details"]["TeamB"]["name"] or "Pendiente"
                    msg_parts.append(f". Nombres Equipo A: {team_a_name_status}, Equipo B: {team_b_name_status}")
                
                full_wait_msg = "".join(msg_parts)
                
                # Enviar mensaje periódicamente
                if wait_for_global_readiness_loops % 5 == 0 or wait_for_global_readiness_loops == 0:
                    try:
                        conn.sendall(f"{full_wait_msg}\n".encode()) # 
                    except socket.error:
                        print(f"DEBUG SERVER [{assigned_player_id}]: Error de socket durante envío de espera global. Cliente probablemente desconectado.")
                        return # Salir del manejador
                
                wait_for_global_readiness_loops += 1
                time.sleep(1) # Esperar antes de volver a verificar el estado global

        # Después del bucle:
        if not is_this_client_still_connected: # Doble verificación por si el cliente se desconectó
             return 

        if not setup_signal_sent_to_this_client and wait_for_global_readiness_loops >= MAX_GLOBAL_WAIT_LOOPS:
            # El manejador de este cliente específico expiró esperando que la partida estuviera globalmente lista.
            print(f"ERROR SERVER [{assigned_player_id}]: Timeout global ({MAX_GLOBAL_WAIT_LOOPS}s) esperando que la partida esté lista. ({num_current_clients}/{current_game_state_ref['max_players']}).")
            try:
                conn.sendall(b"MSG Error: Timeout esperando que la partida este completamente lista. Desconectando.\n")
            except socket.error:
                pass # El cliente podría haberse ido ya
            # El bloque finally de handle_client_connection se encargará de la limpieza.
            return # Salir de este manejador.
        
        # Si setup_signal_sent_to_this_client es true aquí, el cliente de este manejador recibió su indicación.
        # Si es false aquí, significa que es un jugador P2/P4 que recibió TEAMS_INFO y ahora está listo para el bucle principal.
        # (Esta condición necesita refinamiento si P2/P4 no deben continuar si la partida no se preparó)
        # La lógica anterior tiene como objetivo asegurar que P2/P4 también solo continúen si game_is_globally_ready_now fue true.

        print(f"DEBUG SERVER [{assigned_player_id}]: Finalizada fase de espera global. Procediendo al bucle principal de mensajes.")
        # ----- Fin de la NUEVA Fase Consolidada de Espera y Señalización de Configuración ---
        
        while True:
            data_bytes = conn.recv(1024) 
            if not data_bytes:
                print(f"Jugador {assigned_player_id} desconectado (recv vacío).") 
                break
            
            data_decoded_full_message = data_bytes.decode()
            messages_received = data_decoded_full_message.split('\n') 

            for data_single_message in messages_received:
                data = data_single_message.strip() 
                if not data: 
                    continue
                
                # Mantener los logs de depuración anteriores aquí si se desea
                print(f"DEBUG SERVER [{assigned_player_id}]: Datos: '{data}'")
                parts = data.split() 
                if not parts: continue
                command = parts[0] 

                if command == "READY_SETUP": 
                    print(f"DEBUG SERVER [{assigned_player_id}]: Entrando en procesar READY_SETUP. game_active actual: {current_game_state_ref.get('game_active')}")
                    with current_game_state_ref["game_specific_lock"]: 
                        print(f"DEBUG SERVER [{assigned_player_id}]: READY_SETUP - current_game_state_ref adquirido.")
                        can_send_ready = False
                        if current_game_state_ref["mode"] == 2: can_send_ready = True
                        elif current_game_state_ref["mode"] == 4 and assigned_player_id in ("P1", "P3"): can_send_ready = True

                        cond1_not_can_send = not can_send_ready
                        cond2_pid_not_in_setup = assigned_player_id not in current_game_state_ref.get("player_setup_complete", {})
                        cond3_game_active = current_game_state_ref.get("game_active", False) 
                        
                        print(f"DEBUG SERVER [{assigned_player_id}]: READY_SETUP validación -> not_can_send:{cond1_not_can_send}, pid_not_in_setup:{cond2_pid_not_in_setup}, game_active:{cond3_game_active}")

                        if cond1_not_can_send or cond2_pid_not_in_setup or cond3_game_active: 
                            print(f"DEBUG SERVER [{assigned_player_id}]: READY_SETUP ignorado debido a condiciones de validación.")
                            continue
                        
                        print(f"DEBUG SERVER [{assigned_player_id}]: READY_SETUP - Validación pasada. Procediendo a marcar como listo.")
                        current_game_state_ref["player_setup_complete"][assigned_player_id] = True 
                        
                        player_name_for_msg = current_game_state_ref.get("clients", {}).get(assigned_player_id, {}).get('name', assigned_player_id)
                        print(f"DEBUG SERVER [{assigned_player_id}]: Marcado como listo. player_setup_complete ahora es: {current_game_state_ref['player_setup_complete']}")
                        
                        if current_game_state_ref["mode"] == 2:
                            status_msg_for_other = f"MSG El jugador {player_name_for_msg} ha terminado.\n" 
                            notify_players_in_game(current_game_state_ref, status_msg_for_other.encode(), exclude_player_id=assigned_player_id)
                        elif current_game_state_ref["mode"] == 4:
                            my_team_id_for_msg = get_player_team_id_from_game(current_game_state_ref, assigned_player_id) 
                            my_team_name_for_msg = current_game_state_ref["team_details"].get(my_team_id_for_msg, {}).get('name', f"Equipo {my_team_id_for_msg}") 
                            notify_players_in_game(
                                current_game_state_ref, # Añadir current_game_state_ref
                                f"MSG El capitan del {my_team_name_for_msg} ({assigned_player_id}) ha terminado.\n".encode(),
                                exclude_player_id=assigned_player_id # Cambiar nombre del argumento
                            )
                        try:
                            conn.sendall(b"MSG Esperando que el oponente/otros terminen...\n") 
                        except socket.error: 
                            print(f"DEBUG SERVER [{assigned_player_id}]: Socket error al enviar 'MSG Esperando...' después de READY_SETUP. Terminando hilo.")
                            break # Este break sale del for data_single_message, luego podría salir del while True

                        all_set_up = False
                        if current_game_state_ref["mode"] == 2:
                            all_set_up = current_game_state_ref["player_setup_complete"].get("P1", False) and \
                                         current_game_state_ref["player_setup_complete"].get("P2", False) 
                        elif current_game_state_ref["mode"] == 4:
                            all_set_up = current_game_state_ref["player_setup_complete"].get("P1", False) and \
                                         current_game_state_ref["player_setup_complete"].get("P3", False) 
                        
                        print(f"DEBUG SERVER [{assigned_player_id}]: Chequeo all_set_up: {all_set_up}. game_active: {current_game_state_ref['game_active']}")
                        if all_set_up and not current_game_state_ref["game_active"]: 
                             print(f"DEBUG SERVER [{assigned_player_id}]: all_set_up es True y game_active es False. Intentando iniciar juego.")
                             
                             with current_game_state_ref["turn_lock"]: 
                                if not current_game_state_ref["game_active"]: # Doble chequeo, crucial
                                    current_game_state_ref["game_active"] = True 
                                    
                                    if current_game_state_ref["mode"] == 4: 
                                        for team_leader, teammate in [("P1", "P2"), ("P3", "P4")]: 
                                            if team_leader in current_game_state_ref["clients"] and teammate in current_game_state_ref["clients"]:
                                                leader_info = current_game_state_ref["clients"][team_leader]
                                                board_to_send = leader_info.get('last_board') 
                                                if board_to_send:
                                                    teammate_conn_obj = current_game_state_ref["clients"][teammate].get('conn')
                                                    if teammate_conn_obj:
                                                        try:
                                                            teammate_conn_obj.sendall(f"TEAM_BOARD {board_to_send}\n".encode()) 
                                                            print(f"DEBUG SERVER: Enviado TEAM_BOARD de {team_leader} a {teammate}")
                                                        except Exception as e_tb:
                                                            print(f"Error enviando TEAM_BOARD a {teammate}: {e_tb}")

                                    if current_game_state_ref["mode"] == 2:
                                        current_game_state_ref["current_turn_player_id"] = "P1" 
                                    elif current_game_state_ref["mode"] == 4:
                                        current_game_state_ref["current_turn_index"] = 0 
                                        current_game_state_ref["current_turn_player_id"] = current_game_state_ref["turn_order"][0] 
                                        current_game_state_ref["last_shot_details"].clear() 

                                    start_msg = f"START_GAME {current_game_state_ref['current_turn_player_id']}\n".encode() 
                                    notify_players_in_game(current_game_state_ref, start_msg) 
                                    print(f"INFO SERVER: Juego iniciado. Turno para: {current_game_state_ref['current_turn_player_id']}")
                                else: 
                                    print(f"DEBUG SERVER [{assigned_player_id}]: Juego YA ESTABA activo bajo turn_lock. No se reinicia.")
                        # Fin del if all_set_up

                elif command == "TEAM_BOARD_DATA": 
                    if current_game_state_ref["mode"] == 4 and assigned_player_id in ("P1", "P3"):
                        with current_game_state_ref["game_specific_lock"]: 
                            board_payload = " ".join(parts[1:]) 
                            current_game_state_ref["clients"][assigned_player_id]['last_board'] = board_payload.strip() 
                        print(f"DEBUG [{assigned_player_id}]: Recibido TEAM_BOARD_DATA. Length: {len(board_payload)}")
                    # No necesita `continue` explícito si no hay más lógica para este comando en el bucle

                elif command == "SHOT": 
                    if not current_game_state_ref.get("game_active") or current_game_state_ref.get("current_turn_player_id") != assigned_player_id:
                        try: conn.sendall(b"MSG No es tu turno o juego no activo.\n"); continue
                        except: break
                    
                    if current_game_state_ref["mode"] == 2:
                        try:
                            r, c = parts[1], parts[2]
                            target_opponent_id = "P2" if assigned_player_id == "P1" else "P1"
                            
                            notify_players_in_game(current_game_state_ref, f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id])
                            print(f"[{assigned_player_id}] disparo a ({r},{c}). Enviando al oponente.")
                        except IndexError:
                             print(f"ERROR [{assigned_player_id}]: SHOT malformado (2P) - {data}")
                             continue # Continuar con el siguiente mensaje en el buffer
                    
                    elif current_game_state_ref["mode"] == 4:
                        try:
                            target_opponent_id_shot = parts[1]
                            r, c = parts[2], parts[3]
                            
                            with current_game_state_ref["game_specific_lock"]: # Para leer team_id y last_shot_details
                                target_client_info = current_game_state_ref["clients"].get(target_opponent_id_shot)
                                if not target_client_info or get_player_team_id_from_game(current_game_state_ref, target_opponent_id_shot) == get_player_team_id_from_game(current_game_state_ref, assigned_player_id):
                                    try: conn.sendall(b"MSG Oponente invalido.\n"); continue
                                    except: break
                                current_game_state_ref["last_shot_details"][target_opponent_id_shot] = assigned_player_id
                            
                            notify_players_in_game(current_game_state_ref, f"SHOT {r} {c}\n".encode(), target_player_ids=[target_opponent_id_shot])
                            print(f"DEBUG [{assigned_player_id}]: {assigned_player_id} disparo a {target_opponent_id_shot} en ({r},{c})")
                        except IndexError:
                            print(f"ERROR [{assigned_player_id}]: SHOT malformado (4P) - {data}")
                            continue
                
                elif command == "RESULT": 
                    if not current_game_state_ref.get("game_active"): continue
                    try:
                        r_res, c_res, result_char = parts[1], parts[2], parts[3]
                    except IndexError:
                        print(f"ERROR [{assigned_player_id}]: RESULT malformado - {data}")
                        continue

                    if current_game_state_ref["mode"] == 2:
                        original_shooter_id = "P2" if assigned_player_id == "P1" else "P1"
                        notify_players_in_game(current_game_state_ref, f"UPDATE {r_res} {c_res} {result_char}\n".encode(), target_player_ids=[original_shooter_id])
                        
                        with current_game_state_ref["turn_lock"]:
                            if not current_game_state_ref.get("game_active"): continue # Chequeo doble
                            if result_char == 'H':
                                current_game_state_ref["current_turn_player_id"] = original_shooter_id
                                notify_players_in_game(current_game_state_ref, b"YOUR_TURN_AGAIN\n", target_player_ids=[original_shooter_id])
                                notify_players_in_game(current_game_state_ref, b"OPPONENT_TURN_MSG\n", target_player_ids=[assigned_player_id])
                            else: # Miss 'M'
                                current_game_state_ref["current_turn_player_id"] = assigned_player_id
                                notify_players_in_game(current_game_state_ref, b"YOUR_TURN_AGAIN\n", target_player_ids=[assigned_player_id])
                                notify_players_in_game(current_game_state_ref, b"OPPONENT_TURN_MSG\n", target_player_ids=[original_shooter_id])
                            print(f"INFO SERVER (2P): Turno para {current_game_state_ref['current_turn_player_id']}")
                    
                    elif current_game_state_ref["mode"] == 4:
                        original_shooter_id = None
                        with current_game_state_ref["game_specific_lock"]: # Para leer last_shot_details
                            original_shooter_id = current_game_state_ref["last_shot_details"].get(assigned_player_id)
                        
                        if not original_shooter_id or original_shooter_id not in current_game_state_ref.get("clients", {}):
                            continue
                        
                        notify_players_in_game(current_game_state_ref, f"UPDATE {assigned_player_id} {r_res} {c_res} {result_char}\n".encode())
                        print(f"DEBUG SERVER (4P): Enviado UPDATE a todos: {f'UPDATE {assigned_player_id} {r_res} {c_res} {result_char}'}")

                        with current_game_state_ref["turn_lock"]:
                            if not current_game_state_ref.get("game_active"): continue
                            if result_char == 'H':
                                current_game_state_ref["current_turn_player_id"] = original_shooter_id
                            else: # Miss
                                current_game_state_ref["current_turn_index"] = (current_game_state_ref["current_turn_index"] + 1) % current_game_state_ref["max_players"]
                                current_game_state_ref["current_turn_player_id"] = current_game_state_ref["turn_order"][current_game_state_ref["current_turn_index"]]
                            
                            notify_players_in_game(current_game_state_ref, f"TURN {current_game_state_ref['current_turn_player_id']}\n".encode())
                            print(f"INFO SERVER (4P): Turno para {current_game_state_ref['current_turn_player_id']}.")

                elif command == "I_SUNK_MY_SHIP": 
                    # ... (código original de I_SUNK_MY_SHIP, asegurar locks si es necesario para leer last_shot_details) ...
                    if not current_game_state_ref.get("game_active"): continue
                    try:
                        ship_name = parts[1]
                        coords_str_payload = " ".join(parts[2:])

                        if current_game_state_ref["mode"] == 2:
                            shooter_player_id = "P2" if assigned_player_id == "P1" else "P1"
                            notify_players_in_game(current_game_state_ref, f"OPPONENT_SHIP_SUNK {ship_name} {coords_str_payload}\n".encode(), target_player_ids=[shooter_player_id])
                        
                        elif current_game_state_ref["mode"] == 4:
                            original_shooter_id_sunk = None
                            with current_game_state_ref["game_specific_lock"]: # Para leer last_shot_details
                                original_shooter_id_sunk = current_game_state_ref["last_shot_details"].get(assigned_player_id)
                            
                            if not original_shooter_id_sunk or original_shooter_id_sunk not in current_game_state_ref.get("clients",{}):
                                continue
                            
                            shooter_team_id = get_player_team_id_from_game(current_game_state_ref, original_shooter_id_sunk) # No necesita lock si player_teams es estable
                            if not shooter_team_id: continue

                            members_to_notify_sunk = []
                            with current_game_state_ref["game_specific_lock"]: # Para leer team_members_map
                                members_to_notify_sunk = current_game_state_ref["team_members_map"].get(shooter_team_id, [])
                            
                            notify_players_in_game(current_game_state_ref, f"OPPONENT_SHIP_SUNK {assigned_player_id} {ship_name} {coords_str_payload}\n".encode(), target_player_ids=members_to_notify_sunk)
                            print(f"INFO SERVER: Notificado a equipo {shooter_team_id} que hundieron {ship_name} de {assigned_player_id}.")

                    except Exception as e:
                        print(f"Error procesando I_SUNK_MY_SHIP: {e} - Data: {data}")
                        continue
                
                elif command == "GAME_WON": 
                    if current_game_state_ref.get("game_active"):
                        winner_proposer_id = assigned_player_id
                        
                        with current_game_state_ref["turn_lock"]:
                            if not current_game_state_ref.get("game_active"):
                                print(f"DEBUG SERVER [{assigned_player_id}]: GAME_WON pero juego ya inactivo en lock.")
                                break # Salir del bucle de mensajes si el juego terminó por otra razón
                            current_game_state_ref["game_active"] = False
                            current_game_state_ref["current_turn_player_id"] = None

                        if current_game_state_ref["mode"] == 2:
                            loser_id = "P2" if winner_proposer_id == "P1" else "P1"
                            print(f"INFO (2P): Procesando GAME_WON. Ganador: {winner_proposer_id}, Perdedor: {loser_id}.")
                            notify_players_in_game(current_game_state_ref, b"GAME_OVER WIN\n", target_player_ids=[winner_proposer_id])
                            notify_players_in_game(current_game_state_ref, b"GAME_OVER LOSE\n", target_player_ids=[loser_id])
                        
                        elif current_game_state_ref["mode"] == 4:
                            winning_team_id = get_player_team_id_from_game(current_game_state_ref, winner_proposer_id)
                            if not winning_team_id: continue
                            
                            with current_game_state_ref["game_specific_lock"]: # Para leer team_members_map
                                winners = current_game_state_ref["team_members_map"].get(winning_team_id, [])
                                losing_team_id = "TeamB" if winning_team_id == "TeamA" else "TeamA"
                                losers = current_game_state_ref["team_members_map"].get(losing_team_id, [])
                            
                            print(f"INFO (4P): Fin de juego. Ganadores: Equipo {winning_team_id}. Perdedores: Equipo {losing_team_id}.")
                            for p_win_id in winners: notify_players_in_game(current_game_state_ref, b"GAME_OVER WIN\n", target_player_ids=[p_win_id])
                            for p_lose_id in losers: notify_players_in_game(current_game_state_ref, b"GAME_OVER LOSE\n", target_player_ids=[p_lose_id])
                        
                        time.sleep(0.5)
                        break # Salir del bucle de mensajes, el juego terminó para este jugador.
                    else:
                        print(f"WARN SERVER [{assigned_player_id}]: GAME_WON ignorado, juego no activo.")

                # Aquí terminaba el `for data_single_message in messages_received:`
                # Si un `break` ocurrió dentro del for, sale aquí.
            # Aquí termina el `while True:` si el `break` interno lo gatilló (ej. socket error, GAME_WON)
            # o si `if not data_bytes:` fue verdadero.

    except ConnectionResetError: 
        print(f"Jugador {assigned_player_id or addr} ha reseteado la conexion.") 
    except socket.timeout:
        print(f"Socket timeout para {assigned_player_id or addr}.")
    except socket.error as e: 
        # Solo loguear si era relevante o no era la desconexión esperada
        if current_game_state_ref.get("game_active", False) or not initial_player_info_processed:
             if isinstance(e, ConnectionResetError) or (hasattr(e, 'winerror') and e.winerror == 10054): # Común en Windows
                 print(f"Jugador {assigned_player_id or addr} cerró la conexión (socket error detectado).")
             else:
                 print(f"Error de socket con {assigned_player_id or addr}: {e}")
    except Exception as e: 
        print(f"Error inesperado con el jugador {assigned_player_id or addr}: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print(f"Limpiando para el jugador {assigned_player_id or addr} en partida {assigned_game_id or 'N/A'}.")
        # ... (cierre de conexión) ...

        if assigned_game_id is not None and assigned_player_id is not None:
            game_ended_by_this_dc = False
            # Usar games_list_lock para leer active_games, y game_specific_lock para modificar la partida
            with games_list_lock:
                if assigned_game_id in active_games:
                    game_to_clean = active_games[assigned_game_id]
                    with game_to_clean["game_specific_lock"]:
                        if assigned_player_id in game_to_clean["clients"]:
                            del game_to_clean["clients"][assigned_player_id]
                            print(f"Jugador {assigned_player_id} eliminado de clientes de Partida ID: {assigned_game_id}. Restantes: {list(game_to_clean['clients'].keys())}")

                        was_game_active_before_leaving = game_to_clean["game_active"]
                        if was_game_active_before_leaving:
                             with game_to_clean["turn_lock"]: # Usar el turn_lock de la partida específica
                                if game_to_clean["game_active"]: # Doble chequeo
                                    game_to_clean["game_active"] = False
                                    game_to_clean["current_turn_player_id"] = None
                                    game_ended_by_this_dc = True
                            
                        if game_ended_by_this_dc:
                            print(f"INFO SERVER: Jugador {assigned_player_id} se fue durante partida activa {assigned_game_id}.")
                            # Notificar a los jugadores restantes de ESA partida específica
                            # (La lógica de OPPONENT_LEFT y GAME_OVER WIN debe adaptarse para usar notify_players_in_game)
                            # ...

                        if not game_to_clean["clients"]: # Si la partida queda vacía
                            print(f"Partida ID: {assigned_game_id} está vacía. Eliminando de active_games.")
                            # games_list_lock ya está adquirido si esta lógica se mueve dentro del bloque 'with games_list_lock:'
                            # o se readquiere si es necesario.
                            # Este del active_games[assigned_game_id] debe estar bajo games_list_lock
                            # del active_games[assigned_game_id] # ¡CUIDADO! Este 'del' debe estar dentro del 'with games_list_lock:'
                            # Si esta parte del 'finally' está fuera del 'with games_list_lock' inicial (lo cual parece ser el caso),
                            # entonces active_games debe ser accedido/modificado con games_list_lock de nuevo.
                            # Lo más seguro es una estructura así:
                            # with games_list_lock:
                            #    if assigned_game_id in active_games:
                            #        game_to_clean = active_games[assigned_game_id]
                            #        # ... lógica con game_to_clean["game_specific_lock"] ...
                            #        if not game_to_clean["clients"]:
                            #            del active_games[assigned_game_id]
                            pass # La eliminación se hará afuera si es necesario para simplificar.

            # Re-chequear y eliminar si la partida está vacía, ahora con el lock apropiado
            with games_list_lock:
                if assigned_game_id in active_games and not active_games[assigned_game_id]["clients"]:
                    print(f"Confirmando eliminación de Partida ID: {assigned_game_id} (vacía) de active_games.")
                    del active_games[assigned_game_id]

        print(f"Fin de handle_client_connection para {assigned_player_id or addr} en partida {assigned_game_id or 'N/A'}.")

def get_formatted_available_games():
    games_output = []
    with games_list_lock: # Proteger el acceso a active_games
        for game_id, game_state in active_games.items():
            # Usar el lock específico de la partida para leer su estado interno de forma segura
            with game_state["game_specific_lock"]:
                if len(game_state["clients"]) < game_state["max_players"]:
                    # Determinar nombre del creador/equipo (P1 o TeamA)
                    creator_display_name = f"Partida {game_id}"
                    if "P1" in game_state["clients"]:
                        if game_state["mode"] == 2 and 'name' in game_state["clients"]["P1"]:
                            creator_display_name = game_state["clients"]["P1"]['name']
                        elif game_state["mode"] == 4:
                            team_a_name = game_state["team_details"]["TeamA"]["name"]
                            if team_a_name:
                                creator_display_name = f"Equipo: {team_a_name}"
                            # else: Usa el nombre P1 si el nombre del equipo aún no está.
                            elif 'name' in game_state["clients"]["P1"] : # Si P1 tiene nombre (no siempre para 4J)
                                 creator_display_name = game_state["clients"]["P1"]['name']


                    games_output.append({
                        "nombre_creador": creator_display_name, # Será usado como nombre de la partida en el menú del cliente
                        "id": game_id,
                        "jugadores_conectados": len(game_state["clients"]),
                        "max_jugadores": game_state["max_players"]
                    })
    return games_output

# handle_list_games_request no cambia mucho, usa la función anterior.
def handle_list_games_request(conn_list):
    games_data = get_formatted_available_games()
    games_str_parts = []
    for g in games_data:
        # Asegurarse que el nombre no contenga '|' o ';'
        clean_name = str(g['nombre_creador']).replace("|", "").replace(";", "")
        games_str_parts.append(f"{clean_name}|{g['id']}|{g['jugadores_conectados']}|{g['max_jugadores']}")
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
    global current_game_state_ref
    #reset_current_game_state() 

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