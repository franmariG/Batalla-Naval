# server.py
import socket
import threading
import time

HOST = '172.24.43.50'
PORT = 8080

# --- Estado del Servidor ---
clients = {}
# Cambia player_setup_complete y turnos a por-partida
pair_ids = [("P1", "P2"), ("P3", "P4")]
pair_for_player = {"P1": 0, "P2": 0, "P3": 1, "P4": 1}
pair_names = [["P1", "P2"], ["P3", "P4"]]
pair_setup_complete = [{}, {}]  # [{P1: False, P2: False}, {P3: False, P4: False}]
pair_game_active = [False, False]
pair_current_turn = [None, None]
pair_turn_lock = [threading.Lock(), threading.Lock()]
MAX_PLAYERS = 4
game_mode = None  # 2 o 4, según la selección del primer cliente

def notify_pair_opponent(sender_player_id, message_bytes):
    """Notifica solo al oponente del par correspondiente."""
    pair_idx = pair_for_player[sender_player_id]
    p1, p2 = pair_names[pair_idx]
    receiver_player_id = p2 if sender_player_id == p1 else p1
    if receiver_player_id in clients and clients[receiver_player_id].get('conn'):
        try:
            clients[receiver_player_id]['conn'].sendall(message_bytes)
        except Exception as e:
            print(f"Error notificando a {receiver_player_id}: {e}")

# server.py
# ... (mantén el resto de tu server.py igual: imports, HOST, PORT, globals, notify_other_player, player_id_exists_in_clients_dict)
# ... (ASEGÚRATE DE TENER LAS DEFINICIONES GLOBALES DE: clients, player_setup_complete, game_active, current_turn_player_id, turn_lock)

