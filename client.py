# client.py
import pygame
import socket
import threading
import sys
import time
import os

DEFAULT_SERVER_IP = "169.254.107.4" # IP del servidor
PORT = 8080 

# --- Configuración de Pygame ---
SCREEN_WIDTH = 900 
SCREEN_HEIGHT = 500 
GRID_SIZE = 10 
CELL_SIZE = 30 

BOARD_OFFSET_X_MY = 50 
BOARD_OFFSET_Y = 80 
BOARD_OFFSET_X_OPPONENT = BOARD_OFFSET_X_MY + GRID_SIZE * CELL_SIZE + 70 

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

# Estados del juego (se mantienen la mayoría)
STATE_CONNECTING = "CONNECTING"  # Estado inicial al conectar
STATE_WAITING_FOR_PLAYER = "WAITING_FOR_PLAYER"  # Usado mientras se llena la partida
STATE_AWAITING_TEAM_NAME_INPUT = "AWAITING_TEAM_NAME_INPUT" # Nuevo para modo 4J Capitán
STATE_WAITING_FOR_TEAM_INFO = "WAITING_FOR_TEAM_INFO" # Nuevo para esperar TEAMS_INFO_FINAL
STATE_SETUP_SHIPS = "SETUP_SHIPS" 
STATE_WAITING_OPPONENT_SETUP = "WAITING_OPPONENT_SETUP" 
STATE_YOUR_TURN = "YOUR_TURN" 
STATE_OPPONENT_TURN = "OPPONENT_TURN" 
STATE_GAME_OVER = "GAME_OVER" 

SHIPS_CONFIG = [("Carrier", 5), ("Battleship", 4), ("Cruiser", 3), ("Submarine", 3), ("Destroyer", 2)] 
TOTAL_SHIP_CELLS = sum(size for _, size in SHIPS_CONFIG) #

# --- Variables Globales del Cliente ---
screen = None 
font_large = None 
font_medium = None 
font_small = None 
client_socket = None 
player_id_str = None 
current_game_state = STATE_CONNECTING 
status_bar_message = "Conectando al servidor..." 

g_current_game_id_on_client = None 

my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] 
opponent_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] 

ships_to_place_list = list(SHIPS_CONFIG) 
current_ship_placement_index = 0 
current_ship_orientation = 'H' 
my_placed_ships_detailed = [] 
opponent_sunk_ships_log = [] # Para barcos hundidos del oponente 

# Específico del modo de juego
game_mode = 0 
player_name_local = "" # Para modo 2J 
g_my_team_name = None # Para modo 4J 
g_opponent_team_name = None # Para modo 4J 
opponents_info = [] # Para modo 4J: [{"id": "P3", "name": "TeamB_name"}, {"id": "P4", "name": "TeamB_name"}] 
is_captain = False # True si es P1 o P3 en modo 4J
is_team_board_slave = False # True si es P2 o P4 en modo 4J (recibe tablero del capitán) 

ship_images = {} 
SHIP_IMAGE_FILES = { 
    "Carrier": "carrier.png", "Battleship": "battleship.png", "Cruiser": "cruiser.png",
    "Submarine": "submarine.png", "Destroyer": "destroyer.png"
}
BASE_PATH = os.path.dirname(os.path.abspath(__file__)) 
assets_path = os.path.join(BASE_PATH, "assets") 

hit_sound, miss_sound, sunk_sound = None, None, None 
server_ip_global = DEFAULT_SERVER_IP

