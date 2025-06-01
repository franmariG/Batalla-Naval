# client.py
import pygame
import socket
import threading
import sys
import time
import os # Para construir rutas a los archivos de sonido

from server import team_details

# --- Configuración de Conexión ---
SERVER_IP = "169.254.107.4"
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

# --- NUEVA VARIABLE ---
opponents_info = [] # Almacenará los IDs y nombres de los oponentes

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
# player_name = "" # Ya no se usa para nombre individual al inicio
# opponent_name = "" # Se reemplazará por nombres de equipo
g_my_team_name = None
g_opponent_team_name = None
g_player_id_for_team_name_prompt = None # Para saber si este cliente debe pedir nombre de equipo

# NUEVA función para pedir nombre de equipo (similar a prompt_for_player_name)
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
    prompt_message = f"Capitán {g_player_id_for_team_name_prompt}, ingresa el nombre de tu equipo:"

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

# ya no se usa para cuatro jugadores
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
    global client_socket, current_game_state, status_bar_message, player_id_str
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Intentando conectar a {SERVER_IP}:{PORT}...")
        client_socket.connect((SERVER_IP, PORT))
        # Ya NO enviamos PLAYER_NAME aquí. El servidor solicitará el nombre del equipo si es necesario.
        status_bar_message = "Conectado. Esperando ID del servidor..."
        threading.Thread(target=listen_for_server_messages, daemon=True).start()
    except ConnectionRefusedError:
        status_bar_message = "Error: Conexion rechazada por el servidor."
        current_game_state = STATE_GAME_OVER
    except Exception as e:
        status_bar_message = f"Error de conexion: {e}"
        current_game_state = STATE_GAME_OVER

