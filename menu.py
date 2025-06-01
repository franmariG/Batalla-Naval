# menu.py

import pygame
import sys
import os
import socket

# Importa la función principal del cliente
from client import game_main_loop

SCREEN_WIDTH = 900
SCREEN_HEIGHT = 500

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER_COLOR = (100, 149, 237)
BUTTON_TEXT_COLOR = WHITE

# Usaremos la IP del servidor 
SERVER_HOST_FOR_LIST = "169.254.107.4" # Asegúrate que sea la IP correcta de tu servidor
SERVER_PORT_FOR_LIST = 8080

def draw_gradient_background(surface, color1, color2):
    """Dibuja un fondo degradado vertical."""
    for y in range(SCREEN_HEIGHT):
        ratio = y / SCREEN_HEIGHT
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)
        pygame.draw.line(surface, (r, g, b), (0, y), (SCREEN_WIDTH, y))

def draw_button(surface, rect, text, font, is_hovered):
    """Dibuja un botón con efecto de sombra en el texto."""
    color = BUTTON_HOVER_COLOR if is_hovered else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=8)
    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_shadow = font.render(text, True, (0, 0, 0))  # Sombra negra
    text_rect = text_surf.get_rect(center=rect.center)
    shadow_offset = 2
    surface.blit(text_shadow, (text_rect.x + shadow_offset, text_rect.y + shadow_offset))
    surface.blit(text_surf, text_rect)

