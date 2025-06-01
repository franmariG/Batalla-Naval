# menu.py

import pygame
import sys
import socket

# Importa las funciones principales de CADA versión del cliente con un alias para evitar conflictos
from client_2p import game_main_loop as game_main_loop_2p
from client_4p import game_main_loop as game_main_loop_4p

# --- Constantes de la Interfaz ---
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 500
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER_COLOR = (100, 149, 237)
BUTTON_TEXT_COLOR = WHITE

# --- Función para dibujar botones (común para todos los menús) ---
def draw_button(surface, rect, text, font, is_hovered):
    color = BUTTON_HOVER_COLOR if is_hovered else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=8)
    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)

# --- Menú para CREAR Partida ---
def crear_partida_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Crear Partida - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)

    btn_2j = pygame.Rect((SCREEN_WIDTH - 250)//2, SCREEN_HEIGHT // 2 - 60 - 20, 250, 60)
    btn_4j = pygame.Rect((SCREEN_WIDTH - 250)//2, SCREEN_HEIGHT // 2 + 20, 250, 60)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        title_surf = font_title.render("¿Cuántos jugadores?", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 120))
        screen.blit(title_surf, title_rect)

        # Botón 2 jugadores
        draw_button(screen, btn_2j, "2 jugadores", font_button, btn_2j.collidepoint(mouse_pos))
        # Botón 4 jugadores
        draw_button(screen, btn_4j, "4 jugadores", font_button, btn_4j.collidepoint(mouse_pos))
        # Botón Atrás
        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_2j.collidepoint(event.pos):
                    pygame.quit()
                    print("Iniciando cliente para 2 jugadores...")
                    game_main_loop_2p() # Llama a la versión de 2 jugadores
                    sys.exit()
                elif btn_4j.collidepoint(event.pos):
                    pygame.quit()
                    print("Iniciando cliente para 4 jugadores...")
                    game_main_loop_4p() # Llama a la versión de 4 jugadores
                    sys.exit()
                elif btn_atras.collidepoint(event.pos):
                    running = False

# --- Lógica para obtener partidas de 2 JUGADORES ---
def obtener_partidas_2p():
    SERVER_HOST = "172.23.5.221" # IP del servidor de 2 jugadores
    SERVER_PORT = 8081
    partidas = []
    try:
        with socket.create_connection((SERVER_HOST, SERVER_PORT), timeout=2) as s:
            s.sendall(b"LIST_GAMES")
            data = s.recv(1024).decode()
            if data.startswith("GAMES_LIST "):
                games_str = data[len("GAMES_LIST "):]
                if games_str.strip():
                    for item in games_str.split(";"):
                        if "|" in item:
                            nombre, id_str = item.split("|")
                            partidas.append({"nombre_creador": nombre, "id": int(id_str)})
    except Exception as e:
        print(f"Error obteniendo partidas de 2J del servidor: {e}")
    return partidas

# --- Lógica para obtener partidas de 4 JUGADORES ---
def obtener_partidas_4p():
    SERVER_HOST = "169.254.107.4"  # IP del servidor de 4 jugadores
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
        print(f"Error obteniendo partidas de 4J del servidor: {e}")
    return partidas

# --- Menú para UNIRSE a una partida de 2 JUGADORES ---
def unirse_partida_menu_2p():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Unirse a Partida (2 Jugadores) - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)
        
        title_surf = font_title.render("Partidas de 2 Jugadores", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        screen.blit(title_surf, title_rect)

        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))

        partidas_disponibles = obtener_partidas_2p()
        partida_buttons = []
        for idx, partida in enumerate(partidas_disponibles):
            y = 180 + idx * (60 + 30)
            btn_rect = pygame.Rect((SCREEN_WIDTH - 400)//2, y, 400, 60)
            partida_buttons.append((btn_rect, partida))
            texto = f"Creador: {partida['nombre_creador']}"
            draw_button(screen, btn_rect, texto, font_button, btn_rect.collidepoint(mouse_pos))

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
                        pygame.quit()
                        print("Iniciando cliente para 2 jugadores...")
                        game_main_loop_2p()
                        sys.exit()

# --- Menú para UNIRSE a una partida de 4 JUGADORES ---
def unirse_partida_menu_4p():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Unirse a Partida (4 Jugadores) - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        title_surf = font_title.render("Partidas de 4 Jugadores", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100))
        screen.blit(title_surf, title_rect)

        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))

        partidas_disponibles = obtener_partidas_4p()
        partida_buttons = []
        for idx, partida in enumerate(partidas_disponibles):
            y = 180 + idx * (60 + 30)
            btn_rect = pygame.Rect((SCREEN_WIDTH - 500)//2, y, 500, 60) # Botón más ancho
            partida_buttons.append((btn_rect, partida))
            texto = f"{partida['nombre_creador']} ({partida['jugadores_conectados']}/{partida['max_jugadores']})"
            draw_button(screen, btn_rect, texto, font_button, btn_rect.collidepoint(mouse_pos))

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
                        pygame.quit()
                        print("Iniciando cliente para 4 jugadores...")
                        game_main_loop_4p()
                        sys.exit()

# --- NUEVO Menú Intermedio para "Unirse a Partida" ---
def seleccionar_modo_unirse_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Unirse a Partida - Seleccionar Modo")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)

    btn_2j = pygame.Rect((SCREEN_WIDTH - 250)//2, SCREEN_HEIGHT // 2 - 60 - 20, 250, 60)
    btn_4j = pygame.Rect((SCREEN_WIDTH - 250)//2, SCREEN_HEIGHT // 2 + 20, 250, 60)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        title_surf = font_title.render("Unirse a partida de...", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 120))
        screen.blit(title_surf, title_rect)

        draw_button(screen, btn_2j, "2 jugadores", font_button, btn_2j.collidepoint(mouse_pos))
        draw_button(screen, btn_4j, "4 jugadores", font_button, btn_4j.collidepoint(mouse_pos))
        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_2j.collidepoint(event.pos):
                    unirse_partida_menu_2p() # Llama al menú de unirse de 2P
                elif btn_4j.collidepoint(event.pos):
                    unirse_partida_menu_4p() # Llama al menú de unirse de 4P
                elif btn_atras.collidepoint(event.pos):
                    running = False

# --- Bucle del Menú Principal ---
def menu_loop():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("BattleShip - Menú Principal")
    font_title = pygame.font.Font(None, 80)
    font_button = pygame.font.Font(None, 48)

    buttons = [
        {"label": "Crear Partida", "rect": pygame.Rect((SCREEN_WIDTH - 320)//2, 200, 320, 60)},
        {"label": "Unirse a partida", "rect": pygame.Rect((SCREEN_WIDTH - 320)//2, 290, 320, 60)},
        {"label": "Cerrar", "rect": pygame.Rect((SCREEN_WIDTH - 320)//2, 380, 320, 60)},
    ]

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        title_surf = font_title.render("BattleShip", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 120))
        screen.blit(title_surf, title_rect)

        for btn in buttons:
            draw_button(screen, btn["rect"], btn["label"], font_button, btn["rect"].collidepoint(mouse_pos))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if buttons[0]["rect"].collidepoint(event.pos): # Crear Partida
                    crear_partida_menu()
                elif buttons[1]["rect"].collidepoint(event.pos): # Unirse a partida
                    seleccionar_modo_unirse_menu() # Llama al nuevo menú intermedio
                elif buttons[2]["rect"].collidepoint(event.pos): # Cerrar
                    running = False

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    menu_loop()