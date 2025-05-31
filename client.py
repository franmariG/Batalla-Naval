# client.py
import pygame
import socket
import threading
import sys
import time
import os # Para construir rutas a los archivos de sonido

# --- Configuración de Conexión ---
SERVER_IP = "169.254.110.221"
PORT = 8080

# --- Configuración de Pygame ---
SCREEN_WIDTH = 900 
SCREEN_HEIGHT = 500 
GRID_SIZE = 10      
CELL_SIZE = 30      

BOARD_OFFSET_X_MY = 50
BOARD_OFFSET_Y = 80
BOARD_OFFSET_X_OPPONENT = BOARD_OFFSET_X_MY + GRID_SIZE * CELL_SIZE + 70

MY_BOARD_RECT = pygame.Rect(BOARD_OFFSET_X_MY, BOARD_OFFSET_Y, GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)
OPPONENT_BOARD_RECT = pygame.Rect(BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y, GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE_WATER = (100, 149, 237) 
GREEN_PREVIEW_BORDER = (0, 200, 0) 
RED_PREVIEW_BORDER = (200, 0, 0)
RED_HIT = (200, 0, 0)       
YELLOW_MISS = (200, 200, 0) 
BOARD_GRID_COLOR = (50, 50, 150)
TEXT_COLOR = (230, 230, 230)
STATUS_TEXT_COLOR = WHITE

STATE_CONNECTING = "CONNECTING"
STATE_WAITING_FOR_PLAYER = "WAITING_FOR_PLAYER"
STATE_SETUP_SHIPS = "SETUP_SHIPS"
STATE_WAITING_OPPONENT_SETUP = "WAITING_OPPONENT_SETUP"
STATE_YOUR_TURN = "YOUR_TURN"
STATE_OPPONENT_TURN = "OPPONENT_TURN"
STATE_GAME_OVER = "GAME_OVER"

SHIPS_CONFIG = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3), ("Submarine", 3), ("Destroyer", 2)]
TOTAL_SHIP_CELLS = sum(size for _, size in SHIPS_CONFIG)

screen = None
font_large = None
font_medium = None
font_small = None
client_socket = None 
player_id_str = None 
current_game_state = STATE_CONNECTING
status_bar_message = "Conectando al servidor..."

my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
opponent_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] 

ships_to_place_list = list(SHIPS_CONFIG) 
current_ship_placement_index = 0
current_ship_orientation = 'H' 
# NUEVO: Para almacenar información detallada de los barcos colocados
my_placed_ships_detailed = [] 
opponent_sunk_ships_log = [] # NUEVO: Para barcos hundidos del oponente
                             # Estructura: {"name": str, "size": int, "coords": [(r,c),...], "orientation": 'H'/'V' o None}

# Estructura de cada elemento en my_placed_ships_detailed:
# { "name": str, "size": int, "coords": [(r,c), ...], "orientation": 'H'/'V', 
#   "is_sunk": False, "image_rect_on_board": pygame.Rect, "base_image_key": str }

# NUEVO: Diccionarios para imágenes
ship_images = {} # Almacenará imágenes cargadas y rotadas: {"Carrier": {"H": surface, "V": surface}, ...}
# No necesitamos un `sunk_ship_images` separado, generaremos la versión oscura bajo demanda.

# NUEVO: Nombres de archivo de imágenes (¡DEBES TENER ESTOS ARCHIVOS!)
SHIP_IMAGE_FILES = {
    "Carrier": "carrier.png",
    "Battleship": "battleship.png",
    "Cruiser": "cruiser.png",
    "Submarine": "submarine.png",
    "Destroyer": "destroyer.png"
}
# Ruta base para archivos (scripts, sonidos, imágenes)
BASE_PATH = os.path.dirname(os.path.abspath(__file__))
assets_path = os.path.join(BASE_PATH, "assets")

# Variables para sonidos
hit_sound = None
miss_sound = None
sunk_sound = None # NUEVO

# --- Comunicación con el Servidor ---
player_name = ""  # Nuevo: nombre del jugador
opponent_name = ""  # Nuevo: nombre del oponente

