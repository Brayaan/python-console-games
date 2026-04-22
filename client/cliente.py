# Módulo del cliente multijugador.
# Gestiona la conexión TCP al servidor, el hilo de escucha en segundo plano y
# la interfaz de usuario en consola (menús, tableros, chat y modo partida).
import socket
import threading
import sys
import os
import time
from utils.protocolo import Protocolo

# Cambia a True para ver mensajes de depuración en consola
DEBUG = False


class Colores:
    """Constantes de escape ANSI para colorear la salida en la terminal."""
    HEADER    = "\033[95m"
    AZUL      = "\033[94m"
    VERDE     = "\033[92m"
    AMARILLO  = "\033[93m"
    ROJO      = "\033[91m"
    CYAN      = "\033[96m"
    RESET     = "\033[0m"
    BOLD      = "\033[1m"
    UNDERLINE = "\033[4m"


class ClienteJuegos:
    """Cliente de consola para el servidor de juegos multijugador.

    Mantiene la conexión TCP, lanza un hilo daemon que escucha mensajes
    del servidor y expone métodos de UI (menús, tableros, chat) ejecutados
    en el hilo principal para evitar condiciones de carrera con input().
    """

    def __init__(self, host="localhost", puerto=8888):
        self.host = host
        self.puerto = puerto
        self.socket = None           # Conexión TCP con el servidor
        self.conectado = False        # True mientras la conexión esté activa
        self.jugador_id = None        # ID único asignado por el servidor
        self.sala_id = None           # ID de la sala en la que está el jugador
        self.juego_actual = None      # Datos del juego en curso (tablero, turno, etc.)
        self.nombre = None            # Nombre de pantalla del jugador
        self.en_partida = False       # True cuando hay una partida activa
        self.nombre_registrado = False  # True una vez que el servidor confirmó el nombre
        self.ultimo_error = None      # Último mensaje de error recibido del servidor
        self.historial_chat = []      # Lista con los últimos mensajes del chat
        self.nuevo_mensaje_chat = False  # Bandera para refrescar el chat en pantalla
        self.evento_respuesta = threading.Event()   # Sincroniza respuestas del servidor con el hilo principal
        self.datos_recibidos = None   # Datos de la última respuesta del servidor
        self.esperando_actualizacion = threading.Event()  # Espera la confirmación del movimiento
        self.rival_nombre = None      # Nombre del oponente
        self.resultado_partida = None  # Guardado por hilo de fondo, mostrado por hilo principal

    def conectar(self):
        """Establece la conexión TCP con el servidor y arranca el hilo de escucha.

        El hilo daemon de escucha se detiene automáticamente cuando el proceso
        principal termina o el socket se cierra.

        Returns:
            True si la conexión fue exitosa, False en caso contrario.
        """
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.puerto))
            self.conectado = True

            # Hilo daemon: muere junto con el proceso principal
            hilo = threading.Thread(target=self.escuchar_servidor)
            hilo.daemon = True
            hilo.start()

            return True
        except Exception as e:
            print(f"{Colores.ROJO}[ERROR] Error conectando: {e}{Colores.RESET}")
            return False

    def escuchar_servidor(self):
        """Bucle de recepción de mensajes que corre en el hilo daemon.

        Llama a procesar_mensaje() por cada mensaje recibido del servidor.
        Al detectar desconexión o error pone self.conectado=False para que
        el hilo principal pueda salir de sus bucles de espera.
        """
        while self.conectado:
            try:
                mensaje = Protocolo.recibir(self.socket)
                if not mensaje:
                    break
                self.procesar_mensaje(mensaje)
            except Exception as e:
                if self.conectado:
                    print(
                        f"\n{Colores.ROJO}[ERROR] Error en comunicación: {e}{Colores.RESET}"
                    )
                break

        self.conectado = False
        print(f"\n{Colores.ROJO}[ADVERTENCIA] Desconectado del servidor{Colores.RESET}")

    def procesar_mensaje(self, mensaje):
        """Despacha un mensaje recibido del servidor al manejador correspondiente.

        Se ejecuta en el hilo daemon de escucha. Actualiza el estado interno
        (en_partida, juego_actual, historial_chat, etc.) y señaliza los eventos
        que el hilo principal usa para esperar respuestas sincrónicas.

        Args:
            mensaje: Dict deserializado del protocolo con al menos 'tipo' y 'datos'.
        """
        if not mensaje or "tipo" not in mensaje:
            return

        tipo = mensaje["tipo"]
        datos = mensaje.get("datos", {})

        if tipo == "LISTA_JUEGOS":
            self.datos_recibidos = datos
            self.evento_respuesta.set()

        elif tipo == "LISTA_SALAS":
            self.datos_recibidos = datos
            self.evento_respuesta.set()

        elif tipo == "SALA_CREADA":
            # Guardar el ID de sala asignado por el servidor
            self.sala_id = datos["sala_id"]
            print(f"\n{Colores.VERDE}[OK] Sala creada: {datos['sala_id']}{Colores.RESET}")
            print(f"[JUEGO] Juego: {datos['juego']}")
            print(f"{Colores.AMARILLO}Esperando a otro jugador...{Colores.RESET}")
            print("")

        elif tipo == "UNIDO_SALA":
            self.sala_id = datos["sala_id"]
            print(
                f"\n{Colores.VERDE}[OK] Te uniste a la sala {self.sala_id}{Colores.RESET}"
            )
            print(f"[JUEGO] Juego: {datos['juego']}")

            if "nombres" in datos and datos["nombres"]:
                nombres_lista = []
                for jid, nombre in datos["nombres"].items():
                    if nombre:
                        nombres_lista.append(str(nombre))
                if nombres_lista:
                    print(f"[JUGADORES] Jugadores: {', '.join(nombres_lista)}")

            if datos.get("estado") == "JUGANDO":
                print(f"{Colores.VERDE}[JUEGO] ¡Partida lista para comenzar!{Colores.RESET}")
            print("")

        elif tipo == "PARTIDA_INICIADA":
            self.en_partida = True
            self.jugador_id = datos["tu_jugador_id"]  # Guardar el ID que nos asignó el servidor
            self.juego_actual = datos
            self.rival_nombre = datos.get("rival_nombre", "Rival")
            # Mostrar tablero y luego indicar si es nuestro turno
            self.mostrar_tablero(datos["tablero"])
            print(
                f"\n{Colores.BOLD}{Colores.VERDE}[JUEGO] !PARTIDA INICIADA!{Colores.RESET}"
            )
            if datos["turno"] == self.jugador_id:
                print(f"{Colores.VERDE}[TURNO] ES TU TURNO{Colores.RESET}")
            else:
                print(
                    f"{Colores.AMARILLO}[ESPERA] Esperando turno del rival...{Colores.RESET}"
                )

        elif tipo == "ACTUALIZACION":
            self.juego_actual = datos
            self.mostrar_tablero(datos["tablero"])

            if "ultimo_movimiento" in datos and datos["ultimo_movimiento"]:
                mov = datos["ultimo_movimiento"]
                if mov and isinstance(mov, dict):
                    jugador_mov = mov.get("jugador", "")
                    movimiento_val = mov.get("movimiento", "")

                    if jugador_mov and movimiento_val:
                        if jugador_mov == self.jugador_id:
                            print(
                                f"{Colores.AZUL}[OK] Movimiento enviado: {movimiento_val}{Colores.RESET}"
                            )
                        else:
                            print(
                                f"{Colores.AMARILLO}[JUGADOR] Rival movio a {movimiento_val}{Colores.RESET}"
                            )

            if datos.get("turno") == self.jugador_id:
                print(f"{Colores.VERDE}[TURNO] ES TU TURNO{Colores.RESET}")
            else:
                print(
                    f"{Colores.AMARILLO}[ESPERA] Esperando turno del rival...{Colores.RESET}"
                )
            print("")
            # Desbloquear el hilo principal que espera la actualizacion
            self.esperando_actualizacion.set()

        elif tipo == "JUEGO_TERMINADO":
            self.en_partida = False
            self.esperando_actualizacion.set()  # desbloquear si estaba esperando
            self.historial_chat.clear()
            ganador = datos.get("ganador")

            # Guardar resultado para que el hilo principal lo muestre de forma segura.
            # El hilo de fondo NO toca la pantalla (evita race condition con input()).
            self.resultado_partida = {
                "es_ganador": ganador == self.jugador_id,
                "es_empate":  ganador is None,
            }
            # El hilo de fondo no toca la pantalla; _mostrar_resultado_final() lo muestra automaticamente.

        elif tipo == "JUGADOR_DESCONECTADO":
            # El rival cerró la conexión: terminar la partida
            print(f"\n{Colores.ROJO}[ADVERTENCIA] El rival se ha desconectado{Colores.RESET}")
            self.en_partida = False
            print("")

        elif tipo == "ERROR":
            error_msg = datos.get('mensaje', 'Error desconocido')

            # Mensajes amigables para errores de movimiento inválido
            mensajes_amigables = {
                "Casilla ocupada":          "[!] Esa casilla ya esta ocupada, elige otra.",
                "Columna llena":            "[!] Esa columna esta llena, elige otra.",
                "Posición inválida (1-9)":  "[!] Posicion invalida, ingresa un numero del 1 al 9.",
                "Columna inválida (0-6)":   "[!] Columna invalida, ingresa un numero del 1 al 7.",
            }

            if error_msg in mensajes_amigables:
                # Error de jugada: mostrar aviso amigable y volver a pedir movimiento
                print(f"\n{Colores.AMARILLO}{mensajes_amigables[error_msg]}{Colores.RESET}\n")
                self.ultimo_error = None          # No interrumpir el flujo de sala/partida
                self.esperando_actualizacion.set()  # Desbloquear el wait de jugar_turno de inmediato
            else:
                self.ultimo_error = error_msg
                print(f"{Colores.ROJO}[ERROR] Error: {error_msg}{Colores.RESET}")
                print("")
            
        elif tipo == "REGISTRO_EXITOSO":
            self.nombre_registrado = True

        elif tipo == "CHAT":
            jug = datos.get('jugador', '')
            msg = datos.get('mensaje', '')
            ts  = datos.get('timestamp', '')
            linea = f"[{ts}] {jug}: {msg}"  # Formato: [hora] nombre: mensaje
            self.historial_chat.append(linea)
            if len(self.historial_chat) > 20:  # Mantener solo los últimos 20 mensajes
                self.historial_chat.pop(0)

            self.nuevo_mensaje_chat = True
            if self.en_partida:
                # Si es el turno del rival, refrescar tablero para mostrar el nuevo mensaje
                if getattr(self, "juego_actual", None) and self.juego_actual.get("turno") != self.jugador_id:
                    self.mostrar_tablero(self.juego_actual["tablero"])
                else:
                    print(f"\r{Colores.CYAN}[NOTIFICACION] Nuevo mensaje en chat{Colores.RESET}")

        elif tipo == "STATS_RESPONSE":
            self.historial_chat.append(f"{Colores.CYAN}{datos.get('mensaje', '')}{Colores.RESET}")
            if len(self.historial_chat) > 20:
                self.historial_chat.pop(0)
            if self.en_partida:
                if getattr(self, "juego_actual", None) and self.juego_actual.get("turno") != self.jugador_id:
                    self.mostrar_tablero(self.juego_actual["tablero"])
                else:
                    print(f"\r{Colores.CYAN}[NOTIFICACION] Nuevo mensaje de stats{Colores.RESET}")
            
        elif tipo == "ESTADISTICAS_REPORTE":
            self.datos_recibidos = datos
            self.evento_respuesta.set()

    def mostrar_juegos(self, juegos):
        """Imprime el catálogo de juegos disponibles recibido del servidor.

        Args:
            juegos: Dict {juego_id: nombre} con los juegos disponibles.
        """
        if self.en_partida:
            return  # No mostrar mientras estás en partida
        print(f"\n{Colores.BOLD}{Colores.HEADER}[JUEGO] JUEGOS DISPONIBLES{Colores.RESET}")
        print(f"{Colores.BOLD}{'='*40}{Colores.RESET}")
        for id_j, nombre in juegos.items():
            print(f"{Colores.AZUL}{id_j}.{Colores.RESET} {nombre}")
        print(f"{Colores.AMARILLO}0.{Colores.RESET} Volver")
        print("")

    def mostrar_salas(self, salas):
        """Imprime la lista de salas en estado ESPERANDO.

        Args:
            salas: Dict {sala_id: {juego, jugadores, creador}} recibido del servidor.
        """
        if self.en_partida:
            return  # No mostrar mientras estás en partida
        if not salas:
            print(f"\n{Colores.AMARILLO}No hay salas disponibles. ¡Crea una!{Colores.RESET}\n")
            print(f"{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
            return
        print(f"\n{Colores.BOLD}{Colores.HEADER}[SALAS] SALAS DISPONIBLES{Colores.RESET}")
        print(f"{Colores.BOLD}{'='*50}{Colores.RESET}")
        for sala_id, info in salas.items():
            print(f"{Colores.VERDE}[ID] {sala_id}{Colores.RESET}")
            print(f"  [JUEGO] {info['juego']}")
            print(f"  [JUGADOR] Creador: {info['creador']}")
            print()
        print(f"{Colores.AMARILLO}0. Volver{Colores.RESET}\n")

    def mostrar_estadisticas(self, datos):
        """Muestra las estadísticas de la sesión del jugador actual.

        Calcula el porcentaje de victoria y formatea la salida con colores.
        Si el jugador no tiene partidas registradas, muestra un aviso.

        Args:
            datos: Dict global de estadísticas recibido del servidor
                   ({nombre: {jugadas, ganadas, perdidas, empates}}).
        """
        if self.en_partida:
            return
            
        print(f"\n{Colores.BOLD}{Colores.HEADER}[ESTADISTICAS] MIS ESTADÍSTICAS{Colores.RESET}")
        print(f"{Colores.BOLD}{'='*40}{Colores.RESET}")
        
        if not self.nombre or self.nombre not in datos:
            print(f"{Colores.AMARILLO}No hay estadísticas disponibles para ti todavía.{Colores.RESET}")
            print(f"{Colores.AMARILLO}Asegúrate de jugar al menos una partida.{Colores.RESET}\n")
            print(f"{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
            return
            
        mis_stats = datos[self.nombre]   # Extraer solo las stats del jugador actual
        jugadas  = mis_stats.get('jugadas',  0)
        ganadas  = mis_stats.get('ganadas',  0)
        perdidas = mis_stats.get('perdidas', 0)
        empates  = mis_stats.get('empates',  0)

        # Calcular porcentaje de victorias (evitar división por cero)
        porcentaje = (ganadas / jugadas * 100) if jugadas > 0 else 0.0

        print(f"{Colores.AZUL}Nombre:             {Colores.RESET} {self.nombre}")
        print(f"{Colores.AZUL}Partidas jugadas:   {Colores.RESET} {jugadas}")
        print(f"{Colores.VERDE}Partidas ganadas:   {Colores.RESET} {ganadas}")
        print(f"{Colores.ROJO}Partidas perdidas:  {Colores.RESET} {perdidas}")
        print(f"{Colores.AMARILLO}Empates:            {Colores.RESET} {empates}")
        print(f"{Colores.BOLD}% de victoria:      {Colores.RESET} {porcentaje:.1f}%")
        print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")

    def mostrar_chat(self):
        """Imprime las últimas 5 líneas del historial de chat de la sala."""
        print(f"\n{Colores.BOLD}───── CHAT ─────{Colores.RESET}")
        for msg in self.historial_chat[-5:]:
            print(msg)
        print(f"{Colores.BOLD}────────────────{Colores.RESET}")

    def mostrar_tablero(self, tablero_info):
        """Limpia la pantalla y renderiza el tablero del juego activo.

        Muestra primero el historial de chat, luego las identidades (nombre
        y símbolo de cada jugador) y el tablero del juego concreto.

        Args:
            tablero_info: Dict con 'tipo' ('triqui' o 'conecta4') y los datos
                          del tablero devueltos por JuegoBase.obtener_vista().
        """
        os.system("clear" if os.name == "posix" else "cls")

        self.mostrar_chat()
        self.nuevo_mensaje_chat = False

        # Bloque de identidades (disponible tras PARTIDA_INICIADA)
        if self.juego_actual and self.jugador_id:
            tu_simbolo = self.juego_actual.get("tablero", {}).get("tu_simbolo") \
                         if isinstance(self.juego_actual.get("tablero"), dict) \
                         else self.juego_actual.get("tu_simbolo", "?")
            # En ACTUALIZACION, tu_simbolo viene dentro de tablero_info
            if isinstance(tablero_info, dict):
                tu_simbolo = tablero_info.get("tu_simbolo", tu_simbolo)
            pares_simbolo = {"X": "O", "O": "X", "R": "A", "A": "R"}
            rival_simbolo = pares_simbolo.get(tu_simbolo, "?")
            mi_nombre = self.nombre or "Tu"
            rival = self.rival_nombre or "Rival"
            print(f"{Colores.VERDE}[TU]    {mi_nombre:<15} [{Colores.BOLD}{tu_simbolo}{Colores.RESET}{Colores.VERDE}]{Colores.RESET}")
            print(f"{Colores.ROJO}[RIVAL] {rival:<15} [{Colores.BOLD}{rival_simbolo}{Colores.RESET}{Colores.ROJO}]{Colores.RESET}")
            print()

        tipo = tablero_info.get("tipo", "") if isinstance(tablero_info, dict) else ""

        # Elegir el renderizador según el tipo de juego
        if tipo == "triqui":
            self.mostrar_tablero_triqui(tablero_info["tablero"])
        elif tipo == "conecta4":
            self.mostrar_tablero_conecta4(tablero_info["tablero"])
        

    def mostrar_tablero_triqui(self, tablero):
        """Renderiza la cuadrícula 3×3 del Triqui con separadores gráficos.

        Colorea X en verde y O en rojo. Imprime la guía de posiciones (1-9)
        debajo del tablero para ayudar al jugador a elegir casilla.

        Args:
            tablero: Lista plana de 9 celdas (' ', 'X' u 'O').
        """
        print("\n")
        for i in range(0, 9, 3):
            fila = []
            for j in range(3):
                val = tablero[i + j]
                if val == "X":
                    fila.append(f"{Colores.VERDE}X{Colores.RESET}")
                elif val == "O":
                    fila.append(f"{Colores.ROJO}O{Colores.RESET}")
                else:
                    fila.append(" ")
            print(f" {fila[0]} │ {fila[1]} │ {fila[2]} ")
            if i < 6:
                print("───┼───┼───")

        print("\nPosiciones:")
        print(" 1 │ 2 │ 3 ")
        print("───┼───┼───")
        print(" 4 │ 5 │ 6 ")
        print("───┼───┼───")
        print(" 7 │ 8 │ 9 ")
        print(f"\n{Colores.BOLD}Comandos: {Colores.RESET}{Colores.VERDE}[1-9]{Colores.RESET} mover  {Colores.CYAN}[C]{Colores.RESET} chat  {Colores.ROJO}[rendirse]{Colores.RESET} abandonar")

    def mostrar_tablero_conecta4(self, tablero):
        """Renderiza la cuadrícula 6×7 del Conecta 4 con bordes Unicode.

        Colorea R (Rojo) y A (Amarillo). La numeración de columnas (1-7)
        se muestra en la cabecera para guiar la elección del jugador.

        Args:
            tablero: Lista de 6 listas (filas) de 7 celdas (' ', 'R' o 'A').
        """
        print(f"\n{Colores.BOLD}   1   2   3   4   5   6   7{Colores.RESET}")
        print(f"{Colores.BOLD}  ┌───┬───┬───┬───┬───┬───┬───┐{Colores.RESET}")
        
        for i, fila in enumerate(tablero):
            # Imprimir fila con separadores
            print(f"{Colores.BOLD}{i+1} │{Colores.RESET}", end="")
            for celda in fila:
                if celda == "R":
                    print(f" {Colores.ROJO}R{Colores.RESET} ", end="")
                elif celda == "A":
                    print(f" {Colores.AMARILLO}A{Colores.RESET} ", end="")
                else:
                    print("   ", end="")
                print(f"{Colores.BOLD}│{Colores.RESET}", end="")
            print()
            
            # Línea separadora (excepto después de la última fila)
            if i < len(tablero) - 1:
                print(f"{Colores.BOLD}  ├───┼───┼───┼───┼───┼───┼───┤{Colores.RESET}")
        
        print(f"{Colores.BOLD}  └───┴───┴───┴───┴───┴───┴───┘{Colores.RESET}")
        print(f"\n{Colores.BOLD}Comandos: {Colores.RESET}{Colores.VERDE}[1-7]{Colores.RESET} columna  {Colores.CYAN}[C]{Colores.RESET} chat  {Colores.ROJO}[rendirse]{Colores.RESET} abandonar")

    def menu_principal(self):
        """Bucle principal de navegación del cliente.

        En cada iteración limpia la pantalla y muestra las opciones. Si
        self.en_partida es True, cede el control a modo_partida() hasta que
        la partida concluya y el resultado sea mostrado al usuario.
        """
        while self.conectado:
            # Si entramos en partida, ceder el control al modo_partida
            if self.en_partida:
                self.modo_partida()
                # _mostrar_resultado_final ya limpio la pantalla y mostro el resultado
                continue

            # Limpiar en cada iteracion normal para evitar acumulacion de opciones
            os.system("clear" if os.name == "posix" else "cls")
            print(f"\n{Colores.BOLD}OPCIONES:{Colores.RESET}")
            print(f"{Colores.AZUL}1.{Colores.RESET} Ver juegos disponibles")
            print(f"{Colores.AZUL}2.{Colores.RESET} Ver salas disponibles")
            print(f"{Colores.AZUL}3.{Colores.RESET} Crear sala")
            print(f"{Colores.AZUL}4.{Colores.RESET} Unirse a sala")
            print(f"{Colores.AZUL}5.{Colores.RESET} Cambiar nombre")
            print(f"{Colores.AZUL}6.{Colores.RESET} Ver mis estadísticas")
            print(f"{Colores.ROJO}0.{Colores.RESET} Salir")

            try:
                opcion = input(f"\n{Colores.VERDE}➤{Colores.RESET} ").strip()

                if opcion == "1":
                    self.solicitar_juegos()
                elif opcion == "2":
                    self.solicitar_salas()
                elif opcion == "3":
                    self.crear_sala()
                elif opcion == "4":
                    self.unirse_sala()
                elif opcion == "5":
                    self.cambiar_nombre()
                elif opcion == "6":
                    self.solicitar_estadisticas()
                elif opcion == "0":
                    self.desconectar()
                    break
            except Exception:
                continue

    def cambiar_nombre(self):
        """Permite al jugador actualizar su nombre de pantalla.

        Envía una solicitud REGISTRAR_NOMBRE al servidor y espera hasta 2 s
        la confirmación. Si el nombre ya está en uso o hay un error, restaura
        el estado anterior y muestra el mensaje de error correspondiente.
        """
        os.system("clear" if os.name == "posix" else "cls")
        nombre = input(f"\n{Colores.VERDE}[CAMBIO NOMBRE] Ingrese nuevo nombre:{Colores.RESET}\n➤ ").strip()
        if nombre == "0":
            os.system("clear" if os.name == "posix" else "cls")
            return
            
        if 3 <= len(nombre) <= 20:
            self.ultimo_error = None
            old_registrado = self.nombre_registrado
            self.nombre_registrado = False  # Resetear para esperar la nueva confirmación
            Protocolo.enviar(self.socket, {
                'tipo': 'REGISTRAR_NOMBRE',
                'datos': {'nombre': nombre}
            })
            # Esperar hasta 2 segundos por la respuesta del servidor (20 x 0.1s)
            for _ in range(20):
                if self.nombre_registrado or self.ultimo_error or not self.conectado:
                    break
                time.sleep(0.1)

            if self.nombre_registrado:
                self.nombre = nombre
                print(f"{Colores.VERDE}[OK] Nombre cambiado a: {nombre}{Colores.RESET}")
            else:
                # Revertir si el cambio falló
                self.nombre_registrado = old_registrado
                if self.ultimo_error:
                    print(f"{Colores.ROJO}[!] {self.ultimo_error}{Colores.RESET}")
                else:
                    print(f"{Colores.ROJO}[!] No se pudo cambiar el nombre. Intenta de nuevo.{Colores.RESET}")
        else:
            print(f"{Colores.ROJO}[ERROR] El nombre debe tener entre 3 y 20 caracteres.{Colores.RESET}")
            
        print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
        while True:
            opc = input(f"➤ ").strip()
            if opc == "0":
                os.system("clear" if os.name == "posix" else "cls")
                return

    def solicitar_juegos(self):
        """Solicita la lista de juegos al servidor y permite crear una sala.

        Espera hasta 5 s la respuesta del servidor (evento de sincronización).
        Si el usuario elige un juego válido, envía CREAR_SALA y queda en
        espera hasta que la sala se confirme o la partida empiece.
        """
        os.system("clear" if os.name == "posix" else "cls")
        self.evento_respuesta.clear()
        Protocolo.enviar(self.socket, {"tipo": "LISTAR_JUEGOS"})
        if self.evento_respuesta.wait(5.0):
            self.mostrar_juegos(self.datos_recibidos)
            
        while True:
            juego_id = input(f"➤ Seleccionar juego o volver: ").strip()
            if juego_id == "0":
                os.system("clear" if os.name == "posix" else "cls")
                return
            elif juego_id.isdigit():
                self.ultimo_error = None
                self.sala_id = "ESPERANDO"
                Protocolo.enviar(self.socket, {"tipo": "CREAR_SALA", "datos": {"juego_id": int(juego_id)}})
                print(f"{Colores.AMARILLO}Creando sala...{Colores.RESET}")
                while self.sala_id == "ESPERANDO" and not self.ultimo_error and self.conectado:
                    time.sleep(0.1)
                
                # Si la partida ya inicio, salir al bucle de menu para que modo_partida() tome el control
                if self.en_partida:
                    return
                # Si hay error o sala no asignada, mostrar opcion de volver
                print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
                while True:
                    opc = input(f"➤ ").strip()
                    if opc == "0":
                        os.system("clear" if os.name == "posix" else "cls")
                        return

    def solicitar_salas(self):
        """Solicita la lista de salas disponibles al servidor.

        Espera hasta 5 s la respuesta. Permite al usuario ingresar un ID de
        sala para unirse; si la partida ya inició devuelve el control al
        bucle de menu_principal para que modo_partida() tome el control.
        """
        os.system("clear" if os.name == "posix" else "cls")
        self.evento_respuesta.clear()
        Protocolo.enviar(self.socket, {"tipo": "LISTAR_SALAS"})
        if self.evento_respuesta.wait(5.0):
            self.mostrar_salas(self.datos_recibidos)
            if not self.datos_recibidos:
                # mostrar_salas ya imprimio "No hay salas disponibles" + opcion 0
                while True:
                    opc = input(f"➤ ").strip()
                    if opc == "0":
                        os.system("clear" if os.name == "posix" else "cls")
                        return
        else:
            # Timeout: el servidor no respondio en 5 segundos
            print(f"\n{Colores.ROJO}[!] No se pudo obtener la lista de salas. Intenta de nuevo.{Colores.RESET}")
            print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
            while True:
                opc = input(f"➤ ").strip()
                if opc == "0":
                    os.system("clear" if os.name == "posix" else "cls")
                    return

        while True:
            sala_id = input(f"➤ ID de sala o volver: ").strip()
            if sala_id == "0":
                os.system("clear" if os.name == "posix" else "cls")
                return
            elif sala_id:
                self.ultimo_error = None
                self.sala_id = "ESPERANDO"
                Protocolo.enviar(self.socket, {"tipo": "UNIRSE_SALA", "datos": {"sala_id": sala_id}})
                print(f"{Colores.AMARILLO}Uniéndose a la sala...{Colores.RESET}")
                while self.sala_id == "ESPERANDO" and not self.ultimo_error and self.conectado:
                    time.sleep(0.1)

                # Si la partida ya inicio, salir para que modo_partida() tome el control
                if self.en_partida:
                    return
                print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
                while True:
                    opc = input(f"➤ ").strip()
                    if opc == "0":
                        os.system("clear" if os.name == "posix" else "cls")
                        return

    def crear_sala(self):
        """Flujo completo de creación de sala desde el menú principal.

        Muestra los juegos disponibles, solicita el ID de juego, envía
        CREAR_SALA y muestra la sala de espera. Un hilo secundario lee el
        input de cancelación (0+Enter) sin bloquear la detección de partida.
        """
        os.system("clear" if os.name == "posix" else "cls")
        self.evento_respuesta.clear()
        Protocolo.enviar(self.socket, {"tipo": "LISTAR_JUEGOS"})
        if self.evento_respuesta.wait(5.0):
            self.mostrar_juegos(self.datos_recibidos)

        while True:
            juego_id = input(f"➤ Número de juego o volver: ").strip()
            if juego_id == "0":
                os.system("clear" if os.name == "posix" else "cls")
                return
            elif juego_id.isdigit():
                self.ultimo_error = None
                self.sala_id = "ESPERANDO"
                Protocolo.enviar(self.socket, {"tipo": "CREAR_SALA", "datos": {"juego_id": int(juego_id)}})
                # Esperar confirmación del servidor
                while self.sala_id == "ESPERANDO" and not self.ultimo_error and self.conectado:
                    time.sleep(0.1)

                if self.ultimo_error or not self.sala_id:
                    # Error al crear sala
                    while True:
                        opc = input(f"➤ ").strip()
                        if opc == "0":
                            os.system("clear" if os.name == "posix" else "cls")
                            return
                    continue

                # Sala creada exitosamente — mostrar sala de espera
                os.system("clear" if os.name == "posix" else "cls")
                sala_actual = self.sala_id
                print(f"{Colores.BOLD}{Colores.HEADER}╔══════════════════════════════════════╗{Colores.RESET}")
                print(f"{Colores.BOLD}{Colores.HEADER}║         SALA CREADA                  ║{Colores.RESET}")
                print(f"{Colores.BOLD}{Colores.HEADER}╚══════════════════════════════════════╝{Colores.RESET}")
                print(f"\n  [ID] Sala: {Colores.VERDE}{sala_actual}{Colores.RESET}")
                print(f"\n  {Colores.AMARILLO}Esperando a otro jugador...{Colores.RESET}")
                print(f"\n  {Colores.ROJO}Presiona 0 + Enter para cancelar{Colores.RESET}\n")

                # Hilo separado para leer input sin bloquear la detección de en_partida
                cancelar = {"valor": False}
                def leer_cancelar():
                    try:
                        val = input("")
                        if val.strip() == "0":
                            cancelar["valor"] = True
                    except Exception:
                        pass

                import threading
                hilo_input = threading.Thread(target=leer_cancelar, daemon=True)
                hilo_input.start()

                while not self.en_partida and not cancelar["valor"] and self.conectado and not self.ultimo_error:
                    time.sleep(0.2)

                if cancelar["valor"]:
                    # Usuario canceló — notificar al servidor si es necesario
                    self.sala_id = None
                    os.system("clear" if os.name == "posix" else "cls")
                    return

                # Partida iniciada — salir; jugar_turno se encarga del flujo
                return

    def unirse_sala(self):
        """Flujo completo para unirse a una sala existente desde el menú.

        Solicita la lista de salas disponibles, muestra la lista y pide
        al usuario el ID de sala. Una vez enviado UNIRSE_SALA espera hasta
        que la sala sea aceptada o la partida inicie.
        """
        os.system("clear" if os.name == "posix" else "cls")
        self.evento_respuesta.clear()
        Protocolo.enviar(self.socket, {"tipo": "LISTAR_SALAS"})
        if self.evento_respuesta.wait(5.0):
            self.mostrar_salas(self.datos_recibidos)
            if not self.datos_recibidos:
                while True:
                    opc = input(f"➤ ").strip()
                    if opc == "0":
                        os.system("clear" if os.name == "posix" else "cls")
                        return
            
            while True:
                sala_id = input(f"➤ ID de sala o volver: ").strip()
                if sala_id == "0":
                    os.system("clear" if os.name == "posix" else "cls")
                    return
                elif sala_id:
                    self.ultimo_error = None
                    self.sala_id = "ESPERANDO"
                    Protocolo.enviar(self.socket, {"tipo": "UNIRSE_SALA", "datos": {"sala_id": sala_id}})
                    print(f"{Colores.AMARILLO}Uniéndose a la sala...{Colores.RESET}")
                    while self.sala_id == "ESPERANDO" and not self.ultimo_error and self.conectado:
                        time.sleep(0.1)
                        
                    # Si la partida ya inicio, salir para que modo_partida() tome el control
                    if self.en_partida:
                        return
                    print(f"\n{Colores.AMARILLO}0. Volver{Colores.RESET}\n")
                    while True:
                        opc = input(f"➤ ").strip()
                        if opc == "0":
                            os.system("clear" if os.name == "posix" else "cls")
                            return

    def solicitar_estadisticas(self):
        """Solicita las estadísticas globales al servidor y las muestra.

        Espera hasta 5 s la respuesta y delega la visualización a
        mostrar_estadisticas().
        """
        os.system("clear" if os.name == "posix" else "cls")
        self.evento_respuesta.clear()
        Protocolo.enviar(self.socket, {"tipo": "ESTADISTICAS"})
        if self.evento_respuesta.wait(5.0):
            self.mostrar_estadisticas(self.datos_recibidos)
            
        while True:
            opc = input(f"➤ ").strip()
            if opc == "0":
                os.system("clear" if os.name == "posix" else "cls")
                return




    def enviar_movimiento(self, movimiento):
        """Envía un movimiento al servidor con el contexto actual de sala y jugador.

        Args:
            movimiento: Cadena con la posición o columna elegida por el jugador.
        """
        if DEBUG:
            print(f"[DEBUG] Enviando movimiento: {movimiento} | sala={self.sala_id} | jugador={self.jugador_id}")
        if self.sala_id and self.jugador_id:
            Protocolo.enviar(
                self.socket,
                {
                    "tipo": "MOVIMIENTO",
                    "datos": {"movimiento": movimiento},
                    "sala_id": self.sala_id,
                    "jugador_id": self.jugador_id,
                },
            )

    def enviar_rendicion(self):
        """Envía la señal de rendición al servidor y marca la partida como terminada."""
        if self.sala_id:
            Protocolo.enviar(
                self.socket,
                {
                    "tipo": "RENDIRSE",
                    "sala_id": self.sala_id,
                    "jugador_id": self.jugador_id,
                },
            )
        self.en_partida = False

    def enviar_chat(self, mensaje):
        """Envía un mensaje de chat a la sala actual del jugador.

        Args:
            mensaje: Texto a enviar (puede incluir comandos como /stats).
        """
        if self.sala_id:
            Protocolo.enviar(
                self.socket,
                {
                    "tipo": "CHAT",
                    "datos": {"mensaje": mensaje},
                    "sala_id": self.sala_id,
                },
            )

    def modo_partida(self):
        """Bucle principal durante una partida. Maneja turnos y chat."""
        while self.en_partida and self.conectado:
            self.jugar_turno()
        # El hilo principal toma el control aquí: muestra el resultado final
        # de forma segura, sin condición de carrera con el input() de jugar_turno.
        self._mostrar_resultado_final()

    def _mostrar_resultado_final(self):
        """Muestra el resultado de la partida en el hilo principal (sin race condition)."""
        if not self.resultado_partida:
            return
        res = self.resultado_partida
        self.resultado_partida = None  # limpiar para la proxima partida

        os.system("clear" if os.name == "posix" else "cls")
        print(f"\n{Colores.BOLD}{'='*50}{Colores.RESET}")
        if res["es_ganador"]:
            print(f"{Colores.VERDE}  [VICTORIA]{Colores.RESET}")
        elif res["es_empate"]:
            print(f"{Colores.AMARILLO}  [EMPATE]{Colores.RESET}")
        else:
            print(f"{Colores.ROJO}  [DERROTA]{Colores.RESET}")
        print(f"{Colores.BOLD}{'='*50}{Colores.RESET}")
        print(f"\n{Colores.AMARILLO}Volviendo al menu en 3 segundos...{Colores.RESET}")
        time.sleep(3)

    def jugar_turno(self):
        """Captura una entrada del jugador durante su turno o mientras espera."""
        if not self.en_partida or not self.juego_actual:
            return

        mi_turno = self.juego_actual.get("turno") == self.jugador_id

        if mi_turno:
            # Es mi turno: input() bloqueante normal
            prompt = f"\n{Colores.VERDE}Tu movimiento (numero), 'rendirse' o 'C' para chat:{Colores.RESET} "
            try:
                entrada = input(prompt).strip()
            except Exception:
                return
            if not self.en_partida:
                return
        else:
            # No es mi turno: polling sin bloquear para detectar fin de partida automaticamente
            entrada = self._esperar_turno_rival()
            if entrada is None:
                return  # partida termino automaticamente

        # CRITICO: re-evaluar mi_turno (puede haber cambiado mientras esperabamos)
        mi_turno = self.juego_actual.get("turno") == self.jugador_id

        # --- Rendicion ---
        if entrada.lower() == "rendirse":
            self.enviar_rendicion()
            return

        # --- Chat ---
        if entrada.lower() == "c":
            try:
                msg = input(f"{Colores.CYAN}Mensaje (Enter para cancelar): {Colores.RESET}").strip()
            except Exception:
                return
            if msg.lower() == "/ayuda":
                self.historial_chat.append(
                    f"{Colores.AMARILLO}[SISTEMA] Comandos: /stats, /ayuda{Colores.RESET}"
                )
                if len(self.historial_chat) > 20:
                    self.historial_chat.pop(0)
            elif msg:
                self.enviar_chat(msg)
            # Refrescar tablero con el chat actualizado
            if self.juego_actual and self.en_partida:
                self.mostrar_tablero(self.juego_actual["tablero"])
                if mi_turno:
                    print(f"{Colores.VERDE}[TURNO] ES TU TURNO{Colores.RESET}")
                else:
                    print(f"{Colores.AMARILLO}[ESPERA] Esperando turno del rival...{Colores.RESET}")
            return

        # --- Movimiento (solo si es mi turno) ---
        if mi_turno:
            try:
                pos = int(entrada)              # Convertir a número
                self.esperando_actualizacion.clear()  # Preparar el evento antes de enviar
                self.enviar_movimiento(str(pos))
                # Bloquear hasta recibir la confirmación del servidor (máx 10 s)
                self.esperando_actualizacion.wait(timeout=10.0)
            except ValueError:
                if entrada:  # Evitar mostrar error si el usuario sólo presionó Enter
                    print(f"{Colores.ROJO}[ERROR] Ingresa un numero valido{Colores.RESET}")
        else:
            if entrada:
                print(f"{Colores.AMARILLO}Aun no es tu turno. Usa 'C' para chatear.{Colores.RESET}")

    def _esperar_turno_rival(self):
        """
        Espera el turno del rival sin bloquear el hilo principal.
        En Windows usa msvcrt para polling caracter a caracter, lo que permite
        detectar en_partida=False y salir automaticamente cuando termina la partida.
        Retorna la cadena introducida por el usuario, o None si la partida termino.
        """
        if os.name == "nt":
            import msvcrt
            prompt = f"\n{Colores.AMARILLO}Esperando al rival... ('C' chatear, 'rendirse' abandonar): {Colores.RESET}"
            print(prompt, end="", flush=True)
            buf = ""
            while self.en_partida and self.conectado:
                # Si ya es nuestro turno (el rival movio), salir sin consumir mas input
                if self.juego_actual and self.juego_actual.get("turno") == self.jugador_id:
                    print()
                    return ""
                if msvcrt.kbhit():
                    ch = msvcrt.getwche()
                    if ch in ("\r", "\n"):
                        print()
                        return buf.strip()
                    elif ch == "\x08":  # backspace
                        if buf:
                            buf = buf[:-1]
                            sys.stdout.write("\b \b")
                            sys.stdout.flush()
                    else:
                        buf += ch
                time.sleep(0.02)
            print()
            return None  # partida termino o desconectado
        else:
            # Fallback POSIX: input() bloqueante (el usuario debera presionar Enter)
            prompt = f"\n{Colores.AMARILLO}Esperando al rival... ('C' chatear, 'rendirse' abandonar): {Colores.RESET}"
            try:
                return input(prompt).strip()
            except Exception:
                return None



    def desconectar(self):
        """Cierra la conexión TCP con el servidor y detiene el hilo de escucha."""
        self.conectado = False
        if self.socket:
            self.socket.close()

    def registrar_nombre_obligatorio(self):
        """Muestra la pantalla de bienvenida y obliga al jugador a registrar un nombre.

        Repite la solicitud hasta que el servidor confirme el nombre o la
        conexión se interrumpa. El nombre debe tener entre 3 y 20 caracteres
        y no estar en uso por otro jugador activo en la sesión.
        """
        os.system("clear" if os.name == "posix" else "cls")
        print(f"{Colores.BOLD}{Colores.HEADER}")
        print("╔══════════════════════════════════════╗")
        print("║    CONSOLA DE JUEGOS MULTIJUGADOR    ║")
        print("╚══════════════════════════════════════╝")
        print(f"{Colores.RESET}")
        
        while not self.nombre_registrado and self.conectado:
            nombre = input(f"\n{Colores.VERDE}Ingresa tu nombre único (3-20 caracteres):{Colores.RESET} ").strip()
            if 3 <= len(nombre) <= 20:
                self.ultimo_error = None
                Protocolo.enviar(self.socket, {
                    'tipo': 'REGISTRAR_NOMBRE',
                    'datos': {'nombre': nombre}
                })
                # wait for response
                for _ in range(20):
                    if self.nombre_registrado or self.ultimo_error or not self.conectado:
                        break
                    time.sleep(0.1)
                
                if self.nombre_registrado:
                    self.nombre = nombre
                    print(f"\n{Colores.VERDE}[OK] Registrado exitosamente como {nombre}. Bienvenido.{Colores.RESET}")
                    time.sleep(1)
                    break
            else:
                print(f"{Colores.ROJO}[ERROR] El nombre debe tener entre 3 y 20 caracteres.{Colores.RESET}")

    def iniciar(self):
        """Punto de entrada principal del cliente.

        Establece la conexión, registra el nombre del jugador y arranca el
        bucle del menú principal. Si la conexión falla, termina sin lanzar
        excepción.
        """
        if not self.conectar():
            return

        self.registrar_nombre_obligatorio()
        if self.nombre_registrado:
            self.menu_principal()


if __name__ == "__main__":
    host = "localhost"
    puerto = 8888

    # Aceptar host y puerto como argumentos de línea de comandos
    if len(sys.argv) > 2:
        host = sys.argv[1]
        puerto = int(sys.argv[2])
    elif len(sys.argv) > 1:
        host = sys.argv[1]

    cliente = ClienteJuegos(host, puerto)

    try:
        cliente.iniciar()
    except KeyboardInterrupt:
        # El usuario presionó Ctrl+C: desconectar limpiamente
        print(f"\n{Colores.AMARILLO}[DESCONEXION] Hasta luego!{Colores.RESET}")
        cliente.desconectar()