def handle_client_connection(conn, player_id):
    global clients, game_mode, pair_setup_complete, pair_game_active, pair_current_turn

    print(f"Jugador {player_id} ({clients[player_id]['addr']}) conectado.")
    try:
        # Esperar si el cliente envía el modo de juego y/o nombre juntos
        conn.settimeout(2.0)
        try:
            initial_bytes = conn.recv(1024)
            if initial_bytes:
                initial_msg = initial_bytes.decode().strip()
                # Procesar todos los comandos recibidos juntos
                cmds = initial_msg.split("PLAYER_NAME")
                mode_processed = False
                name_processed = False
                for part in cmds:
                    part = part.strip()
                    if part.startswith("MODE_SELECT"):
                        try:
                            mode_val = int(part.split()[1])
                            if game_mode is None and mode_val in (2, 4):
                                game_mode = mode_val
                                print(f"Modo de juego seleccionado: {game_mode} jugadores.")
                            elif game_mode is None:
                                game_mode = 2
                        except Exception as e:
                            print(f"Error procesando MODE_SELECT: {e}")
                        # Informar al cliente el modo seleccionado
                        conn.sendall(f"GAME_MODE {game_mode}".encode())
                        mode_processed = True
                    elif part:
                        # Si hay algo más, puede ser el nombre
                        player_name = part.strip()
                        if player_name:
                            clients[player_id]['name'] = player_name
                            print(f"Nombre recibido de {player_id}: {player_name}")
                            name_processed = True
                # Si no se recibió el nombre, esperar otro mensaje
                if not name_processed:
                    name_bytes = conn.recv(1024)
                    if name_bytes:
                        name_msg = name_bytes.decode().strip()
                        if name_msg.startswith("PLAYER_NAME "):
                            player_name = name_msg[len("PLAYER_NAME "):].strip()
                            clients[player_id]['name'] = player_name
                            print(f"Nombre recibido de {player_id}: {player_name}")
                        else:
                            clients[player_id]['name'] = f"Jugador {player_id}"
                # Si no se recibió el modo, informar el modo actual (si ya fue seleccionado)
                if not mode_processed and game_mode:
                    conn.sendall(f"GAME_MODE {game_mode}".encode())
            else:
                clients[player_id]['name'] = f"Jugador {player_id}"
        except socket.timeout:
            clients[player_id]['name'] = f"Jugador {player_id}"
        finally:
            conn.settimeout(None)
        conn.sendall(f"PLAYER_ID {player_id}".encode())
        time.sleep(0.1)

        # --- Cambios aquí: lógica por par ---
        pair_idx = pair_for_player[player_id]
        p1, p2 = pair_names[pair_idx]
        # Inicializa setup para el par si no existe
        for pid in (p1, p2):
            if pid not in pair_setup_complete[pair_idx]:
                pair_setup_complete[pair_idx][pid] = False

        # Esperar a que ambos jugadores del par estén conectados y tengan nombre
        wait_loops = 0
        while not (p1 in clients and p2 in clients and
                   'name' in clients[p1] and 'name' in clients[p2]):
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'):
                print(f"DEBUG [{player_id}]: Jugador desconectado mientras esperaba a su par. Terminando hilo de espera.")
                return
            if not pair_game_active[pair_idx]:
                conn.sendall(b"MSG Esperando a tu oponente...")
            if wait_loops % 5 == 0:
                print(f"DEBUG [{player_id}]: Esperando a su par ({p1}, {p2}) (lleva {wait_loops}s).")
            time.sleep(1)

        # Enviar nombre del oponente solo del par
        other_id = p2 if player_id == p1 else p1
        opponent_name = clients[other_id].get('name', f"Jugador {other_id}")
        try:
            conn.sendall(f"OPPONENT_NAME {opponent_name}".encode())
        except Exception as e:
            print(f"Error enviando nombre del oponente a {player_id}: {e}")

        # Esperar a que ambos jugadores del par estén conectados
        wait_loops = 0
        while not (p1 in clients and p2 in clients):
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'):
                print(f"DEBUG [{player_id}]: Jugador desconectado mientras esperaba a su par. Terminando hilo de espera.")
                return
            if not pair_game_active[pair_idx]:
                conn.sendall(b"MSG Esperando a tu oponente...")
            if wait_loops % 5 == 0:
                print(f"DEBUG [{player_id}]: Esperando a su par ({p1}, {p2}) (lleva {wait_loops}s).")
            time.sleep(1)
        if player_id not in clients or not clients[player_id].get('conn'):
            print(f"DEBUG [{player_id}]: Jugador desconectado antes de SETUP_YOUR_BOARD. Terminando hilo.")
            return

        # Solo enviar SETUP_YOUR_BOARD si este jugador no ha completado el setup y ambos están conectados
        if not pair_setup_complete[pair_idx][player_id]:
            conn.sendall(b"SETUP_YOUR_BOARD")
            print(f"DEBUG [{player_id}]: Enviado SETUP_YOUR_BOARD.")
    except socket.error as e:
        print(f"Error de socket inicial con {player_id} (probablemente desconectado): {e}")
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

            # --- Procesamiento de Comandos por par ---
            if command == "READY_SETUP":
                if pair_setup_complete[pair_idx][player_id]:
                    continue
                if pair_game_active[pair_idx]:
                    continue

                pair_setup_complete[pair_idx][player_id] = True
                print(f"DEBUG [{player_id}]: Marcado como listo. pair_setup_complete[{pair_idx}]: {pair_setup_complete[pair_idx]}")
                
                status_msg_for_other = f"MSG El jugador {player_id} ha terminado de colocar sus barcos."
                notify_pair_opponent(player_id, status_msg_for_other.encode())
                
                try:
                    conn.sendall(b"MSG Esperando que el oponente termine la configuracion...")
                except socket.error:
                    break 

                is_p1_ready = pair_setup_complete[pair_idx][p1]
                is_p2_ready = pair_setup_complete[pair_idx][p2]
                print(f"DEBUG [{player_id}]: Chequeando inicio de juego. {p1} Ready: {is_p1_ready}, {p2} Ready: {is_p2_ready}, Game Active: {pair_game_active[pair_idx]}")

                if is_p1_ready and is_p2_ready and not pair_game_active[pair_idx]: 
                    with pair_turn_lock[pair_idx]:
                        if not pair_game_active[pair_idx]: 
                            pair_game_active[pair_idx] = True 
                            pair_current_turn[pair_idx] = p1
                            
                            conn_p1 = clients.get(p1, {}).get('conn')
                            conn_p2 = clients.get(p2, {}).get('conn')
                            start_game_msg_bytes = f"START_GAME {pair_current_turn[pair_idx]}".encode()
                            error_sending_start = False

                            if conn_p1:
                                try: conn_p1.sendall(start_game_msg_bytes); print(f"DEBUG [{player_id}]: Enviado START_GAME a P1.")
                                except Exception as e: print(f"ERROR [{player_id}]: Fallo al enviar START_GAME a P1: {e}"); error_sending_start = True
                            else: print(f"ERROR [{player_id}]: No se encontró conexión para P1 al intentar enviar START_GAME."); error_sending_start = True

                            if conn_p2:
                                try: conn_p2.sendall(start_game_msg_bytes); print(f"DEBUG [{player_id}]: Enviado START_GAME a P2.")
                                except Exception as e: print(f"ERROR [{player_id}]: Fallo al enviar START_GAME a P2: {e}"); error_sending_start = True
                            else: print(f"ERROR [{player_id}]: No se encontró conexión para P2 al intentar enviar START_GAME."); error_sending_start = True
                            
                            if not error_sending_start:
                                print(f"INFO: Ambos jugadores notificados. El juego ha comenzado. Turno para: {pair_current_turn[pair_idx]}")
                            else:
                                print(f"ERROR: Hubo un problema al notificar a los jugadores para iniciar el juego. Reseteando game_active.")
                                pair_game_active[pair_idx] = False 
                                pair_current_turn[pair_idx] = None 
                        else:
                            print(f"DEBUG [{player_id}]: 'game_active' es TRUE dentro del lock. Otro hilo ya inició el juego.")
                else:
                    if not is_p1_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque P1 no está listo ({is_p1_ready}). Estado actual: {pair_setup_complete[pair_idx]}")
                    if not is_p2_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque P2 no está listo ({is_p2_ready}). Estado actual: {pair_setup_complete[pair_idx]}")
                    if pair_game_active[pair_idx] and is_p1_ready and is_p2_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque game_active es True (aunque P1 y P2 listos).")

            elif command == "SHOT":
                if not pair_game_active[pair_idx]:
                    print(f"DEBUG [{player_id}]: SHOT ignorado porque 'game_active' es False.")
                    try: conn.sendall(b"MSG El juego no ha comenzado o ya termino.")
                    except: pass
                    continue
                
                if pair_current_turn[pair_idx] != player_id:
                    print(f"DEBUG [{player_id}]: SHOT ignorado porque no es su turno (es de {pair_current_turn[pair_idx]}).")
                    try: conn.sendall(b"MSG No es tu turno.")
                    except: pass
                    continue
                
                shot_data_to_other = f"SHOT {parts[1]} {parts[2]}"
                notify_pair_opponent(player_id, shot_data_to_other.encode())
                print(f"[{player_id}] disparo a ({parts[1]},{parts[2]}). Enviando al oponente.")

            elif command == "RESULT":
                if not pair_game_active[pair_idx]:
                    continue
                
                original_shooter_id = p2 if player_id == p1 else p1
                update_message_for_shooter = f"UPDATE {parts[1]} {parts[2]} {parts[3]}"
                if original_shooter_id in clients and clients[original_shooter_id].get('conn'):
                    try: clients[original_shooter_id]['conn'].sendall(update_message_for_shooter.encode())
                    except: pass
                
                result_char = parts[3] 
                with pair_turn_lock[pair_idx]:
                    if not pair_game_active[pair_idx]: continue # Re-chequear dentro del lock
                    if result_char == 'H': 
                        pair_current_turn[pair_idx] = original_shooter_id 
                        if pair_current_turn[pair_idx] in clients and clients[pair_current_turn[pair_idx]].get('conn'):
                            try: clients[pair_current_turn[pair_idx]]['conn'].sendall(b"YOUR_TURN_AGAIN")
                            except: pass
                        player_who_was_hit_id = player_id
                        if player_who_was_hit_id in clients and clients[player_who_was_hit_id].get('conn'):
                             try: clients[player_who_was_hit_id]['conn'].sendall(b"OPPONENT_TURN_MSG") 
                             except: pass
                        print(f"Impacto de {original_shooter_id}. {original_shooter_id} sigue jugando.")
                    else: 
                        pair_current_turn[pair_idx] = player_id 
                        if pair_current_turn[pair_idx] in clients and clients[pair_current_turn[pair_idx]].get('conn'):
                             try: clients[pair_current_turn[pair_idx]]['conn'].sendall(b"YOUR_TURN_AGAIN")
                             except: pass
                        other_player_for_turn_notify = original_shooter_id
                        if other_player_for_turn_notify in clients and clients[other_player_for_turn_notify].get('conn'):
                            try: clients[other_player_for_turn_notify]['conn'].sendall(b"OPPONENT_TURN_MSG")
                            except: pass
                        print(f"Fallo de {original_shooter_id}. Turno para {pair_current_turn[pair_idx]}.")
            
            elif command == "GAME_WON":
                if not pair_game_active[pair_idx]: 
                    print(f"DEBUG [{player_id}]: GAME_WON ignorado porque 'game_active' es False.")
                    continue 
                
                winner_id = player_id
                loser_id = p2 if winner_id == p1 else p1
                print(f"Comando GAME_WON recibido de {winner_id}. Terminando juego del par {pair_idx}.")
                with pair_turn_lock[pair_idx]: # Es importante asegurar que game_active y current_turn se modifiquen atomicamente
                    if pair_game_active[pair_idx] : # Solo si no fue ya puesto a False por otro medio
                        pair_game_active[pair_idx] = False 
                        pair_current_turn[pair_idx] = None 
                    else: # El juego ya estaba marcado como inactivo, no hacer nada más aquí
                        print(f"DEBUG [{player_id}]: GAME_WON procesado, pero 'game_active' ya era False.")
                        break # Salir del bucle si el juego ya terminó

                # Enviar mensajes de fin de juego fuera del lock de turnos
                # pero después de que game_active ha sido puesto a False.
                if winner_id in clients and clients[winner_id].get('conn'):
                    try: clients[winner_id]['conn'].sendall(b"GAME_OVER WIN"); print(f"Enviado GAME_OVER WIN a {winner_id}")
                    except: pass
                
                if loser_id in clients and clients[loser_id].get('conn'):
                    try: clients[loser_id]['conn'].sendall(b"GAME_OVER LOSE"); print(f"Enviado GAME_OVER LOSE a {loser_id}")
                    except: pass
                
                time.sleep(0.5) 
                print(f"DEBUG [{player_id}]: Hilo del ganador ({winner_id}) terminando después de GAME_WON.")
                break # Hilo del ganador termina. El hilo del perdedor terminará por desconexión del cliente o error.
            
            else:
                print(f"WARN [{player_id}]: Comando desconocido o no manejable en el estado actual: '{command}'")

    except ConnectionResetError:
        print(f"Jugador {player_id} ha reseteado la conexion.")
    except socket.error as e:
        # Solo imprimir error si el juego se supone activo o en setup
        # (game_active es True O (game_active es False Y current_turn_player_id es None PERO alguno de los setup es False))
        is_in_setup = not game_active and current_turn_player_id is None and \
                      (not player_setup_complete.get("P1", True) or not player_setup_complete.get("P2", True))

        if game_active or is_in_setup: 
            print(f"Error de socket con {player_id} durante juego/setup: {e}")
    except Exception as e:
        print(f"Error inesperado con el jugador {player_id}: {e}")
    finally:
        print(f"Limpiando para el jugador {player_id}.")
        was_game_active_before_leaving = game_active 
        
        # Cerrar la conexión del jugador actual si aún está abierta
        # El socket puede ya estar cerrado si hubo un error de recv() o sendall()
        if conn and conn.fileno() != -1: 
            try: 
                conn.shutdown(socket.SHUT_RDWR) # Indicar que no se enviarán/recibirán más datos
            except socket.error: pass # Ignorar si ya está cerrado o no conectado
            try:
                conn.close()
            except socket.error: pass

        # Eliminar al jugador del diccionario de clientes
        # Es importante hacerlo después de cualquier uso de `clients[player_id]`
        # y antes de `notify_other_player` si se va a llamar desde aquí.
        player_left_id = None
        if player_id in clients: 
            player_left_id = player_id
            del clients[player_id]
            print(f"Jugador {player_id} eliminado de 'clients'. Clientes restantes: {list(clients.keys())}")

        # Si el jugador se fue DURANTE un juego activo, notificar al otro.
        if was_game_active_before_leaving and player_left_id:
            # Solo notificar si el otro jugador todavía existe
            other_player_still_exists = ("P1" in clients and player_left_id == "P2") or \
                                      ("P2" in clients and player_left_id == "P1")
            if other_player_still_exists:
                print(f"Jugador {player_left_id} se fue durante una partida activa. Notificando al otro.")
                notify_pair_opponent(player_left_id, b"OPPONENT_LEFT")
            
            # Marcar el juego como inactivo ya que un jugador se fue
            with pair_turn_lock: # Asegurar que estas variables se actualizan de forma segura
                if game_active : # Solo si seguía activo
                    game_active = False
                    current_turn_player_id = None

        # Si no quedan clientes, resetear el estado del servidor para una nueva partida.
        if not clients: 
            print("Todos los jugadores se han desconectado. Reseteando estado del servidor para una nueva partida.")
            player_setup_complete["P1"] = False
            player_setup_complete["P2"] = False
            with pair_turn_lock: # Asegurar que estas variables se actualizan de forma segura
                game_active = False 
                current_turn_player_id = None