def prompt_for_player_name():
    """Muestra una pantalla para que el usuario escriba su nombre antes de conectarse."""
    global screen, font_large, font_medium, font_small
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Batalla Naval - Ingresa tu nombre")
    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 36)
    font_small = pygame.font.Font(None, 28)
    input_box = pygame.Rect(SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2, 300, 48)
    color_inactive = pygame.Color('lightskyblue3')
    color_active = pygame.Color('dodgerblue2')
    color = color_inactive
    active = False
    text = ""
    done = False

    while not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if input_box.collidepoint(event.pos):
                    active = not active
                else:
                    active = False
                color = color_active if active else color_inactive
            if event.type == pygame.KEYDOWN:
                if active:
                    if event.key == pygame.K_RETURN:
                        if text.strip():
                            done = True
                    elif event.key == pygame.K_BACKSPACE:
                        text = text[:-1]
                    elif len(text) < 20 and event.unicode.isprintable():
                        text += event.unicode

        screen.fill(BLACK)
        draw_text_on_screen(screen, "Ingresa tu nombre:", (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 60), font_medium)
        txt_surface = font_large.render(text, True, color)
        width = max(300, txt_surface.get_width()+10)
        input_box.w = width
        screen.blit(txt_surface, (input_box.x+5, input_box.y+5))
        pygame.draw.rect(screen, color, input_box, 2)
        draw_text_on_screen(screen, "Presiona Enter para continuar", (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 + 60), font_small)
        pygame.display.flip()
    return text.strip()

def connect_to_server_thread():
    global client_socket, current_game_state, status_bar_message, player_id_str, player_name
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Intentando conectar a {SERVER_IP}:{PORT}...")
        client_socket.connect((SERVER_IP, PORT))
        # Enviar el nombre del jugador al servidor
        if player_name:
            try:
                client_socket.sendall(f"PLAYER_NAME {player_name}".encode())
            except Exception as e:
                print(f"Error enviando nombre de jugador: {e}")
        status_bar_message = "Conectado. Esperando asignacion..."
        threading.Thread(target=listen_for_server_messages, daemon=True).start()
    except ConnectionRefusedError:
        status_bar_message = "Error: Conexion rechazada por el servidor."
        current_game_state = STATE_GAME_OVER
    except Exception as e:
        status_bar_message = f"Error de conexion: {e}"
        current_game_state = STATE_GAME_OVER

