# client.py
import pygame
import socket
import threading
import sys
import time
import os

# SERVER_IP será seteado en game_main_loop o usado el default
DEFAULT_SERVER_IP = "169.254.107.4" # IP del servidor unificado
PORT = 8080 # [cite: 721, 990]

# --- Configuración de Pygame ---
SCREEN_WIDTH = 900 # [cite: 721, 991]
SCREEN_HEIGHT = 500 # [cite: 721, 991]
GRID_SIZE = 10 # [cite: 721, 991]
CELL_SIZE = 30 # [cite: 721, 991]

BOARD_OFFSET_X_MY = 50 # [cite: 721, 991]
BOARD_OFFSET_Y = 80 # [cite: 721, 991]
BOARD_OFFSET_X_OPPONENT = BOARD_OFFSET_X_MY + GRID_SIZE * CELL_SIZE + 70 # [cite: 721, 991]

WHITE = (255, 255, 255) # [cite: 721, 991]
BLACK = (0, 0, 0) # [cite: 721, 991]
BLUE_WATER = (100, 149, 237) # [cite: 721, 991]
GREEN_PREVIEW_BORDER = (0, 200, 0) # [cite: 721, 991]
RED_PREVIEW_BORDER = (200, 0, 0) # [cite: 722, 991]
RED_HIT = (200, 0, 0) # [cite: 722, 991]
YELLOW_MISS = (200, 200, 0) # [cite: 722, 991]
BOARD_GRID_COLOR = (50, 50, 150) # [cite: 722, 991]
TEXT_COLOR = (230, 230, 230) # [cite: 722, 991]
STATUS_TEXT_COLOR = WHITE # [cite: 722, 992]

# Estados del juego (se mantienen la mayoría)
STATE_CONNECTING = "CONNECTING" # [cite: 722, 992]
STATE_WAITING_FOR_PLAYER = "WAITING_FOR_PLAYER" # [cite: 722, 992] # Usado mientras se llena la partida
STATE_AWAITING_TEAM_NAME_INPUT = "AWAITING_TEAM_NAME_INPUT" # Nuevo para modo 4J Capitán
STATE_WAITING_FOR_TEAM_INFO = "WAITING_FOR_TEAM_INFO" # Nuevo para esperar TEAMS_INFO_FINAL
STATE_SETUP_SHIPS = "SETUP_SHIPS" # [cite: 722, 992]
STATE_WAITING_OPPONENT_SETUP = "WAITING_OPPONENT_SETUP" # [cite: 722, 992]
STATE_YOUR_TURN = "YOUR_TURN" # [cite: 722, 992]
STATE_OPPONENT_TURN = "OPPONENT_TURN" # [cite: 722, 992]
STATE_GAME_OVER = "GAME_OVER" # [cite: 722, 992]

SHIPS_CONFIG = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3), ("Submarine", 3), ("Destroyer", 2)] # [cite: 722, 992]
TOTAL_SHIP_CELLS = sum(size for _, size in SHIPS_CONFIG) # [cite: 722, 992]

# --- Variables Globales del Cliente ---
screen = None # [cite: 722, 992]
font_large = None # [cite: 722, 992]
font_medium = None # [cite: 722, 992]
font_small = None # [cite: 722, 992]
client_socket = None # [cite: 722, 992]
player_id_str = None # [cite: 722, 992]
current_game_state = STATE_CONNECTING # [cite: 722, 992]
status_bar_message = "Conectando al servidor..." # [cite: 722, 992]

g_current_game_id_on_client = None # Para almacenar el ID de la partida a la que el cliente está conectado

my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] # [cite: 722, 992]
opponent_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] # [cite: 723, 992]

ships_to_place_list = list(SHIPS_CONFIG) # [cite: 723, 992]
current_ship_placement_index = 0 # [cite: 723, 992]
current_ship_orientation = 'H' # [cite: 723, 992]
my_placed_ships_detailed = [] # [cite: 723, 992]
opponent_sunk_ships_log = [] # Para barcos hundidos del oponente [cite: 723, 993]

# Específico del modo de juego
game_mode = 0 # 2 o 4, se setea en game_main_loop
player_name_local = "" # Para modo 2J [cite: 725]
g_my_team_name = None # Para modo 4J [cite: 995]
g_opponent_team_name = None # Para modo 4J [cite: 995]
opponents_info = [] # Para modo 4J: [{"id": "P3", "name": "TeamB_name"}, {"id": "P4", "name": "TeamB_name"}] [cite: 993]
is_captain = False # True si es P1 o P3 en modo 4J
is_team_board_slave = False # True si es P2 o P4 en modo 4J (recibe tablero del capitán) [cite: 1169]

ship_images = {} # [cite: 724, 994]
SHIP_IMAGE_FILES = { # [cite: 725, 995]
    "Carrier": "carrier.png", "Battleship": "battleship.png", "Cruiser": "cruiser.png",
    "Submarine": "submarine.png", "Destroyer": "destroyer.png"
}
BASE_PATH = os.path.dirname(os.path.abspath(__file__)) # [cite: 725, 995]
assets_path = os.path.join(BASE_PATH, "assets") # [cite: 725, 995]

hit_sound, miss_sound, sunk_sound = None, None, None # [cite: 725, 995]
server_ip_global = DEFAULT_SERVER_IP


