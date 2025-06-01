# client.py
import pygame
import socket
import threading
import sys
import time
import os

# --- Configuración ---
SCREEN_WIDTH, SCREEN_HEIGHT = 900, 500
GRID_SIZE, CELL_SIZE = 10, 30
# ... (todas las demás constantes de colores, offsets, etc. de tus archivos originales)

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BLUE_WATER = (100, 149, 237)
RED_HIT = (200, 0, 0)
YELLOW_MISS = (200, 200, 0)
BOARD_GRID_COLOR = (50, 50, 150)
TEXT_COLOR = (230, 230, 230)
STATUS_TEXT_COLOR = WHITE
GREEN_PREVIEW_BORDER = (0, 200, 0)
RED_PREVIEW_BORDER = (200, 0, 0)
BOARD_OFFSET_X_MY = 50
BOARD_OFFSET_Y = 80
BOARD_OFFSET_X_OPPONENT = BOARD_OFFSET_X_MY + GRID_SIZE * CELL_SIZE + 70

STATE_SETUP_SHIPS = "SETUP_SHIPS"
STATE_GAME_OVER = "GAME_OVER"

SHIPS_CONFIG = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3), ("Submarine", 3), ("Destroyer", 2)]
TOTAL_SHIP_CELLS = sum(size for _, size in SHIPS_CONFIG)

# --- Estado Global del Cliente ---
client_socket = None
player_id_str = None
game_mode = None # '2P' o '4P'
current_game_state = "CONNECTING"
status_bar_message = "Iniciando..."
# ... (el resto de variables globales de estado: my_board_data, opponent_board_data, etc.)
my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
opponent_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
ships_to_place_list = list(SHIPS_CONFIG)
current_ship_placement_index = 0
current_ship_orientation = 'H'
my_placed_ships_detailed = []
opponent_sunk_ships_log = []
g_my_team_name = ""
g_opponent_team_name = ""
opponents_info = [] # Para 4P

screen = None
font_large = None
font_medium = None
font_small = None

ship_images = {} # Almacenará imágenes cargadas y rotadas: {"Carrier": {"H": surface, "V": surface}, ...}
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

# --- Funciones de Pygame (draw_game_grid, etc.) ---
# (Copia aquí TODAS las funciones de ayuda de Pygame de tus archivos originales)
# draw_game_grid, draw_text_on_screen, get_grid_cell_from_mouse, can_place_ship_at,
# create_darkened_image, check_and_update_my_sunk_ships, etc.
# La única que cambia es attempt_to_place_ship