def prompt_for_player_name_gui(): # Similar a la versión 2J 
    global screen, font_large, font_medium, font_small # Asegurarse que están inicializadas
    pygame.display.set_caption("Batalla Naval - Ingresa tu nombre") 
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
        draw_text_on_screen(screen, "Ingresa tu nombre:", (SCREEN_WIDTH // 2 - 150, SCREEN_HEIGHT // 2 - 60), font_medium, WHITE) 
        txt_surface = font_large.render(text, True, color) 
        width = max(300, txt_surface.get_width()+10) 
        input_box.w = width 
        screen.blit(txt_surface, (input_box.x+5, input_box.y+5)) 
        pygame.draw.rect(screen, color, input_box, 2, border_radius=5) 
        draw_text_on_screen(screen, "Presiona Enter para continuar", (input_box.x, SCREEN_HEIGHT // 2 + 60), font_small, WHITE) 
        pygame.display.flip() 
    return text.strip() 

def prompt_for_team_name_gui(): # De la versión 4J 
    global screen, font_large, font_medium, font_small, player_id_str
    pygame.display.set_caption(f"Batalla Naval - Capitán {player_id_str}, nombra tu Equipo") 
    input_box = pygame.Rect(SCREEN_WIDTH // 2 - 200, SCREEN_HEIGHT // 2, 400, 48) 
    color_inactive = pygame.Color('lightskyblue3') 
    color_active = pygame.Color('dodgerblue2') 
    color = color_inactive 
    active = False 
    text = "" 
    done = False
    prompt_message = f"Capitan {player_id_str}, ingresa el nombre de tu equipo:" 

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
                    elif len(text) < 25 and event.unicode.isprintable(): 
                        text += event.unicode 

        screen.fill(BLACK) 
        draw_text_on_screen(screen, prompt_message, (SCREEN_WIDTH // 2 - input_box.w // 2 - 10 , SCREEN_HEIGHT // 2 - 60), font_medium, WHITE) 
        txt_surface = font_large.render(text, True, color) 
        screen.blit(txt_surface, (input_box.x+10, input_box.y+5)) 
        pygame.draw.rect(screen, color, input_box, 2, border_radius=5) 
        draw_text_on_screen(screen, "Presiona Enter para continuar", (input_box.x, SCREEN_HEIGHT // 2 + 60), font_small, WHITE) 
        pygame.display.flip()
    return text.strip()

def connect_to_server_thread(action, game_id_for_join=None): # Nuevos argumentos
    global client_socket, current_game_state, status_bar_message, player_id_str
    global game_mode, player_name_local, server_ip_global, g_current_game_id_on_client 

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
            if game_mode == 2 and player_name_local: 
                initial_server_msg_payload += f" {player_name_local.replace(' ', '_')}"
        else:
            status_bar_message = "Error: Acción de conexión no especificada o ID de partida faltante."
            current_game_state = STATE_GAME_OVER
            
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
    global is_captain, is_team_board_slave, current_ship_placement_index 
    global g_current_game_id_on_client # Para almacenar el ID de la partida asignada

    data_buffer = "" 
    while current_game_state != STATE_GAME_OVER and client_socket: 
        try:
            data_bytes = client_socket.recv(2048)  # Aumentado por si acaso
            if not data_bytes: 
                if current_game_state != STATE_GAME_OVER : 
                    status_bar_message = "Desconectado del servidor (recv vacío)."
                    current_game_state = STATE_GAME_OVER 
                break 
            
            data_buffer += data_bytes.decode() 
            
            while '\n' in data_buffer: 
                message, data_buffer = data_buffer.split('\n', 1) 
                message = message.strip() 
                if not message: continue 

                print(f"DEBUG CLIENT [{player_id_str or 'N/A'}]: Servidor dice: '{message}'") 
                parts = message.split() 
                if not parts: continue 
                command = parts[0] 

                if command == "MSG": 
                    status_bar_message = ' '.join(parts[1:])
                elif command == "PLAYER_ID": 
                    player_id_str = parts[1] 
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
                    status_bar_message = f"ID asignado: {player_id_str}. Esperando..." 
                    if game_mode == 4:
                        is_captain = (player_id_str == "P1" or player_id_str == "P3")
                        is_team_board_slave = (player_id_str == "P2" or player_id_str == "P4")
                        if not is_captain and not is_team_board_slave: # Reset para 2J
                            is_captain = False
                            is_team_board_slave = False

                elif command == "OPPONENT_NAME": # Modo 2J 
                    if game_mode == 2:
                        g_opponent_team_name = ' '.join(parts[1:]) # Usamos esta var para el nombre del oponente en 2J
                        status_bar_message = f"Oponente: {g_opponent_team_name}. Esperando configuración..."

                elif command == "REQUEST_TEAM_NAME": # Modo 4J, para capitanes 
                    if game_mode == 4 and is_captain:
                        current_game_state = STATE_AWAITING_TEAM_NAME_INPUT  
                        status_bar_message = "Servidor solicita nombre de equipo. Ingresa en ventana." 
                
                elif command == "TEAMS_INFO_FINAL": # Modo 4J 
                    if game_mode == 4:
                        try:
                            g_my_team_name = parts[1].replace("_", " ") 
                            g_opponent_team_name = parts[2].replace("_", " ") 
                            opponents_info.clear() 
                            if len(parts) > 3: 
                                opponent_ids_received = parts[3:] 
                                for opp_id in opponent_ids_received: 
                                    opponents_info.append({"id": opp_id, "name": g_opponent_team_name}) 
                            status_bar_message = f"Tu equipo: {g_my_team_name}. Oponente: {g_opponent_team_name}." 
                            current_game_state = STATE_WAITING_FOR_PLAYER 
                            print(f"INFO CLIENT: Nombres de equipo recibidos. Mío: '{g_my_team_name}', Oponente: '{g_opponent_team_name}'. Opponent IDs: {[oi['id'] for oi in opponents_info]}") 
                        except IndexError:
                            print(f"Error parseando TEAMS_INFO_FINAL: {message}") 

                elif command == "SETUP_YOUR_BOARD": 
                     # Solo si no es esclavo de tablero (P2/P4 en 4J)
                    if not is_team_board_slave:
                        current_game_state = STATE_SETUP_SHIPS 
                        current_ship_placement_index = 0 
                        my_placed_ships_detailed.clear()
                        my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
                        status_bar_message = f"{player_id_str}: Coloca tus barcos. 'R' para rotar." 
                    else: 
                         status_bar_message = "Esperando tablero del capitán de tu equipo..."
                
                elif command == "TEAM_BOARD": # Solo para P2/P4 en modo 4J [cite: 1018]
                    if game_mode == 4 and is_team_board_slave:
                        print(f"DEBUG CLIENT [{player_id_str}]: Procesando TEAM_BOARD: {message[:100]}...") 
                        my_board_data = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)] 
                        my_placed_ships_detailed.clear() 
                        
                        board_content_str = message[len("TEAM_BOARD "):].strip() 
                        if not board_content_str: 
                            print(f"WARN CLIENT [{player_id_str}]: TEAM_BOARD recibido con payload vacío.") 
                        else:
                            barcos_str_list = board_content_str.split(";") 
                            for barco_def_str in barcos_str_list: 
                                barco_def_str = barco_def_str.strip() 
                                if not barco_def_str: continue 
                                try:
                                    coords_part, name, orient = barco_def_str.split("|") 
                                    coords_str_list = coords_part.strip().split() 
                                    parsed_coords_int = [int(x) for x in coords_str_list]
                                    
                                    current_ship_coords_tuples = [] 
                                    if len(parsed_coords_int) % 2 != 0: continue 

                                    for i in range(0, len(parsed_coords_int), 2): 
                                        r, c = parsed_coords_int[i], parsed_coords_int[i+1] 
                                        if not (0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE): 
                                            current_ship_coords_tuples.clear(); break 
                                        my_board_data[r][c] = 1 # MARCAR EN EL TABLERO LÓGIC
                                        current_ship_coords_tuples.append((r, c)) 
                                    
                                    if not current_ship_coords_tuples: continue 

                                    ref_r, ref_c = current_ship_coords_tuples[0] 
                                    img_top_left_x = BOARD_OFFSET_X_MY + ref_c * CELL_SIZE 
                                    img_top_left_y = BOARD_OFFSET_Y + ref_r * CELL_SIZE 
                                    
                                    ship_img_data_slave = ship_images.get(name) 
                                    width, height = (len(current_ship_coords_tuples) * CELL_SIZE, CELL_SIZE) 
                                    if orient == 'V': width, height = CELL_SIZE, len(current_ship_coords_tuples) * CELL_SIZE
                                    
                                    if ship_img_data_slave: 
                                        actual_img_slave = ship_img_data_slave.get(orient) 
                                        if actual_img_slave: 
                                            width, height = actual_img_slave.get_width(), actual_img_slave.get_height() 
                                    
                                    ship_screen_rect_slave = pygame.Rect(img_top_left_x, img_top_left_y, width, height) 
                                    my_placed_ships_detailed.append({ 
                                        "name": name, "base_image_key": name, 
                                        "size": len(current_ship_coords_tuples), "coords": list(current_ship_coords_tuples), 
                                        "orientation": orient, "is_sunk": False, 
                                        "image_rect_on_board": ship_screen_rect_slave 
                                    })
                                    print(f"DEBUG CLIENT [{player_id_str}]: TEAM_BOARD: Añadido barco '{name}'") 
                                except Exception as e_tb_parse:
                                    print(f"ERROR CLIENT [{player_id_str}]: TEAM_BOARD parse error: {e_tb_parse} en '{barco_def_str}'") 
                                    
                        current_game_state = STATE_WAITING_OPPONENT_SETUP 
                        status_bar_message = "Tablero de equipo recibido. Esperando al oponente..." 
                    continue # Importante para no procesar como otro comando

                elif command == "START_GAME": 
                    starting_player = parts[1] 
                    if starting_player == player_id_str: 
                        current_game_state = STATE_YOUR_TURN 
                        status_bar_message = "¡Tu turno! Dispara en el tablero enemigo." 
                    else: 
                        current_game_state = STATE_OPPONENT_TURN 
                        status_bar_message = f"Turno del oponente ({starting_player}). Esperando..." 
                
                elif command == "SHOT": # Disparo recibido en mi tablero 
                    r, c = int(parts[1]), int(parts[2]) 
                    shot_result_char = 'M'
                    if my_board_data[r][c] == 1: # Es un barco no impactado
                        my_board_data[r][c] = 'H' # Marcar como impacto 
                        shot_result_char = 'H' 
                        if hit_sound: hit_sound.play() 
                        check_and_update_my_sunk_ships() 
                    elif my_board_data[r][c] == 0: # Agua 
                        my_board_data[r][c] = 'M' # Marcar como fallo 
                        if miss_sound: miss_sound.play() 
                    send_message_to_server(f"RESULT {r} {c} {shot_result_char}") 

                elif command == "UPDATE": # Resultado de mi disparo [cite: 747, 1081]
                    if game_mode == 2:
                        r_upd, c_upd = int(parts[1]), int(parts[2]) 
                        result_char_upd = parts[3] 
                        current_cell_state_opp = opponent_board_data[r_upd][c_upd] 
                        if result_char_upd == 'H': 
                            if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'H' 
                            if hit_sound: hit_sound.play() 
                            status_bar_message = f"¡Impacto en ({r_upd},{c_upd})!"
                        elif result_char_upd == 'M': 
                            if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'M' 
                            if miss_sound: miss_sound.play() 
                            status_bar_message = f"Agua en ({r_upd},{c_upd})." 
                        
                        if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER: 
                            send_message_to_server("GAME_WON") 
                    
                    elif game_mode == 4:
                        try:
                            target_player_id_update = parts[1] # A quién se le actualiza el tablero [cite: 1082]
                            r_upd, c_upd = int(parts[2]), int(parts[3])
                            result_char_upd = parts[4] 
                            
                            is_opponent_target = any(opp['id'] == target_player_id_update for opp in opponents_info) 

                            if is_opponent_target: 
                                current_cell_state_opp = opponent_board_data[r_upd][c_upd] 
                                if result_char_upd == 'H': 
                                    if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'H' 
                                    if hit_sound: hit_sound.play() 
                                    status_bar_message = f"¡Impacto en ({r_upd},{c_upd}) del oponente {target_player_id_update}!"
                                elif result_char_upd == 'M': 
                                    if current_cell_state_opp != 'S': opponent_board_data[r_upd][c_upd] = 'M' 
                                    if miss_sound: miss_sound.play() 
                                    status_bar_message = f"Agua en ({r_upd},{c_upd}) del oponente {target_player_id_update}."
                                if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER:
                                    send_message_to_server("GAME_WON") 
                            else: # Es un update para mi equipo (no debería pasar si yo disparé, pero por si acaso)
                                if my_board_data[r_upd][c_upd] == 1 and result_char_upd == 'H': 
                                    my_board_data[r_upd][c_upd] = 'H' 
                                    check_and_update_my_sunk_ships() 
                                elif my_board_data[r_upd][c_upd] == 0 and result_char_upd == 'M': 
                                    my_board_data[r_upd][c_upd] = 'M' 
                        except (IndexError, ValueError) as e_upd4:
                            print(f"Error procesando UPDATE (4P): {message}, {e_upd4}") 
                
                elif command == "OPPONENT_SHIP_SUNK": 
                    try:
                        if game_mode == 2:
                            ship_name_sunk_2p = parts[1] 
                            flat_coords_2p = [int(p) for p in parts[2:]] 
                            sunk_ship_coords_tuples_2p = [] 
                            for i in range(0, len(flat_coords_2p), 2): sunk_ship_coords_tuples_2p.append((flat_coords_2p[i], flat_coords_2p[i+1]))
                            status_bar_message = f"¡Hundiste el {ship_name_sunk_2p} del oponente!" 
                            if sunk_sound: sunk_sound.play() 
                            sunk_ship_size_2p = 0; orient_2p = None 
                            for name_cfg, size_cfg in SHIPS_CONFIG: 
                                if name_cfg == ship_name_sunk_2p: sunk_ship_size_2p = size_cfg; break 
                            if len(sunk_ship_coords_tuples_2p) > 0: 
                                if sunk_ship_size_2p == 1: orient_2p = 'H' 
                                elif len(sunk_ship_coords_tuples_2p) > 1:
                                    r_same = all(c[0] == sunk_ship_coords_tuples_2p[0][0] for c in sunk_ship_coords_tuples_2p) 
                                    c_same = all(c[1] == sunk_ship_coords_tuples_2p[0][1] for c in sunk_ship_coords_tuples_2p) 
                                    if r_same and not c_same: orient_2p = 'H' 
                                    elif not r_same and c_same: orient_2p = 'V' 
                            opponent_sunk_ships_log.append({"name": ship_name_sunk_2p, "size": sunk_ship_size_2p, "coords": sunk_ship_coords_tuples_2p, "orientation": orient_2p}) 
                            for r_s, c_s in sunk_ship_coords_tuples_2p: 
                                if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE: opponent_board_data[r_s][c_s] = 'S' 
                        
                        elif game_mode == 4:
                            id_jugador_afectado_sunk = parts[1] 
                            ship_name_sunk_4p = parts[2] 
                            flat_coords_str_4p = parts[3:] 
                            sunk_ship_coords_tuples_4p = [] 
                            if len(flat_coords_str_4p) % 2 != 0: continue 
                            for i in range(0, len(flat_coords_str_4p), 2): 
                                try: sunk_ship_coords_tuples_4p.append((int(flat_coords_str_4p[i]), int(flat_coords_str_4p[i+1]))) 
                                except ValueError: sunk_ship_coords_tuples_4p.clear(); break 
                            if not sunk_ship_coords_tuples_4p: continue 
                            
                            status_bar_message = f"¡Hundiste el {ship_name_sunk_4p} de {id_jugador_afectado_sunk}!" 
                            if sunk_sound: sunk_sound.play() #
                            sunk_ship_size_4p = 0; orient_4p = None 
                            for name_cfg, size_cfg in SHIPS_CONFIG: 
                                if name_cfg == ship_name_sunk_4p: sunk_ship_size_4p = size_cfg; break 
                            if sunk_ship_size_4p == 0 : print(f"WARN: Tamaño desconocido para {ship_name_sunk_4p}") 

                            if len(sunk_ship_coords_tuples_4p) > 0: 
                                if sunk_ship_size_4p == 1: orient_4p = 'H' 
                                elif len(sunk_ship_coords_tuples_4p) > 1: 
                                    r_same = all(c[0] == sunk_ship_coords_tuples_4p[0][0] for c in sunk_ship_coords_tuples_4p)
                                    c_same = all(c[1] == sunk_ship_coords_tuples_4p[0][1] for c in sunk_ship_coords_tuples_4p) 
                                    if r_same and not c_same: orient_4p = 'H' 
                                    elif not r_same and c_same: orient_4p = 'V' 
                            
                            opponent_sunk_ships_log.append({"name": ship_name_sunk_4p, "size": sunk_ship_size_4p, "coords": sunk_ship_coords_tuples_4p, "orientation": orient_4p}) 
                            for r_s, c_s in sunk_ship_coords_tuples_4p: 
                                if 0 <= r_s < GRID_SIZE and 0 <= c_s < GRID_SIZE: opponent_board_data[r_s][c_s] = 'S'
                        
                        # Chequeo de victoria común después de procesar el hundimiento
                        if check_if_opponent_is_defeated(opponent_board_data) and current_game_state != STATE_GAME_OVER: 
                            send_message_to_server("GAME_WON") 
                    except Exception as e_sunk:
                        print(f"Error procesando OPPONENT_SHIP_SUNK: {e_sunk} - Datos: {message}") 

                elif command == "YOUR_TURN_AGAIN": # Modo 2J 
                    if game_mode == 2:
                        current_game_state = STATE_YOUR_TURN 
                        if not status_bar_message.startswith("¡Impacto") and not status_bar_message.startswith("Agua"): 
                            status_bar_message = "¡Tu turno! Dispara." 
                        else: status_bar_message += " ¡Sigue tu turno!" 
                
                elif command == "OPPONENT_TURN_MSG": # Modo 2J 
                     if game_mode == 2:
                        current_game_state = STATE_OPPONENT_TURN 
                        status_bar_message = "Turno del oponente. Esperando..." 
                
                elif command == "TURN": # Modo 4J 
                    if game_mode == 4:
                        next_turn_player_id = parts[1] 
                        if next_turn_player_id == player_id_str:
                            current_game_state = STATE_YOUR_TURN 
                            status_bar_message = "¡Tu turno! Dispara en el tablero enemigo." 
                        else: 
                            current_game_state = STATE_OPPONENT_TURN 
                            status_bar_message = f"Turno del jugador {next_turn_player_id}. Esperando..." 
            
                elif command == "GAME_OVER": 
                    current_game_state = STATE_GAME_OVER 
                    if parts[1] == "WIN": status_bar_message = "¡HAS GANADO LA PARTIDA! :D" 
                    else: status_bar_message = "Has perdido. Mejor suerte la proxima. :(" 
                    # El hilo de escucha terminará debido al cambio de estado 
                
                elif command == "OPPONENT_LEFT": # Un jugador del equipo oponente se fue (Modo 2J) 
                    if game_mode == 2 and current_game_state != STATE_GAME_OVER: 
                        status_bar_message = "El oponente se ha desconectado. ¡Ganas por defecto!" 
                        current_game_state = STATE_GAME_OVER 
                
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


        except ConnectionResetError: 
            if current_game_state != STATE_GAME_OVER: 
                status_bar_message = "Conexion perdida con el servidor (reset)." 
                current_game_state = STATE_GAME_OVER 
            break 
        except socket.error as e: 
            if current_game_state != STATE_GAME_OVER: 
                status_bar_message = f"Error de socket: {e}" 
                current_game_state = STATE_GAME_OVER 
            break 
        except Exception as e: 
            print(f"Error escuchando al servidor: {e} (Mensaje: '{message}')") 
            if current_game_state != STATE_GAME_OVER: 
                status_bar_message = f"Error de red general: {e}" 
                current_game_state = STATE_GAME_OVER 
            break 
    
    print(f"Hilo de escucha del cliente ({player_id_str or 'N/A'}) terminado.") 

def send_message_to_server(message):
    global status_bar_message, current_game_state
    if client_socket and client_socket.fileno() != -1: 
        try:
            client_socket.sendall(f"{message}\n".encode()) 
        except socket.error as e: 
            print(f"Error enviando mensaje: {e}") 
            if current_game_state != STATE_GAME_OVER: 
                status_bar_message = "Error de red al enviar." 
                current_game_state = STATE_GAME_OVER 
        except Exception as e: 
            print(f"Excepción general al enviar mensaje: {e}") 
            if current_game_state != STATE_GAME_OVER: 
                status_bar_message = "Error desconocido al enviar." 
                current_game_state = STATE_GAME_OVER 


def create_darkened_image(original_image_surface, darkness_alpha=128): 
    if original_image_surface is None: return None
    darkened_surface = original_image_surface.copy()
    overlay = pygame.Surface(darkened_surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, darkness_alpha))
    darkened_surface.blit(overlay, (0, 0))
    return darkened_surface

def check_and_update_my_sunk_ships(): 
    global my_placed_ships_detailed, my_board_data, status_bar_message, sunk_sound
    for ship_info in my_placed_ships_detailed: 
        if not ship_info["is_sunk"]: 
            hits_on_ship = 0
            for r_coord, c_coord in ship_info["coords"]: 
                if my_board_data[r_coord][c_coord] == 'H': hits_on_ship += 1 
            if hits_on_ship == ship_info["size"]: 
                ship_info["is_sunk"] = True 
                sunk_ship_name = ship_info["name"] 
                print(f"INFO: ¡Mi {sunk_ship_name} ha sido hundido!") 
                coords_list_for_server = [] 
                for r_s, c_s in ship_info["coords"]: 
                    coords_list_for_server.extend([str(r_s), str(c_s)]) 
                coords_payload_str = " ".join(coords_list_for_server) 
                send_message_to_server(f"I_SUNK_MY_SHIP {sunk_ship_name} {coords_payload_str}") 
                if sunk_sound: sunk_sound.play() 


def draw_game_grid(surface, offset_x, offset_y, board_matrix, is_my_board): 
    for r_idx in range(GRID_SIZE): 
        for c_idx in range(GRID_SIZE): 
            cell_rect = pygame.Rect(offset_x + c_idx * CELL_SIZE, offset_y + r_idx * CELL_SIZE, CELL_SIZE, CELL_SIZE) 
            pygame.draw.rect(surface, BLUE_WATER, cell_rect) 
            pygame.draw.rect(surface, BOARD_GRID_COLOR, cell_rect, 1) 

    # Dibujar imágenes de barcos
    if is_my_board: 
        for ship_detail in my_placed_ships_detailed: 
            ship_name = ship_detail["base_image_key"] 
            orientation = ship_detail["orientation"] 
            ship_img_dict = ship_images.get(ship_name) 
            if ship_img_dict: 
                current_ship_image = ship_img_dict.get(orientation) 
                if current_ship_image: 
                    image_to_draw = create_darkened_image(current_ship_image) if ship_detail["is_sunk"] else current_ship_image 
                    if image_to_draw and ship_detail.get("image_rect_on_board"): 
                        surface.blit(image_to_draw, ship_detail["image_rect_on_board"].topleft) 
    else: # Tablero oponente
        for sunk_info in opponent_sunk_ships_log: 
            ship_name_opp = sunk_info["name"] 
            orientation_opp = sunk_info.get("orientation") 
            coords_opp = sunk_info["coords"] 
            if not coords_opp or orientation_opp is None: continue 
            ship_img_data_opp = ship_images.get(ship_name_opp) 
            if ship_img_data_opp: 
                base_image_opp = ship_img_data_opp.get(orientation_opp) 
                if base_image_opp: 
                    darkened_opp_ship_img = create_darkened_image(base_image_opp, darkness_alpha=150) 
                    if darkened_opp_ship_img: 
                        min_r = min(r for r,c in coords_opp) 
                        min_c = min(c for r,c in coords_opp) 
                        screen_x = offset_x + min_c * CELL_SIZE 
                        screen_y = offset_y + min_r * CELL_SIZE 
                        surface.blit(darkened_opp_ship_img, (screen_x, screen_y)) 
    
    # Dibujar marcadores de celda (H, M, S)
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
                # Fondo verde para 'S' (originalmente para depuración)
                debug_fill_s = pygame.Surface((CELL_SIZE, CELL_SIZE), pygame.SRCALPHA) 
                debug_fill_s.fill((0, 80, 0, 100)) # Verde oscuro semi-transparent
                surface.blit(debug_fill_s, cell_rect.topleft) 
                line_thickness_sunk, padding_sunk = 5, 5 
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.top + padding_sunk), (cell_rect.right - padding_sunk, cell_rect.bottom - padding_sunk), line_thickness_sunk) 
                pygame.draw.line(surface, (255, 50, 50), (cell_rect.left + padding_sunk, cell_rect.bottom - padding_sunk), (cell_rect.right - padding_sunk, cell_rect.top + padding_sunk), line_thickness_sunk) 


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
        if board[current_r][current_c] == 1: return False, [] # Casilla ya ocupado
        ship_coords.append((current_r, current_c)) 
    return True, ship_coords 

def attempt_to_place_ship(board, r, c, ship_config_tuple): 
    global current_ship_placement_index, my_placed_ships_detailed, current_game_state, status_bar_message
    global game_mode, player_id_str # Necesario para TEAM_BOARD_DATA
    
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
        width, height = (ship_size * CELL_SIZE, CELL_SIZE) # Default H 
        if current_ship_orientation == 'V': width, height = CELL_SIZE, ship_size * CELL_SIZE

        if ship_img_data: 
            actual_image = ship_img_data.get(current_ship_orientation) 
            if actual_image: width, height = actual_image.get_width(), actual_image.get_height() 
        ship_screen_rect = pygame.Rect(img_top_left_x, img_top_left_y, width, height) 

        my_placed_ships_detailed.append({ 
            "name": ship_name, "base_image_key": ship_name, "size": ship_size, 
            "coords": actual_ship_coords, "orientation": current_ship_orientation, 
            "is_sunk": False, "image_rect_on_board": ship_screen_rect 
        })
        
        current_ship_placement_index += 1 
        if current_ship_placement_index >= len(ships_to_place_list): 
            # Si es modo 4J y es capitán (P1/P3), enviar datos del tablero
            if game_mode == 4 and is_captain: # (player_id_str == "P1" or player_id_str == "P3") 
                barcos_serializados = [] 
                for barco in my_placed_ships_detailed: 
                    coords_flat = " ".join(f"{r_coord} {c_coord}" for r_coord, c_coord in barco["coords"]) 
                    barcos_serializados.append(f"{coords_flat}|{barco['name']}|{barco['orientation']}") 
                payload = ";".join(barcos_serializados) 
                send_message_to_server(f"TEAM_BOARD_DATA {payload}") 
                print(f"DEBUG CLIENT [{player_id_str}]: Enviado TEAM_BOARD_DATA.")

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

        if row is not None and col is not None: 
            ship_img_data = ship_images.get(ship_name) 
            if ship_img_data: 
                preview_img_original = ship_img_data.get(current_ship_orientation) 
                if preview_img_original: 
                    preview_img = preview_img_original.copy() 
                    preview_img.set_alpha(180) 
                    screen_x = BOARD_OFFSET_X_MY + col * CELL_SIZE 
                    screen_y = BOARD_OFFSET_Y + row * CELL_SIZE 
                    surface.blit(preview_img, (screen_x, screen_y)) 
                    
                    can_place_flag, _ = can_place_ship_at(my_board_data, row, col, ship_size, current_ship_orientation) 
                    border_color = GREEN_PREVIEW_BORDER if can_place_flag else RED_PREVIEW_BORDER 
                    img_rect_for_border = pygame.Rect(screen_x, screen_y, preview_img.get_width(), preview_img.get_height()) 
                    pygame.draw.rect(surface, border_color, img_rect_for_border, 2) 

def check_if_opponent_is_defeated(opponent_b): 
    hit_and_sunk_cells = 0 
    for r in range(GRID_SIZE): 
        for c in range(GRID_SIZE): 
            if opponent_b[r][c] == 'H' or opponent_b[r][c] == 'S': hit_and_sunk_cells += 1 
    if hit_and_sunk_cells >= TOTAL_SHIP_CELLS: 
        print(f"DEBUG CLIENT: ¡Victoria local detectada! Celdas H/S oponente: {hit_and_sunk_cells}/{TOTAL_SHIP_CELLS}") 
        return True 
    return False 


def game_main_loop(mode, server_ip_to_join=None, game_id_to_join=None, action="CREATE"): # action y game_id_to_join
    global screen, font_large, font_medium, font_small, current_game_state, status_bar_message
    global current_ship_orientation, hit_sound, miss_sound, sunk_sound, client_socket
    global game_mode, player_name_local, server_ip_global
    global g_my_team_name, g_opponent_team_name, is_captain, is_team_board_slave, player_id_str
    global g_current_game_id_on_client # Nueva global

    game_mode = mode
    server_ip_global = server_ip_to_join if server_ip_to_join else DEFAULT_SERVER_IP
    # game_id_to_join no se usa activamente en este cliente para conectar, pero podría ser útil

    if len(sys.argv) > 1: server_ip_global = sys.argv[1] # Override por argumento CLI [c
    print(f"Usando IP del servidor: {server_ip_global}, Modo de juego: {game_mode}") 

    pygame.init() 
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT)) 
    pygame.display.set_caption(f"Batalla Naval Cliente - Modo {game_mode}J") 
    font_large = pygame.font.Font(None, 48) 
    font_medium = pygame.font.Font(None, 36) 
    font_small = pygame.font.Font(None, 28) 

    if game_mode == 2 and action == "CREATE": # Solo pedir nombre si crea una partida 2J
        player_name_local = prompt_for_player_name_gui()
        if not player_name_local:
            # ... (salir si no hay nombre)
            return # Añadido para asegurar que no continúe
    elif game_mode == 2 and action == "JOIN": # Si se une a 2J, también pedir nombre
        player_name_local = prompt_for_player_name_gui() # O decidir si el nombre es necesario al unirse
        if not player_name_local: player_name_local = f"JugadorInvitado" # Fallback

    # Cargar sonidos
    pygame.mixer.init() 
    try:
        hit_sound_file = os.path.join(assets_path, "acertado.wav") 
        miss_sound_file = os.path.join(assets_path, "fallido.wav") 
        sunk_sound_file = os.path.join(assets_path, "hundido.wav") 
        if os.path.exists(hit_sound_file): hit_sound = pygame.mixer.Sound(hit_sound_file) 
        if os.path.exists(miss_sound_file): miss_sound = pygame.mixer.Sound(miss_sound_file) 
        if os.path.exists(sunk_sound_file): sunk_sound = pygame.mixer.Sound(sunk_sound_file) 
    except Exception as e: print(f"Error cargando sonidos: {e}") 

    # Cargar imágenes de barcos
    print("Cargando imágenes de barcos...") 
    for ship_name_key, ship_size_val in SHIPS_CONFIG: 
        ship_filename = SHIP_IMAGE_FILES.get(ship_name_key) 
        if not ship_filename: print(f"No se definio imagen para: {ship_name_key}"); continue 
        try:
            image_path = os.path.join(assets_path, ship_filename) 
            if os.path.exists(image_path): 
                img_h_original = pygame.image.load(image_path).convert_alpha() 
                scaled_h_width, scaled_h_height = ship_size_val * CELL_SIZE, CELL_SIZE 
                img_h = pygame.transform.scale(img_h_original, (scaled_h_width, scaled_h_height)) 
                img_v_temp = pygame.transform.rotate(img_h_original, 90) 
                scaled_v_width, scaled_v_height = CELL_SIZE, ship_size_val * CELL_SIZE 
                img_v = pygame.transform.scale(img_v_temp, (scaled_v_width, scaled_v_height)) 
                ship_images[ship_name_key] = {"H": img_h, "V": img_v} 
            else: print(f"Archivo no encontrado: {image_path}"); ship_images[ship_name_key] = None 
        except Exception as e_img: print(f"Error cargando imagen {ship_name_key}: {e_img}"); ship_images[ship_name_key] = None 

    # Pasar la acción y el game_id (si es JOIN) al hilo de conexión
    threading.Thread(target=connect_to_server_thread, args=(action, game_id_to_join), daemon=True).start()

    is_game_running = True 
    game_clock = pygame.time.Clock() 

    while is_game_running: 
        mouse_current_pos = pygame.mouse.get_pos() #

        if current_game_state == STATE_AWAITING_TEAM_NAME_INPUT:
             # Este estado especial se maneja aquí para el input GUI
            if game_mode == 4 and is_captain:
                print(f"DEBUG CLIENT [{player_id_str}]: Estado AWAITING_TEAM_NAME_INPUT detectado. Mostrando prompt.") 
                team_name_entered = prompt_for_team_name_gui() 
                if team_name_entered: 
                    send_message_to_server(f"TEAM_NAME_IS {team_name_entered}") 
                    status_bar_message = f"Nombre de equipo '{team_name_entered}' enviado. Esperando..." 
                    current_game_state = STATE_WAITING_FOR_TEAM_INFO # Esperar TEAMS_INFO_FINA
                else: 
                    status_bar_message = "Ingreso de nombre cancelado. Esperando acción del servidor..." 
                    current_game_state = STATE_WAITING_FOR_TEAM_INFO # O un estado de error/reintentando
            else: # No debería estar en este estado si no es capitán en modo 4J
                current_game_state = STATE_WAITING_FOR_PLAYER # Volver a un estado de espera general

        for event in pygame.event.get(): 
            if event.type == pygame.QUIT: is_game_running = False 
            
            if current_game_state != STATE_AWAITING_TEAM_NAME_INPUT and current_game_state != STATE_GAME_OVER : 
                if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: 
                    # Lógica de clic para SETUP y YOUR_TURN
                    can_place_now = (current_game_state == STATE_SETUP_SHIPS and \
                                     current_ship_placement_index < len(ships_to_place_list) and \
                                     not is_team_board_slave) # P2/P4 no colocan [
                    
                    if can_place_now: 
                        r_place, c_place = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y) 
                        if r_place is not None and c_place is not None: 
                            attempt_to_place_ship(my_board_data, r_place, c_place, ships_to_place_list[current_ship_placement_index]) 
                    
                    elif current_game_state == STATE_YOUR_TURN: 
                        r_shot, c_shot = get_grid_cell_from_mouse(mouse_current_pos, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y) 
                        if r_shot is not None and c_shot is not None: 
                            # Verificar si la celda ya fue disparada
                            if opponent_board_data[r_shot][c_shot] == 0: # Solo disparar a celdas no tocada
                                if game_mode == 2: 
                                    send_message_to_server(f"SHOT {r_shot} {c_shot}")
                                elif game_mode == 4:
                                    if opponents_info and opponents_info[0].get('id'): 
                                        # Disparar al primer oponente del equipo contrario por defecto
                                        target_id_4p = opponents_info[0]['id'] 
                                        send_message_to_server(f"SHOT {target_id_4p} {r_shot} {c_shot}") 
                                        print(f"INFO CLIENT [{player_id_str}]: SHOT enviado a {target_id_4p} en ({r_shot},{c_shot})") 
                                    else: status_bar_message = "Error: No hay información de oponentes para disparar."; print("WARN CLIENT: No opponents_info para SHOT")
                                status_bar_message = "Disparo enviado. Esperando resultado..." 
                            else: status_bar_message = "Ya disparaste en esa celda."
                
                if event.type == pygame.KEYDOWN:
                    if current_game_state == STATE_SETUP_SHIPS and not is_team_board_slave : 
                        if event.key == pygame.K_r:
                            current_ship_orientation = 'V' if current_ship_orientation == 'H' else 'H' 
                            next_ship_name_display = ""
                            if current_ship_placement_index < len(ships_to_place_list): 
                                next_ship_name_display = ships_to_place_list[current_ship_placement_index][0] #
                            orientation_text = "Horizontal" if current_ship_orientation == 'H' else "Vertical" 
                            status_bar_message = f"Coloca: {next_ship_name_display}. Orient: {orientation_text}. 'R' para rotar." 
        
        # --- Dibujado ---
        screen.fill(BLACK) 
        
        # Título de ventana dinámico
        window_title_dyn = f"Batalla Naval - {player_id_str or 'Conectando...'}" 
        if game_mode == 2 and g_opponent_team_name: window_title_dyn += f" vs {g_opponent_team_name}"
        elif game_mode == 4 and g_my_team_name: window_title_dyn = f"{g_my_team_name} ({player_id_str}) - Batalla Naval" 
        pygame.display.set_caption(window_title_dyn) 

        # Info de jugadores/equipos
        my_display_name = player_id_str or "Asignando..." 
        if game_mode == 2 and player_name_local: my_display_name = player_name_local
        elif game_mode == 4 and g_my_team_name: my_display_name = f"Equipo: {g_my_team_name} ({player_id_str})" 
        
        opponent_display_name = "Esperando..." 
        if game_mode == 2 and g_opponent_team_name: opponent_display_name = f"Oponente: {g_opponent_team_name}"
        elif game_mode == 4 and g_opponent_team_name: opponent_display_name = f"Equipo Oponente: {g_opponent_team_name}" 
        
        draw_text_on_screen(screen, my_display_name, (BOARD_OFFSET_X_MY, 10), font_small) 
        draw_text_on_screen(screen, opponent_display_name, (BOARD_OFFSET_X_OPPONENT - 20, 10), font_small)

        draw_text_on_screen(screen, "TU FLOTA", (BOARD_OFFSET_X_MY, BOARD_OFFSET_Y - 40), font_medium) 
        draw_text_on_screen(screen, "FLOTA ENEMIGA", (BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y - 40), font_medium) 
        
        draw_game_grid(screen, BOARD_OFFSET_X_MY, BOARD_OFFSET_Y, my_board_data, True) 
        draw_game_grid(screen, BOARD_OFFSET_X_OPPONENT, BOARD_OFFSET_Y, opponent_board_data, False) 

        if current_game_state == STATE_SETUP_SHIPS and not is_team_board_slave: 
            draw_ship_placement_preview(screen, mouse_current_pos)
            if current_ship_placement_index < len(ships_to_place_list): 
                 ship_name_disp, ship_size_disp = ships_to_place_list[current_ship_placement_index]
                 orient_text_disp = 'H' if current_ship_orientation == 'H' else 'V'
                 info_text_disp = f"Colocando: {ship_name_disp} ({ship_size_disp}) Orient: {orient_text_disp}" 
                 draw_text_on_screen(screen, info_text_disp, (10, SCREEN_HEIGHT - 70), font_small)

        pygame.draw.rect(screen, (30,30,30), (0, SCREEN_HEIGHT - 40, SCREEN_WIDTH, 40)) 
        draw_text_on_screen(screen, status_bar_message, (10, SCREEN_HEIGHT - 30), font_small, STATUS_TEXT_COLOR) 
        
        pygame.display.flip() 
        game_clock.tick(30) 

    print("Saliendo del bucle principal de Pygame.") 
    if client_socket: 
        print("Cerrando socket del cliente...") 
        try:
            client_socket.close() 
        except Exception as e_close:
            print(f"Error al cerrar el socket del cliente: {e_close}") 
    pygame.quit() 
    sys.exit() 


if __name__ == "__main__": 
    # game_main_loop() # Ya no se llama directamente así. Se llama desde menu.py con el modo.
    print("Este archivo es el cliente de Batalla Naval. Ejecuta 'menu.py' para iniciar.")