def prompt_for_player_name_gui(): # Similar a la versión 2J [cite: 725, 1003]
    global screen, font_large, font_medium, font_small # Asegurarse que están inicializadas
    pygame.display.set_caption("Batalla Naval - Ingresa tu nombre") # [cite: 726, 1004]
    input_box = pygame.Rect(SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2, 300, 48) # [cite: 726, 1004]
    color_inactive = pygame.Color('lightskyblue3') # [cite: 726, 1004]
    color_active = pygame.Color('dodgerblue2') # [cite: 726, 1004]
    color = color_inactive # [cite: 726, 1004]
    active = False # [cite: 726, 1004]
    text = "" # [cite: 726, 1004]
    done = False # [cite: 726, 1005]

    while not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: # [cite: 727, 1005]
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN: # [cite: 727, 1005]
                if input_box.collidepoint(event.pos): # [cite: 727, 1005]
                    active = not active # [cite: 728, 1006]
                else:
                    active = False # [cite: 728, 1006]
                color = color_active if active else color_inactive # [cite: 728, 1006]
            if event.type == pygame.KEYDOWN: # [cite: 728, 1006]
                if active: # [cite: 729, 1007]
                    if event.key == pygame.K_RETURN: # [cite: 729, 1007]
                        if text.strip(): # [cite: 729, 1007]
                            done = True # [cite: 729, 1007]
                    elif event.key == pygame.K_BACKSPACE: # [cite: 730, 1008]
                        text = text[:-1] # [cite: 730, 1008]
                    elif len(text) < 20 and event.unicode.isprintable(): # [cite: 730, 1008]
                        text += event.unicode # [cite: 730, 1008]

        screen.fill(BLACK) # [cite: 730, 1008]
        draw_text_on_screen(screen, "Ingresa tu nombre:", (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 60), font_medium, WHITE) # [cite: 731, 1009]
        txt_surface = font_large.render(text, True, color) # [cite: 731, 1009]
        width = max(300, txt_surface.get_width()+10) # [cite: 731, 1009]
        input_box.w = width # [cite: 731, 1009]
        screen.blit(txt_surface, (input_box.x+5, input_box.y+5)) # [cite: 731, 1009]
        pygame.draw.rect(screen, color, input_box, 2, border_radius=5) # [cite: 731, 1009]
        draw_text_on_screen(screen, "Presiona Enter para continuar", (input_box.x, SCREEN_HEIGHT // 2 + 60), font_small, WHITE) # [cite: 731, 1009]
        pygame.display.flip() # [cite: 732, 1010]
    return text.strip() # [cite: 732, 1010]

def prompt_for_team_name_gui(): # De la versión 4J [cite: 996]
    global screen, font_large, font_medium, font_small, player_id_str
    pygame.display.set_caption(f"Batalla Naval - Capitán {player_id_str}, nombra tu Equipo") # [cite: 997]
    input_box = pygame.Rect(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT // 2, 400, 48) # [cite: 997]
    color_inactive = pygame.Color('lightskyblue3') # [cite: 997]
    color_active = pygame.Color('dodgerblue2') # [cite: 997]
    color = color_inactive # [cite: 997]
    active = False # [cite: 997]
    text = "" # [cite: 997]
    done = False
    prompt_message = f"Capitan {player_id_str}, ingresa el nombre de tu equipo:" # [cite: 998]

    while not done:
        for event in pygame.event.get():
            if event.type == pygame.QUIT: # [cite: 998]
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN: # [cite: 998]
                if input_box.collidepoint(event.pos): # [cite: 999]
                    active = not active
                else:
                    active = False
                color = color_active if active else color_inactive # [cite: 999]
            if event.type == pygame.KEYDOWN: # [cite: 1000]
                if active: # [cite: 1000]
                    if event.key == pygame.K_RETURN: # [cite: 1000]
                        if text.strip(): # [cite: 1000]
                            done = True # [cite: 1001]
                    elif event.key == pygame.K_BACKSPACE: # [cite: 1001]
                        text = text[:-1] # [cite: 1001]
                    elif len(text) < 25 and event.unicode.isprintable(): # [cite: 1001]
                        text += event.unicode # [cite: 1002]

        screen.fill(BLACK) # [cite: 1002]
        draw_text_on_screen(screen, prompt_message, (SCREEN_WIDTH // 2 - input_box.w // 2 - 10 , SCREEN_HEIGHT // 2 - 60), font_medium, WHITE) # [cite: 1002]
        txt_surface = font_large.render(text, True, color) # [cite: 1002]
        screen.blit(txt_surface, (input_box.x+10, input_box.y+5)) # [cite: 1003]
        pygame.draw.rect(screen, color, input_box, 2, border_radius=5) # [cite: 1003]
        draw_text_on_screen(screen, "Presiona Enter para continuar", (input_box.x, SCREEN_HEIGHT // 2 + 60), font_small, WHITE) # [cite: 1003]
        pygame.display.flip()
    return text.strip()


def connect_to_server_thread(action, game_id_for_join=None): # Nuevos argumentos
    global client_socket, current_game_state, status_bar_message, player_id_str
    global game_mode, player_name_local, server_ip_global, g_current_game_id_on_client # Añadido g_current_game_id_on_client

    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        print(f"Intentando conectar a {server_ip_global}:{PORT}...")
        client_socket.connect((server_ip_global, PORT))

        initial_server_msg_payload = ""
        if action == "CREATE":
            initial_server_msg_payload = f"CREATE_GAME {game_mode}"
            if game_mode == 2 and player_name_local:
                initial_server_msg_payload += f" {player_name_local.replace(' ', '_')}"
        elif action == "JOIN" and game_id_for_join is not None:
            initial_server_msg_payload = f"JOIN_GAME {game_id_for_join} {game_mode}" # Cliente envía el modo de la partida a la que se une
            if game_mode == 2 and player_name_local: # Opcional: enviar nombre al unirse a 2J
                initial_server_msg_payload += f" {player_name_local.replace(' ', '_')}"
        else:
            status_bar_message = "Error: Acción de conexión no especificada o ID de partida faltante."
            current_game_state = STATE_GAME_OVER
            # Considerar cerrar el socket aquí si es un error irrecuperable.
            return

        client_socket.sendall(f"{initial_server_msg_payload}\n".encode())
        print(f"DEBUG CLIENT: Enviado al servidor: {initial_server_msg_payload}")

        status_bar_message = "Conectado. Esperando asignación..."
        threading.Thread(target=listen_for_server_messages, daemon=True).start()
    except ConnectionRefusedError:
        status_bar_message = "Error: Conexion rechazada por el servidor."
        current_game_state = STATE_GAME_OVER
    except Exception as e:
        status_bar_message = f"Error de conexion: {e}"
        current_game_state = STATE_GAME_OVER


def listen_for_server_messages():
    global current_game_state, status_bar_message, player_id_str, my_board_data, opponent_board_data
    global opponent_sunk_ships_log, game_mode, g_my_team_name, g_opponent_team_name, opponents_info
    global is_captain, is_team_board_slave, current_ship_placement_index # Asegurar acceso
    global g_current_game_id_on_client # Para almacenar el ID de la partida asignada

    data_buffer = "" # [cite: 735]
    while current_game_state != STATE_GAME_OVER and client_socket: # [cite: 735]
        try:
            data_bytes = client_socket.recv(2048) # [cite: 735, 1014] # Aumentado por si acaso
            if not data_bytes: # [cite: 735, 1014]
                if current_game_state != STATE_GAME_OVER : # [cite: 736, 1014]
                    status_bar_message = "Desconectado del servidor (recv vacío)." # [cite: 736, 1015]
                    current_game_state = STATE_GAME_OVER # [cite: 736, 1015]
                break # [cite: 736, 1015]
            
            data_buffer += data_bytes.decode() # [cite: 737, 1015]
            
            while '\n' in data_buffer: # [cite: 737, 1015]
                message, data_buffer = data_buffer.split('\n', 1) # [cite: 738, 1016]
                message = message.strip() # [cite: 738, 1016]
                if not message: continue # [cite: 738, 1016]

                print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: Servidor dice: '{message}'") # [cite: 738, 1017]
                parts = message.split() # [cite: 739, 1017]
                if not parts: continue # [cite: 739, 1017]
                command = parts[0] # [cite: 739, 1018]

                if command == "MSG": # [cite: 740, 1051]
                    status_bar_message = ' '.join(parts[1:])
                elif command == "PLAYER_ID": # [cite: 740, 1052]
                    player_id_str = parts[1] # [cite: 740, 1052]
                    player_id_str = parts[1]
                    if len(parts) > 2: # Servidor envía game_id
                        try:
                            g_current_game_id_on_client = int(parts[2])
                            status_bar_message = f"ID: {player_id_str} en Partida: {g_current_game_id_on_client}. Esperando..."
                        except ValueError:
                            status_bar_message = f"ID asignado: {player_id_str}. ID de partida inválido: {parts[2]}"
                            g_current_game_id_on_client = None # Marcar como inválido
                    else: # Fallback por si el servidor no envía el game_id (compatibilidad o error)
                        status_bar_message = f"ID asignado: {player_id_str}. Esperando..."
                        g_current_game_id_on_client = None # No se recibió ID de partida
                    status_bar_message = f"ID asignado: {player_id_str}. Esperando..." # [cite: 1052]
                    if game_mode == 4:
                        is_captain = (player_id_str == "P1" or player_id_str == "P3")
                        is_team_board_slave = (player_id_str == "P2" or player_id_str == "P4")
                        if not is_captain and not is_team_board_slave: # Reset para 2J
                            is_captain = False
                            is_team_board_slave = False


                elif command == "OPPONENT_NAME": # Modo 2J [cite: 740]
                    if game_mode == 2:
                        g_opponent_team_name = ' '.join(parts[1:]) # Usamos esta var para el nombre del oponente en 2J
                        status_bar_message = f"Oponente: {g_opponent_team_name}. Esperando configuración..."

                elif command == "REQUEST_TEAM_NAME": # Modo 4J, para capitanes [cite: 1053]
                    if game_mode == 4 and is_captain:
                        current_game_state = STATE_AWAITING_TEAM_NAME_INPUT # [cite: 1064]
                        status_bar_message = "Servidor solicita nombre de equipo. Ingresa en ventana." # [cite: 1064]
                
                elif command == "TEAMS_INFO_FINAL": # Modo 4J [cite: 1066]
                    if game_mode == 4:
                        try:
                            g_my_team_name = parts[1].replace("_", " ") # [cite: 1066]
                            g_opponent_team_name = parts[2].replace("_", " ") # [cite: 1067]
                            opponents_info.clear() # [cite: 1067]
                            if len(parts) > 3: # [cite: 1068]
                                opponent_ids_received = parts[3:] # [cite: 1069]
                                for opp_id in opponent_ids_received: # [cite: 1069]
                                    opponents_info.append({"id": opp_id, "name": g_opponent_team_name}) # [cite: 1071]
                            status_bar_message = f"Tu equipo: {g_my_team_name}. Oponente: {g_opponent_team_name}." # [cite: 1071]
                            current_game_state = STATE_WAITING_FOR_PLAYER # O un estado más específico si es necesario antes de SETUP
                            print(f"INFO CLIENT: Nombres de equipo recibidos. Mío: '{g_my_team_name}', Oponente: '{g_opponent_team_name}'. Opponent IDs: {[oi['id'] for oi in opponents_info]}") # [cite: 1071]
                        except IndexError:
                            print(f"Error parseando TEAMS_INFO_FINAL: {message}") # [cite: 1073]

                elif command == "SETUP_YOUR_BOARD": # [cite: 741, 1074]
                     # Solo si no es esclavo de tablero (P2/P4 en 4J)
                    if not is_team_board_slave:
                        current_game_state = STATE_SETUP_SHIPS # [cite: 741, 1074]
                        current_ship_placement_index = 0 # Reset para colocación
                        my_placed_ships_detailed.clear()
                        my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
                        status_bar_message = f"{player_id_str}: Coloca tus barcos. 'R' para rotar." # [cite: 741, 1075]
                    else: # P2/P4 esperan TEAM_BOARD
                         status_bar_message = "Esperando tablero del capitán de tu equipo..."
                
                elif command == "TEAM_BOARD": # Solo para P2/P4 en modo 4J [cite: 1018]
                    if game_mode == 4 and is_team_board_slave:
                        print(f"DEBUG CLIENT [{player_id_str}]: Procesando TEAM_BOARD: {message[:100]}...") # [cite: 1018]
                        my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] # [cite: 1019]
                        my_placed_ships_detailed.clear() # [cite: 1019]
                        
                        board_content_str = message[len("TEAM_BOARD "):].strip() # [cite: 1019]
                        if not board_content_str: # [cite: 1020]
                            print(f"WARN CLIENT [{player_id_str}]: TEAM_BOARD recibido con payload vacío.") # [cite: 1020]
                        else:
                            barcos_str_list = board_content_str.split(";") # [cite: 1021]
                            for barco_def_str in barcos_str_list: # [cite: 1022]
                                barco_def_str = barco_def_str.strip() # [cite: 1022]
                                if not barco_def_str: continue # [cite: 1023]
                                try:
                                    coords_part, name, orient = barco_def_str.split("|") # [cite: 1024]
                                    coords_str_list = coords_part.strip().split() # [cite: 1026]
                                    parsed_coords_int = [int(x) for x in coords_str_list] # [cite: 1027]
                                    
                                    current_ship_coords_tuples = [] # [cite: 1028]
                                    if len(parsed_coords_int) % 2 != 0: continue # [cite: 1028]

                                    for i in range(0, len(parsed_coords_int), 2): # [cite: 1029]
                                        r, c = parsed_coords_int[i], parsed_coords_int[i+1] # [cite: 1029]
                                        if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE): # [cite: 1030]
                                            current_ship_coords_tuples.clear(); break # [cite: 1031]
                                        my_board_data[r][c] = 1 # MARCAR EN EL TABLERO LÓGICO [cite: 1032]
                                        current_ship_coords_tuples.append((r, c)) # [cite: 1032]
                                    
                                    if not current_ship_coords_tuples: continue # [cite: 1033]

                                    ref_r, ref_c = current_ship_coords_tuples[0] # [cite: 1036]
                                    img_top_left_x = BOARD_OFFSET_X_MY + ref_c * CELL_SIZE # [cite: 1036, 1037]
                                    img_top_left_y = BOARD_OFFSET_Y + ref_r * CELL_SIZE # [cite: 1037]
                                    
                                    ship_img_data_slave = ship_images.get(name) # [cite: 1038]
                                    width, height = (len(current_ship_coords_tuples) * CELL_SIZE, CELL_SIZE) # Default H [cite: 1038]
                                    if orient == 'V': width, height = CELL_SIZE, len(current_ship_coords_tuples) * CELL_SIZE
                                    
                                    if ship_img_data_slave: # [cite: 1039]
                                        actual_img_slave = ship_img_data_slave.get(orient) # [cite: 1039]
                                        if actual_img_slave: # [cite: 1040]
                                            width, height = actual_img_slave.get_width(), actual_img_slave.get_height() # [cite: 1040]
                                    
                                    ship_screen_rect_slave = pygame.Rect(img_top_left_x, img_top_left_y, width, height) # [cite: 1041]
                                    my_placed_ships_detailed.append({ # [cite: 1041]
                                        "name": name, "base_image_key": name, # [cite: 1042]
                                        "size": len(current_ship_coords_tuples), "coords": list(current_ship_coords_tuples), # [cite: 1042]
                                        "orientation": orient, "is_sunk": False, # [cite: 1043]
                                        "image_rect_on_board": ship_screen_rect_slave # [cite: 1044]
                                    })
                                    print(f"DEBUG CLIENT [{player_id_str}]: TEAM_BOARD: Añadido barco '{name}'") # [cite: 1044]
                                except Exception as e_tb_parse:
                                    print(f"ERROR CLIENT [{player_id_str}]: TEAM_BOARD parse error: {e_tb_parse} en '{barco_def_str}'") # [cite: 1045, 1046, 1047]
                                    
                        current_game_state = STATE_WAITING_OPPONENT_SETUP # [cite: 1050]
                        status_bar_message = "Tablero de equipo recibido. Esperando al oponente..." # [cite: 1051]
                    continue # Importante para no procesar como otro comando

                elif command == "START_GAME": # [cite: 742, 1075]
                    starting_player = parts[1] # [cite: 742, 1075]
                    if starting_player == player_id_str: # [cite: 742, 1075]
                        current_game_state = STATE_YOUR_TURN # [cite: 742, 1076]
                        status_bar_message = "¡Tu turno! Dispara en el tablero enemigo." # [cite: 743, 1077]
                    else: # [cite: 743, 1077]
                        current_game_state = STATE_OPPONENT_TURN # [cite: 743, 1077]
                        status_bar_message = f"Turno del oponente ({starting_player}). Esperando..." # [cite: 743, 1078]
                
                elif command == "SHOT": # Disparo recibido en mi tablero [cite: 744, 1078]
                    r, c = int(parts[1]), int(parts[2]) # [cite: 744, 1078]
                    shot_result_char = 'M' # [cite: 744, 1078]
                    if my_board_data[r][c] == 1: # Es un barco no impactado [cite: 744, 1079]
                        my_board_data[r][c] = 'H' # Marcar como impacto [cite: 745, 1079]
                        shot_result_char = 'H' # [cite: 745, 1079]
                        if hit_sound: hit_sound.play() # [cite: 745, 1079]
                        check_and_update_my_sunk_ships() # [cite: 745, 1080]
                    elif my_board_data[r][c] == 0: # Agua [cite: 746, 1080]
                        my_board_data[r][c] = 'M' # Marcar como fallo [cite: 746, 1080]
                        if miss_sound: miss_sound.play() # [cite: 746, 1081]
                    send_message_to_server(f"RESULT {r} {c} {shot_result_char}") # [cite: 747, 1081]

                elif command == "UPDATE": # Resultado de mi disparo [cite: 747, 1081]
                    if game_mode == 2:
                        r_upd, c_upd = int(parts[1]), int(parts[2]) # [cite: 747]
                        result_char_upd = parts[3] # [cite: 747]
                        current_cell_state_opp = opponent_board_data[r_upd][c_upd] # [cite: 747]
                        if result_char_upd == 'H': # [cite: 748]
                            if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'H' # [cite: 750]
                            if hit_sound: hit_sound.play() # [cite: 750]
                            status_bar_message = f"¡Impacto en ({r_upd},{c_upd})!"
                        elif result_char_upd == 'M': # [cite: 754]
                            if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'M' # [cite: 755]
                            if miss_sound: miss_sound.play() # [cite: 756]
                            status_bar_message = f"Agua en ({r_upd},{c_upd})." # [cite: 755]
                        
                        if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER: # [cite: 751, 753]
                            send_message_to_server("GAME_WON") # [cite: 753]
                    
                    elif game_mode == 4:
                        try:
                            target_player_id_update = parts[1] # A quién se le actualiza el tablero [cite: 1082]
                            r_upd, c_upd = int(parts[2]), int(parts[3]) # [cite: 1082]
                            result_char_upd = parts[4] # [cite: 1082]
                            
                            is_opponent_target = any(opp['id'] == target_player_id_update for opp in opponents_info) # [cite: 1083]

                            if is_opponent_target: # [cite: 1084]
                                current_cell_state_opp = opponent_board_data[r_upd][c_upd] # [cite: 1083]
                                if result_char_upd == 'H': # [cite: 1084]
                                    if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'H' # [cite: 1087]
                                    if hit_sound: hit_sound.play() # [cite: 1087]
                                    status_bar_message = f"¡Impacto en ({r_upd},{c_upd}) del oponente {target_player_id_update}!"
                                elif result_char_upd == 'M': # [cite: 1088]
                                    if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'M' # [cite: 1089]
                                    if miss_sound: miss_sound.play() # [cite: 1089]
                                    status_bar_message = f"Agua en ({r_upd},{c_upd}) del oponente {target_player_id_update}."
                                if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER: # [cite: 1090]
                                    send_message_to_server("GAME_WON") # [cite: 1090]
                            else: # Es un update para mi equipo (no debería pasar si yo disparé, pero por si acaso)
                                if my_board_data[r_upd][c_upd] == 1 and result_char_upd == 'H': # [cite: 1091]
                                    my_board_data[r_upd][c_upd] = 'H' # [cite: 1092]
                                    check_and_update_my_sunk_ships() # [cite: 1092]
                                elif my_board_data[r_upd][c_upd] == 0 and result_char_upd == 'M': # [cite: 1092]
                                    my_board_data[r_upd][c_upd] = 'M' # [cite: 1093]
                        except (IndexError, ValueError) as e_upd4:
                            print(f"Error procesando UPDATE (4P): {message}, {e_upd4}") # [cite: 1093]
                
                elif command == "OPPONENT_SHIP_SUNK": # [cite: 756, 1094]
                    try:
                        if game_mode == 2:
                            ship_name_sunk_2p = parts[1] # [cite: 756]
                            flat_coords_2p = [int(p) for p in parts[2:]] # [cite: 757]
                            sunk_ship_coords_tuples_2p = [] # [cite: 757]
                            for i in range(0, len(flat_coords_2p), 2): sunk_ship_coords_tuples_2p.append((flat_coords_2p[i], flat_coords_2p[i+1])) # [cite: 757]
                            status_bar_message = f"¡Hundiste el {ship_name_sunk_2p} del oponente!" # [cite: 758]
                            if sunk_sound: sunk_sound.play() # [cite: 759]
                            sunk_ship_size_2p = 0; orient_2p = None # [cite: 759, 761]
                            for name_cfg, size_cfg in SHIPS_CONFIG: # [cite: 759]
                                if name_cfg == ship_name_sunk_2p: sunk_ship_size_2p = size_cfg; break # [cite: 760]
                            if len(sunk_ship_coords_tuples_2p) > 0: # [cite: 761]
                                if sunk_ship_size_2p == 1: orient_2p = 'H' # [cite: 762]
                                elif len(sunk_ship_coords_tuples_2p) > 1:
                                    r_same = all(c[0] == sunk_ship_coords_tuples_2p[0][0] for c in sunk_ship_coords_tuples_2p) # [cite: 761]
                                    c_same = all(c[1] == sunk_ship_coords_tuples_2p[0][1] for c in sunk_ship_coords_tuples_2p) # [cite: 761]
                                    if r_same and not c_same: orient_2p = 'H' # [cite: 762]
                                    elif not r_same and c_same: orient_2p = 'V' # [cite: 762]
                            opponent_sunk_ships_log.append({"name": ship_name_sunk_2p, "size": sunk_ship_size_2p, "coords": sunk_ship_coords_tuples_2p, "orientation": orient_2p}) # [cite: 763]
                            for r_s, c_s in sunk_ship_coords_tuples_2p: # [cite: 764]
                                if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE: opponent_board_data[r_s][c_s] = 'S' # [cite: 765]
                        
                        elif game_mode == 4:
                            id_jugador_afectado_sunk = parts[1] # [cite: 1096]
                            ship_name_sunk_4p = parts[2] # [cite: 1098]
                            flat_coords_str_4p = parts[3:] # [cite: 1099]
                            sunk_ship_coords_tuples_4p = [] # [cite: 1100]
                            if len(flat_coords_str_4p) % 2 != 0: continue # [cite: 1100]
                            for i in range(0, len(flat_coords_str_4p), 2): # [cite: 1101]
                                try: sunk_ship_coords_tuples_4p.append((int(flat_coords_str_4p[i]), int(flat_coords_str_4p[i+1]))) # [cite: 1102]
                                except ValueError: sunk_ship_coords_tuples_4p.clear(); break # [cite: 1103]
                            if not sunk_ship_coords_tuples_4p: continue # [cite: 1105]
                            
                            status_bar_message = f"¡Hundiste el {ship_name_sunk_4p} de {id_jugador_afectado_sunk}!" # [cite: 1106]
                            if sunk_sound: sunk_sound.play() # [cite: 1107]
                            sunk_ship_size_4p = 0; orient_4p = None # [cite: 1107, 1111]
                            for name_cfg, size_cfg in SHIPS_CONFIG: # [cite: 1108]
                                if name_cfg == ship_name_sunk_4p: sunk_ship_size_4p = size_cfg; break # [cite: 1108]
                            if sunk_ship_size_4p == 0 : print(f"WARN: Tamaño desconocido para {ship_name_sunk_4p}") # [cite: 1109]

                            if len(sunk_ship_coords_tuples_4p) > 0: # [cite: 1111]
                                if sunk_ship_size_4p == 1: orient_4p = 'H' # [cite: 1111]
                                elif len(sunk_ship_coords_tuples_4p) > 1: # [cite: 1112]
                                    r_same = all(c[0] == sunk_ship_coords_tuples_4p[0][0] for c in sunk_ship_coords_tuples_4p) # [cite: 1113]
                                    c_same = all(c[1] == sunk_ship_coords_tuples_4p[0][1] for c in sunk_ship_coords_tuples_4p) # [cite: 1113]
                                    if r_same and not c_same: orient_4p = 'H' # [cite: 1113]
                                    elif not r_same and c_same: orient_4p = 'V' # [cite: 1114]
                            
                            opponent_sunk_ships_log.append({"name": ship_name_sunk_4p, "size": sunk_ship_size_4p, "coords": sunk_ship_coords_tuples_4p, "orientation": orient_4p}) # [cite: 1115]
                            for r_s, c_s in sunk_ship_coords_tuples_4p: # [cite: 1117]
                                if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE: opponent_board_data[r_s][c_s] = 'S' # [cite: 1117]
                        
                        # Chequeo de victoria común después de procesar el hundimiento
                        if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER: # [cite: 766, 767, 1118]
                            send_message_to_server("GAME_WON") # [cite: 769, 1118]
                    except Exception as e_sunk:
                        print(f"Error procesando OPPONENT_SHIP_SUNK: {e_sunk} - Datos: {message}") # [cite: 769, 1119]

                elif command == "YOUR_TURN_AGAIN": # Modo 2J [cite: 770]
                    if game_mode == 2:
                        current_game_state = STATE_YOUR_TURN # [cite: 770]
                        if not status_bar_message.startswith("¡Impacto") and not status_bar_message.startswith("Agua"): # [cite: 770]
                            status_bar_message = "¡Tu turno! Dispara." # [cite: 771]
                        else: status_bar_message += " ¡Sigue tu turno!" # [cite: 771]
                
                elif command == "OPPONENT_TURN_MSG": # Modo 2J [cite: 772]
                     if game_mode == 2:
                        current_game_state = STATE_OPPONENT_TURN # [cite: 772]
                        status_bar_message = "Turno del oponente. Esperando..." # [cite: 772]
                
                elif command == "TURN": # Modo 4J (reemplaza YOUR_TURN_AGAIN y OPPONENT_TURN_MSG) [cite: 1120]
                    if game_mode == 4:
                        next_turn_player_id = parts[1] # [cite: 1120]
                        if next_turn_player_id == player_id_str: # [cite: 1124]
                            current_game_state = STATE_YOUR_TURN # [cite: 1124]
                            status_bar_message = "¡Tu turno! Dispara en el tablero enemigo." # [cite: 1124]
                        else: # [cite: 1125]
                            current_game_state = STATE_OPPONENT_TURN # [cite: 1125]
                            status_bar_message = f"Turno del jugador {next_turn_player_id}. Esperando..." # [cite: 1126]
            
                elif command == "GAME_OVER": # [cite: 773, 1126]
                    current_game_state = STATE_GAME_OVER # [cite: 773, 1127]
                    if parts[1] == "WIN": status_bar_message = "¡HAS GANADO LA PARTIDA! :D" # [cite: 773, 1127]
                    else: status_bar_message = "Has perdido. Mejor suerte la proxima. :(" # [cite: 774, 1128]
                    # El hilo de escucha terminará debido al cambio de estado [cite: 775, 1128]
                
                elif command == "OPPONENT_LEFT": # Un jugador del equipo oponente se fue (Modo 2J) [cite: 776, 1130]
                    if game_mode == 2 and current_game_state != STATE_GAME_OVER: # [cite: 777, 1130]
                        status_bar_message = "El oponente se ha desconectado. ¡Ganas por defecto!" # [cite: 777, 1130]
                        current_game_state = STATE_GAME_OVER # [cite: 777, 1131]
                
                elif command == "OPPONENT_TEAM_LEFT": # Un jugador del equipo oponente se fue (Modo 4J)
                    if game_mode == 4 and current_game_state != STATE_GAME_OVER:
                        # El mensaje del servidor ya indica quién ganó/perdió
                        # parts[1:] es el mensaje del servidor
                        full_opponent_left_msg = " ".join(parts[1:])
                        # No necesitamos cambiar el estado a GAME_OVER WIN/LOSE aquí,
                        # porque el servidor enviará GAME_OVER WIN/LOSE por separado después de este mensaje.
                        # Este mensaje es solo informativo.
                        status_bar_message = full_opponent_left_msg
                        # El GAME_OVER que viene después se encargará del estado.


        except ConnectionResetError: # [cite: 777, 1131]
            if current_game_state != STATE_GAME_OVER: # [cite: 778, 1131]
                status_bar_message = "Conexion perdida con el servidor (reset)." # [cite: 778, 1132]
                current_game_state = STATE_GAME_OVER # [cite: 778, 1132]
            break # [cite: 778, 1132]
        except socket.error as e: # [cite: 778, 1132]
            if current_game_state != STATE_GAME_OVER: # [cite: 779, 1132]
                status_bar_message = f"Error de socket: {e}" # [cite: 779, 1132]
                current_game_state = STATE_GAME_OVER # [cite: 779, 1132]
            break # [cite: 779, 1132]
        except Exception as e: # [cite: 779, 1133]
            print(f"Error escuchando al servidor: {e} (Mensaje: '{message}')") # [cite: 779, 1133]
            if current_game_state != STATE_GAME_OVER: # [cite: 780, 1133]
                status_bar_message = f"Error de red general: {e}" # [cite: 780, 1133]
                current_game_state = STATE_GAME_OVER # [cite: 780, 1133]
            break # [cite: 780, 1133]
    
    print(f"Hilo de escucha del cliente ({player_id_str or 'N/A'}) terminado.") # [cite: 780, 1134]


def send_message_to_server(message):
    global status_bar_message, current_game_state
    if client_socket and client_socket.fileno() != -1: # [cite: 781, 1135]
        try:
            client_socket.sendall(f"{message}\n".encode()) # [cite: 782, 1136]
        except socket.error as e: # [cite: 782, 1136]
            print(f"Error enviando mensaje: {e}") # [cite: 782, 1136]
            if current_game_state != STATE_GAME_OVER: # [cite: 782, 1136]
                status_bar_message = "Error de red al enviar." # [cite: 783, 1137]
                current_game_state = STATE_GAME_OVER # [cite: 783, 1137]
        except Exception as e: # [cite: 783, 1137]
            print(f"Excepción general al enviar mensaje: {e}") # [cite: 783, 1137]
            if current_game_state != STATE_GAME_OVER: # [cite: 784, 1137]
                status_bar_message = "Error desconocido al enviar." # [cite: 784, 1138]
                current_game_state = STATE_GAME_OVER # [cite: 784, 1138]


def create_darkened_image(original_image_surface, darkness_alpha=128): # [cite: 784, 1138]
    if original_image_surface is None: return None
    darkened_surface = original_image_surface.copy()
    overlay = pygame.Surface(darkened_surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, darkness_alpha))
    darkened_surface.blit(overlay, (0, 0))
    return darkened_surface

def check_and_update_my_sunk_ships(): # [cite: 785, 1139]
    global my_placed_ships_detailed, my_board_data, status_bar_message, sunk_sound
    for ship_info in my_placed_ships_detailed: # [cite: 785, 1139]
        if not ship_info["is_sunk"]: # [cite: 785, 1139]
            hits_on_ship = 0
            for r_coord, c_coord in ship_info["coords"]: # [cite: 785, 1139]
                if my_board_data[r_coord][c_coord] == 'H': hits_on_ship += 1 # [cite: 785, 1139]
            if hits_on_ship == ship_info["size"]: # [cite: 786, 1140]
                ship_info["is_sunk"] = True # [cite: 786, 1140]
                sunk_ship_name = ship_info["name"] # [cite: 786, 1140]
                print(f"INFO: ¡Mi {sunk_ship_name} ha sido hundido!") # [cite: 786, 1140]
                coords_list_for_server = [] # [cite: 786, 1140]
                for r_s, c_s in ship_info["coords"]: # [cite: 787, 1141]
                    coords_list_for_server.extend([str(r_s), str(c_s)]) # [cite: 787, 1141]
                coords_payload_str = " ".join(coords_list_for_server) # [cite: 787, 1141]
                send_message_to_server(f"I_SUNK_MY_SHIP {sunk_ship_name} {coords_payload_str}") # [cite: 787, 1141]
                if sunk_sound: sunk_sound.play() # [cite: 788, 1142]


def draw_game_grid(surface, offset_x, offset_y, board_matrix, is_my_board): # [cite: 788, 1142]
    for r_idx in range(GRID_SIZE): # [cite: 788, 1142]
        for c_idx in range(GRID_SIZE): # [cite: 788, 1142]
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE) # [cite: 788, 1142]
            pygame.draw.rect(surface, BLUE_WATER, cell_rect) # [cite: 789, 1143]
            pygame.draw.rect(surface, BOARD_GRID_COLOR, cell_rect, 1) # [cite: 789, 1143]

    # Dibujar imágenes de barcos
    if is_my_board: # [cite: 790, 1144]
        for ship_detail in my_placed_ships_detailed: # [cite: 790, 1144]
            ship_name = ship_detail["base_image_key"] # [cite: 790, 1144]
            orientation = ship_detail["orientation"] # [cite: 790, 1144]
            ship_img_dict = ship_images.get(ship_name) # [cite: 790, 1144]
            if ship_img_dict: # [cite: 790, 1144]
                current_ship_image = ship_img_dict.get(orientation) # [cite: 791, 1145]
                if current_ship_image: # [cite: 791, 1145]
                    image_to_draw = create_darkened_image(current_ship_image) if ship_detail["is_sunk"] else current_ship_image # [cite: 791, 1145]
                    if image_to_draw and ship_detail.get("image_rect_on_board"): # [cite: 791, 1145]
                        surface.blit(image_to_draw, ship_detail["image_rect_on_board"].topleft) # [cite: 792, 1146]
    else: # Tablero oponente [cite: 792, 1146]
        for sunk_info in opponent_sunk_ships_log: # [cite: 792, 1146]
            ship_name_opp = sunk_info["name"] # [cite: 792, 1146]
            orientation_opp = sunk_info.get("orientation") # [cite: 792, 1146]
            coords_opp = sunk_info["coords"] # [cite: 792, 1146]
            if not coords_opp or orientation_opp is None: continue # [cite: 793, 1147]
            ship_img_data_opp = ship_images.get(ship_name_opp) # [cite: 793, 1147]
            if ship_img_data_opp: # [cite: 793, 1147]
                base_image_opp = ship_img_data_opp.get(orientation_opp) # [cite: 793, 1147]
                if base_image_opp: # [cite: 793, 1147]
                    darkened_opp_ship_img = create_darkened_image(base_image_opp, darkness_alpha=150) # [cite: 793, 1147]
                    if darkened_opp_ship_img: # [cite: 794, 1148]
                        min_r = min(r for r,c in coords_opp) # [cite: 794, 1148]
                        min_c = min(c for r,c in coords_opp) # [cite: 794, 1148]
                        screen_x = offset_x + min_c * CELL_SIZE # [cite: 795, 1149]
                        screen_y = offset_y + min_r * CELL_SIZE # [cite: 795, 1149]
                        surface.blit(darkened_opp_ship_img, (screen_x, screen_y)) # [cite: 795, 1149]
    
    # Dibujar marcadores de celda (H, M, S)
    for r_idx in range(GRID_SIZE): # [cite: 795, 1149]
        for c_idx in range(GRID_SIZE): # [cite: 795, 1149]
            cell_val = board_matrix[r_idx][c_idx] # [cite: 796, 1150]
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE) # [cite: 796, 1150]
            if cell_val == 'H': # [cite: 796, 1150]
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.top + 5), (cell_rect.right - 5, cell_rect.bottom - 5), 4) # [cite: 796, 1150]
                pygame.draw.line(surface, RED_HIT, (cell_rect.left + 5, cell_rect.bottom - 5), (cell_rect.right - 5, cell_rect.top + 5), 4) # [cite: 797, 1151]
            elif cell_val == 'M': # [cite: 797, 1151]
                pygame.draw.circle(surface, YELLOW_MISS, cell_rect.center, CELL_SIZE // 4) # [cite: 797, 1151]
            elif cell_val == 'S': # [cite: 797, 1151]
                # Fondo verde para 'S' (originalmente para depuración)
                debug_fill_s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA) # [cite: 798, 1152]
                debug_fill_s.fill((0, 80, 0, 100)) # Verde oscuro semi-transparente [cite: 798, 1152]
                surface.blit(debug_fill_s, cell_rect.topleft) # [cite: 798, 1152]
                line_thickness_sunk, padding_sunk = 5, 5 # [cite: 798, 1152]
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.top + padding_sunk), (cell_rect.right - padding_sunk, cell_rect.bottom - padding_sunk), line_thickness_sunk) # [cite: 799, 1153]
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.bottom - padding_sunk), (cell_rect.right - padding_sunk, cell_rect.top + padding_sunk), line_thickness_sunk) # [cite: 799, 1153]


