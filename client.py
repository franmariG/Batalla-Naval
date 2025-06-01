# client.py

import pygame
import socket
import sys
import time
import json # For sending complex data like board arrays

# --- Constants ---
DEFAULT_SERVER_IP = "127.0.0.1"
DEFAULT_SERVER_PORT = 6789

SCREEN_WIDTH_2P = 900 # Original width for 2 players
SCREEN_HEIGHT_2P = 500
SCREEN_WIDTH_4P = 1000 # Adjusted for 4 players (2x2 grid of boards)
SCREEN_HEIGHT_4P = 750

GRID_SIZE = 10
CELL_SIZE_2P = 30
CELL_SIZE_4P = 25 # Slightly smaller cells for 4-player layout
BOARD_MARGIN = 30
BOARD_SPACING_4P = 20

# Derived board display size
GRID_DISPLAY_SIZE_2P = GRID_SIZE * CELL_SIZE_2P
GRID_DISPLAY_SIZE_4P = GRID_SIZE * CELL_SIZE_4P


# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (200, 200, 200)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
RED = (255, 0, 0)
SHIP_COLOR = (100, 100, 100) # Color for player's own ships
HIT_COLOR = RED
MISS_COLOR = BLUE
SUNK_COLOR = (165, 42, 42) # Brown
WATER_COLOR = (0, 105, 148) # Sea Blue
GRID_LINE_COLOR = BLACK
TEXT_COLOR = BLACK
STATUS_TEXT_COLOR = WHITE
OPPONENT_BOARD_BG = (150, 150, 180) # Light slate blue for opponent boards

# Game States (Client-side)
STATE_CONNECTING = "CONNECTING"
STATE_WAITING_FOR_PLAYERS = "WAITING_FOR_PLAYERS"
STATE_SETUP_SHIPS = "SETUP_SHIPS"
STATE_MY_TURN = "MY_TURN"
STATE_OPPONENT_TURN = "OPPONENT_TURN"
STATE_SELECT_TARGET_PLAYER = "SELECT_TARGET_PLAYER" # For 4-player mode
STATE_GAME_OVER = "GAME_OVER"

# Ship definitions (name, size)
SHIPS_TO_PLACE_LIST = [
    ("Carrier", 5),
    ("Battleship", 4),
    ("Cruiser", 3),
    ("Submarine", 3),
    ("Destroyer", 2)
]

# Global variables (managed within game_main_loop scope or passed around)
client_socket = None
my_player_id = -1
opponent_ids_map = {} # Maps display index to actual player_id for opponents
player_boards = {} # {player_id: board_data_array}
player_ship_counts = {} # {player_id: number of ships floating}

current_game_state = STATE_CONNECTING
status_bar_message = "Connecting to server..."
current_ship_placement_index = 0
current_ship_orientation = 'H'  # 'H' or 'V'
game_winner_id = None
active_player_turn_id = None # Whose turn it is currently

# Board cell states (client interpretation)
CELL_EMPTY = 0
CELL_SHIP = 1
CELL_MISS = 2
CELL_HIT = 3
CELL_SUNK_SHIP = 4 # Part of a sunk ship

# --- Network Functions ---
def connect_to_server(server_ip, server_port):
    global client_socket
    try:
        client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client_socket.connect((server_ip, server_port))
        client_socket.setblocking(False) # Non-blocking for Pygame loop
        return client_socket
    except socket.error as e:
        print(f"Error connecting to server {server_ip}:{server_port} - {e}")
        return None

def send_message(message_dict):
    global client_socket
    if client_socket:
        try:
            # print(f"CLIENT SEND: {message_dict}") # Debug
            message_json = json.dumps(message_dict)
            client_socket.sendall(message_json.encode('utf-8') + b'\n') # Add newline as delimiter
        except socket.error as e:
            print(f"Socket error while sending: {e}")
            # Handle disconnection or error appropriately
            # current_game_state = STATE_GAME_OVER # Or some error state
            # status_bar_message = "Connection lost."


