# menu.py

import pygame
import sys
import os

# Assuming client.py is in the same directory or Python path
try:
    from client import game_main_loop, DEFAULT_SERVER_IP, DEFAULT_SERVER_PORT
except ImportError:
    print("ERROR: client.py not found. Make sure it's in the same directory.")
    sys.exit(1)

SCREEN_WIDTH = 900
SCREEN_HEIGHT = 500

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BUTTON_COLOR = (70, 130, 180)        # Steel Blue
BUTTON_HOVER_COLOR = (100, 149, 237) # Cornflower Blue
BUTTON_TEXT_COLOR = WHITE
TITLE_COLOR = (60, 60, 60)
BACKGROUND_COLOR = (210, 210, 210) # Light Gray

# --- Button Drawing Function ---
def draw_button(surface, rect, text, font, is_hovered):
    color = BUTTON_HOVER_COLOR if is_hovered else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=10)
    pygame.draw.rect(surface, (50,100,150), rect, border_radius=10, width=3) # Border

    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)

# --- Input Text Box (Simple) ---
def draw_input_box(surface, rect, text, font, is_active, prompt="Server IP:"):
    # Draw prompt
    prompt_surf = font.render(prompt, True, BLACK)
    prompt_rect = prompt_surf.get_rect(midright=(rect.left - 10, rect.centery))
    surface.blit(prompt_surf, prompt_rect)

    # Draw box
    color = BUTTON_HOVER_COLOR if is_active else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=5)
    pygame.draw.rect(surface, (50,100,150), rect, border_radius=5, width=2)

    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = text_surf.get_rect(midleft=(rect.left + 10, rect.centery))
    surface.blit(text_surf, text_rect)


def main_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("BattleShip - Main Menu")
    clock = pygame.time.Clock()

    font_title = pygame.font.Font(None, 74)
    font_button = pygame.font.Font(None, 50)
    font_input = pygame.font.Font(None, 36)

    title_text = font_title.render("BattleShip", True, TITLE_COLOR)
    title_rect = title_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 5))

    button_width = 300
    button_height = 60
    button_spacing = 20

    button_2player_rect = pygame.Rect(
        (SCREEN_WIDTH - button_width) // 2,
        title_rect.bottom + 50,
        button_width, button_height
    )
    button_4player_rect = pygame.Rect(
        (SCREEN_WIDTH - button_width) // 2,
        button_2player_rect.bottom + button_spacing,
        button_width, button_height
    )
    button_quit_rect = pygame.Rect(
        (SCREEN_WIDTH - button_width) // 2,
        button_4player_rect.bottom + button_spacing,
        button_width, button_height
    )

    # Server IP input
    input_box_rect = pygame.Rect(
        (SCREEN_WIDTH - button_width) // 2,
        button_quit_rect.bottom + 40,
        button_width, 40
    )
    server_ip_text = DEFAULT_SERVER_IP
    input_active = False

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        is_2player_hovered = button_2player_rect.collidepoint(mouse_pos)
        is_4player_hovered = button_4player_rect.collidepoint(mouse_pos)
        is_quit_hovered = button_quit_rect.collidepoint(mouse_pos)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: # Left click
                    if is_2player_hovered:
                        print(f"Starting 2-Player Game, connecting to {server_ip_text}...")
                        if game_main_loop(num_players_expected=2, server_ip=server_ip_text, server_port=DEFAULT_SERVER_PORT):
                            pass # Game finished, back to menu (or could quit)
                        else:
                            print("Failed to start or connect to game.")
                    elif is_4player_hovered:
                        print(f"Starting 4-Player Game, connecting to {server_ip_text}...")
                        if game_main_loop(num_players_expected=4, server_ip=server_ip_text, server_port=DEFAULT_SERVER_PORT):
                            pass
                        else:
                            print("Failed to start or connect to game.")
                    elif is_quit_hovered:
                        running = False
                    
                    if input_box_rect.collidepoint(mouse_pos):
                        input_active = True
                    else:
                        input_active = False

            if event.type == pygame.KEYDOWN and input_active:
                if event.key == pygame.K_RETURN:
                    input_active = False
                elif event.key == pygame.K_BACKSPACE:
                    server_ip_text = server_ip_text[:-1]
                else:
                    server_ip_text += event.unicode

        screen.blit(title_text, title_rect)

        draw_button(screen, button_2player_rect, "2-Player Game", font_button, is_2player_hovered)
        draw_button(screen, button_4player_rect, "4-Player Game", font_button, is_4player_hovered)
        draw_button(screen, button_quit_rect, "Quit", font_button, is_quit_hovered)
        draw_input_box(screen, input_box_rect, server_ip_text, font_input, input_active)


        pygame.display.flip()
        clock.tick(30)

    pygame.quit()
    sys.exit()

if __name__ == '__main__':
    # Check if client.py is accessible before starting
    try:
        from client import game_main_loop
    except ImportError:
        print("Fatal Error: client.py is missing or not in the Python path.")
        print("Please ensure client.py is in the same directory as menu.py.")
        input("Press Enter to exit.") # Keep console open to see error
        sys.exit(1)
    main_menu()