def draw_text_on_screen(surface, text_content, position, font_to_use, color=TEXT_COLOR): # [cite: 799, 1153]
    text_surface = font_to_use.render(text_content, True, color) # [cite: 800, 1154]
    surface.blit(text_surface, position) # [cite: 800, 1154]

def get_grid_cell_from_mouse(mouse_coords, board_start_x, board_start_y): # [cite: 800, 1154]
    mouse_x, mouse_y = mouse_coords
    if board_start_x <= mouse_x < board_start_x + GRID_SIZE * CELL_SIZE and \
       board_start_y <= mouse_y < board_start_y + GRID_SIZE * CELL_SIZE: # [cite: 800, 1154]
        col = (mouse_x - board_start_x) // CELL_SIZE # [cite: 800, 1154]
        row = (mouse_y - board_start_y) // CELL_SIZE # [cite: 800, 1154]
        return row, col
    return None, None # [cite: 801, 1154]

def can_place_ship_at(board, r, c, ship_size, orientation): # [cite: 801, 1155]
    ship_coords = [] # [cite: 801, 1155]
    for i in range(ship_size): # [cite: 801, 1155]
        current_r, current_c = r, c
        if orientation == 'H': current_c += i # [cite: 801, 1155]
        else: current_r += i # [cite: 801, 1155]
        if not (0 <= current_r < GRID_SIZE and 0 <= current_c < GRID_SIZE): return False, [] # [cite: 801, 1155]
        if board[current_r][current_c] == 1: return False, [] # Casilla ya ocupada [cite: 801, 1155]
        ship_coords.append((current_r, current_c)) # [cite: 801, 1155]
    return True, ship_coords # [cite: 801, 1155]