def listen_for_server_messages():
    global current_game_state, status_bar_message, player_id_str, my_board_data, opponent_board_data, client_socket
    global opponent_sunk_ships_log # Asegurar acceso global
    global opponent_name
    
    # Búfer para almacenar datos incompletos del servidor
    data_buffer = ""
    # Bucle mientras el juego no haya terminado Y el socket exista
    while current_game_state != STATE_GAME_OVER and client_socket: 
        try:
            data_bytes = client_socket.recv(1024)
            if not data_bytes:
                if current_game_state != STATE_GAME_OVER : 
                    status_bar_message = "Desconectado del servidor (recv vacío)."
                    current_game_state = STATE_GAME_OVER
                break 
            
            # Añadir los nuevos datos al búfer
            data_buffer += data_bytes.decode()
            
           # Procesar todos los mensajes completos (separados por nueva línea)
            # El servidor debería enviar cada mensaje terminado con \n
            while '\n' in data_buffer:
                # Extraer el primer mensaje completo y quitarlo del búfer
                message, data_buffer = data_buffer.split('\n', 1)
                message = message.strip() # Limpiar espacios en blanco
                if not message:
                    continue

                print(f"Servidor dice: {message}")
                parts = message.split()
                if not parts:
                    continue
                command = parts[0]


            if command == "MSG":
                    status_bar_message = ' '.join(parts[1:])
            elif command == "PLAYER_ID":
                player_id_str = parts[1]
            elif command == "OPPONENT_NAME":
                opponent_name = ' '.join(parts[1:])
            elif command == "SETUP_YOUR_BOARD":
                current_game_state = STATE_SETUP_SHIPS
                status_bar_message = f"{player_id_str}: Coloca tus barcos. 'R' para rotar. Click para colocar."
            elif command == "START_GAME": 
                starting_player = parts[1]
                if starting_player == player_id_str:
                    current_game_state = STATE_YOUR_TURN
                    status_bar_message = "¡Tu turno! Dispara en el tablero enemigo." 
                else:
                    current_game_state = STATE_OPPONENT_TURN
                    status_bar_message = f"Turno del oponente ({starting_player}). Esperando..."
            elif command == "SHOT": 
                r, c = int(parts[1]), int(parts[2])
                shot_result_char = 'M' 
                if my_board_data[r][c] == 1: 
                    my_board_data[r][c] = 'H' 
                    shot_result_char = 'H'
                    if hit_sound: hit_sound.play()
                    # NUEVO: Comprobar si este impacto hundió uno de nuestros barcos
                    check_and_update_my_sunk_ships() 
                elif my_board_data[r][c] == 0: 
                    my_board_data[r][c] = 'M' 
                    if miss_sound: miss_sound.play() # Sonido de fallo en nuestra agua
                
                send_message_to_server(f"RESULT {r} {c} {shot_result_char}")

            elif command == "UPDATE": 
                r, c = int(parts[1]), int(parts[2])
                result_char = parts[3] 
                
                current_cell_state_on_opponent_board = opponent_board_data[r][c]

                if result_char == 'H':
                    # Solo marcar como 'H' si no es ya 'S' (parte de un barco ya confirmado hundido).
                    # Si es 'S', significa que OPPONENT_SHIP_SUNK llegó primero para esta celda.
                    if current_cell_state_on_opponent_board != 'S':
                        opponent_board_data[r][c] = 'H'
                    
                    if hit_sound: hit_sound.play()

                    # Chequear victoria DESPUÉS de actualizar el estado de la celda.
                    is_victory = check_if_opponent_is_defeated(opponent_board_data)
                    hits_count = 0 
                    for r_debug in range(GRID_SIZE):
                        for c_debug in range(GRID_SIZE):
                            if opponent_board_data[r_debug][c_debug] == 'H' or opponent_board_data[r_debug][c_debug] == 'S':
                                hits_count +=1
                    print(f"DEBUG CLIENT (en UPDATE): Chequeando victoria. Celdas H/S oponente: {hits_count}/{TOTAL_SHIP_CELLS}. ¿Victoria?: {is_victory}")

                    if is_victory and current_game_state != STATE_GAME_OVER:
                        print(f"DEBUG CLIENT (en UPDATE): ¡Victoria local detectada! Enviando GAME_WON.")
                        send_message_to_server("GAME_WON")
                        # No cambiar current_game_state aquí, esperar GAME_OVER del servidor.
                
                elif result_char == 'M':
                    # Solo marcar como 'M' si no es 'S'. Un fallo no debería afectar un barco hundido.
                    if current_cell_state_on_opponent_board != 'S':
                        opponent_board_data[r][c] = 'M'
                    status_bar_message = f"Agua en ({r},{c})." 
                    if miss_sound: miss_sound.play()
                
                # El mensaje de status_bar_message se actualizará con YOUR_TURN_AGAIN o OPPONENT_TURN_MSG
            elif command == "OPPONENT_SHIP_SUNK": 
                try:
                    ship_name = parts[1]
                    flat_coords = [int(p) for p in parts[2:]]
                    sunk_ship_coords_tuples = []
                    for i in range(0, len(flat_coords), 2):
                        sunk_ship_coords_tuples.append((flat_coords[i], flat_coords[i+1]))

                    status_bar_message = f"¡Hundiste el {ship_name} del oponente!"
                    print(f"INFO: Servidor informa: El {ship_name} del oponente en {sunk_ship_coords_tuples} ha sido hundido.")
                    if sunk_sound: sunk_sound.play()

                    sunk_ship_size = 0
                    for cfg_name, cfg_size in SHIPS_CONFIG:
                        if cfg_name == ship_name:
                            sunk_ship_size = cfg_size
                            break
                    
                    guessed_orientation = None
                    if len(sunk_ship_coords_tuples) > 0:
                        all_r_same = all(coord[0] == sunk_ship_coords_tuples[0][0] for coord in sunk_ship_coords_tuples)
                        all_c_same = all(coord[1] == sunk_ship_coords_tuples[0][1] for coord in sunk_ship_coords_tuples)
                        if all_r_same and not all_c_same : guessed_orientation = 'H'
                        elif not all_r_same and all_c_same : guessed_orientation = 'V'
                        elif sunk_ship_size == 1: guessed_orientation = 'H'

                    opponent_sunk_ships_log.append({
                        "name": ship_name, "size": sunk_ship_size,
                        "coords": sunk_ship_coords_tuples, "orientation": guessed_orientation
                    })

                    # Marcar TODAS las celdas de este barco hundido como 'S'
                    # Esto asegura que incluso la celda del último impacto sea 'S'.
                    for r_s, c_s in sunk_ship_coords_tuples:
                        if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE:
                            opponent_board_data[r_s][c_s] = 'S' 
                    
                    # AHORA, chequear victoria OTRA VEZ, ya que el estado 'S' es definitivo.
                    is_victory_after_sunk = check_if_opponent_is_defeated(opponent_board_data)
                    hits_count_after_sunk = 0
                    for r_debug in range(GRID_SIZE):
                        for c_debug in range(GRID_SIZE):
                            if opponent_board_data[r_debug][c_debug] == 'H' or opponent_board_data[r_debug][c_debug] == 'S':
                                hits_count_after_sunk +=1
                    print(f"DEBUG CLIENT (en OPPONENT_SHIP_SUNK): Chequeando victoria. Celdas H/S oponente: {hits_count_after_sunk}/{TOTAL_SHIP_CELLS}. ¿Victoria?: {is_victory_after_sunk}")

                    if is_victory_after_sunk and current_game_state != STATE_GAME_OVER:
                        print(f"DEBUG CLIENT (en OPPONENT_SHIP_SUNK): ¡Victoria local detectada! Enviando GAME_WON.")
                        send_message_to_server("GAME_WON")

                except Exception as e:
                    print(f"Error procesando OPPONENT_SHIP_SUNK: {e} - Datos: {message}")

            elif command == "YOUR_TURN_AGAIN": 
                current_game_state = STATE_YOUR_TURN
                # Mantener el mensaje de impacto/agua si fue el último, o poner "Tu turno"
                if not status_bar_message.startswith("¡Impacto") and not status_bar_message.startswith("Agua"):
                    status_bar_message = "¡Tu turno! Dispara."
                else: # Añadir al mensaje de impacto/agua que sigue siendo nuestro turno
                    status_bar_message += " ¡Sigue tu turno!"


            elif command == "OPPONENT_TURN_MSG": 
                current_game_state = STATE_OPPONENT_TURN
                status_bar_message = "Turno del oponente. Esperando..."
            
            elif command == "GAME_OVER": 
                current_game_state = STATE_GAME_OVER # Esto detendrá el bucle listen_for_server_messages
                if parts[1] == "WIN":
                    status_bar_message = "¡HAS GANADO LA PARTIDA! :D"
                else:
                    status_bar_message = "Has perdido. Mejor suerte la proxima. :("
                # El bucle de escucha terminará debido a current_game_state
                # El socket se cerrará al salir de la aplicación o si el servidor lo cierra.
                # No es necesario cerrar el client_socket aquí explícitamente,
                # ya que podría haber otros hilos o la app principal aún usándolo o queriendo limpiarlo al final.
                # Dejar que el programa principal lo cierre al salir.
                # client_socket.close() # Podría ser problemático si se cierra prematuramente

            elif command == "OPPONENT_LEFT":
                if current_game_state != STATE_GAME_OVER : # Solo si el juego no ha terminado por otra razón
                    status_bar_message = "El oponente se ha desconectado. ¡Ganas por defecto!"
                    current_game_state = STATE_GAME_OVER # Esto detendrá el bucle

        except ConnectionResetError:
            if current_game_state != STATE_GAME_OVER:
                status_bar_message = "Conexion perdida con el servidor (reset)."
                current_game_state = STATE_GAME_OVER
            break 
        except socket.error as e: # Otros errores de socket
            if current_game_state != STATE_GAME_OVER:
                status_bar_message = f"Error de socket: {e}"
                current_game_state = STATE_GAME_OVER
            break
        except Exception as e:
            print(f"Error escuchando al servidor: {e}")
            if current_game_state != STATE_GAME_OVER:
                status_bar_message = f"Error de red general: {e}"
                current_game_state = STATE_GAME_OVER
            break
    
    print(f"Hilo de escucha del cliente ({player_id_str or 'N/A'}) terminado.")
    # Si el socket sigue abierto y el juego terminó, se podría cerrar aquí,
    # pero es más seguro dejar que el hilo principal de Pygame lo haga al salir.
    # if client_socket:
    #     try: client_socket.close()
    #     except: pass


