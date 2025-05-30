import pygame
import sys
import os

# Importa la función principal del cliente
from client import game_main_loop

SCREEN_WIDTH = 900
SCREEN_HEIGHT = 500

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER_COLOR = (100, 149, 237)
BUTTON_TEXT_COLOR = WHITE

def draw_button(surface, rect, text, font, is_hovered):
    color = BUTTON_HOVER_COLOR if is_hovered else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=8)
    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)

def menu_loop():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("BattleShip - Menú")
    font_title = pygame.font.Font(None, 80)
    font_button = pygame.font.Font(None, 48)

    # Definir botones
    button_width = 320
    button_height = 60
    spacing = 30
    start_y = SCREEN_HEIGHT // 2 - (button_height * 3 + spacing * 2) // 2

    buttons = [
        {"label": "Crear Partida", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y, button_width, button_height)},
        {"label": "Unirse a partida", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y + button_height + spacing, button_width, button_height)},
        {"label": "Cerrar", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y + 2*(button_height + spacing), button_width, button_height)},
    ]

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        # Título
        title_surf = font_title.render("BattleShip", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 120))
        screen.blit(title_surf, title_rect)

        # Botones
        for btn in buttons:
            is_hovered = btn["rect"].collidepoint(mouse_pos)
            draw_button(screen, btn["rect"], btn["label"], font_button, is_hovered)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                break
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                for idx, btn in enumerate(buttons):
                    if btn["rect"].collidepoint(event.pos):
                        if btn["label"] == "Crear Partida":
                            # Aquí podrías implementar la lógica de crear partida (servidor)
                            # Por ahora, solo muestra un mensaje temporal
                            print("Función 'Crear Partida' no implementada.")
                        elif btn["label"] == "Unirse a partida":
                            pygame.quit()
                            game_main_loop()  # Llama a la función principal del cliente
                            sys.exit()
                        elif btn["label"] == "Cerrar":
                            running = False
                            break
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    menu_loop()