def listen_for_server_messages():
    global current_game_state, status_bar_message, player_id_str, my_board_data, opponent_board_data, client_socket
    global opponent_sunk_ships_log, g_my_team_name, g_opponent_team_name, g_player_id_for_team_name_prompt
    global opponents_info, is_team_board_slave # is_team_board_slave ya existía

    data_buffer = ""
    while current_game_state != STATE_GAME_OVER and client_socket: 
        try:
            data_bytes = client_socket.recv(2048) # Aumentar un poco por si llegan varios mensajes
            if not data_bytes:
                # ... (manejo de desconexión como lo tienes) ...
                if current_game_state != STATE_GAME_OVER : 
                    status_bar_message = "Desconectado del servidor (recv vacío)."
                current_game_state = STATE_GAME_OVER
                break 
            
            # Añadir los nuevos datos al búfer
            data_buffer += data_bytes.decode()
            while '\n' in data_buffer:
                # Extraer el primer mensaje completo y quitarlo del búfer
                message, data_buffer = data_buffer.split('\n', 1)
                message = message.strip() # Limpiar espacios en blanco
                if not message:
                    continue
                print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: Servidor dice: {message}") # Enhanced Debug
                print(f"Servidor dice: {message}")
                parts = message.split()
                if not parts:
                    continue
                command = parts[0]

                # --- BLOQUE PARA TEAM_BOARD (debe ir antes de otros elif) ---
                if command == "TEAM_BOARD":
                    print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: Procesando TEAM_BOARD: {message}") # DEBUG
                    my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
                    my_placed_ships_detailed.clear()
                    
                    board_content_str = message[len("TEAM_BOARD "):].strip()
                    if not board_content_str:
                        print(f"WARN CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD recibido con payload vacío.")
                        is_team_board_slave = True # Still set this as the role is assigned
                        current_game_state = STATE_WAITING_OPPONENT_SETUP
                        status_bar_message = "Esperando al oponente (tablero de equipo vacío recibido)..."
                        continue
                    
                    barcos_str_list = board_content_str.split(";")
                    
                    for idx, barco_definition_str in enumerate(barcos_str_list):
                        barco_definition_str = barco_definition_str.strip()
                        if not barco_definition_str:
                            print(f"WARN CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: cadena de barco vacía en índice {idx}.")
                            continue
                        try:
                            coords_part, name, orient = barco_definition_str.split("|") # [cite: 170]
                            coords_part = coords_part.strip()
                            name = name.strip()
                            orient = orient.strip()

                            if not coords_part or not name or not orient:
                                print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: Partes inválidas en '{barco_definition_str}'")
                                continue
                                
                            coords_str_list = coords_part.split()
                            parsed_coords_int = [int(x) for x in coords_str_list] # [cite: 170]
                            
                            current_ship_coords_tuples = [] # Para este barco específico
                            if len(parsed_coords_int) % 2 != 0:
                                print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: Número impar de componentes de coordenadas para '{name}': {coords_part}")
                                continue # Saltar este barco

                            for i in range(0, len(parsed_coords_int), 2): # [cite: 171]
                                r, c = parsed_coords_int[i], parsed_coords_int[i+1]
                                if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE):
                                    print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: Coordenadas ({r},{c}) fuera de rango para '{name}'. Saltando este barco.")
                                    current_ship_coords_tuples.clear() # Invalida este barco
                                    break 
                                my_board_data[r][c] = 1 # *** CRITICAL: Mark cell in grid data ***
                                current_ship_coords_tuples.append((r, c)) # [cite: 172]
                            
                            if not current_ship_coords_tuples: # Si el bucle anterior falló o no se añadieron coordenadas
                                print(f"WARN CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: No se procesaron coordenadas válidas para el barco '{name}' con def: '{barco_definition_str}'")
                                continue

                            # Determinar la esquina superior izquierda para la imagen del barco
                            # Usa la primera coordenada como referencia para la posición de la imagen
                            # Esto asume que las coordenadas están ordenadas o que la primera es la ancla.
                            ref_r, ref_c = current_ship_coords_tuples[0] 
                            
                            img_top_left_x = BOARD_OFFSET_X_MY + ref_c * CELL_SIZE # [cite: 173]
                            img_top_left_y = BOARD_OFFSET_Y + ref_r * CELL_SIZE # [cite: 173]
                            
                            ship_img_data = ship_images.get(name) # [cite: 174]
                            # Default width/height, can be overridden by actual image dimensions
                            width = len(current_ship_coords_tuples) * CELL_SIZE if orient == 'H' else CELL_SIZE 
                            height = CELL_SIZE if orient == 'H' else len(current_ship_coords_tuples) * CELL_SIZE
                                
                            if ship_img_data:
                                actual_image = ship_img_data.get(orient)
                                if actual_image:
                                    width = actual_image.get_width()
                                    height = actual_image.get_height()
                            ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, width, height)
                            my_placed_ships_detailed.append({ # [cite: 177]
                                "name": name,
                                "base_image_key": name, # [cite: 177]
                                "size": len(current_ship_coords_tuples), # [cite: 178]
                                "coords": list(current_ship_coords_tuples), # Asegurar que es una nueva lista
                                "orientation": orient, # [cite: 178]
                                "is_sunk": False, # [cite: 179]
                                "image_rect_on_board": ship_screen_rect # [cite: 179]
                            })
                            print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: Añadido barco '{name}' con {len(current_ship_coords_tuples)} segmentos.")
                        except ValueError as e:
                            print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: ValueError al parsear coordenadas en '{barco_definition_str}': {e}")
                            continue # Procesar el siguiente barco
                        except IndexError as e:
                            print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: IndexError al parsear partes del barco en '{barco_definition_str}': {e}")
                            continue # Procesar el siguiente barco
                        except Exception as e:
                            print(f"ERROR CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD: Excepción inesperada procesando barco '{barco_definition_str}': {e}")
                            import traceback
                            traceback.print_exc() # Imprime el traceback completo
                            continue # Procesar el siguiente barco
                    print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: TEAM_BOARD procesado. {len(my_placed_ships_detailed)} barcos cargados en my_placed_ships_detailed.")
                    print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: my_board_data (primeras 3 filas):")
                    for i in range(min(3, GRID_SIZE)):
                         print(f"  {my_board_data[i]}")

                    is_team_board_slave = True # [cite: 180]
                    current_game_state = STATE_WAITING_OPPONENT_SETUP # [cite: 181]
                    status_bar_message = "Tablero de equipo recibido. Esperando al oponente..."
                    continue # Importante para no procesar como otro comando si hay data_buffer remanente
                
                if command == "MSG":
                    status_bar_message = ' '.join(parts[1:])
                elif command == "PLAYER_ID":
                    player_id_str = parts[1]
                    g_player_id_for_team_name_prompt = player_id_str # Guardar para el prompt de nombre de equipo
                    status_bar_message = f"ID asignado: {player_id_str}. Esperando inicio..."
                elif command == "REQUEST_TEAM_NAME":
                    # El servidor pide a este cliente (P1 o P3) que ingrese el nombre del equipo
                    status_bar_message = "El servidor solicita el nombre de tu equipo."
                    # Es importante que el prompt se muestre en el hilo principal de Pygame.
                    # Esta función de escucha está en un hilo secundario.
                    # Una forma es poner una bandera y que el bucle principal de Pygame lo maneje.
                    # Por ahora, llamaremos a una función que bloquea este hilo hasta que se ingrese el nombre.
                    # (Esto no es ideal para GUI muy responsivas, pero simplifica)
                    
                    # Esta llamada a prompt_for_team_name_gui() ahora se hace condicionalmente 
                    # en el bucle principal de Pygame cuando una bandera se activa.
                    # Aquí solo activamos la bandera o ponemos un estado.
                    # Para simplificar aquí, vamos a asumir que podemos llamar a una función que pide el nombre
                    # y bloquea este hilo hasta que se obtenga. Para una GUI real, se usarían colas/eventos.
                    
                    # Solución más simple para ahora (bloqueante, pero evita rediseño mayor inmediato):
                    # OJO: Esto bloqueará este hilo de escucha. Si Pygame se congela, hay que cambiarlo.
                    # Una mejor manera es poner current_game_state = "PROMPTING_TEAM_NAME" y que el
                    # bucle principal de Pygame maneje el input y luego envíe el mensaje.
                    # Por ahora, probemos así para ver si el flujo funciona:
                    if player_id_str == team_details["TeamA"]["captain"] or player_id_str == team_details["TeamB"]["captain"]: # Doble chequeo
                        print(f"DEBUG CLIENT [{player_id_str}]: Recibido REQUEST_TEAM_NAME. Abriendo prompt...")
                        # Aquí, en un juego real, activarías un estado para que el bucle principal de Pygame muestre el input.
                        # Por ahora, vamos a simular que el prompt se maneja y se obtiene el nombre.
                        # NO LLAMAR A prompt_for_team_name_gui() directamente desde este hilo si causa problemas de Pygame.
                        # En su lugar:
                        current_game_state = "AWAITING_TEAM_NAME_INPUT" # Nuevo estado
                        status_bar_message = "Ingresa el nombre de tu equipo y presiona Enter."
                        # El bucle principal de Pygame detectará "AWAITING_TEAM_NAME_INPUT", llamará a
                        # prompt_for_team_name_gui(), y luego enviará el mensaje.
                    else:
                        print(f"DEBUG CLIENT [{player_id_str}]: Recibido REQUEST_TEAM_NAME pero no soy capitán. Ignorando.")
                elif command == "TEAMS_INFO_FINAL":
                    try:
                        g_my_team_name = parts[1].replace("_", " ") # Reemplazar underscores si el servidor los usa para espacios
                        g_opponent_team_name = parts[2].replace("_", " ")
                        
                        opponents_info.clear() # Limpiar la lista de oponentes anterior
                        if len(parts) > 3: # Si se enviaron los IDs de los oponentes
                            # parts[3:] serán los IDs individuales de los oponentes. Ej: "P3", "P4"
                            opponent_ids_received = parts[3:] 
                            for opp_id in opponent_ids_received:
                                # Guardamos el ID. El 'name' podría ser el nombre del equipo oponente para referencia,
                                # o un placeholder si no se necesita para mostrar nombres individuales.
                                opponents_info.append({"id": opp_id, "name": g_opponent_team_name}) 
                        
                        status_bar_message = f"Tu equipo: {g_my_team_name}. Oponente: {g_opponent_team_name}. Esperando configuración..."
                        print(f"INFO CLIENT: Nombres de equipo recibidos. Mío: '{g_my_team_name}', Oponente: '{g_opponent_team_name}'. opponents_info: {opponents_info}")
                        
                        # Si el juego estaba en un estado de espera de nombres, puede avanzar
                        if current_game_state == "WAITING_FOR_TEAM_NAMES" or current_game_state == STATE_WAITING_FOR_PLAYER : # Si estaba esperando esto
                           pass # La lógica de SETUP_YOUR_BOARD o START_GAME lo moverá al siguiente estado
                    except IndexError:
                        print(f"Error parseando TEAMS_INFO_FINAL: {message}")
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
                    try:
                        target_player_id = parts[1] # ID de un jugador del equipo que recibió el disparo
                        r, c = int(parts[2]), int(parts[3])
                        result_char = parts[4]
                        current_cell_state_on_opponent_board = opponent_board_data[r][c]

                        # Comprobar si el jugador afectado es un oponente
                        is_opponent_target = any(opp['id'] == target_player_id for opp in opponents_info)

                        if is_opponent_target:
                            # Actualizamos nuestro tablero de oponente
                            if result_char == 'H':
                                # Solo marcar como 'H' si no es ya 'S' (parte de un barco ya confirmado hundido).
                                # Si es 'S', significa que OPPONENT_SHIP_SUNK llegó primero para esta celda.
                                if current_cell_state_on_opponent_board != 'S':
                                    opponent_board_data[r][c] = 'H'
                                if hit_sound: hit_sound.play()
                            elif result_char == 'M':
                                # Solo marcar como 'M' si no es 'S'. Un fallo no debería afectar un barco hundido.
                                if current_cell_state_on_opponent_board != 'S':
                                    opponent_board_data[r][c] = 'M'
                                if miss_sound: miss_sound.play()
                            # La lógica de victoria ya existente funciona bien aquí
                            if check_if_opponent_is_defeated(opponent_board_data):
                                send_message_to_server("GAME_WON")
                        else:
                            # El afectado es de nuestro equipo, actualizamos nuestro propio tablero
                            if my_board_data[r][c] == 1 and result_char == 'H':
                                my_board_data[r][c] = 'H'
                                check_and_update_my_sunk_ships()
                            elif my_board_data[r][c] == 0 and result_char == 'M':
                                my_board_data[r][c] = 'M'

                    except (IndexError, ValueError):
                        print(f"Error procesando UPDATE: {message}")
                    
                    # El mensaje de status_bar_message se actualizará con YOUR_TURN_AGAIN o OPPONENT_TURN_MSG
                elif command == "OPPONENT_SHIP_SUNK": 
                    try:
                        # Formato esperado del servidor: OPPONENT_SHIP_SUNK {ID_AFECTADO} {NOMBRE_BARCO} {coords...}
                        # parts[0] = "OPPONENT_SHIP_SUNK"
                        # parts[1] = ID del jugador cuyo barco fue hundido (ej. "P3")
                        # parts[2] = Nombre del barco (ej. "Battleship")
                        # parts[3:]= Coordenadas como strings (ej. "9", "5", "9", "6", ...)

                        if len(parts) < 4: # Mínimo: COMANDO, ID_AFECTADO, NOMBRE_BARCO, R1, C1
                            print(f"Error: Mensaje OPPONENT_SHIP_SUNK malformado (muy corto): {message}")
                            continue

                        id_jugador_afectado = parts[1] # ID del jugador cuyo barco se hundió
                        ship_name_sunk = parts[2]           # Nombre del barco hundido
                        
                        status_bar_message = f"¡Hundiste el {ship_name_sunk} del equipo {g_opponent_team_name} (jugador {id_jugador_afectado})!"
                        # Las coordenadas comienzan desde parts[3]
                        flat_coords_str = parts[3:]
                        
                        # Convertir coordenadas a enteros
                        sunk_ship_coords_tuples = []
                        if len(flat_coords_str) % 2 != 0:
                            print(f"Error: Número impar de componentes de coordenadas en OPPONENT_SHIP_SUNK: {flat_coords_str}")
                            continue # Saltar este mensaje si las coordenadas son inválidas

                        for i in range(0, len(flat_coords_str), 2):
                            try:
                                r_coord = int(flat_coords_str[i])
                                c_coord = int(flat_coords_str[i+1])
                                sunk_ship_coords_tuples.append((r_coord, c_coord))
                            except ValueError:
                                print(f"Error: Coordenada no entera en OPPONENT_SHIP_SUNK: '{flat_coords_str[i]}' o '{flat_coords_str[i+1]}'")
                                # Podrías decidir saltar este barco o manejar el error de otra forma
                                sunk_ship_coords_tuples.clear() # No procesar barco con coords inválidas
                                break
                        
                        if not sunk_ship_coords_tuples: # Si hubo error en las coordenadas o no hay
                             print(f"Advertencia: No se procesaron coordenadas para OPPONENT_SHIP_SUNK {ship_name_sunk}.")
                             continue
                         
                        # El resto de tu lógica para este comando puede seguir aquí...
                        status_bar_message = f"¡Hundiste el {ship_name_sunk} de {id_jugador_afectado}!" # Actualizado para más claridad
                        print(f"INFO: Servidor informa: El {ship_name_sunk} de {id_jugador_afectado} en {sunk_ship_coords_tuples} ha sido hundido.")
                        if sunk_sound: sunk_sound.play()

                        sunk_ship_size = 0
                        for cfg_name, cfg_size in SHIPS_CONFIG:
                            if cfg_name == ship_name_sunk:
                                sunk_ship_size = cfg_size
                                break
                            
                        if sunk_ship_size == 0:
                            print(f"WARN: Tamaño desconocido para el barco oponente hundido: {ship_name_sunk}")
                            # Puedes asignar un tamaño por defecto o simplemente no añadirlo al log si es crítico
                            # continue 
                        
                        guessed_orientation = None
                        if len(sunk_ship_coords_tuples) > 0 : # Solo si tenemos coordenadas
                            if sunk_ship_size == 1: # Para barcos de una celda
                                guessed_orientation = 'H' # O 'V', según tu imagen base
                            elif len(sunk_ship_coords_tuples) > 1 :
                                all_r_same = all(coord[0] == sunk_ship_coords_tuples[0][0] for coord in sunk_ship_coords_tuples)
                                all_c_same = all(coord[1] == sunk_ship_coords_tuples[0][1] for coord in sunk_ship_coords_tuples)
                                if all_r_same and not all_c_same : guessed_orientation = 'H'
                                elif not all_r_same and all_c_same : guessed_orientation = 'V'
                        
                        print(f"DEBUG CLIENT: OPPONENT_SHIP_SUNK - TargetPlayer: {id_jugador_afectado}, Ship: {ship_name_sunk}, Size: {sunk_ship_size}, Coords: {sunk_ship_coords_tuples}, Guessed Orientation: {guessed_orientation}")


                        opponent_sunk_ships_log.append({
                            "name": ship_name_sunk, "size": sunk_ship_size,
                            "coords": sunk_ship_coords_tuples, "orientation": guessed_orientation
                        })

                        # Marcar TODAS las celdas de este barco hundido como 'S'
                        # Esto asegura que incluso la celda del último impacto sea 'S'.
                        for r_s, c_s in sunk_ship_coords_tuples:
                            if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE:
                                opponent_board_data[r_s][c_s] = 'S' 
                        
                        if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER:
                            print(f"DEBUG CLIENT (en OPPONENT_SHIP_SUNK): ¡Victoria local detectada! Enviando GAME_WON.")
                            send_message_to_server("GAME_WON")

                    except Exception as e:
                        # El error original se debía a los índices. Con los cambios, este catch podría capturar otros problemas.
                        print(f"Error GRAVE procesando OPPONENT_SHIP_SUNK: {e} - Datos: {message}")

                # Reemplazamos YOUR_TURN_AGAIN y OPPONENT_TURN_MSG con esto
                elif command == "TURN": # [cite: 169]
                    next_turn_player_id = parts[1] # ID individual
                    
                    # Determinar si el next_turn_player_id es de mi equipo o del oponente
                    # Esta lógica necesita que el cliente conozca la asignación de jugadores a equipos.
                    # El servidor podría enviar esta información después de que todos se conecten.
                    # Por ahora, nos basamos en el ID individual para el mensaje.
                    
                    if next_turn_player_id == player_id_str:
                        current_game_state = STATE_YOUR_TURN
                        status_bar_message = "¡Tu turno! Dispara en el tablero enemigo."
                    else:
                        current_game_state = STATE_OPPONENT_TURN
                        # Para mostrar el nombre del equipo del jugador actual, necesitaríamos más info del servidor
                        # o que el cliente infiera el equipo del next_turn_player_id.
                        # Por simplicidad, usamos el ID individual por ahora:
                        status_bar_message = f"Turno del jugador {next_turn_player_id}. Esperando..."
                
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
    global is_team_board_slave, player_id_str

    ship_name, ship_size = ship_config_tuple
    can_place, temp_coords = can_place_ship_at(board, r, c, ship_size, current_ship_orientation)

    if can_place:
        actual_ship_coords = []
        for sr, sc in temp_coords:
            board[sr][sc] = 1 
            actual_ship_coords.append((sr,sc))
        
        img_top_left_x = BOARD_OFFSET_X_MY + c * CELL_SIZE
        img_top_left_y = BOARD_OFFSET_Y + r * CELL_SIZE
        ship_img_data = ship_images.get(ship_name)
        width, height = (ship_size * CELL_SIZE, CELL_SIZE)
        if ship_img_data:
            actual_image = ship_img_data.get(current_ship_orientation)
            if actual_image:
                width = actual_image.get_width()
                height = actual_image.get_height()
        ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, width, height)

        my_placed_ships_detailed.append({
            "name": ship_name,
            "base_image_key": ship_name,
            "size": ship_size,
            "coords": actual_ship_coords,
            "orientation": current_ship_orientation,
            "is_sunk": False,
            "image_rect_on_board": ship_screen_rect
        })
        
        current_ship_placement_index += 1
        if current_ship_placement_index >= len(ships_to_place_list):
            # --- Serializar y enviar el estado de los barcos antes de READY_SETUP ---
            if player_id_str in ("P1", "P3"):
                barcos_serializados = []
                for barco in my_placed_ships_detailed:
                    coords_flat = " ".join(f"{r} {c}" for r, c in barco["coords"])
                    barcos_serializados.append(f"{coords_flat}|{barco['name']}|{barco['orientation']}")
                payload = ";".join(barcos_serializados)
                send_message_to_server(f"TEAM_BOARD_DATA {payload}")
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
    
    # Comprobar si el total de celdas impactadas/hundidas alcanza el total de celdas de todos los barcos
    if hit_and_sunk_cells_on_opponent >= TOTAL_SHIP_CELLS:
        print(f"DEBUG: ¡Victoria detectada! Celdas impactadas/hundidas: {hit_and_sunk_cells_on_opponent}/{TOTAL_SHIP_CELLS}")
        return True
    return False

