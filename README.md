# Batalla Naval 🚢

Este proyecto es una implementación de un juego de Batalla Naval multijugador en línea para la asignatura Sistemas Distribuidos. El objetivo era desarrollar una versión inicial 1 contra 1 y luego expandirla a un modo multijugador más complejo, específicamente un 2 contra 2. La implementación se enfoca en el uso de sockets y multihilos para manejar las conexiones de los jugadores y la lógica del juego de manera concurrente.

El desarrollo se dividió en dos etapas principales, abordando los desafíos de la concurrencia y la gestión del estado del juego en un entorno de red.

## Características

* **Multijugador en Red**: Juega con amigos u oponentes a través de una red. Se ha probado exitosamente utilizando ZeroTier para la conectividad en red.
* **Gestión Concurrente**: El servidor maneja múltiples clientes simultáneamente gracias al uso de multihilos.
* **Sistema de Turnos**: El juego gestiona automáticamente el orden de los turnos para cada partida.
* **Comunicación Cliente-Servidor**: Protocolo de comunicación claro para el intercambio de comandos y estados del juego.
* **Interfaz Gráfica**: Interfaz visual para una experiencia de juego interactiva en el cliente (implementada con Pygame).
* **Menú Inicial**: Un menú simple permite al jugador crear, unirse o listar partidas disponibles.

## Modos de Juego

El juego soporta dos modos principales:

* **2 Jugadores (1 vs 1)**: El clásico juego de Batalla Naval donde dos oponentes compiten directamente.
  
* **4 Jugadores (2 vs 2)**: Dos equipos de dos jugadores. En este modo:
  * Los compañeros de equipo comparten el mismo tablero.
  * Los capitanes (P1 y P3) son responsables de configurar el tablero inicial de su equipo.
  * Los disparos se realizan por turnos de manera rotatoria entre los jugadores de ambos equipos (P1, P3, P2, P4).
  * Los resultados de los disparos y los hundimientos de barcos se comunican a todos los jugadores de la partida.

## Arquitectura

El sistema se basa en una arquitectura cliente-servidor:

**Servidor (server.py)**:

* Actúa como el coordinador central del juego.
* Escucha y acepta nuevas conexiones de clientes en un hilo principal dedicado.
* Para cada cliente conectado, crea un hilo separado (handle_client_connection) para manejar su comunicación y lógica de juego específica.
* Gestiona el estado de todas las partidas activas en un diccionario (active_games).

* Utiliza threading.Lock y threading.RLock para garantizar la seguridad de los datos al acceder o modificar estados compartidos, como la lista de partidas * (games_list_lock), la generación de IDs de partida (game_id_lock), o el estado de una partida específica (game_specific_lock, turn_lock).
* Maneja la creación de nuevas partidas y la unión de jugadores a partidas existentes.

* Implementa la lógica del juego, procesando los comandos de los clientes (disparos, resultados, etc.) y actualizando el estado de la partida.
* Notifica a los jugadores sobre eventos del juego (turnos, actualizaciones de tablero, fin de partida).

* Realiza una limpieza adecuada de las conexiones y los estados de las partidas cuando los clientes se desconectan.

**Cliente (client.py)**:

* Se conecta al servidor y se une o crea una partida.
* Gestiona la interfaz gráfica del usuario (GUI) para que el jugador interactúe con el juego (asumiendo Pygame).
* Envía comandos al servidor (ej., CREATE_GAME, JOIN_GAME, SHOT, READY_SETUP).
* Recibe y procesa mensajes del servidor para actualizar su estado de juego y la GUI.

**Menú (menu.py)**:

Proporciona una interfaz inicial para que el jugador elija si desea crear una nueva partida indicando el modo de juego, unirse a una existente o listar las partidas disponibles.

## Requisitos

Asegúrate de tener Python 3.x instalado.
Necesitarás instalar pygame para la interfaz gráfica del cliente:

```Bash
pip install pygame
```

## Estructura de Archivos

```Bash
├── assets/ # Contiene todos los archivos de audio e imágenes del juego
├── client.py
├── menu.py
├── README.md
└── server.py
```

## Configuración de Red

El servidor se configura con una dirección IP y un puerto. Para probar el juego entre diferentes máquinas, se recomienda usar una red virtual como ZeroTier.

En server.py, la variable HOST debe ser la dirección IP de ZeroTier de la máquina donde se ejecutará el servido, tambien se puede jugar de manera local usando la ip de tu red.
Asegúrate de que la dirección IP y el puerto de conexión en los archivos cliente (client.py y menu.py) coincidan con la configuración del servidor.

### Ejecución del Servidor

Para iniciar el servidor, abre una terminal y ejecuta:

```Bash
python server.py
```

Verás mensajes en la consola indicando que el servidor está escuchando conexiones. Por ejemplo, INFO SERVER: Jugador P1 (addr) creó Partida ID: X (Modo Y)..

### Ejecución del Cliente

Para ejecutar un cliente, abre una terminal (o una nueva terminal para cada cliente adicional) y ejecuta:

```Bash
python menu.py
```
El menú te guiará para crear o unirte a una partida.

## Limpieza de Conexiones

El servidor implementa un mecanismo de limpieza de conexiones para asegurar la estabilidad y el uso eficiente de los recursos:

* **Detección de Desconexión**: Cuando un cliente se desconecta inesperadamente (ej., ConnectionResetError, socket.timeout), el hilo correspondiente en el servidor detecta esta situación.
* **Eliminación de Cliente**: El cliente desconectado es eliminado de la lista de clientes de la partida activa.
* **Fin de Partida por Desconexión**: Si un jugador se desconecta durante una partida activa, la partida se marca como inactiva y se resetea el turno actual (asumiendo lógica de juego). Se notifica a los jugadores restantes que la partida ha terminado.
* **Manejo de Errores**: Se incluyen bloques try-except-finally para capturar y manejar diversas excepciones de socket y otras, asegurando que se realice la limpieza incluso en caso de errores inesperados.

* **Cierre del Servidor**: Al apagar el servidor (Ctrl+C), se espera que los hilos de los clientes terminen sus operaciones para garantizar un cierre ordenado.

## Autores

* Franmari Garcia 
  * Usuario de GitHub: franmariG
    
* Magleo Medina
  * Usuario de GitHub: MagleoMedina
