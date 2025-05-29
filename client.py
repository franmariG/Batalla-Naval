# client.py
import pygame
import socket
import threading
import sys
import time
import os # Para construir rutas a los archivos de sonido

# --- Configuración de Conexión ---
SERVER_IP = '172.24.43.50' 
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
def connect_to_server_thread():
    global client_socket, current_game_state, status_bar_message, player_id_str
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Intentando conectar a {SERVER_IP}:{PORT}...")
        client_socket.connect((SERVER_IP, PORT))
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
    
    # Bucle mientras el juego no haya terminado Y el socket exista
    while current_game_state != STATE_GAME_OVER and client_socket: 
        try:
            data_bytes = client_socket.recv(1024)
            if not data_bytes:
                if current_game_state != STATE_GAME_OVER : 
                    status_bar_message = "Desconectado del servidor (recv vacío)."
                    current_game_state = STATE_GAME_OVER
                break 
            
            message = data_bytes.decode()
            # print(f"Servidor dice: {message}") # Descomentar para depuración detallada de mensajes
            parts = message.split()
            command = parts[0]

            if command == "MSG":
                status_bar_message = ' '.join(parts[1:])
            elif command == "PLAYER_ID":
                player_id_str = parts[1]
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
                opponent_board_data[r][c] = result_char
                
                if result_char == 'H':
                    status_bar_message = f"¡Impacto en ({r},{c})!"
                    if hit_sound: hit_sound.play() # Sonido de nuestro acierto
                    if check_if_opponent_is_defeated(opponent_board_data):
                        send_message_to_server("GAME_WON")
                        # No cambiar estado aquí, esperar GAME_OVER del servidor
                        # TODO (Futuro): Si el servidor envía "OPPONENT_SUNK <ship_name>", reproducir sunk_sound aquí
                    # y actualizar visualización del tablero enemigo.
                else: # Miss
                    status_bar_message = f"Agua en ({r},{c})."
                    if miss_sound: miss_sound.play() # Sonido de nuestro fallo
                
                # El mensaje de status_bar_message se actualizará con YOUR_TURN_AGAIN o OPPONENT_TURN_MSG


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
            client_socket.sendall(message.encode())
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

# --- NUEVA Función para Comprobar y Actualizar Barcos Hundidos (Propios) ---
def check_and_update_my_sunk_ships():
    global my_placed_ships_detailed, my_board_data, status_bar_message
    a_ship_was_newly_sunk = False
    for ship_info in my_placed_ships_detailed:
        if not ship_info["is_sunk"]: # Solo chequear los que no están ya hundidos
            hits_on_ship = 0
            for r_coord, c_coord in ship_info["coords"]:
                if my_board_data[r_coord][c_coord] == 'H':
                    hits_on_ship += 1
            
            if hits_on_ship == ship_info["size"]:
                ship_info["is_sunk"] = True
                a_ship_was_newly_sunk = True
                sunk_ship_name = ship_info["name"]
                print(f"INFO: ¡Mi {sunk_ship_name} ha sido hundido!")
                # Actualizar mensaje de estado, pero podría ser sobreescrito rápidamente
                # Es mejor si el mensaje principal de turno o acción toma precedencia.
                # status_bar_message = f"¡Tu {sunk_ship_name} ha sido hundido!" 
                if sunk_sound: 
                    sunk_sound.play()
                # Opcional: Enviar mensaje al servidor de que nuestro barco se hundió
                # send_message_to_server(f"MY_SHIP_SUNK {sunk_ship_name}")
    return a_ship_was_newly_sunk

# --- Lógica y Dibujo de Pygame ---
def draw_game_grid(surface, offset_x, offset_y, board_matrix, is_my_board):
    # 1. Dibujar celdas de agua y rejilla
    for r_idx in range(GRID_SIZE):
        for c_idx in range(GRID_SIZE):
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            pygame.draw.rect(surface, BLUE_WATER, cell_rect) 
            pygame.draw.rect(surface, BOARD_GRID_COLOR, cell_rect, 1) 
    
    # 2. Si es mi tablero, dibujar mis barcos (normales o hundidos)
    if is_my_board:
        for ship_detail in my_placed_ships_detailed:
            ship_name = ship_detail["base_image_key"] # Nombre para buscar en ship_images
            orientation = ship_detail["orientation"]
            ship_img_dict = ship_images.get(ship_name)

            if ship_img_dict:
                current_ship_image = ship_img_dict.get(orientation)
                if current_ship_image:
                    if ship_detail["is_sunk"]:
                        # Crear y usar versión oscurecida
                        image_to_draw = create_darkened_image(current_ship_image)
                    else:
                        image_to_draw = current_ship_image
                    
                    if image_to_draw and ship_detail.get("image_rect_on_board"):
                        # image_rect_on_board tiene las coordenadas de pantalla correctas
                        surface.blit(image_to_draw, ship_detail["image_rect_on_board"].topleft)
    
    # 3. Dibujar impactos (H) y fallos (M) encima de todo
    # Esto se hace iterando board_matrix, que contiene 'H' y 'M'
    for r_idx in range(GRID_SIZE):
        for c_idx in range(GRID_SIZE):
            cell_val = board_matrix[r_idx][c_idx]
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE)
            if cell_val == 'H': 
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.top + 5), (cell_rect.right - 5, cell_rect.bottom - 5), 4)
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.bottom - 5), (cell_rect.right - 5, cell_rect.top + 5), 4)
            elif cell_val == 'M': 
                pygame.draw.circle(surface, YELLOW_MISS, cell_rect.center, CELL_SIZE // 4)
            # NOTA: Ya no dibujamos '1' (barco genérico) aquí para `my_board` porque las imágenes lo cubren.

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
                    
def check_if_opponent_is_defeated(opponent_b):
    hits_on_opponent = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if opponent_b[r][c] == 'H':
                hits_on_opponent += 1
    return hits_on_opponent >= TOTAL_SHIP_CELLS

def game_main_loop():
    global screen, font_large, font_medium, font_small, current_game_state, status_bar_message
    global current_ship_orientation, SERVER_IP, hit_sound, miss_sound,sunk_sound, client_socket
    global ship_images # Para que sea accesible
    
    if len(sys.argv) > 1: SERVER_IP = sys.argv[1]
    print(f"Usando IP del servidor: {SERVER_IP}")

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
        # ... (resto del bucle principal) ...
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