def prompt_for_team_name_gui():
    global screen, font_large, font_medium, font_small # Asegúrate que estén inicializadas si no lo están globalmente antes
    
    # Si las fuentes no están inicializadas porque game_main_loop aún no lo hizo:
    if font_large is None: pygame.font.init() # Necesario si pygame no está completamente init
    if font_large is None: font_large = pygame.font.Font(None, 48)
    if font_medium is None: font_medium = pygame.font.Font(None, 36)
    if font_small is None: font_small = pygame.font.Font(None, 28)
    if screen is None: # Si el screen no está seteado (debería estarlo por game_main_loop)
        screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))


    pygame.display.set_caption("Batalla Naval - Nombra tu Equipo")
    input_box = pygame.Rect(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT // 2, 400, 48)
    color_inactive = pygame.Color('lightskyblue3')
    color_active = pygame.Color('dodgerblue2')
    color = color_inactive
    active = False
    text = ""
    done = False
    prompt_message = f"Capitán, ingresa el nombre de tu equipo:"

    while not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
            if event.type == pygame.MOUSEBUTTONDOWN:
                if input_box.collidepoint(event.pos):
                    active = not active
                else:
                    active = False
                color = color_active if active else color_inactive
            if event.type == pygame.KEYDOWN:
                if active:
                    if event.key == pygame.K_RETURN:
                        if text.strip(): # Aceptar si no está vacío después de strip
                            done = True
                    elif event.key == pygame.K_BACKSPACE:
                        text = text[:-1]
                    elif len(text) < 25 and event.unicode.isprintable(): # Limitar longitud
                        text += event.unicode

        screen.fill(BLACK) # Fondo negro
        draw_text_on_screen(screen, prompt_message, (SCREEN_WIDTH // 2 - input_box.w // 2 - 10 , SCREEN_HEIGHT // 2 - 60), font_medium, WHITE)
        
        # Renderizar texto del input
        txt_surface = font_large.render(text, True, color)
        # Ajustar ancho del input_box dinámicamente o mantenerlo fijo
        # input_box.w = max(400, txt_surface.get_width()+20) # Dinámico
        screen.blit(txt_surface, (input_box.x+10, input_box.y+5))
        pygame.draw.rect(screen, color, input_box, 2, border_radius=5)
        
        draw_text_on_screen(screen, "Presiona Enter para continuar", (input_box.x, SCREEN_HEIGHT // 2 + 60), font_small, WHITE)
        pygame.display.flip()
        
    return text.strip()

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
def create_darkened_image(original_image_surface, darkness_alpha=128):
    if original_image_surface is None: return None
    darkened_surface = original_image_surface.copy()
    overlay = pygame.Surface(darkened_surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, darkness_alpha)) # Negro semi-transparente
    darkened_surface.blit(overlay, (0, 0))
    return darkened_surface

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

def draw_text_on_screen(surface, text_content, position, font_to_use, color=TEXT_COLOR):
    text_surface = font_to_use.render(text_content, True, color)
    surface.blit(text_surface, position)

# ... (y el resto de funciones de dibujo y ayuda de pygame) ...

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
    can_place, temp_coords = can_place_ship_at(my_board_data, r, c, ship_size, current_ship_orientation)

    if can_place:
        # ... (lógica para añadir el barco a my_placed_ships_detailed) ...
        # Esta parte es igual que en tus archivos anteriores
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
            # Si es 4P y P1/P3, serializar y enviar el tablero ANTES de READY_SETUP
            if game_mode == '4P' and (player_id_str == "P1" or player_id_str == "P3"):
                board_payload_parts = []
                for ship_detail in my_placed_ships_detailed:
                    # Usar comas para separar r,c y espacios para separar pares de coordenadas
                    coords_str_list = [f"{r},{c}" for r, c in ship_detail["coords"]]
                    coords_flat = " ".join(coords_str_list)
                    # Formato: name|orientation|size|r1,c1 r2,c2 r3,c3 ...
                    board_payload_parts.append(f"{ship_detail['name']}|{ship_detail['orientation']}|{ship_detail['size']}|{coords_flat}")
                final_board_payload = ";".join(board_payload_parts)
                send_message_to_server(f"CAPTAIN_BOARD_DATA {final_board_payload}")
                print(f"DEBUG CLIENT [{player_id_str}]: Sent CAPTAIN_BOARD_DATA")

            send_message_to_server("READY_SETUP") # [cite: 121]
            current_game_state = "WAITING_OPPONENT_SETUP" # [cite: 121]
            status_bar_message = "Barcos colocados. Esperando al oponente..." # [cite: 121]
        else:
            next_ship_name = ships_to_place_list[current_ship_placement_index][0] # [cite: 121]
            status_bar_message = f"Coloca: {next_ship_name}. 'R' para rotar." # [cite: 121]
        return True
    return False

# --- Comunicación con el Servidor ---

def send_message_to_server(message):
    if client_socket:
        try:
            client_socket.sendall(f"{message}\n".encode())
        except socket.error as e:
            print(f"Error enviando mensaje: {e}")
            # ... (manejo de error, cambiar estado a GAME_OVER) ...
            global status_bar_message, current_game_state
            if current_game_state != STATE_GAME_OVER: # Solo si no está ya en Game Over
                status_bar_message = "Error de red al enviar."
                current_game_state = STATE_GAME_OVER
        except Exception as e: # Otras excepciones
            print(f"Excepción general al enviar mensaje: {e}")
            if current_game_state != STATE_GAME_OVER:
                status_bar_message = "Error desconocido al enviar."
                current_game_state = STATE_GAME_OVER

def listen_for_server_messages():
    global current_game_state, status_bar_message, game_mode, player_id_str, g_my_team_name, g_opponent_team_name, opponents_info

    data_buffer = ""
    while current_game_state != "GAME_OVER":
        try:
            data_bytes = client_socket.recv(2048)
            if not data_bytes:
                status_bar_message = "Desconectado del servidor."
                current_game_state = "GAME_OVER"
                break

            data_buffer += data_bytes.decode()
            
            while '\n' in data_buffer:
                message, data_buffer = data_buffer.split('\n', 1)
                message = message.strip()
                if not message: continue

                print(f"Servidor dice: {message}")
                parts = message.split()
                command = parts[0]

                # --- Lógica de Despacho según el Comando ---
                if command == "MSG":
                    status_bar_message = ' '.join(parts[1:])
                
                elif command == "SETUP_YOUR_BOARD":
                    current_game_state = "SETUP_SHIPS"
                    status_bar_message = f"{player_id_str}: Coloca tus barcos. 'R' para rotar."
                
                elif command == "TEAM_BOARD":
                    if game_mode == '4P' and (player_id_str == "P2" or player_id_str == "P4"): # Solo para compañeros de equipo
                        print(f"DEBUG CLIENT [{player_id_str}]: Received TEAM_BOARD from captain.")
                        board_payload = " ".join(parts[1:])

                        my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] # Resetea el tablero
                        my_placed_ships_detailed.clear() # Limpia los barcos existentes

                        ship_definitions = board_payload.split(';')
                        for ship_def_str in ship_definitions:
                            if not ship_def_str.strip(): continue # Ignorar definiciones vacías
                            try:
                                # Formato esperado del servidor: name|orientation|size|r1,c1 r2,c2 ...
                                name, orientation, size_str, coords_str_flat = ship_def_str.split('|')
                                size = int(size_str)
                                coord_pairs_str = coords_str_flat.split(' ')
                                actual_ship_coords = []

                                min_r_for_rect, min_c_for_rect = GRID_SIZE, GRID_SIZE 

                                for pair_str in coord_pairs_str:
                                    if not pair_str.strip(): continue
                                    r_str, c_str = pair_str.split(',')
                                    r, c = int(r_str), int(c_str)
                                    if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE:
                                        my_board_data[r][c] = 1 # Marcar la celda como ocupada
                                        actual_ship_coords.append((r,c))
                                        if r < min_r_for_rect: min_r_for_rect = r
                                        if c < min_c_for_rect: min_c_for_rect = c
                                    else:
                                        print(f"ERROR CLIENT [{player_id_str}]: TEAM_BOARD coord ({r},{c}) out of bounds for ship {name}")
                                        raise ValueError("Coordinate out of bounds")


                                if not actual_ship_coords: continue # Si no se pudieron parsear coordenadas válidas

                                # Calcular el Rect de la imagen para dibujarla
                                img_top_left_x = BOARD_OFFSET_X_MY + min_c_for_rect * CELL_SIZE
                                img_top_left_y = BOARD_OFFSET_Y + min_r_for_rect * CELL_SIZE

                                ship_img_data = ship_images.get(name)
                                img_width, img_height = (size * CELL_SIZE, CELL_SIZE) if orientation == 'H' else (CELL_SIZE, size * CELL_SIZE) # Default
                                if ship_img_data:
                                    actual_image_surf = ship_img_data.get(orientation)
                                    if actual_image_surf:
                                        img_width = actual_image_surf.get_width()
                                        img_height = actual_image_surf.get_height()

                                ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, img_width, img_height)

                                my_placed_ships_detailed.append({
                                    "name": name, 
                                    "base_image_key": name, 
                                    "size": size,
                                    "coords": actual_ship_coords, 
                                    "orientation": orientation,
                                    "is_sunk": False, 
                                    "image_rect_on_board": ship_screen_rect
                                })
                            except Exception as e:
                                print(f"ERROR CLIENT [{player_id_str}]: Failed to parse TEAM_BOARD ship_def '{ship_def_str}': {e}")

                        status_bar_message = "Tablero de equipo recibido. Esperando inicio de juego..."
                        current_game_state = "WAITING_OPPONENT_SETUP" # O un estado que indique que está listo

                        # P2/P4 deben confirmar al servidor que han recibido y procesado el tablero
                        send_message_to_server("READY_SETUP")
                        print(f"DEBUG CLIENT [{player_id_str}]: Processed TEAM_BOARD and sent READY_SETUP.")
                    else:
                        print(f"DEBUG CLIENT [{player_id_str}]: Ignored TEAM_BOARD (not P2 or P4, or not 4P mode).")
                
                elif command == "START_GAME":
                    starting_player = parts[1]
                    if starting_player == player_id_str:
                        current_game_state = "YOUR_TURN"
                        status_bar_message = "¡Tu turno! Dispara."
                    else:
                        current_game_state = "OPPONENT_TURN"
                        status_bar_message = f"Turno del oponente ({starting_player}). Esperando..."

                elif command == "TURN": # Comando unificado para cambio de turno
                    next_player = parts[1]
                    if next_player == player_id_str:
                        current_game_state = "YOUR_TURN"
                        status_bar_message = "¡Tu turno! Dispara."
                    else:
                        current_game_state = "OPPONENT_TURN"
                        status_bar_message = f"Turno de {next_player}. Esperando..."

                # --- Lógica Específica del Modo de Juego ---
                elif command == "SHOT":
                    # Lógica para cuando te disparan (igual en 2P y 4P)
                    r, c = int(parts[1]), int(parts[2])
                    result = 'M'
                    if my_board_data[r][c] == 1:
                        my_board_data[r][c] = 'H'
                        result = 'H'
                        # check_and_update_my_sunk_ships() # Comprobar si se hundió un barco
                    send_message_to_server(f"RESULT {r} {c} {result}")

                elif command == "UPDATE":
                    if game_mode == '2P':
                        r, c, result = int(parts[1]), int(parts[2]), parts[3]
                        if result == 'H': opponent_board_data[r][c] = 'H'
                        else: opponent_board_data[r][c] = 'M'
                    elif game_mode == '4P':
                        target_player, r, c, result = parts[1], int(parts[2]), int(parts[3]), parts[4]
                        # Solo actualizar si el afectado es un oponente
                        if any(opp['id'] == target_player for opp in opponents_info):
                            if result == 'H': opponent_board_data[r][c] = 'H'
                            else: opponent_board_data[r][c] = 'M'
                
                elif command == "REQUEST_TEAM_NAME":
                    current_game_state = "AWAITING_TEAM_NAME_INPUT"
                    status_bar_message = "Capitán, ingresa el nombre de tu equipo."

                elif command == "TEAMS_INFO_FINAL":
                    g_my_team_name = parts[1].replace('_', ' ')
                    g_opponent_team_name = parts[2].replace('_', ' ')
                    opponents_info.clear()
                    for opp_id in parts[3:]:
                        opponents_info.append({'id': opp_id})
                    status_bar_message = f"Equipo: {g_my_team_name}. Oponente: {g_opponent_team_name}"

                elif command == "GAME_OVER":
                    current_game_state = "GAME_OVER"
                    status_bar_message = "¡Has GANADO!" if parts[1] == "WIN" else "Has perdido."
                
                elif command == "OPPONENT_LEFT":
                    current_game_state = "GAME_OVER"
                    status_bar_message = "Un oponente se ha ido. ¡Ganas por defecto!"

        except Exception as e:
            print(f"Error escuchando al servidor: {e}")
            current_game_state = "GAME_OVER"
            status_bar_message = "Error de conexión."
            break

def game_main_loop(server_ip, server_port, action, game_type=None, game_name=None, game_id=None):
    """Bucle principal de juego. Se conecta al servidor y entra en el modo de juego."""
    global client_socket, player_id_str, game_mode, current_game_state, status_bar_message

    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((server_ip, server_port))
        
        # Enviar la acción inicial al lobby del servidor
        if action == 'CREATE':
            send_message_to_server(f"CREATE_GAME {game_type} {game_name}")
        elif action == 'JOIN':
            send_message_to_server(f"JOIN_GAME {game_id}")

        # Esperar respuesta del servidor (JOIN_SUCCESS)
        response = client_socket.recv(1024).decode().strip()
        if response.startswith("JOIN_SUCCESS"):
            _, player_id_str, game_mode = response.split()
            print(f"Unido con éxito como {player_id_str} a una partida {game_mode}.")
            status_bar_message = "Esperando a otros jugadores..."
        else:
            print(f"Error al unirse a la partida: {response}")
            status_bar_message = "Error al unirse a la partida."
            return

    except Exception as e:
        print(f"No se pudo conectar al servidor: {e}")
        status_bar_message = "No se pudo conectar al servidor."
        # Aquí podrías volver al menú principal en lugar de cerrar
        return
        
    threading.Thread(target=listen_for_server_messages, daemon=True).start()

    # --- Bucle de Pygame ---
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption(f"Batalla Naval Cliente") 
    font_large = pygame.font.Font(None, 48)
    font_medium = pygame.font.Font(None, 36)
    font_small = pygame.font.Font(None, 28)

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
    print(f"CLIENT [{player_id_str or 'NEW'}]: Starting game_main_loop. Action: {action}")
    is_game_running = True
    while is_game_running:
        mouse_pos = pygame.mouse.get_pos()
        
        # Si el servidor pide el nombre del equipo, mostrar el prompt
        if current_game_state == "AWAITING_TEAM_NAME_INPUT":
            print(f"CLIENT [{player_id_str}]: State is AWAITING_TEAM_NAME_INPUT. Calling prompt.")
            team_name = prompt_for_team_name_gui()
            print(f"CLIENT [{player_id_str}]: Prompt returned. Team name: '{team_name}'. Sending TEAM_NAME_IS.")
            # ...
            send_message_to_server(f"TEAM_NAME_IS {team_name}")
            current_game_state = "WAITING_OPPONENT_SETUP"
            status_bar_message = "Nombre de equipo enviado."

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                print(f"CLIENT [{player_id_str}]: QUIT event received in main loop. Setting is_game_running to False.")
                is_game_running = False
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if current_game_state == "YOUR_TURN":
                    r, c = get_grid_cell_from_mouse(mouse_pos, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y)
                    if r is not None and opponent_board_data[r][c] == 0:
                        if game_mode == '2P':
                            send_message_to_server(f"SHOT {r} {c}")
                        elif game_mode == '4P' and opponents_info:
                            # Disparar al primer oponente por defecto (se puede mejorar con una UI)
                            target_id = opponents_info[0]['id']
                            send_message_to_server(f"SHOT {target_id} {r} {c}")
                        status_bar_message = "Disparo enviado."

                elif current_game_state == "SETUP_SHIPS":
                    r, c = get_grid_cell_from_mouse(mouse_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y)
                    if r is not None and c is not None:
                        attempt_to_place_ship(my_board_data, r, c, ships_to_place_list[current_ship_placement_index]) # [cite: 231]
                    
        
        # --- Dibujo ---
        screen.fill(BLACK)
        # ... (toda la lógica de dibujo de tableros, texto, etc.) ...
        # Esta lógica puede usar `game_mode` para dibujar cosas diferentes
        # ej: `f"Tu equipo: {g_my_team_name}"` vs `f"Tu flota"`
        
        # Actualizar título de ventana con nombre de equipo si está disponible
        window_title = "Batalla Naval Cliente"
        if g_my_team_name:
            window_title = f"{g_my_team_name} (Jugador {player_id_str or 'N/A'}) - Batalla Naval"
        elif player_id_str:
            window_title = f"Jugador {player_id_str} - Batalla Naval"
        pygame.display.set_caption(window_title)
        
        # Mostrar nombres de equipo
        draw_text_on_screen(screen, f"Equipo Oponente: {g_opponent_team_name or 'Esperando...'}", (BOARD_OFFSET_X_OPPONENT - 20, 10), font_small) # Ajustado
        draw_text_on_screen(screen, f"TU EQUIPO ({g_my_team_name or player_id_str or 'Asignando...'})", (BOARD_OFFSET_X_MY, 10), font_small) # Ajustado y pos Y

        # Etiquetas de tableros (se mantienen igual)
        draw_text_on_screen(screen, "TU FLOTA", (BOARD_OFFSET_X_MY, BOARD_OFFSET_Y - 40), font_medium)
        draw_text_on_screen(screen, "FLOTA ENEMIGA", (BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y - 40), font_medium)
        
        # ... (dibujo de rejillas y preview como lo tienes) ...
        draw_game_grid(screen, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y, my_board_data, True) # [cite: 239]
        draw_game_grid(screen, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y, opponent_board_data, False)

        if current_game_state == STATE_SETUP_SHIPS:
            draw_ship_placement_preview(screen, mouse_pos)
            if current_ship_placement_index < len(ships_to_place_list):
                 ship_name, ship_size_val = ships_to_place_list[current_ship_placement_index]
                 orient_text = 'H' if current_ship_orientation == 'H' else 'V'
                 info_text = f"Colocando: {ship_name} ({ship_size_val}) Orient: {orient_text}"
                 draw_text_on_screen(screen, info_text, (10, SCREEN_HEIGHT - 70), font_small)

        pygame.draw.rect(screen, (30,30,30), (0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40))
        draw_text_on_screen(screen, status_bar_message, (10, SCREEN_HEIGHT - 30), font_small, STATUS_TEXT_COLOR)
        
        
        pygame.display.flip()
    print(f"CLIENT [{player_id_str}]: Exited main game loop. is_game_running: {is_game_running}")
    print(f"CLIENT [{player_id_str}]: Calling pygame.quit()")
    pygame.quit()
    if client_socket: client_socket.close()
    sys.exit()