# NUEVO: Variable para saber si el jugador es "esclavo" del tablero de equipo (P2/P4)
is_team_board_slave = False

def game_main_loop():
    global screen, font_large, font_medium, font_small, current_game_state, status_bar_message
    global current_ship_orientation, SERVER_IP, hit_sound, miss_sound, sunk_sound, client_socket
    global g_my_team_name, g_opponent_team_name # Añadir las nuevas globales
    global is_team_board_slave, player_id_str # is_team_board_slave ya existía

    if len(sys.argv) > 1: SERVER_IP = sys.argv[1]
    print(f"Usando IP del servidor: {SERVER_IP}")

    # Ya NO se llama a prompt_for_player_name() aquí al inicio.

    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    # El título se puede actualizar después de recibir el player_id_str o nombre de equipo
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

    threading.Thread(target=connect_to_server_thread, daemon=True).start()

    is_game_running = True
    game_clock = pygame.time.Clock()

    while is_game_running:
        mouse_current_pos = pygame.mouse.get_pos()
        # --- NUEVO: Manejo del estado para pedir nombre de equipo ---
        if current_game_state == "AWAITING_TEAM_NAME_INPUT":
            # Esta es una forma de integrar el prompt en el bucle principal
            # El hilo de escucha puso el estado, ahora el hilo principal actúa
            print(f"DEBUG CLIENT [{player_id_str}]: Estado AWAITING_TEAM_NAME_INPUT detectado. Mostrando prompt.")
            team_name_entered = prompt_for_team_name_gui() # Esta función ahora usa pygame y corre en el hilo principal
            if team_name_entered:
                send_message_to_server(f"TEAM_NAME_IS {team_name_entered}")
                status_bar_message = f"Nombre de equipo '{team_name_entered}' enviado. Esperando al otro equipo..."
                current_game_state = "WAITING_FOR_TEAM_NAMES" # Nuevo estado para esperar la confirmación de ambos nombres
            else:
                # El usuario cerró el prompt o no ingresó nada (prompt_for_team_name_gui debería manejar esto)
                # Podríamos reenviar REQUEST_TEAM_NAME o usar un default si el servidor no lo maneja
                status_bar_message = "Ingreso de nombre de equipo cancelado o vacío. Esperando..."
                # Quizás volver a un estado de espera pasiva o que el servidor re-solicite.
                # Por ahora, el servidor usará un default si no recibe TEAM_NAME_IS a tiempo.
                current_game_state = "WAITING_FOR_TEAM_NAMES" # O un estado de error
                
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                is_game_running = False
            
            # Solo procesar eventos de juego si no estamos en medio de un input de nombre de equipo
            if current_game_state != "AWAITING_TEAM_NAME_INPUT" and current_game_state != STATE_GAME_OVER :
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # ... (lógica de clic para SETUP_SHIPS y YOUR_TURN como la tienes) ...
                    if current_game_state == STATE_SETUP_SHIPS and current_ship_placement_index < len(ships_to_place_list) and not is_team_board_slave: # [cite: 230]
                        r, c = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y)
                        if r is not None and c is not None:
                            attempt_to_place_ship(my_board_data, r, c, ships_to_place_list[current_ship_placement_index]) # [cite: 231]
                    
                    elif current_game_state == STATE_YOUR_TURN:
                        r_shot, c_shot = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y)

                        if r_shot is not None and c_shot is not None: # Solo si el clic fue en una celda
                            cell_val_opp = opponent_board_data[r_shot][c_shot]
                            opp_info_valid = bool(opponents_info and opponents_info[0].get('id'))
                            can_shoot_condition = (opp_info_valid and cell_val_opp == 0)

                            # print(f"DEBUG CLIENT [{player_id_str}] Intento Disparo:")
                            # print(f"   Estado: {current_game_state}")
                            # print(f"  Clic en: ({r_shot}, {c_shot})")
                            # print(f"  opponents_info: {opponents_info}") # Ver si tiene IDs
                            # print(f"  Valor celda oponente [{r_shot}][{c_shot}]: {cell_val_opp}")
                            # print(f"  Condición 'opponents_info es válido': {opp_info_valid}")
                            # print(f"  Condición 'celda oponente es 0': {cell_val_opp == 0}")
                            # print(f"  ¿Se cumple condición para disparar?: {can_shoot_condition}")

                            if can_shoot_condition:
                                target_id = opponents_info[0]['id'] 
                                send_message_to_server(f"SHOT {target_id} {r_shot} {c_shot}")
                                status_bar_message = "Disparo enviado. Esperando resultado..."
                                print(f"INFO CLIENT [{player_id_str}]: SHOT enviado a {target_id} en ({r_shot},{c_shot})")
                            else:
                                status_bar_message = "No se puede disparar en esa celda o no hay oponentes." # Mensaje de UI
                                print(f"WARN CLIENT [{player_id_str}]: Disparo no realizado. Chequear condiciones de arriba.")
                if event.type == pygame.KEYDOWN:
                    if current_game_state == STATE_SETUP_SHIPS and not is_team_board_slave:
                        if event.key == pygame.K_r:
                            current_ship_orientation = 'V' if current_ship_orientation == 'H' else 'H'
                            next_ship_name_display = ""
                            if current_ship_placement_index < len(ships_to_place_list):
                                next_ship_name_display = ships_to_place_list[current_ship_placement_index][0]
                            orientation_text = "Horizontal" if current_ship_orientation == 'H' else "Vertical"
                            status_bar_message = f"Coloca: {next_ship_name_display}. Orient: {orientation_text}. 'R' para rotar."
        screen.fill(BLACK)
        
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
            # No enviar más mensajes si el juego ha terminado o hay error.
            # Solo cerrar.
            # client_socket.shutdown(socket.SHUT_RDWR) # Puede dar error si ya está cerrado
            client_socket.close()
        except Exception as e:
            print(f"Error al cerrar el socket del cliente: {e}")
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    game_main_loop()