# --- Helper Functions ---
def initialize_board():
    return [[CELL_EMPTY for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]

def get_board_rects(num_players_expected, screen_width, screen_height):
    """Calculates positions for player and opponent boards."""
    board_rects = {} # {player_id or 'my_board' or 'opponent_X': pygame.Rect}
    cell_size = CELL_SIZE_4P if num_players_expected == 4 else CELL_SIZE_2P
    grid_display_size = GRID_SIZE * cell_size

    if num_players_expected == 2:
        my_board_x = BOARD_MARGIN
        my_board_y = (screen_height - grid_display_size) // 2
        board_rects['my_board'] = pygame.Rect(my_board_x, my_board_y, grid_display_size, grid_display_size)

        opponent_board_x = my_board_x + grid_display_size + BOARD_MARGIN * 2 # More spacing
        opponent_board_y = my_board_y
        board_rects['opponent_0'] = pygame.Rect(opponent_board_x, opponent_board_y, grid_display_size, grid_display_size)
    
    elif num_players_expected == 4:
        # 2x2 Grid layout
        # Top-left: Opponent 0
        # Top-right: Opponent 1
        # Bottom-left: My Board
        # Bottom-right: Opponent 2

        positions = [
            (BOARD_MARGIN, BOARD_MARGIN),  # Opponent 0 (placeholder for player with lowest ID other than self)
            (BOARD_MARGIN + grid_display_size + BOARD_SPACING_4P, BOARD_MARGIN), # Opponent 1
            (BOARD_MARGIN, BOARD_MARGIN + grid_display_size + BOARD_SPACING_4P), # My Board
            (BOARD_MARGIN + grid_display_size + BOARD_SPACING_4P, BOARD_MARGIN + grid_display_size + BOARD_SPACING_4P) # Opponent 2
        ]
        
        board_rects['opponent_0'] = pygame.Rect(positions[0][0], positions[0][1], grid_display_size, grid_display_size)
        board_rects['opponent_1'] = pygame.Rect(positions[1][0], positions[1][1], grid_display_size, grid_display_size)
        board_rects['my_board'] = pygame.Rect(positions[2][0], positions[2][1], grid_display_size, grid_display_size)
        board_rects['opponent_2'] = pygame.Rect(positions[3][0], positions[3][1], grid_display_size, grid_display_size)
        
    return board_rects


def draw_game_grid(surface, board_rect, board_data, show_ships, cell_size, is_targetable=False, is_selected_target=False):
    grid_display_size = GRID_SIZE * cell_size
    pygame.draw.rect(surface, OPPONENT_BOARD_BG if not show_ships else WATER_COLOR, board_rect) # Background

    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            cell_rect = pygame.Rect(board_rect.left + c * cell_size, board_rect.top + r * cell_size, cell_size, cell_size)
            cell_value = board_data[r][c]
            cell_color = WATER_COLOR

            if cell_value == CELL_SHIP and show_ships:
                cell_color = SHIP_COLOR
            elif cell_value == CELL_MISS:
                cell_color = MISS_COLOR
            elif cell_value == CELL_HIT:
                cell_color = HIT_COLOR
            elif cell_value == CELL_SUNK_SHIP:
                cell_color = SUNK_COLOR
            
            pygame.draw.rect(surface, cell_color, cell_rect)
            pygame.draw.rect(surface, GRID_LINE_COLOR, cell_rect, 1) # Cell border

    # Highlight if it's a targetable board and currently selected
    if is_targetable and is_selected_target:
         pygame.draw.rect(surface, GREEN, board_rect, 3) # Green highlight for selected target board
    elif is_targetable: # Just to show it can be clicked
         pygame.draw.rect(surface, GRAY, board_rect, 2)


def draw_ship_placement_preview(surface, mouse_pos, board_rect, cell_size):
    global current_ship_placement_index, current_ship_orientation, SHIPS_TO_PLACE_LIST
    if current_ship_placement_index >= len(SHIPS_TO_PLACE_LIST):
        return

    ship_name, ship_size = SHIPS_TO_PLACE_LIST[current_ship_placement_index]
    
    if not board_rect.collidepoint(mouse_pos):
        return

    col = (mouse_pos[0] - board_rect.left) // cell_size
    row = (mouse_pos[1] - board_rect.top) // cell_size

    if not (0 <= col < GRID_SIZE and 0 <= row < GRID_SIZE):
        return

    preview_color = (0, 200, 0, 150)  # Semi-transparent green
    temp_surface = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
    
    valid_placement = True
    preview_rects = []

    for i in range(ship_size):
        r, c = row, col
        if current_ship_orientation == 'H':
            c += i
        else: # 'V'
            r += i
        
        if not (0 <= c < GRID_SIZE and 0 <= r < GRID_SIZE):
            valid_placement = False
            break
        # Add collision check with already placed ships if needed here by checking player_boards[my_player_id]
        # For simplicity, server will do final validation. Client preview is indicative.
        
        preview_rects.append(pygame.Rect(board_rect.left + c * cell_size, board_rect.top + r * cell_size, cell_size, cell_size))

    preview_color = (0, 200, 0, 150) if valid_placement else (200, 0, 0, 150) # Green or Red
    for pr in preview_rects:
        temp_surface.fill(preview_color)
        surface.blit(temp_surface, pr.topleft)


def draw_text_on_screen(surface, text, position, font, color=TEXT_COLOR):
    text_surface = font.render(text, True, color)
    surface.blit(text_surface, position)


def get_grid_coords_from_mouse(mouse_pos, board_rect, cell_size):
    if not board_rect.collidepoint(mouse_pos):
        return None, None

    col = (mouse_pos[0] - board_rect.left) // cell_size
    row = (mouse_pos[1] - board_rect.top) // cell_size

    if 0 <= col < GRID_SIZE and 0 <= row < GRID_SIZE:
        return row, col
    return None, None


# --- Main Game Loop ---
def game_main_loop(num_players_expected, server_ip=DEFAULT_SERVER_IP, server_port=DEFAULT_SERVER_PORT):
    global client_socket, my_player_id, opponent_ids_map, player_boards, player_ship_counts
    global current_game_state, status_bar_message, current_ship_placement_index, current_ship_orientation
    global game_winner_id, active_player_turn_id

    # Reset globals for a new game
    client_socket = None
    my_player_id = -1
    opponent_ids_map = {} 
    player_boards = {}
    player_ship_counts = {}
    current_game_state = STATE_CONNECTING
    status_bar_message = f"Connecting to {server_ip}..."
    current_ship_placement_index = 0
    current_ship_orientation = 'H'
    game_winner_id = None
    active_player_turn_id = None
    selected_target_opponent_idx = -1 # For 4-player mode, index into opponent_ids_map visual layout

    pygame.init()

    screen_width = SCREEN_WIDTH_4P if num_players_expected == 4 else SCREEN_WIDTH_2P
    screen_height = SCREEN_HEIGHT_4P if num_players_expected == 4 else SCREEN_HEIGHT_2P
    cell_size = CELL_SIZE_4P if num_players_expected == 4 else CELL_SIZE_2P

    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption(f"BattleShip - {num_players_expected} Player Game")
    font_small = pygame.font.Font(None, 24)
    font_medium = pygame.font.Font(None, 36)
    font_large = pygame.font.Font(None, 48)
    game_clock = pygame.time.Clock()

    client_socket = connect_to_server(server_ip, server_port)
    if not client_socket:
        status_bar_message = "Connection Failed. Please check server IP and if server is running."
        # Show this message for a few seconds then return to menu
        start_time = time.time()
        while time.time() - start_time < 3: # Display error for 3 seconds
            screen.fill(BLACK)
            draw_text_on_screen(screen, status_bar_message, (50, screen_height // 2 - 20), font_medium, RED)
            pygame.display.flip()
            for event in pygame.event.get(): # Allow quitting during error
                 if event.type == pygame.QUIT: pygame.quit(); sys.exit()
        return False # Indicate failure to menu

    send_message({"type": "JOIN_GAME", "mode": num_players_expected})
    current_game_state = STATE_WAITING_FOR_PLAYERS
    status_bar_message = "Waiting for other players..."

    board_display_rects = {} # Will be populated once game starts

    # Buffer for incoming socket data
    socket_buffer = ""

    running = True
    while running:
        mouse_current_pos = pygame.mouse.get_pos()
        
        # --- Event Handling ---
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if current_game_state == STATE_SETUP_SHIPS:
                    if event.key == pygame.K_r: # Rotate ship
                        current_ship_orientation = 'V' if current_ship_orientation == 'H' else 'H'
            
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click
                    if current_game_state == STATE_SETUP_SHIPS and 'my_board' in board_display_rects:
                        my_board_rect = board_display_rects['my_board']
                        row, col = get_grid_coords_from_mouse(mouse_current_pos, my_board_rect, cell_size)
                        if row is not None and col is not None:
                            if current_ship_placement_index < len(SHIPS_TO_PLACE_LIST):
                                ship_name, ship_size = SHIPS_TO_PLACE_LIST[current_ship_placement_index]
                                send_message({
                                    "type": "PLACE_SHIP",
                                    "ship_name": ship_name,
                                    "size": ship_size,
                                    "row": row,
                                    "col": col,
                                    "orientation": current_ship_orientation
                                })
                                # Ship placement success/failure will be confirmed by server message
                    
                    elif current_game_state == STATE_MY_TURN:
                        target_player_id_to_attack = None
                        attack_coords = None

                        if num_players_expected == 2:
                            # In 2P, there's only one opponent, key is 'opponent_0' in board_display_rects
                            # and opponent_ids_map[0] will give the actual player_id
                            if 'opponent_0' in board_display_rects and opponent_ids_map.get(0) is not None:
                                opponent_board_rect = board_display_rects['opponent_0']
                                row, col = get_grid_coords_from_mouse(mouse_current_pos, opponent_board_rect, cell_size)
                                if row is not None:
                                    target_player_id_to_attack = opponent_ids_map[0]
                                    attack_coords = (row, col)
                        else: # 4-Player: must have selected a target board first
                            if selected_target_opponent_idx != -1:
                                opponent_key = f'opponent_{selected_target_opponent_idx}'
                                if opponent_key in board_display_rects and opponent_ids_map.get(selected_target_opponent_idx) is not None:
                                    opponent_board_rect = board_display_rects[opponent_key]
                                    row, col = get_grid_coords_from_mouse(mouse_current_pos, opponent_board_rect, cell_size)
                                    if row is not None:
                                        target_player_id_to_attack = opponent_ids_map[selected_target_opponent_idx]
                                        attack_coords = (row, col)
                            else: # If no board explicitly selected, check if click was on any opponent board
                                for i in range(num_players_expected -1):
                                    opp_key = f'opponent_{i}'
                                    if opp_key in board_display_rects and opponent_ids_map.get(i) is not None:
                                        if board_display_rects[opp_key].collidepoint(mouse_current_pos):
                                            selected_target_opponent_idx = i # Select this board
                                            status_bar_message = f"Selected Opponent {opponent_ids_map[i]}. Click on their grid to fire."
                                            break # Don't fire on this click, just select

                        if target_player_id_to_attack is not None and attack_coords is not None:
                             send_message({
                                "type": "ATTACK",
                                "target_player_id": target_player_id_to_attack,
                                "row": attack_coords[0],
                                "col": attack_coords[1]
                            })
                             selected_target_opponent_idx = -1 # Reset selection after firing

        # --- Network Message Processing ---
        if client_socket:
            try:
                data = client_socket.recv(4096).decode('utf-8')
                socket_buffer += data
                
                while '\n' in socket_buffer:
                    message_json, socket_buffer = socket_buffer.split('\n', 1)
                    if message_json:
                        msg = json.loads(message_json)
                        # print(f"CLIENT RECV: {msg}") # Debug

                        if msg["type"] == "ERROR":
                            status_bar_message = f"Server Error: {msg['message']}"
                            if msg.get("fatal"): # e.g. room full, version mismatch
                                running = False # Or specific error handling
                                # Potentially show error then return after delay (like connection fail)

                        elif msg["type"] == "WAIT_UPDATE":
                            status_bar_message = f"Waiting: {msg['current_players']}/{msg['expected_players']} players. You are Player {msg['your_id']}"
                            my_player_id = msg['your_id']
                            if my_player_id not in player_boards: # Initialize own board structure
                                player_boards[my_player_id] = initialize_board()


                        elif msg["type"] == "GAME_START":
                            my_player_id = msg['your_id']
                            all_player_ids = msg['all_player_ids']
                            player_turn_order = msg['player_turn_order'] # Not directly used by client for now, but server sends it

                            # Initialize boards for all players
                            for pid in all_player_ids:
                                player_boards[pid] = initialize_board()
                                player_ship_counts[pid] = len(SHIPS_TO_PLACE_LIST) # Initial ship count

                            # Setup opponent_ids_map based on visual layout
                            # For 2P: one opponent at index 0
                            # For 4P: three opponents at indices 0, 1, 2
                            # The actual player_ids are sorted and assigned.
                            
                            temp_opponent_ids = sorted([pid for pid in all_player_ids if pid != my_player_id])
                            opponent_ids_map.clear()
                            for i, opp_id in enumerate(temp_opponent_ids):
                                opponent_ids_map[i] = opp_id # visual_idx -> actual_player_id
                            
                            board_display_rects = get_board_rects(num_players_expected, screen_width, screen_height)
                            current_game_state = STATE_SETUP_SHIPS
                            status_bar_message = "Place your ships! (R to rotate)"
                            current_ship_placement_index = 0 # Reset for placement

                        elif msg["type"] == "SHIP_PLACEMENT_SUCCESS":
                            # Server confirms ship placed, update local board
                            pid = msg['player_id']
                            if pid == my_player_id: # Only care about my successful placements for preview
                                for r, c in msg['ship_coords']:
                                    player_boards[my_player_id][r][c] = CELL_SHIP
                                current_ship_placement_index += 1
                                if current_ship_placement_index >= len(SHIPS_TO_PLACE_LIST):
                                    status_bar_message = "All ships placed. Waiting for other players..."
                                    send_message({"type": "FINISH_SETUP"})
                                else:
                                    ship_name, ship_size = SHIPS_TO_PLACE_LIST[current_ship_placement_index]
                                    status_bar_message = f"Place {ship_name} ({ship_size}). R to rotate."
                        
                        elif msg["type"] == "SHIP_PLACEMENT_INVALID":
                             if msg['player_id'] == my_player_id:
                                status_bar_message = f"Invalid placement: {msg['reason']}. Try again."

                        elif msg["type"] == "UPDATE_TURN":
                            active_player_turn_id = msg['player_id_turn']
                            if active_player_turn_id == my_player_id:
                                current_game_state = STATE_MY_TURN
                                status_bar_message = "Your turn to attack!"
                                if num_players_expected > 2:
                                    status_bar_message += " Select an opponent board first."
                                    selected_target_opponent_idx = -1 # Reset target selection
                            else:
                                current_game_state = STATE_OPPONENT_TURN
                                status_bar_message = f"Opponent {active_player_turn_id}'s turn."
                        
                        elif msg["type"] == "ATTACK_RESULT":
                            target_pid = msg['target_player_id']
                            row, col = msg['row'], msg['col']
                            result = msg['result'] # "MISS", "HIT", "SUNK"
                            
                            if target_pid in player_boards:
                                if result == "MISS":
                                    player_boards[target_pid][row][col] = CELL_MISS
                                elif result == "HIT":
                                    player_boards[target_pid][row][col] = CELL_HIT
                                elif result == "SUNK":
                                    player_boards[target_pid][row][col] = CELL_HIT # Mark the hit
                                    # Server also sends coordinates of the entire sunk ship
                                    for sr, sc in msg['sunk_ship_coords']:
                                        player_boards[target_pid][sr][sc] = CELL_SUNK_SHIP
                                    player_ship_counts[target_pid] -= 1
                                    status_bar_message = f"Player {msg['attacker_id']} SUNK a ship of Player {target_pid}!"
                                else: # Should not happen
                                    status_bar_message = f"Player {msg['attacker_id']} {result.lower()} Player {target_pid} at ({row},{col})."
                            
                            # If I was the attacker, my turn ends. Server will send next UPDATE_TURN.
                            # If the attack was on me, my board updates.

                        elif msg["type"] == "PLAYER_DEFEATED":
                            defeated_pid = msg['player_id']
                            player_ship_counts[defeated_pid] = 0 # Mark as defeated
                            if defeated_pid == my_player_id:
                                status_bar_message = "All your ships have been sunk! You are defeated."
                                # current_game_state can remain, just observe. Server controls turns.
                            else:
                                status_bar_message = f"Player {defeated_pid} has been defeated!"
                                # If this was the selected target, reset selection
                                if num_players_expected > 2:
                                    for idx, pid_val in opponent_ids_map.items():
                                        if pid_val == defeated_pid and selected_target_opponent_idx == idx:
                                            selected_target_opponent_idx = -1
                                            break

                        elif msg["type"] == "GAME_OVER":
                            game_winner_id = msg.get('winner_id') # Can be None if draw (not typical for BS)
                            current_game_state = STATE_GAME_OVER
                            if game_winner_id == my_player_id:
                                status_bar_message = "YOU ARE THE WINNER! Congratulations!"
                            elif game_winner_id is not None:
                                status_bar_message = f"GAME OVER! Player {game_winner_id} is the winner!"
                            else:
                                status_bar_message = "GAME OVER! It's a draw or server ended game."
                            # Could add a "Play Again?" or "Back to Menu" button here after a delay

            except BlockingIOError:
                pass # No data received, common in non-blocking mode
            except json.JSONDecodeError:
                print("Error decoding JSON from server.")
                socket_buffer = "" # Clear potentially corrupt buffer
            except socket.error as e:
                print(f"Socket error during receive: {e}")
                status_bar_message = "Connection lost to server."
                current_game_state = STATE_GAME_OVER # Or a specific error state
                running = False # End game loop

        # --- Drawing ---
        screen.fill(BLACK) # Background

        if current_game_state != STATE_CONNECTING and current_game_state != STATE_WAITING_FOR_PLAYERS and board_display_rects:
            # Draw My Board
            if my_player_id != -1 and 'my_board' in board_display_rects and my_player_id in player_boards:
                draw_text_on_screen(screen, f"Your Board (Player {my_player_id}) - Ships: {player_ship_counts.get(my_player_id, 'N/A')}",
                                    (board_display_rects['my_board'].left, board_display_rects['my_board'].top - 25), font_small, WHITE)
                draw_game_grid(screen, board_display_rects['my_board'], player_boards[my_player_id], True, cell_size)
                if current_game_state == STATE_SETUP_SHIPS:
                    draw_ship_placement_preview(screen, mouse_current_pos, board_display_rects['my_board'], cell_size)

            # Draw Opponent Boards
            for i in range(num_players_expected - 1):
                opponent_key = f'opponent_{i}'
                actual_opponent_id = opponent_ids_map.get(i)
                if opponent_key in board_display_rects and actual_opponent_id is not None and actual_opponent_id in player_boards:
                    is_targetable_board = (current_game_state == STATE_MY_TURN and player_ship_counts.get(actual_opponent_id, 0) > 0)
                    is_selected = (selected_target_opponent_idx == i)

                    draw_text_on_screen(screen, f"Opponent (Player {actual_opponent_id}) - Ships: {player_ship_counts.get(actual_opponent_id, 'N/A')}",
                                        (board_display_rects[opponent_key].left, board_display_rects[opponent_key].top - 25), font_small, WHITE)
                    draw_game_grid(screen, board_display_rects[opponent_key], player_boards[actual_opponent_id], False, cell_size,
                                   is_targetable_board, is_selected if num_players_expected > 2 else False)

            # Ship placement helper text
            if current_game_state == STATE_SETUP_SHIPS:
                if current_ship_placement_index < len(SHIPS_TO_PLACE_LIST):
                    ship_name, ship_size_val = SHIPS_TO_PLACE_LIST[current_ship_placement_index]
                    orient_text = 'H' if current_ship_orientation == 'H' else 'V'
                    info_text = f"Placing: {ship_name} ({ship_size_val}) Orient: {orient_text} (R to rotate)"
                    draw_text_on_screen(screen, info_text, (10, screen_height - 70), font_small, WHITE)
        
        elif current_game_state == STATE_GAME_OVER: # Special display for game over
            msg_text = status_bar_message
            if game_winner_id == my_player_id:
                color = GREEN
            elif game_winner_id is None:
                color = WHITE
            else:
                color = RED
            text_surf = font_large.render(msg_text, True, color)
            text_rect = text_surf.get_rect(center=(screen_width//2, screen_height//2))
            screen.blit(text_surf, text_rect)
            
            # Add a "Back to Menu" prompt after a delay
            # For now, user quits manually or menu loop re-prompts

        # Status Bar
        status_bar_height = 40
        pygame.draw.rect(screen, (30,30,30), (0, screen_height - status_bar_height, screen_width, status_bar_height))
        draw_text_on_screen(screen, status_bar_message, (10, screen_height - status_bar_height + 10), font_small, STATUS_TEXT_COLOR)
        
        pygame.display.flip()
        game_clock.tick(30) # FPS

    # --- End of Game Loop ---
    if client_socket:
        send_message({"type": "LEAVE_GAME"}) # Inform server
        time.sleep(0.1) # Give a moment for message to send
        client_socket.close()
        client_socket = None
    
    # pygame.quit() # Don't quit pygame here if menu is to resume control
    return True # Indicate normal exit to menu

if __name__ == '__main__':
    # This allows testing client.py directly, e.g., for 2 players
    print("Client.py run directly - starting a 2-player game by default.")
    # A simple way to choose mode if run directly:
    mode = 0
    while mode not in [2,4]:
        try:
            mode = int(input("Enter number of players (2 or 4): "))
        except ValueError:
            print("Invalid input.")

    ip_addr = input(f"Enter Server IP (default {DEFAULT_SERVER_IP}): ") or DEFAULT_SERVER_IP
    game_main_loop(num_players_expected=mode, server_ip=ip_addr)
    pygame.quit()
    sys.exit()