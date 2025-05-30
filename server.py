# server.py
import socket
import threading
import time

HOST = "192.168.1.105"
PORT = 8080

# --- Estado del Servidor ---
clients = {}
player_setup_complete = {"P1": False, "P2": False}
game_active = False
current_turn_player_id = None
turn_lock = threading.Lock()

def notify_other_player(sender_player_id, message_bytes):
    receiver_player_id = "P2" if sender_player_id == "P1" else "P1"
    if receiver_player_id in clients and clients[receiver_player_id].get('conn'): # .get('conn') for safety
        try:
            clients[receiver_player_id]['conn'].sendall(message_bytes)
        except Exception as e:
            print(f"Error notificando a {receiver_player_id}: {e}")

# server.py
# ... (mantén el resto de tu server.py igual: imports, HOST, PORT, globals, notify_other_player, player_id_exists_in_clients_dict)
# ... (ASEGÚRATE DE TENER LAS DEFINICIONES GLOBALES DE: clients, player_setup_complete, game_active, current_turn_player_id, turn_lock)

def handle_client_connection(conn, player_id):
    global game_active, current_turn_player_id, player_setup_complete, clients

    print(f"Jugador {player_id} ({clients[player_id]['addr']}) conectado.")
    try:
        # Esperar si el cliente envía el nombre primero
        conn.settimeout(2.0)
        try:
            initial_bytes = conn.recv(1024)
            if initial_bytes:
                initial_msg = initial_bytes.decode().strip()
                if initial_msg.startswith("PLAYER_NAME "):
                    player_name = initial_msg[len("PLAYER_NAME "):].strip()
                    clients[player_id]['name'] = player_name
                    print(f"Nombre recibido de {player_id}: {player_name}")
                else:
                    clients[player_id]['name'] = f"Jugador {player_id}"
            else:
                clients[player_id]['name'] = f"Jugador {player_id}"
        except socket.timeout:
            clients[player_id]['name'] = f"Jugador {player_id}"
        finally:
            conn.settimeout(None)
        conn.sendall(f"PLAYER_ID {player_id}".encode())
        time.sleep(0.1)

        # Esperar a que ambos jugadores estén conectados y tengan nombre
        wait_loops = 0
        while len(clients) < 2 or not all('name' in c for c in clients.values()):
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'): 
                print(f"DEBUG [{player_id}]: Jugador desconectado mientras esperaba al otro. Terminando hilo de espera.")
                return 
            if not game_active:
                conn.sendall(b"MSG Esperando al otro jugador...")
            if wait_loops % 5 == 0:
                print(f"DEBUG [{player_id}]: Sigue esperando al otro jugador/nombres (lleva {wait_loops}s). Clientes actuales: {list(clients.keys())}")
            time.sleep(1)

        # Enviar el nombre del oponente a este cliente
        other_id = "P2" if player_id == "P1" else "P1"
        opponent_name = clients[other_id].get('name', f"Jugador {other_id}")
        try:
            conn.sendall(f"OPPONENT_NAME {opponent_name}".encode())
        except Exception as e:
            print(f"Error enviando nombre del oponente a {player_id}: {e}")

        # Bucle de espera hasta que ambos jugadores estén conectados
        wait_loops = 0
        while len(clients) < 2:
            wait_loops += 1
            if player_id not in clients or not clients[player_id].get('conn'): 
                print(f"DEBUG [{player_id}]: Jugador desconectado mientras esperaba al otro. Terminando hilo de espera.")
                return 
            if not game_active: # Solo enviar si el juego no ha empezado o terminado
                 conn.sendall(b"MSG Esperando al otro jugador...")
            
            # Para evitar un log spam si un jugador espera mucho y el otro tarda o no conecta
            if wait_loops % 5 == 0: # Imprime cada 5 segundos aprox
                print(f"DEBUG [{player_id}]: Sigue esperando al otro jugador (lleva {wait_loops}s). Clientes actuales: {list(clients.keys())}")
            time.sleep(1)
            
        if player_id not in clients or not clients[player_id].get('conn'):
            print(f"DEBUG [{player_id}]: Jugador desconectado antes de SETUP_YOUR_BOARD. Terminando hilo.")
            return

        # Solo enviar SETUP_YOUR_BOARD si este jugador no ha completado el setup y ambos están conectados
        # player_setup_complete.get(player_id, False) es más seguro que player_setup_complete[player_id]
        if len(clients) == 2 and not player_setup_complete.get(player_id, False):
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

            # --- Procesamiento de Comandos ---
            if command == "READY_SETUP":
                if player_id not in player_setup_complete:
                    print(f"DEBUG [{player_id}]: 'player_id' ({player_id}) no encontrado en player_setup_complete ({list(player_setup_complete.keys())}). Ignorando READY_SETUP.")
                    continue
                if game_active: 
                    print(f"DEBUG [{player_id}]: Juego ya activo. Ignorando READY_SETUP.")
                    continue
                
                player_setup_complete[player_id] = True
                print(f"DEBUG [{player_id}]: Marcado como listo. player_setup_complete: {player_setup_complete}")
                
                status_msg_for_other = f"MSG El jugador {player_id} ha terminado de colocar sus barcos."
                notify_other_player(player_id, status_msg_for_other.encode())
                
                try:
                    conn.sendall(b"MSG Esperando que el oponente termine la configuracion...")
                except socket.error:
                    print(f"DEBUG [{player_id}]: Error al enviar 'MSG Esperando...' (probablemente desconectado).")
                    break 

                is_p1_ready = player_setup_complete.get("P1", False)
                is_p2_ready = player_setup_complete.get("P2", False)
                print(f"DEBUG [{player_id}]: Chequeando inicio de juego. P1 Ready: {is_p1_ready}, P2 Ready: {is_p2_ready}, Game Active: {game_active}")

                if is_p1_ready and is_p2_ready and not game_active: 
                    print(f"DEBUG [{player_id}]: Condición para iniciar juego CUMPLIDA. Intentando adquirir lock.")
                    with turn_lock:
                        print(f"DEBUG [{player_id}]: Lock adquirido.")
                        if not game_active: 
                            print(f"DEBUG [{player_id}]: 'game_active' es False DENTRO DEL LOCK. Iniciando juego.")
                            game_active = True 
                            current_turn_player_id = "P1"
                            
                            conn_p1 = clients.get("P1", {}).get('conn')
                            conn_p2 = clients.get("P2", {}).get('conn')
                            start_game_msg_bytes = f"START_GAME {current_turn_player_id}".encode()
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
                                print(f"INFO: Ambos jugadores notificados. El juego ha comenzado. Turno para: {current_turn_player_id}")
                            else:
                                print(f"ERROR: Hubo un problema al notificar a los jugadores para iniciar el juego. Reseteando game_active.")
                                game_active = False 
                                current_turn_player_id = None 
                        else:
                            print(f"DEBUG [{player_id}]: 'game_active' es TRUE dentro del lock. Otro hilo ya inició el juego.")
                else:
                    if not is_p1_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque P1 no está listo ({is_p1_ready}). Estado actual: {player_setup_complete}")
                    if not is_p2_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque P2 no está listo ({is_p2_ready}). Estado actual: {player_setup_complete}")
                    if game_active and is_p1_ready and is_p2_ready: print(f"DEBUG [{player_id}]: Condición NO cumplida porque game_active es True (aunque P1 y P2 listos).")

            elif command == "SHOT":
                if not game_active:
                    print(f"DEBUG [{player_id}]: SHOT ignorado porque 'game_active' es False.")
                    try: conn.sendall(b"MSG El juego no ha comenzado o ya termino.")
                    except: pass
                    continue
                
                if current_turn_player_id != player_id:
                    print(f"DEBUG [{player_id}]: SHOT ignorado porque no es su turno (es de {current_turn_player_id}).")
                    try: conn.sendall(b"MSG No es tu turno.")
                    except: pass
                    continue
                
                shot_data_to_other = f"SHOT {parts[1]} {parts[2]}"
                notify_other_player(player_id, shot_data_to_other.encode())
                print(f"[{player_id}] disparo a ({parts[1]},{parts[2]}). Enviando al oponente.")

            elif command == "RESULT":
                if not game_active:
                    print(f"DEBUG [{player_id}]: RESULT ignorado porque 'game_active' es False.")
                    continue
                
                original_shooter_id = "P2" if player_id == "P1" else "P1"
                update_message_for_shooter = f"UPDATE {parts[1]} {parts[2]} {parts[3]}"
                if original_shooter_id in clients and clients[original_shooter_id].get('conn'):
                    try: clients[original_shooter_id]['conn'].sendall(update_message_for_shooter.encode())
                    except Exception as e: print(f"Error enviando UPDATE a {original_shooter_id}: {e}")
                
                result_char = parts[3] 
                with turn_lock:
                    if not game_active: continue # Re-chequear dentro del lock
                    if result_char == 'H': 
                        current_turn_player_id = original_shooter_id 
                        if current_turn_player_id in clients and clients[current_turn_player_id].get('conn'):
                            try: clients[current_turn_player_id]['conn'].sendall(b"YOUR_TURN_AGAIN")
                            except Exception as e: print(f"Error enviando YOUR_TURN_AGAIN a {current_turn_player_id}: {e}")
                        player_who_was_hit_id = player_id
                        if player_who_was_hit_id in clients and clients[player_who_was_hit_id].get('conn'):
                             try: clients[player_who_was_hit_id]['conn'].sendall(b"OPPONENT_TURN_MSG") 
                             except Exception as e: print(f"Error enviando OPPONENT_TURN_MSG a {player_who_was_hit_id}: {e}")
                        print(f"Impacto de {original_shooter_id}. {original_shooter_id} sigue jugando.")
                    else: 
                        current_turn_player_id = player_id 
                        if current_turn_player_id in clients and clients[current_turn_player_id].get('conn'):
                             try: clients[current_turn_player_id]['conn'].sendall(b"YOUR_TURN_AGAIN")
                             except Exception as e: print(f"Error enviando YOUR_TURN_AGAIN a {current_turn_player_id}: {e}")
                        other_player_for_turn_notify = original_shooter_id
                        if other_player_for_turn_notify in clients and clients[other_player_for_turn_notify].get('conn'):
                            try: clients[other_player_for_turn_notify]['conn'].sendall(b"OPPONENT_TURN_MSG")
                            except Exception as e: print(f"Error enviando OPPONENT_TURN_MSG a {other_player_for_turn_notify}: {e}")
                        print(f"Fallo de {original_shooter_id}. Turno para {current_turn_player_id}.")
                        
            elif command == "I_SUNK_MY_SHIP": # NUEVO COMANDO
                if not game_active:
                    print(f"DEBUG [{player_id}]: I_SUNK_MY_SHIP ignorado, juego no activo.")
                    continue
                
                try:
                    ship_name = parts[1]
                    # parts[2:] contendrá todas las coordenadas como strings ['r1', 'c1', 'r2', 'c2', ...]
                    # Las unimos de nuevo para pasarlas tal cual al otro cliente.
                    coords_str_payload = " ".join(parts[2:]) 
                    print(f"DEBUG [{player_id}]: Recibido I_SUNK_MY_SHIP para {ship_name} con coords payload: '{coords_str_payload}'")


                    # Este mensaje viene del jugador CUYO barco fue hundido (player_id).
                    # Necesitamos notificar al OTRO jugador (el que disparó).
                    shooter_player_id = "P2" if player_id == "P1" else "P1"
                    
                    notification_msg = f"OPPONENT_SHIP_SUNK {ship_name} {coords_str_payload}"
                    
                    if shooter_player_id in clients and clients[shooter_player_id].get('conn'):
                        try:
                            clients[shooter_player_id]['conn'].sendall(notification_msg.encode())
                            print(f"INFO [{player_id}]: Notificado a {shooter_player_id} que hundió un {ship_name} del oponente.")
                        except Exception as e:
                            print(f"ERROR [{player_id}]: Fallo al enviar OPPONENT_SHIP_SUNK a {shooter_player_id}: {e}")
                    else:
                        print(f"WARN [{player_id}]: No se pudo notificar a {shooter_player_id} sobre el hundimiento (no conectado o no encontrado).")
                except IndexError:
                    print(f"ERROR [{player_id}]: Comando I_SUNK_MY_SHIP malformado: {data}")
                except Exception as e:
                    print(f"ERROR [{player_id}]: Excepción procesando I_SUNK_MY_SHIP: {e}")
                    
            elif command == "GAME_WON":
                print(f"DEBUG SERVER [{player_id}]: Comando GAME_WON recibido. Estado actual de 'game_active': {game_active}") # DEBUG
                if game_active: 
                    winner_id = player_id
                    loser_id = "P2" if winner_id == "P1" else "P1"
                    print(f"INFO [{player_id}]: Procesando GAME_WON. Ganador: {winner_id}, Perdedor: {loser_id}.")
                    with turn_lock:
                        if game_active : 
                            game_active = False 
                            current_turn_player_id = None 
                        else:
                            print(f"DEBUG SERVER [{player_id}]: GAME_WON procesado, pero 'game_active' ya era False dentro del lock. No se enviarán mensajes GAME_OVER desde aquí.")
                            break # El juego ya terminó por otro medio
                    
                    # Enviar mensajes de fin de juego (asegurarse que game_active fue puesto a False ANTES de esto por este hilo)
                    # Es posible que el otro hilo (del perdedor) termine por desconexión del cliente al recibir GAME_OVER LOSE.
                    if winner_id in clients and clients[winner_id].get('conn'):
                        try: clients[winner_id]['conn'].sendall(b"GAME_OVER WIN"); print(f"DEBUG SERVER [{player_id}]: Enviado GAME_OVER WIN a {winner_id}")
                        except Exception as e: print(f"ERROR SERVER [{player_id}]: Fallo al enviar GAME_OVER WIN a {winner_id}: {e}")
                    
                    if loser_id in clients and clients[loser_id].get('conn'):
                        try: clients[loser_id]['conn'].sendall(b"GAME_OVER LOSE"); print(f"DEBUG SERVER [{player_id}]: Enviado GAME_OVER LOSE a {loser_id}")
                        except Exception as e: print(f"ERROR SERVER [{player_id}]: Fallo al enviar GAME_OVER LOSE a {loser_id}: {e}")
                    
                    time.sleep(0.5) 
                    print(f"DEBUG SERVER [{player_id}]: Hilo del jugador {winner_id} terminando después de procesar GAME_WON.")
                    break 
                else:
                    print(f"WARN SERVER [{player_id}]: GAME_WON ignorado porque 'game_active' es False.")

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
                notify_other_player(player_left_id, b"OPPONENT_LEFT")
            
            # Marcar el juego como inactivo ya que un jugador se fue
            with turn_lock: # Asegurar que estas variables se actualizan de forma segura
                if game_active : # Solo si seguía activo
                    game_active = False
                    current_turn_player_id = None

        # Si no quedan clientes, resetear el estado del servidor para una nueva partida.
        if not clients: 
            print("Todos los jugadores se han desconectado. Reseteando estado del servidor para una nueva partida.")
            player_setup_complete["P1"] = False
            player_setup_complete["P2"] = False
            with turn_lock: # Asegurar que estas variables se actualizan de forma segura
                game_active = False 
                current_turn_player_id = None

