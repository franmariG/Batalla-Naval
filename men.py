# menu.py

import pygame
import sys
import socket
# Importa el cliente unificado. Asegúrate de que client.py esté en la misma carpeta.
import client

# --- Constantes de Configuración y UI ---
SERVER_IP = "169.254.107.4" # IP del servidor. Si el servidor está en otra PC, pon su IP aquí.
SERVER_PORT = 8080
SCREEN_WIDTH = 900
SCREEN_HEIGHT = 500

WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
BUTTON_COLOR = (70, 130, 180)
BUTTON_HOVER_COLOR = (100, 149, 237)
BUTTON_TEXT_COLOR = WHITE
INPUT_BOX_INACTIVE_COLOR = (150, 150, 150)
INPUT_BOX_ACTIVE_COLOR = (200, 200, 255)

# --- Funciones de Ayuda para la UI ---

def draw_button(surface, rect, text, font, is_hovered):
    """Dibuja un botón estándar."""
    color = BUTTON_HOVER_COLOR if is_hovered else BUTTON_COLOR
    pygame.draw.rect(surface, color, rect, border_radius=8)
    text_surf = font.render(text, True, BUTTON_TEXT_COLOR)
    text_rect = text_surf.get_rect(center=rect.center)
    surface.blit(text_surf, text_rect)

def draw_text_input_box(surface, rect, text, font, is_active):
    """Dibuja una caja de entrada de texto."""
    color = INPUT_BOX_ACTIVE_COLOR if is_active else INPUT_BOX_INACTIVE_COLOR
    pygame.draw.rect(surface, color, rect, 2, border_radius=5)
    text_surface = font.render(text, True, WHITE)
    surface.blit(text_surface, (rect.x + 10, rect.y + 10))
    # Para que el rect del input no se haga más grande
    # rect.w = max(350, text_surface.get_width() + 20)

# --- Funciones de Comunicación con el Servidor ---

def obtener_partidas_disponibles():
    """Se conecta al servidor y solicita la lista de partidas disponibles."""
    partidas = []
    try:
        with socket.create_connection((SERVER_IP, SERVER_PORT), timeout=2) as s:
            s.sendall(b"LIST_GAMES\n")
            response = s.recv(4096).decode()
            if response.startswith("GAMES_LIST"):
                games_str = response[len("GAMES_LIST "):].strip()
                if games_str:
                    for item in games_str.split(';'):
                        # Protocolo: gid|name|gtype|p_curr|p_max
                        parts = item.split('|')
                        if len(parts) == 5:
                            partidas.append({
                                "id": parts[0], "name": parts[1], "type": parts[2],
                                "p_curr": parts[3], "p_max": parts[4]
                            })
    except Exception as e:
        print(f"Error obteniendo partidas: {e}")
        # Devuelve una partida de error para mostrar en la UI
        partidas.append({"id": "err", "name": f"No se pudo conectar al servidor en {SERVER_IP}", "type": "ERR", "p_curr": "0", "p_max": "0"})
    return partidas

# --- Menús de la Aplicación ---