def attempt_to_place_ship(board, r, c, ship_config_tuple): # [cite: 802, 1156]
    global current_ship_placement_index, my_placed_ships_detailed, current_game_state, status_bar_message
    global game_mode, player_id_str # Necesario para TEAM_BOARD_DATA
    
    ship_name, ship_size = ship_config_tuple # [cite: 802, 1156]
    can_place, temp_coords = can_place_ship_at(board, r, c, ship_size, current_ship_orientation) # [cite: 802, 1156]

    if can_place: # [cite: 802, 1156]
        actual_ship_coords = [] # [cite: 802, 1156]
        for sr, sc in temp_coords: # [cite: 802, 1156]
            board[sr][sc] = 1 # [cite: 802, 1156]
            actual_ship_coords.append((sr,sc)) # [cite: 802, 1156]
        
        img_top_left_x = BOARD_OFFSET_X_MY + c * CELL_SIZE # [cite: 804, 1157]
        img_top_left_y = BOARD_OFFSET_Y + r * CELL_SIZE # [cite: 804, 1157]
        ship_img_data = ship_images.get(ship_name) # [cite: 804, 1157]
        width, height = (ship_size * CELL_SIZE, CELL_SIZE) # Default H [cite: 804, 1157]
        if current_ship_orientation == 'V': width, height = CELL_SIZE, ship_size * CELL_SIZE
        
        if ship_img_data: # [cite: 805, 1157]
            actual_image = ship_img_data.get(current_ship_orientation) # [cite: 805, 1157]
            if actual_image: width, height = actual_image.get_width(), actual_image.get_height() # [cite: 805, 1158]
        ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, width, height) # [cite: 805, 1158]

        my_placed_ships_detailed.append({ # [cite: 806, 1158]
            "name": ship_name, "base_image_key": ship_name, "size": ship_size, # [cite: 806, 1158]
            "coords": actual_ship_coords, "orientation": current_ship_orientation, # [cite: 806, 1159]
            "is_sunk": False, "image_rect_on_board": ship_screen_rect # [cite: 806, 1159]
        })
        
        current_ship_placement_index += 1 # [cite: 807, 1159]
        if current_ship_placement_index >= len(ships_to_place_list): # [cite: 807, 1159]
            # Si es modo 4J y es capitán (P1/P3), enviar datos del tablero
            if game_mode == 4 and is_captain: # (player_id_str == "P1" or player_id_str == "P3") [cite: 1160]
                barcos_serializados = [] # [cite: 1160]
                for barco in my_placed_ships_detailed: # [cite: 1160]
                    coords_flat = " ".join(f"{r_coord} {c_coord}" for r_coord, c_coord in barco["coords"]) # [cite: 1160]
                    barcos_serializados.append(f"{coords_flat}|{barco['name']}|{barco['orientation']}") # [cite: 1160]
                payload = ";".join(barcos_serializados) # [cite: 1161]
                send_message_to_server(f"TEAM_BOARD_DATA {payload}") # [cite: 1161]
                print(f"DEBUG CLIENT [{player_id_str}]: Enviado TEAM_BOARD_DATA.")

            send_message_to_server("READY_SETUP") # [cite: 807, 1161]
            current_game_state = STATE_WAITING_OPPONENT_SETUP # [cite: 807, 1161]
            status_bar_message = "Barcos colocados. Esperando al oponente..." # [cite: 808, 1162]
        else: # [cite: 808, 1162]
            next_ship_name = ships_to_place_list[current_ship_placement_index][0] # [cite: 808, 1162]
            status_bar_message = f"Coloca: {next_ship_name}. 'R' para rotar." # [cite: 809, 1163]
        return True # [cite: 809, 1163]
    return False # [cite: 809, 1163]