def send_message_to_server(message):
    if client_socket and client_socket.fileno() != -1: # Chequear si el socket no está cerrado
        try:
            # ANTES:
            # client_socket.sendall(message.encode())

            # AHORA (añadimos f-string y \n):
            client_socket.sendall(f"{message}\n".encode())
        except socket.error as e:
            print(f"Error enviando mensaje: {e}")
            global status_bar_message, current_game_state
            if current_game_state != STATE_GAME_OVER: # Solo si no está ya en Game Over
                status_bar_message = "Error de red al enviar."
                current_game_state = STATE_GAME_OVER
        except Exception as e: # Otras excepciones
            print(f"Excepción general al enviar mensaje: {e}")
            if current_game_state != STATE_GAME_OVER:
                status_bar_message = "Error desconocido al enviar."
                current_game_state = STATE_GAME_OVER

# --- NUEVA Función para Oscurecer Imágenes ---
def create_darkened_image(original_image_surface, darkness_alpha=128):
    if original_image_surface is None: return None
    # Crea una copia para no modificar la original si se reutiliza
    darkened_surface = original_image_surface.copy()
    # Crea una capa de oscurecimiento
    overlay = pygame.Surface(darkened_surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, darkness_alpha)) # Negro semi-transparente
    darkened_surface.blit(overlay, (0, 0))
    return darkened_surface