def unirse_partida_menu():
    """Muestra la lista de partidas disponibles y permite unirse a una."""
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Unirse a Partida - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_button = pygame.font.Font(None, 36)
    font_small = pygame.font.Font(None, 32)
    clock = pygame.time.Clock()

    btn_atras = pygame.Rect(20, 20, 120, 44)
    btn_refrescar = pygame.Rect(SCREEN_WIDTH - 140, 20, 120, 44)
    
    partidas_disponibles = obtener_partidas_disponibles()

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        # Título
        title_surf = font_title.render("Partidas Disponibles", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 60))
        screen.blit(title_surf, title_rect)

        # Botones de control
        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))
        draw_button(screen, btn_refrescar, "Refrescar", font_small, btn_refrescar.collidepoint(mouse_pos))

        # Dibujar lista de partidas
        partida_buttons = []
        for idx, partida in enumerate(partidas_disponibles):
            y = 120 + idx * 70
            btn_rect = pygame.Rect((SCREEN_WIDTH - 600) // 2, y, 600, 60)
            partida_buttons.append({"rect": btn_rect, "data": partida})
            
            texto = f"{partida['name']} ({partida['type']}) - {partida['p_curr']}/{partida['p_max']}"
            if partida['type'] == 'ERR':
                texto = partida['name']
            
            is_hovered = btn_rect.collidepoint(mouse_pos)
            draw_button(screen, btn_rect, texto, font_button, is_hovered)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if btn_atras.collidepoint(event.pos):
                    running = False
                elif btn_refrescar.collidepoint(event.pos):
                    partidas_disponibles = obtener_partidas_disponibles()
                else:
                    for btn in partida_buttons:
                        if btn["rect"].collidepoint(event.pos) and btn['data']['type'] != 'ERR':
                            pygame.quit()
                            # Lanzar el cliente unificado con la acción JOIN
                            client.game_main_loop(
                                server_ip=SERVER_IP, server_port=SERVER_PORT,
                                action='JOIN',
                                game_id=btn['data']['id']
                            )
                            running = False # Salir del bucle del menú
                            # o 'return'
                            break # Salir del bucle for de los botones
        clock.tick(30)


def crear_partida_menu():
    """Permite al usuario nombrar y crear una partida de 2 o 4 jugadores."""
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Crear Partida - BattleShip")
    font_title = pygame.font.Font(None, 60)
    font_label = pygame.font.Font(None, 36)
    font_button = pygame.font.Font(None, 44)
    font_small = pygame.font.Font(None, 32)
    
    game_name = ""
    input_rect = pygame.Rect((SCREEN_WIDTH - 350) // 2, 200, 350, 50)
    input_active = True

    btn_2j = pygame.Rect((SCREEN_WIDTH - 350) // 2, 300, 165, 60)
    btn_4j = pygame.Rect((SCREEN_WIDTH - 350) // 2 + 185, 300, 165, 60)
    btn_atras = pygame.Rect(20, 20, 120, 44)

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        # Título
        title_surf = font_title.render("Crear Nueva Partida", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 80))
        screen.blit(title_surf, title_rect)
        
        # Etiqueta para la caja de texto
        label_surf = font_label.render("Nombre de la Partida:", True, WHITE)
        screen.blit(label_surf, (input_rect.x, input_rect.y - 40))

        # Caja de texto
        draw_text_input_box(screen, input_rect, game_name, font_label, input_active)

        # Botones
        draw_button(screen, btn_2j, "2 Jugadores", font_button, btn_2j.collidepoint(mouse_pos))
        draw_button(screen, btn_4j, "4 Jugadores", font_button, btn_4j.collidepoint(mouse_pos))
        draw_button(screen, btn_atras, "Atrás", font_small, btn_atras.collidepoint(mouse_pos))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if input_rect.collidepoint(event.pos):
                    input_active = True
                else:
                    input_active = False

                if btn_atras.collidepoint(event.pos):
                    running = False
                
                # Crear partida de 2 Jugadores
                elif btn_2j.collidepoint(event.pos) and game_name.strip():
                    pygame.quit()
                    client.game_main_loop(
                        server_ip=SERVER_IP, server_port=SERVER_PORT,
                        action='CREATE', game_type='2P', game_name=game_name.strip()
                    )
                    running = False # Salir del bucle del menú para volver al menú principal o cerrar si es necesario
                # o simplemente 'return' si quieres que la función del menú termine aquí.

                # Crear partida de 4 Jugadores
                elif btn_4j.collidepoint(event.pos) and game_name.strip():
                    pygame.quit()
                    client.game_main_loop(
                        server_ip=SERVER_IP, server_port=SERVER_PORT,
                        action='CREATE', game_type='4P', game_name=game_name.strip()
                    )
                    running = False # Salir del bucle del menú
                    # o 'return'

            if event.type == pygame.KEYDOWN and input_active:
                if event.key == pygame.K_BACKSPACE:
                    game_name = game_name[:-1]
                elif len(game_name) < 20: # Limitar longitud del nombre
                    game_name += event.unicode


def menu_loop():
    """Bucle del menú principal."""
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("BattleShip - Menú Principal")
    font_title = pygame.font.Font(None, 80)
    font_button = pygame.font.Font(None, 48)

    buttons = [
        {"label": "Crear Partida", "rect": pygame.Rect((SCREEN_WIDTH - 320) // 2, 200, 320, 60)},
        {"label": "Unirse a Partida", "rect": pygame.Rect((SCREEN_WIDTH - 320) // 2, 290, 320, 60)},
        {"label": "Cerrar", "rect": pygame.Rect((SCREEN_WIDTH - 320) // 2, 380, 320, 60)},
    ]

    running = True
    while running:
        mouse_pos = pygame.mouse.get_pos()
        screen.fill(BLACK)

        title_surf = font_title.render("BattleShip", True, WHITE)
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 120))
        screen.blit(title_surf, title_rect)

        for btn in buttons:
            draw_button(screen, btn["rect"], btn["label"], font_button, btn["rect"].collidepoint(mouse_pos))

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if buttons[0]["rect"].collidepoint(event.pos):  # Crear Partida
                    crear_partida_menu()
                elif buttons[1]["rect"].collidepoint(event.pos):  # Unirse a partida
                    unirse_partida_menu()
                elif buttons[2]["rect"].collidepoint(event.pos):  # Cerrar
                    running = False

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    menu_loop()