def draw_ship_placement_preview(surface, mouse_pos): # [cite: 809, 1163]
    if current_game_state == STATE_SETUP_SHIPS and current_ship_placement_index < len(ships_to_place_list): # [cite: 809, 1163]
        ship_name, ship_size = ships_to_place_list[current_ship_placement_index] # [cite: 809, 1163]
        row, col = get_grid_cell_from_mouse(mouse_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y) # [cite: 809, 1163]

        if row is not None and col is not None: # [cite: 809, 1163]
            ship_img_data = ship_images.get(ship_name) # [cite: 809, 1163]
            if ship_img_data: # [cite: 810, 1164]
                preview_img_original = ship_img_data.get(current_ship_orientation) # [cite: 810, 1164]
                if preview_img_original: # [cite: 810, 1164]
                    preview_img = preview_img_original.copy() # [cite: 810, 1164]
                    preview_img.set_alpha(180) # [cite: 810, 1164]
                    screen_x = BOARD_OFFSET_X_MY + col * CELL_SIZE # [cite: 811, 1165]
                    screen_y = BOARD_OFFSET_Y + row * CELL_SIZE # [cite: 811, 1165]
                    surface.blit(preview_img, (screen_x, screen_y)) # [cite: 812, 1166]
                    
                    can_place_flag, _ = can_place_ship_at(my_board_data, row, col, ship_size, current_ship_orientation) # [cite: 812, 1166]
                    border_color = GREEN_PREVIEW_BORDER if can_place_flag else RED_PREVIEW_BORDER # [cite: 812, 1166]
                    img_rect_for_border = pygame.Rect(screen_x, screen_y, preview_img.get_width(), preview_img.get_height()) # [cite: 813, 1167]
                    pygame.draw.rect(surface, border_color, img_rect_for_border, 2) # [cite: 813, 1167]