# --- Función check_and_update_my_sunk_ships ACTUALIZADA (sin cambios funcionales respecto a la última, solo el envío de mensaje) ---
def check_and_update_my_sunk_ships():
    global my_placed_ships_detailed, my_board_data, status_bar_message, sunk_sound
    for ship_info in my_placed_ships_detailed:
        if not ship_info["is_sunk"]: 
            hits_on_ship = 0
            for r_coord, c_coord in ship_info["coords"]:
                if my_board_data[r_coord][c_coord] == 'H':
                    hits_on_ship += 1
            if hits_on_ship == ship_info["size"]:
                ship_info["is_sunk"] = True
                sunk_ship_name = ship_info["name"]
                print(f"INFO: ¡Mi {sunk_ship_name} ha sido hundido!")
                coords_list_for_server = []
                for r_s, c_s in ship_info["coords"]:
                    coords_list_for_server.append(str(r_s))
                    coords_list_for_server.append(str(c_s))
                coords_payload_str = " ".join(coords_list_for_server)
                send_message_to_server(f"I_SUNK_MY_SHIP {sunk_ship_name} {coords_payload_str}")
                # print(f"DEBUG: Enviado I_SUNK_MY_SHIP {sunk_ship_name} con coords: {coords_payload_str}") # Ya lo tenías
                if sunk_sound: sunk_sound.play()

# --- Lógica y Dibujo de Pygame ---
def draw_game_grid(surface, offset_x, offset_y, board_matrix, is_my_board):
    # 1. Dibujar celdas de agua y rejilla (sin cambios)
    for r_idx in range(GRID_SIZE):
        for c_idx in range(GRID_SIZE):
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(surface, BLUE_WATER, cell_rect) 
            pygame.draw.rect(surface, BOARD_GRID_COLOR, cell_rect, 1) 

    # 2. Dibujar IMÁGENES de barcos (propios o del oponente hundidos)
    # Esta sección se dibuja PRIMERO para que los marcadores H, M, S queden ENCIMA.
    if is_my_board:
        for ship_detail in my_placed_ships_detailed:
            # ... (lógica existente para dibujar tus imágenes de barcos, normales o hundidos/oscurecidos)
            ship_name = ship_detail["base_image_key"] 
            orientation = ship_detail["orientation"]
            ship_img_dict = ship_images.get(ship_name)
            if ship_img_dict:
                current_ship_image = ship_img_dict.get(orientation)
                if current_ship_image:
                    image_to_draw = create_darkened_image(current_ship_image) if ship_detail["is_sunk"] else current_ship_image
                    if image_to_draw and ship_detail.get("image_rect_on_board"):
                        surface.blit(image_to_draw, ship_detail["image_rect_on_board"].topleft)
    else: # Es el tablero del oponente
        for sunk_info in opponent_sunk_ships_log:
            # ... (lógica existente para dibujar imágenes de barcos hundidos del oponente)
            ship_name = sunk_info["name"]
            orientation = sunk_info.get("orientation")
            coords = sunk_info["coords"]
            if not coords or orientation is None: continue
            ship_img_data = ship_images.get(ship_name)
            if ship_img_data:
                base_image = ship_img_data.get(orientation)
                if base_image:
                    darkened_opponent_ship_img = create_darkened_image(base_image, darkness_alpha=150)
                    if darkened_opponent_ship_img:
                        min_r = min(r for r,c in coords)
                        min_c = min(c for r,c in coords)
                        screen_x = offset_x + min_c * CELL_SIZE
                        screen_y = offset_y + min_r * CELL_SIZE
                        surface.blit(darkened_opponent_ship_img, (screen_x, screen_y))
    
    # 3. Dibujar MARCADORES de celda (H, M, S) ENCIMA de las imágenes
    for r_idx in range(GRID_SIZE):
        for c_idx in range(GRID_SIZE):
            cell_val = board_matrix[r_idx][c_idx] 
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            
            if cell_val == 'H': 
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.top + 5), (cell_rect.right - 5, cell_rect.bottom - 5), 4)
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.bottom - 5), (cell_rect.right - 5, cell_rect.top + 5), 4)
            elif cell_val == 'M': 
                pygame.draw.circle(surface, YELLOW_MISS, cell_rect.center, CELL_SIZE // 4)
            elif cell_val == 'S': 
                # Fondo verde para depurar y resaltar
                debug_fill_s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA)
                debug_fill_s.fill((0, 80, 0, 100)) # Verde oscuro semi-transparente
                surface.blit(debug_fill_s, cell_rect.topleft)

                line_thickness_sunk = 5 
                padding_sunk = 5 
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.top + padding_sunk), (cell_rect.right - padding_sunk, cell_rect.bottom - padding_sunk), line_thickness_sunk)
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.bottom - padding_sunk), (cell_rect.right - padding_sunk, cell_rect.top + padding_sunk), line_thickness_sunk)
                # print(f"DEBUG_DRAW: Dibujando 'S' marker (X gruesa + fondo verde) en celda ({r_idx},{c_idx})")