def player_id_exists_in_clients_dict(clients_dict):
    """Chequea si P1 o P2 aún existen en el diccionario de clientes."""
    return "P1" in clients_dict or "P2" in clients_dict


def start_server():
    global clients, game_mode

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
    except OSError as e:
        print(f"Error al enlazar el socket en {HOST}:{PORT} - {e}")
        return
        
    server_socket.listen(MAX_PLAYERS)
    print(f"Servidor de Batalla Naval escuchando en {HOST}:{PORT}")
    
    while True:
        # Determinar el máximo de jugadores según el modo (por defecto 2)
        max_players = game_mode if game_mode in (2, 4) else 2
        if len(clients) < max_players:
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

            assigned_player_id = None
            # Asignar P1, P2, P3, P4 según disponibilidad
            for pid in ("P1", "P2", "P3", "P4"):
                if pid not in clients:
                    assigned_player_id = pid
                    break

            if assigned_player_id:
                # Inicializar el estado de setup para el par correspondiente
                pair_idx = pair_for_player[assigned_player_id]
                if assigned_player_id not in pair_setup_complete[pair_idx]:
                    pair_setup_complete[pair_idx][assigned_player_id] = False
                clients[assigned_player_id] = {'conn': conn, 'addr': addr}
                thread = threading.Thread(target=handle_client_connection, args=(conn, assigned_player_id), daemon=True)
                thread.start()
                if len(clients) == max_players:
                    print(f"{max_players} jugadores conectados. La fase de configuracion comenzara para cada uno.")
            else:
                print(f"Conexión de {addr} rechazada, slots ocupados o estado inconsistente.")
                try:
                    conn.sendall(b"MSG Servidor actualmente lleno o en mantenimiento. Intenta mas tarde.")
                    conn.close()
                except: pass
        else:
            time.sleep(1)

    print("Bucle principal del servidor terminado.")
    if server_socket:
        server_socket.close()


if __name__ == "__main__":
    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()
    print("Presiona Ctrl+C para detener el servidor.")
    try:
        while server_thread.is_alive(): # Mantener el hilo principal vivo mientras el servidor corre
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nDeteniendo el servidor (Ctrl+C)...")
    finally:
        print("Servidor principal finalizando.")
        # Los hilos daemon deberían terminar.
        # Podríamos cerrar el socket del servidor aquí si no se hizo en start_server
        # pero start_server debería manejar su propio cierre.