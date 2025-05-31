import pygame
import sys
import os
import socket  # <-- Añadir para comunicación con el servidor

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

def crear_partida_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Crear Partida - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)

    button_width = 250
    button_height = 60
    spacing = 40
    start_y = SCREEN_HEIGHT // 2 - button_height - spacing // 2

    btn_2j = pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y, button_width, button_height)
    btn_4j = pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y + button_height + spacing, button_width, button_height)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        # Título
        title_surf = font_title.render("¿Cuántos jugadores?", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 120))
        screen.blit(title_surf, title_rect)

        # Botón 2 jugadores
        is_hovered_2j = btn_2j.collidepoint(mouse_pos)
        draw_button(screen, btn_2j, "2 jugadores", font_button, is_hovered_2j)

        # Botón 4 jugadores
        is_hovered_4j = btn_4j.collidepoint(mouse_pos)
        draw_button(screen, btn_4j, "4 jugadores", font_button, is_hovered_4j)

        # Botón Atrás
        is_hovered_atras = btn_atras.collidepoint(mouse_pos)
        draw_button(screen, btn_atras, "Atrás", font_small, is_hovered_atras)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_2j.collidepoint(event.pos):
                    pygame.quit()
                    game_main_loop()  # Aquí se debería crear la partida de 2 jugadores
                    sys.exit()
                elif btn_4j.collidepoint(event.pos):
                    # Aquí podrías implementar la lógica para 4 jugadores
                    print("Función para 4 jugadores no implementada.")
                elif btn_atras.collidepoint(event.pos):
                    running = False

def obtener_partidas_disponibles():
    """
    Solicita al servidor la lista de partidas disponibles.
    Retorna una lista de diccionarios con 'nombre_creador', 'id', 'jugadores_conectados', 'max_jugadores'.
    """
    SERVER_HOST = "172.23.43.50"
    SERVER_PORT = 8080
    partidas = []
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=2) as s:
            s.sendall(b"LIST_GAMES")
            data = s.recv(1024).decode()
            if data.startswith("GAMES_LIST "):
                games_str = data[len("GAMES_LIST "):]
                if games_str.strip():
                    for item in games_str.split(";"):
                        campos = item.split("|")
                        if len(campos) >= 4:
                            nombre, id_str, conectados_str, max_jugadores_str = campos[:4]
                            partidas.append({
                                "nombre_creador": nombre,
                                "id": int(id_str),
                                "jugadores_conectados": int(conectados_str),
                                "max_jugadores": int(max_jugadores_str)
                            })
    except Exception as e:
        print(f"Error obteniendo partidas del servidor: {e}")
    return partidas

def unirse_partida_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Unirse a Partida - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)

    # Obtener partidas disponibles del servidor
    partidas_disponibles = obtener_partidas_disponibles()

    button_width = 400
    button_height = 60
    spacing = 30
    start_y = 180
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        # Título
        title_surf = font_title.render("Partidas disponibles", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        screen.blit(title_surf, title_rect)

        # Botón Atrás
        is_hovered_atras = btn_atras.collidepoint(mouse_pos)
        draw_button(screen, btn_atras, "Atrás", font_small, is_hovered_atras)

        # Refrescar la lista de partidas cada vez que se muestra el menú
        partidas_disponibles = obtener_partidas_disponibles()

        # Lista de partidas
        partida_buttons = []
        for idx, partida in enumerate(partidas_disponibles):
            y = start_y + idx * (button_height + spacing)
            btn_rect = pygame.Rect((SCREEN_WIDTH - button_width)//2, y, button_width, button_height)
            partida_buttons.append((btn_rect, partida))
            is_hovered = btn_rect.collidepoint(mouse_pos)
            texto = f"Creador: {partida['nombre_creador']} ({partida['jugadores_conectados']}/{partida['max_jugadores']} jugadores)"
            draw_button(screen, btn_rect, texto, font_button, is_hovered)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_atras.collidepoint(event.pos):
                    running = False
                for btn_rect, partida in partida_buttons:
                    if btn_rect.collidepoint(event.pos):
                        # Aquí se uniría a la partida seleccionada
                        pygame.quit()
                        game_main_loop()
                        sys.exit()

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
                            crear_partida_menu()
                        elif btn["label"] == "Unirse a partida":
                            unirse_partida_menu()
                        elif btn["label"] == "Cerrar":
                            running = False
                            break
    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    menu_loop()