def check_if_opponent_is_defeated(opponent_b): # [cite: 813, 1167]
    hit_and_sunk_cells = 0 # [cite: 813, 1167]
    for r in range(GRID_SIZE): # [cite: 813, 1167]
        for c in range(GRID_SIZE): # [cite: 813, 1167]
            if opponent_b[r][c] == 'H' or opponent_b[r][c] == 'S': hit_and_sunk_cells += 1 # [cite: 814, 1168]
    if hit_and_sunk_cells >= TOTAL_SHIP_CELLS: # [cite: 814, 1168]
        print(f"DEBUG CLIENT: ¡Victoria local detectada! Celdas H/S oponente: {hit_and_sunk_cells}/{TOTAL_SHIP_CELLS}") # [cite: 815, 1169]
        return True # [cite: 815, 1169]
    return False # [cite: 816, 1169]


def game_main_loop(mode, server_ip_to_join=None, game_id_to_join=None, action="CREATE"): # action y game_id_to_join
    global screen, font_large, font_medium, font_small, current_game_state, status_bar_message
    global current_ship_orientation, hit_sound, miss_sound, sunk_sound, client_socket
    global game_mode, player_name_local, server_ip_global
    global g_my_team_name, g_opponent_team_name, is_captain, is_team_board_slave, player_id_str
    global g_current_game_id_on_client # Nueva global

    game_mode = mode
    server_ip_global = server_ip_to_join if server_ip_to_join else DEFAULT_SERVER_IP
    # game_id_to_join no se usa activamente en este cliente para conectar, pero podría ser útil

    if len(sys.argv) > 1: server_ip_global = sys.argv[1] # Override por argumento CLI [cite: 816]
    print(f"Usando IP del servidor: {server_ip_global}, Modo de juego: {game_mode}") # [cite: 816]

    pygame.init() # [cite: 816, 1170]
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT)) # [cite: 817, 1170]
    pygame.display.set_caption(f"Batalla Naval Cliente - Modo {game_mode}J") # [cite: 817, 1170]
    font_large = pygame.font.Font(None, 48) # [cite: 817, 1170]
    font_medium = pygame.font.Font(None, 36) # [cite: 817, 1170]
    font_small = pygame.font.Font(None, 28) # [cite: 817, 1170]

    if game_mode == 2 and action == "CREATE": # Solo pedir nombre si crea una partida 2J
        player_name_local = prompt_for_player_name_gui()
        if not player_name_local:
            # ... (salir si no hay nombre)
            return # Añadido para asegurar que no continúe
    elif game_mode == 2 and action == "JOIN": # Si se une a 2J, también pedir nombre
        player_name_local = prompt_for_player_name_gui() # O decidir si el nombre es necesario al unirse
        if not player_name_local: player_name_local = f"JugadorInvitado" # Fallback

    # Cargar sonidos
    pygame.mixer.init() # [cite: 817, 1170]
    try:
        hit_sound_file = os.path.join(assets_path, "acertado.wav") # [cite: 817, 1170]
        miss_sound_file = os.path.join(assets_path, "fallido.wav") # [cite: 817, 1171]
        sunk_sound_file = os.path.join(assets_path, "hundido.wav") # [cite: 817, 1171]
        if os.path.exists(hit_sound_file): hit_sound = pygame.mixer.Sound(hit_sound_file) # [cite: 818, 1171]
        if os.path.exists(miss_sound_file): miss_sound = pygame.mixer.Sound(miss_sound_file) # [cite: 818, 1171]
        if os.path.exists(sunk_sound_file): sunk_sound = pygame.mixer.Sound(sunk_sound_file) # [cite: 818, 1171]
    except Exception as e: print(f"Error cargando sonidos: {e}") # [cite: 818, 1172]

    # Cargar imágenes de barcos
    print("Cargando imágenes de barcos...") # [cite: 819, 1172]
    for ship_name_key, ship_size_val in SHIPS_CONFIG: # [cite: 820, 1173]
        ship_filename = SHIP_IMAGE_FILES.get(ship_name_key) # [cite: 820, 1173]
        if not ship_filename: print(f"No se definio imagen para: {ship_name_key}"); continue # [cite: 820, 1173]
        try:
            image_path = os.path.join(assets_path, ship_filename) # [cite: 821, 1174]
            if os.path.exists(image_path): # [cite: 821, 1174]
                img_h_original = pygame.image.load(image_path).convert_alpha() # [cite: 821, 1174]
                scaled_h_width, scaled_h_height = ship_size_val * CELL_SIZE, CELL_SIZE # [cite: 823, 1176]
                img_h = pygame.transform.scale(img_h_original, (scaled_h_width, scaled_h_height)) # [cite: 823, 1176]
                img_v_temp = pygame.transform.rotate(img_h_original, 90) # [cite: 824, 1177]
                scaled_v_width, scaled_v_height = CELL_SIZE, ship_size_val * CELL_SIZE # [cite: 824, 1177]
                img_v = pygame.transform.scale(img_v_temp, (scaled_v_width, scaled_v_height)) # [cite: 824, 1177]
                ship_images[ship_name_key] = {"H": img_h, "V": img_v} # [cite: 825, 1178]
            else: print(f"Archivo no encontrado: {image_path}"); ship_images[ship_name_key] = None # [cite: 825, 1178]
        except Exception as e_img: print(f"Error cargando imagen {ship_name_key}: {e_img}"); ship_images[ship_name_key] = None # [cite: 826, 1179]

    # Pasar la acción y el game_id (si es JOIN) al hilo de conexión
    threading.Thread(target=connect_to_server_thread, args=(action, game_id_to_join), daemon=True).start()

    is_game_running = True # [cite: 826, 1179]
    game_clock = pygame.time.Clock() # [cite: 826, 1179]

    while is_game_running: # [cite: 826, 1179]
        mouse_current_pos = pygame.mouse.get_pos() # [cite: 826, 1179]

        if current_game_state == STATE_AWAITING_TEAM_NAME_INPUT: # [cite: 1180]
             # Este estado especial se maneja aquí para el input GUI
            if game_mode == 4 and is_captain: # [cite: 1180]
                print(f"DEBUG CLIENT [{player_id_str}]: Estado AWAITING_TEAM_NAME_INPUT detectado. Mostrando prompt.") # [cite: 1180]
                team_name_entered = prompt_for_team_name_gui() # [cite: 1181]
                if team_name_entered: # [cite: 1181]
                    send_message_to_server(f"TEAM_NAME_IS {team_name_entered}") # [cite: 1181]
                    status_bar_message = f"Nombre de equipo '{team_name_entered}' enviado. Esperando..." # [cite: 1182]
                    current_game_state = STATE_WAITING_FOR_TEAM_INFO # Esperar TEAMS_INFO_FINAL [cite: 1182]
                else: # [cite: 1182]
                    status_bar_message = "Ingreso de nombre cancelado. Esperando acción del servidor..." # [cite: 1183]
                    current_game_state = STATE_WAITING_FOR_TEAM_INFO # O un estado de error/reintento [cite: 1184]
            else: # No debería estar en este estado si no es capitán en modo 4J
                current_game_state = STATE_WAITING_FOR_PLAYER # Volver a un estado de espera general

        for event in pygame.event.get(): # [cite: 827, 1185]
            if event.type == pygame.QUIT: is_game_running = False # [cite: 827, 1185]
            
            if current_game_state != STATE_AWAITING_TEAM_NAME_INPUT and current_game_state != STATE_GAME_OVER : # [cite: 827, 1185]
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: # [cite: 827, 1186]
                    # Lógica de clic para SETUP y YOUR_TURN
                    can_place_now = (current_game_state == STATE_SETUP_SHIPS and \
                                     current_ship_placement_index < len(ships_to_place_list) and \
                                     not is_team_board_slave) # P2/P4 no colocan [cite: 828, 1186]
                    
                    if can_place_now: # [cite: 1186]
                        r_place, c_place = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y) # [cite: 828, 1187]
                        if r_place is not None and c_place is not None: # [cite: 828, 1187]
                            attempt_to_place_ship(my_board_data, r_place, c_place, ships_to_place_list[current_ship_placement_index]) # [cite: 828, 1187]
                    
                    elif current_game_state == STATE_YOUR_TURN: # [cite: 829, 1188]
                        r_shot, c_shot = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y) # [cite: 829, 1188]
                        if r_shot is not None and c_shot is not None: # [cite: 829, 1188]
                            # Verificar si la celda ya fue disparada
                            if opponent_board_data[r_shot][c_shot] == 0: # Solo disparar a celdas no tocadas [cite: 829, 1189]
                                if game_mode == 2: # [cite: 830]
                                    send_message_to_server(f"SHOT {r_shot} {c_shot}") # [cite: 830]
                                elif game_mode == 4:
                                    if opponents_info and opponents_info[0].get('id'): # [cite: 1189]
                                        # Disparar al primer oponente del equipo contrario por defecto
                                        # Una mejora sería permitir seleccionar a cuál de los dos oponentes disparar
                                        target_id_4p = opponents_info[0]['id'] # [cite: 1193]
                                        send_message_to_server(f"SHOT {target_id_4p} {r_shot} {c_shot}") # [cite: 1193]
                                        print(f"INFO CLIENT [{player_id_str}]: SHOT enviado a {target_id_4p} en ({r_shot},{c_shot})") # [cite: 1195]
                                    else: status_bar_message = "Error: No hay información de oponentes para disparar."; print("WARN CLIENT: No opponents_info para SHOT") # [cite: 1196]
                                status_bar_message = "Disparo enviado. Esperando resultado..." # [cite: 830, 1194]
                            else: status_bar_message = "Ya disparaste en esa celda." # [cite: 1196]
                
                if event.type == pygame.KEYDOWN: # [cite: 831, 1196]
                    if current_game_state == STATE_SETUP_SHIPS and not is_team_board_slave : # [cite: 831, 1197]
                        if event.key == pygame.K_r: # [cite: 832, 1197]
                            current_ship_orientation = 'V' if current_ship_orientation == 'H' else 'H' # [cite: 832, 1197]
                            next_ship_name_display = "" # [cite: 832, 1197]
                            if current_ship_placement_index < len(ships_to_place_list): # [cite: 833, 1198]
                                next_ship_name_display = ships_to_place_list[current_ship_placement_index][0] # [cite: 833, 1198]
                            orientation_text = "Horizontal" if current_ship_orientation == 'H' else "Vertical" # [cite: 833, 1198]
                            status_bar_message = f"Coloca: {next_ship_name_display}. Orient: {orientation_text}. 'R' para rotar." # [cite: 834, 1200]
        
        # --- Dibujado ---
        screen.fill(BLACK) # [cite: 834, 1200]
        
        # Título de ventana dinámico
        window_title_dyn = f"Batalla Naval - {player_id_str or 'Conectando...'}" # [cite: 1200]
        if game_mode == 2 and g_opponent_team_name: window_title_dyn += f" vs {g_opponent_team_name}"
        elif game_mode == 4 and g_my_team_name: window_title_dyn = f"{g_my_team_name} ({player_id_str}) - Batalla Naval" # [cite: 1200]
        pygame.display.set_caption(window_title_dyn) # [cite: 1201]

        # Info de jugadores/equipos
        my_display_name = player_id_str or "Asignando..." # [cite: 834]
        if game_mode == 2 and player_name_local: my_display_name = player_name_local
        elif game_mode == 4 and g_my_team_name: my_display_name = f"Equipo: {g_my_team_name} ({player_id_str})" # [cite: 1201]
        
        opponent_display_name = "Esperando..." # [cite: 834]
        if game_mode == 2 and g_opponent_team_name: opponent_display_name = f"Oponente: {g_opponent_team_name}"
        elif game_mode == 4 and g_opponent_team_name: opponent_display_name = f"Equipo Oponente: {g_opponent_team_name}" # [cite: 1201]
        
        draw_text_on_screen(screen, my_display_name, (BOARD_OFFSET_X_MY, 10), font_small) # [cite: 1201]
        draw_text_on_screen(screen, opponent_display_name, (BOARD_OFFSET_X_OPPONENT - 20, 10), font_small) # [cite: 1201]

        draw_text_on_screen(screen, "TU FLOTA", (BOARD_OFFSET_X_MY, BOARD_OFFSET_Y - 40), font_medium) # [cite: 834, 1202]
        draw_text_on_screen(screen, "FLOTA ENEMIGA", (BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y - 40), font_medium) # [cite: 834, 1202]
        
        draw_game_grid(screen, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y, my_board_data, True) # [cite: 835, 1202]
        draw_game_grid(screen, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y, opponent_board_data, False) # [cite: 835, 1202]

        if current_game_state == STATE_SETUP_SHIPS and not is_team_board_slave: # [cite: 835, 1202]
            draw_ship_placement_preview(screen, mouse_current_pos) # [cite: 835, 1203]
            if current_ship_placement_index < len(ships_to_place_list): # [cite: 835, 1203]
                 ship_name_disp, ship_size_disp = ships_to_place_list[current_ship_placement_index] # [cite: 835, 1203]
                 orient_text_disp = 'H' if current_ship_orientation == 'H' else 'V' # [cite: 836, 1203]
                 info_text_disp = f"Colocando: {ship_name_disp} ({ship_size_disp}) Orient: {orient_text_disp}" # [cite: 836, 1203]
                 draw_text_on_screen(screen, info_text_disp, (10, SCREEN_HEIGHT - 70), font_small) # [cite: 836, 1204]

        pygame.draw.rect(screen, (30,30,30), (0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40)) # [cite: 836, 1204]
        draw_text_on_screen(screen, status_bar_message, (10, SCREEN_HEIGHT - 30), font_small, STATUS_TEXT_COLOR) # [cite: 836, 1204]
        
        pygame.display.flip() # [cite: 837, 1204]
        game_clock.tick(30) # [cite: 837, 1204]

    print("Saliendo del bucle principal de Pygame.") # [cite: 837, 1204]
    if client_socket: # [cite: 837, 1204]
        print("Cerrando socket del cliente...") # [cite: 837, 1204]
        try:
            # client_socket.shutdown(socket.SHUT_RDWR) # Puede dar error si ya está cerrado por el servidor [cite: 1206]
            client_socket.close() # [cite: 1205, 1206]
        except Exception as e_close:
            print(f"Error al cerrar el socket del cliente: {e_close}") # [cite: 1205, 1206]
    pygame.quit() # [cite: 837, 1205]
    sys.exit() # [cite: 837, 1205]


if __name__ == "__main__": # [cite: 838]
    # game_main_loop() # Ya no se llama directamente así. Se llama desde menu.py con el modo.
    print("Este archivo es el cliente de Batalla Naval. Ejecuta 'menu.py' para iniciar.")