def crear_partida_menu():
    global SCREEN_WIDTH, SCREEN_HEIGHT  
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)
    pygame.display.set_caption("Crear Partida - Batalla Naval") #
    font_title = pygame.font.Font(pygame.font.match_font('arial'), 60)
    font_button = pygame.font.Font(pygame.font.match_font('arial'), 44)
    font_small = pygame.font.Font(pygame.font.match_font('arial'), 32)

    running = True #
    while running:
        screen.fill(BLACK) #
        draw_gradient_background(screen, (30, 30, 60), (10, 10, 30))  # Fondo degradado
        
        # Ajustar tamaños y posiciones dinámicamente
        width, height = screen.get_size()
        button_width = width // 3
        button_height = height // 10
        spacing = height // 20
        start_y = height // 2 - button_height - spacing // 2
        
        btn_2j = pygame.Rect((width - button_width) // 2, start_y, button_width, button_height)
        btn_4j = pygame.Rect((width - button_width) // 2, start_y + button_height + spacing, button_width, button_height)
        btn_atras = pygame.Rect(20, 20, 120, 44)
        
        mouse_pos = pygame.mouse.get_pos() #
            
        title_surf = font_title.render("¿Cuántos jugadores?", True, WHITE) #
        title_rect = title_surf.get_rect(center=(width // 2, height // 5))
        screen.blit(title_surf, title_rect)

        is_hovered_2j = btn_2j.collidepoint(mouse_pos) #
        draw_button(screen, btn_2j, "2 jugadores", font_button, is_hovered_2j) #

        is_hovered_4j = btn_4j.collidepoint(mouse_pos) #
        draw_button(screen, btn_4j, "4 jugadores", font_button, is_hovered_4j) #

        is_hovered_atras = btn_atras.collidepoint(mouse_pos) #
        draw_button(screen, btn_atras, "Atrás", font_small, is_hovered_atras) #

        pygame.display.flip() #

        for event in pygame.event.get():
            if event.type == pygame.QUIT: #
                pygame.quit() #
                sys.exit() #
                
            if event.type == pygame.VIDEORESIZE:
                SCREEN_WIDTH, SCREEN_HEIGHT = event.w, event.h  # Modificar variables globales
                screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.RESIZABLE)

            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: #
                if btn_2j.collidepoint(event.pos):
                    pygame.quit()
                    game_main_loop(mode=2, action="CREATE") # acción para crear
                    sys.exit()
                elif btn_4j.collidepoint(event.pos):
                    pygame.quit()
                    game_main_loop(mode=4, action="CREATE") # acción para crear
                    sys.exit()
                elif btn_atras.collidepoint(event.pos): #
                    running = False

def obtener_partidas_disponibles():
    """
    Solicita al servidor la lista de partidas disponibles.
    Retorna una lista de diccionarios con 'nombre_creador', 'id', 'jugadores_conectados', 'max_jugadores'.
    """ #
    partidas = []
    try:
        # Usamos la IP y puerto definidos globalmente para la lista de partidas
        with socket.create_connection((SERVER_HOST_FOR_LIST, SERVER_PORT_FOR_LIST), timeout=2) as s: #
            s.sendall(b"LIST_GAMES") #
            data = s.recv(1024).decode() #
            if data.startswith("GAMES_LIST "): #
                games_str = data[len("GAMES_LIST "):] #
                if games_str.strip(): #
                    for item in games_str.split(";"): #
                        campos = item.split("|") #
                        # El servidor unificado siempre enviará los 4 campos
                        if len(campos) >= 4: #
                             nombre, id_str, conectados_str, max_jugadores_str = campos[:4] #
                             partidas.append({ #
                                "nombre_creador": nombre, #
                                "id": int(id_str), #
                                "jugadores_conectados": int(conectados_str), #
                                "max_jugadores": int(max_jugadores_str) #
                            })
    except Exception as e:
        print(f"Error obteniendo partidas del servidor: {e}") #
    return partidas #

def unirse_partida_menu():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT)) #
    pygame.display.set_caption("Unirse a Partida - Batalla Naval") #
    font_title = pygame.font.Font(pygame.font.match_font('arial'), 60) #
    font_button = pygame.font.Font(pygame.font.match_font('arial'), 44) #
    font_small = pygame.font.Font(pygame.font.match_font('arial'), 32) #

    button_width = 450 # Aumentado para más texto
    button_height = 60 #
    spacing = 30 #
    start_y = 180 #
    btn_atras = pygame.Rect(20, 20, 120, 44) #

    running = True #
    partida_buttons = []

    while running:
        mouse_pos = pygame.mouse.get_pos() #
        screen.fill(BLACK) #

        title_surf = font_title.render("Partidas disponibles", True, WHITE) #
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, 100)) #
        screen.blit(title_surf, title_rect) #

        is_hovered_atras = btn_atras.collidepoint(mouse_pos) #
        draw_button(screen, btn_atras, "Atrás", font_small, is_hovered_atras) #

        # Refrescar la lista de partidas cada vez que se muestra el menú
        partidas_disponibles = obtener_partidas_disponibles() #
        partida_buttons.clear() #

        if not partidas_disponibles:
            no_games_text = font_button.render("No hay partidas disponibles", True, WHITE)
            no_games_rect = no_games_text.get_rect(center=(SCREEN_WIDTH // 2, start_y + button_height))
            screen.blit(no_games_text, no_games_rect)
        else:
            for idx, partida in enumerate(partidas_disponibles): #
                y = start_y + idx * (button_height + spacing) #
                btn_rect = pygame.Rect((SCREEN_WIDTH - button_width)//2, y, button_width, button_height) #
                partida_buttons.append((btn_rect, partida)) #
                is_hovered = btn_rect.collidepoint(mouse_pos) #
                # Texto mejorado para mostrar toda la información relevante
                texto = f"{partida['nombre_creador']} ({partida['jugadores_conectados']}/{partida['max_jugadores']})" #
                if partida['jugadores_conectados'] >= partida['max_jugadores']:
                    texto += " - Llena"
                draw_button(screen, btn_rect, texto, font_button, is_hovered) #

        pygame.display.flip() #

        for event in pygame.event.get():
            if event.type == pygame.QUIT: #
                pygame.quit() #
                sys.exit() #
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: #
                if btn_atras.collidepoint(event.pos): #
                    running = False #
                for btn_rect, partida in partida_buttons: #
                    if btn_rect.collidepoint(event.pos):
                        if partida['jugadores_conectados'] < partida['max_jugadores']:
                            pygame.quit()
                            # Usar la IP del servidor para la lista de partidas también para unirse.
                            game_main_loop(mode=partida['max_jugadores'],
                                        server_ip_to_join=SERVER_HOST_FOR_LIST, # Usar la IP definida
                                        game_id_to_join=partida['id'], # Pasar el ID de la partida
                                        action="JOIN") # acción para unirse
                            sys.exit()
                        else:
                            print("Esta partida está llena.")


def menu_loop():
    pygame.init() #
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT)) #
    pygame.display.set_caption("Batalla Naval- Menú") #
    font_title = pygame.font.Font(pygame.font.match_font('arial'), 80) #
    font_button = pygame.font.Font(pygame.font.match_font('arial'), 48) #

    button_width = 320 #
    button_height = 60 #
    spacing = 30 #
    start_y = SCREEN_HEIGHT // 2 - (button_height * 3 + spacing * 2) // 2 # # Ajustar si hay más botones

    buttons = [ #
        {"label": "Crear Partida", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y, button_width, button_height)}, #
        {"label": "Unirse a partida", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y + button_height + spacing, button_width, button_height)}, #
        {"label": "Cerrar", "rect": pygame.Rect((SCREEN_WIDTH - button_width)//2, start_y + 2*(button_height + spacing), button_width, button_height)}, #
    ]

    running = True #
    while running:
        mouse_pos = pygame.mouse.get_pos() #
        screen.fill(BLACK) #

        # Ajustar la posición del título para que quede más abajo
        title_surf = font_title.render("Batalla Naval", True, WHITE) #
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH//2, start_y - button_height - spacing))
        screen.blit(title_surf, title_rect) #

        for btn in buttons: #
            is_hovered = btn["rect"].collidepoint(mouse_pos) #
            draw_button(screen, btn["rect"], btn["label"], font_button, is_hovered) #

        pygame.display.flip() #

        for event in pygame.event.get():
            if event.type == pygame.QUIT: #
                running = False #
                break #
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1: #
                for idx, btn in enumerate(buttons): #
                    if btn["rect"].collidepoint(event.pos): #
                        if btn["label"] == "Crear Partida": #
                            crear_partida_menu() #
                        elif btn["label"] == "Unirse a partida": #
                            unirse_partida_menu() #
                        elif btn["label"] == "Cerrar": #
                            running = False #
                            break #
    pygame.quit() #
    sys.exit() #

if __name__ == "__main__":
    menu_loop() #