def player_id_exists_in_clients_dict(clients_dict):
    """Chequea si P1 o P2 aún existen en el diccionario de clientes."""
    return "P1" in clients_dict or "P2" in clients_dict


def start_server():
    global clients, player_setup_complete, game_active, current_turn_player_id

    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((HOST, PORT))
    except OSError as e:
        print(f"Error al enlazar el socket en {HOST}:{PORT} - {e}")
        return
        
    server_socket.listen(2)
    print(f"Servidor de Batalla Naval escuchando en {HOST}:{PORT}")
    
    while True:
        if len(clients) < 2:
            if not clients: # Si el diccionario está realmente vacío
                print("Servidor listo y esperando jugadores...")

            try:
                conn, addr = server_socket.accept()
            except OSError: # Socket del servidor cerrado
                print("Socket del servidor cerrado. Terminando bucle de aceptación.")
                break
            except Exception as e:
                print(f"Error aceptando conexión: {e}")
                continue


            assigned_player_id = None
            # Asignar P1 si no está, luego P2 si no está.
            if "P1" not in clients:
                assigned_player_id = "P1"
            elif "P2" not in clients: # Implies P1 está en clients
                assigned_player_id = "P2"
            
            if assigned_player_id:
                # Reiniciar estado de setup para el nuevo jugador si es necesario
                player_setup_complete[assigned_player_id] = False

                clients[assigned_player_id] = {'conn': conn, 'addr': addr}
                thread = threading.Thread(target=handle_client_connection, args=(conn, assigned_player_id), daemon=True)
                thread.start()
                
                if len(clients) == 2:
                    print("Dos jugadores conectados. La fase de configuracion comenzara para cada uno.")
            else:
                # No debería llegar aquí si len(clients) < 2, pero por si acaso.
                print(f"Conexión de {addr} rechazada, slots P1/P2 ocupados o estado inconsistente.")
                try:
                    conn.sendall(b"MSG Servidor actualmente lleno o en mantenimiento. Intenta mas tarde.")
                    conn.close()
                except: pass
        else: 
            # Hay dos clientes, esperar a que el juego termine o se desconecten.
            # El `finally` en `handle_client_connection` limpiará `clients`.
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