def draw_text_on_screen(surface, text_content, position, font_to_use, color=TEXT_COLOR):
    text_surface = font_to_use.render(text_content, True, color)
    surface.blit(text_surface, position)

def get_grid_cell_from_mouse(mouse_coords, board_start_x, board_start_y):
    mouse_x, mouse_y = mouse_coords
    if board_start_x <= mouse_x < board_start_x + GRID_SIZE * CELL_SIZE and \
       board_start_y <= mouse_y < board_start_y + GRID_SIZE * CELL_SIZE:
        col = (mouse_x - board_start_x) // CELL_SIZE
        row = (mouse_y - board_start_y) // CELL_SIZE
        return row, col
    return None, None

def can_place_ship_at(board, r, c, ship_size, orientation):
    ship_coords = []
    for i in range(ship_size):
        current_r, current_c = r, c
        if orientation == 'H': current_c += i
        else: current_r += i
        if not (0 <= current_r < GRID_SIZE and 0 <= current_c < GRID_SIZE): return False, []
        if board[current_r][current_c] == 1: return False, [] 
        ship_coords.append((current_r, current_c))
    return True, ship_coords

def attempt_to_place_ship(board, r, c, ship_config_tuple):
    global current_ship_placement_index, my_placed_ships_detailed, current_game_state, status_bar_message
    
    ship_name, ship_size = ship_config_tuple
    can_place, temp_coords = can_place_ship_at(board, r, c, ship_size, current_ship_orientation)

    if can_place:
        actual_ship_coords = []
        for sr, sc in temp_coords:
            board[sr][sc] = 1 
            actual_ship_coords.append((sr,sc))
        
        # Calcular el Rect de la imagen para dibujarla en el tablero
        # (r,c) es la celda superior-izquierda del barco.
        img_top_left_x = BOARD_OFFSET_X_MY + c * CELL_SIZE
        img_top_left_y = BOARD_OFFSET_Y + r * CELL_SIZE
        
        # Obtener dimensiones de la imagen actual para el Rect
        # Esto asume que ship_images ya está poblado con imágenes escaladas
        ship_img_data = ship_images.get(ship_name)
        width, height = (ship_size * CELL_SIZE, CELL_SIZE) # Default a horizontal
        if ship_img_data:
            actual_image = ship_img_data.get(current_ship_orientation)
            if actual_image:
                width = actual_image.get_width()
                height = actual_image.get_height()
        
        ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, width, height)

        my_placed_ships_detailed.append({
            "name": ship_name, # Usado como clave para mensajes, etc.
            "base_image_key": ship_name, # Usado para buscar en ship_images
            "size": ship_size,
            "coords": actual_ship_coords, 
            "orientation": current_ship_orientation,
            "is_sunk": False,
            "image_rect_on_board": ship_screen_rect # Rect en coordenadas de pantalla
        })
        
        current_ship_placement_index += 1
        if current_ship_placement_index >= len(ships_to_place_list):
            send_message_to_server("READY_SETUP")
            current_game_state = STATE_WAITING_OPPONENT_SETUP
            status_bar_message = "Barcos colocados. Esperando al oponente..."
        else:
            next_ship_name = ships_to_place_list[current_ship_placement_index][0]
            status_bar_message = f"Coloca: {next_ship_name}. 'R' para rotar."
        return True
    return False

def draw_ship_placement_preview(surface, mouse_pos):
    if current_game_state == STATE_SETUP_SHIPS and current_ship_placement_index < len(ships_to_place_list):
        ship_name, ship_size = ships_to_place_list[current_ship_placement_index]
        row, col = get_grid_cell_from_mouse(mouse_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y)

        if row is not None and col is not None: # Mouse sobre el tablero de colocación
            ship_img_data = ship_images.get(ship_name)
            if ship_img_data:
                preview_img_original = ship_img_data.get(current_ship_orientation)
                if preview_img_original:
                    preview_img = preview_img_original.copy()
                    preview_img.set_alpha(180) # Semi-transparente para previsualización

                    # Coordenadas de pantalla para la esquina superior-izquierda de la imagen
                    screen_x = BOARD_OFFSET_X_MY + col * CELL_SIZE
                    screen_y = BOARD_OFFSET_Y + row * CELL_SIZE
                    
                    surface.blit(preview_img, (screen_x, screen_y))

                    # Dibujar borde alrededor de la imagen de previsualización
                    can_place_flag, _ = can_place_ship_at(my_board_data, row, col, ship_size, current_ship_orientation)
                    border_color = GREEN_PREVIEW_BORDER if can_place_flag else RED_PREVIEW_BORDER
                    img_rect_for_border = pygame.Rect(screen_x, screen_y, preview_img.get_width(), preview_img.get_height())
                    pygame.draw.rect(surface, border_color, img_rect_for_border, 2)
                    
# --- check_if_opponent_is_defeated (YA MODIFICADA para contar H y S) ---
def check_if_opponent_is_defeated(opponent_b):
    hit_and_sunk_cells_on_opponent = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if opponent_b[r][c] == 'H' or opponent_b[r][c] == 'S': # Cuenta H y S
                hit_and_sunk_cells_on_opponent += 1
    if hit_and_sunk_cells_on_opponent >= TOTAL_SHIP_CELLS:
        # El print de DEBUG ya está en los puntos de llamada
        return True
    return False
    
    # Comprobar si el total de celdas impactadas/hundidas alcanza el total de celdas de todos los barcos
    if hit_and_sunk_cells_on_opponent >= TOTAL_SHIP_CELLS:
        print(f"DEBUG: ¡Victoria detectada! Celdas impactadas/hundidas: {hit_and_sunk_cells_on_opponent}/{TOTAL_SHIP_CELLS}")
        return True
    return False

def game_main_loop():
    global screen, font_large, font_medium, font_small, current_game_state, status_bar_message
    global current_ship_orientation, SERVER_IP, hit_sound, miss_sound, client_socket, player_name, opponent_name

    if len(sys.argv) > 1: SERVER_IP = sys.argv[1]
    print(f"Usando IP del servidor: {SERVER_IP}")

    # --- Pedir nombre antes de inicializar el juego ---
    player_name = prompt_for_player_name()

    pygame.init()
    
    # --- Mueve esta línea ARRIBA de la carga de imágenes ---
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(f"Batalla Naval Cliente")
    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 36)
    font_small = pygame.font.Font(None, 28)
    # --- Fin del movimiento ---

    # --- Inicializar Sonidos ---
    pygame.mixer.init()
    try:
        hit_sound_file = os.path.join(assets_path, "acertado.wav")
        miss_sound_file = os.path.join(assets_path, "fallido.wav")
        sunk_sound_file = os.path.join(assets_path, "hundido.wav") # NUEVO
        
        if os.path.exists(hit_sound_file): hit_sound = pygame.mixer.Sound(hit_sound_file)
        else: print(f"Advertencia: No se encontró {hit_sound_file}")
        
        if os.path.exists(miss_sound_file): miss_sound = pygame.mixer.Sound(miss_sound_file)
        else: print(f"Advertencia: No se encontró {miss_sound_file}")

        if os.path.exists(sunk_sound_file): sunk_sound = pygame.mixer.Sound(sunk_sound_file) # NUEVO
        else: print(f"Advertencia: No se encontró {sunk_sound_file}")

    except Exception as e: print(f"Error cargando sonidos: {e}")
    
     # --- Cargar Imágenes de Barcos ---
    print("Cargando imágenes de barcos...")
    # SHIPS_CONFIG es una lista de tuplas, por ejemplo: [("Carrier", 5), ...]
    # Cuando iteras, 'ship_name_key' será el nombre y 'ship_size' será el número entero.
    for ship_name_key, ship_size in SHIPS_CONFIG: # <-- Cambiado 'ship_detail_tuple' a 'ship_size'
        ship_filename = SHIP_IMAGE_FILES.get(ship_name_key)
        if not ship_filename:
            print(f"   No se definió archivo de imagen para: {ship_name_key}")
            ship_images[ship_name_key] = None # Marcar como no disponible
            continue

        try:
            image_path = os.path.join(assets_path, ship_filename)
            if os.path.exists(image_path):
                # Cargar imagen base (asumimos que es horizontal)
                img_h_original = pygame.image.load(image_path).convert_alpha()
                
                # 'ship_size' ya es el entero (5, 4, 3, etc.)
                # ship_size = ship_detail_tuple[1] # <--- ¡Esta línea causaba el error!
                
                # Escalar imagen horizontal
                scaled_h_width = ship_size * CELL_SIZE
                scaled_h_height = CELL_SIZE
                img_h = pygame.transform.scale(img_h_original, (scaled_h_width, scaled_h_height))
                
                # Crear imagen vertical rotando y escalando la original (o la horizontal escalada)
                img_v_temp = pygame.transform.rotate(img_h_original, 90)
                scaled_v_width = CELL_SIZE
                scaled_v_height = ship_size * CELL_SIZE
                img_v = pygame.transform.scale(img_v_temp, (scaled_v_width, scaled_v_height))
                
                ship_images[ship_name_key] = {"H": img_h, "V": img_v}
                print(f"   Imagen para {ship_name_key} cargada y procesada.")
            else:
                print(f"   Archivo de imagen NO ENCONTRADO para {ship_name_key}: {image_path}")
                ship_images[ship_name_key] = None
        except Exception as e:
            print(f"   Error cargando/procesando imagen para {ship_name_key}: {e}")
            ship_images[ship_name_key] = None

    threading.Thread(target=connect_to_server_thread, daemon=True).start()

    is_game_running = True
    game_clock = pygame.time.Clock()

    while is_game_running:
        mouse_current_pos = pygame.mouse.get_pos()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                is_game_running = False
            
            if current_game_state != STATE_GAME_OVER :
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    if current_game_state == STATE_SETUP_SHIPS and current_ship_placement_index < len(ships_to_place_list):
                        r, c = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y)
                        if r is not None and c is not None:
                            attempt_to_place_ship(my_board_data, r, c, ships_to_place_list[current_ship_placement_index])
                    elif current_game_state == STATE_YOUR_TURN:
                        r, c = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y)
                        if r is not None and c is not None and opponent_board_data[r][c] == 0:
                            send_message_to_server(f"SHOT {r} {c}")
                            status_bar_message = "Disparo enviado. Esperando resultado..."
                
                if event.type == pygame.KEYDOWN:
                    if current_game_state == STATE_SETUP_SHIPS:
                        if event.key == pygame.K_r:
                            current_ship_orientation = 'V' if current_ship_orientation == 'H' else 'H'
                            next_ship_name_display = ""
                            if current_ship_placement_index < len(ships_to_place_list):
                                next_ship_name_display = ships_to_place_list[current_ship_placement_index][0]
                            orientation_text = "Horizontal" if current_ship_orientation == 'H' else "Vertical"
                            status_bar_message = f"Coloca: {next_ship_name_display}. Orient: {orientation_text}. 'R' para rotar."
        
        screen.fill(BLACK)
        # Mostrar el nombre del oponente en la interfaz
        draw_text_on_screen(screen, f"Oponente: {opponent_name or '---'}", (SCREEN_WIDTH - 250, 10), font_small)
        draw_text_on_screen(screen, f"TU FLOTA ({player_id_str or '---'})", (BOARD_OFFSET_X_MY, BOARD_OFFSET_Y - 40), font_medium)
        draw_text_on_screen(screen, "FLOTA ENEMIGA", (BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y - 40), font_medium)
        
        draw_game_grid(screen, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y, my_board_data, True)
        draw_game_grid(screen, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y, opponent_board_data, False)

        if current_game_state == STATE_SETUP_SHIPS:
            draw_ship_placement_preview(screen, mouse_current_pos)
            if current_ship_placement_index < len(ships_to_place_list):
                 ship_name, ship_size_val = ships_to_place_list[current_ship_placement_index]
                 orient_text = 'H' if current_ship_orientation == 'H' else 'V'
                 info_text = f"Colocando: {ship_name} ({ship_size_val}) Orient: {orient_text}"
                 draw_text_on_screen(screen, info_text, (10, SCREEN_HEIGHT - 70), font_small)

        pygame.draw.rect(screen, (30,30,30), (0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40))
        draw_text_on_screen(screen, status_bar_message, (10, SCREEN_HEIGHT - 30), font_small, STATUS_TEXT_COLOR)
        
        pygame.display.flip()
        game_clock.tick(30)

    print("Saliendo del bucle principal de Pygame.")
    if client_socket:
        print("Cerrando socket del cliente...")
        try:
            client_socket.shutdown(socket.SHUT_RDWR)
            client_socket.close()
        except Exception as e:
            print(f"Error al cerrar el socket del cliente: {e}")
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    game_main_loop()