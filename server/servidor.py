# Módulo principal del servidor multijugador.
# Gestiona las conexiones TCP entrantes, el ciclo de vida de las salas de juego,
# el enrutamiento de mensajes por tipo (protocolo JSON sobre TCP) y las
# estadísticas de partida en memoria.
import socket
import threading
import uuid
import random
from datetime import datetime
import re
from utils.protocolo import Protocolo
from games.Triqui import Triqui
from games.conecta4 import Conecta4

# Cambia a True para ver trazas detalladas de movimientos en consola del servidor
DEBUG = False

# Puerto UDP usado para el descubrimiento automático de servidores en la LAN
PUERTO_BEACON = 8889


class SalaJuego:
    """Representa una sala de espera/juego con capacidad para 2 jugadores.

    Almacena los sockets y nombres de ambos jugadores, el estado de la sala
    (ESPERANDO → JUGANDO → TERMINADO) y la instancia del juego activo.
    """

    def __init__(self, juego_id, nombre_juego):
        self.id = str(uuid.uuid4())[:8]     # ID único de 8 chars para identificar la sala
        self.juego_id = juego_id
        self.nombre_juego = nombre_juego
        self.jugadores = {}                  # {jugador_id: {"socket": socket, "nombre": str}}
        self.estado = "ESPERANDO"            # Máquina de estados: ESPERANDO → JUGANDO → TERMINADO
        self.juego = None

        # Instanciar el juego concreto según el ID seleccionado por el creador
        if juego_id == "1":
            self.juego = Triqui()
        elif juego_id == "3":
            self.juego = Conecta4()

    def agregar_jugador(self, jugador_id, socket_cliente, nombre):
        """Registra un jugador en la sala si aún hay espacio.

        Cuando se alcanza el cupo de 2, transiciona el estado a JUGANDO e
        inicializa la lógica del juego con los IDs de ambos jugadores.

        Args:
            jugador_id: ID único del jugador (str UUID truncado).
            socket_cliente: Socket TCP del cliente.
            nombre: Nombre de pantalla del jugador.

        Returns:
            True si el jugador fue agregado exitosamente, False si la sala está llena.
        """
        if len(self.jugadores) < 2:
            self.jugadores[jugador_id] = {"socket": socket_cliente, "nombre": nombre}
            if len(self.jugadores) == 2:
                # Segunda conexión: arrancar el juego con ambos IDs
                self.estado = "JUGANDO"
                self.juego.iniciar(list(self.jugadores.keys()))
                print(f"[JUEGO] Sala {self.id} lista para jugar")
            return True
        return False

    def obtener_oponente(self, jugador_id):
        """Retorna el ID del jugador contrario al indicado.

        Args:
            jugador_id: ID del jugador de referencia.

        Returns:
            ID del oponente, o None si la sala tiene menos de 2 jugadores.
        """
        for jid in self.jugadores:
            if jid != jugador_id:
                return jid
        return None

    def broadcast(self, mensaje, excluir=None):
        """Envía un mensaje JSON a todos los jugadores de la sala.

        Los errores de envío se ignoran silenciosamente para no interrumpir
        la notificación al resto de jugadores (p.ej., si uno ya se desconectó).

        Args:
            mensaje: Dict serializable a JSON que se enviará.
            excluir: ID de jugador que debe omitirse del envío (opcional).
        """
        for jid, datos in self.jugadores.items():
            if excluir and jid == excluir:
                continue
            try:
                if datos["socket"]:
                    Protocolo.enviar(datos["socket"], mensaje)
            except Exception:
                pass  # Ignorar fallos individuales: el resto sí recibe el mensaje


class ServidorJuegos:
    """Servidor TCP multijugador que gestiona salas, partidas y estadísticas.

    Cada cliente que se conecta recibe un hilo dedicado (manejar_cliente).
    La comunicación se realiza mediante el protocolo de framing definido en
    utils.protocolo (cabecera de 4 bytes + payload JSON). El acceso a las
    estructuras compartidas (salas, jugadores, nombres_activos) se protege
    con un threading.Lock para evitar condiciones de carrera.
    """

    def __init__(self, host="0.0.0.0", puerto=8888):
        self.host = host
        self.puerto = puerto
        self.ip_local = self._obtener_ip_local()  # IP real de la interfaz de red activa
        # Socket TCP IPv4; SO_REUSEADDR permite reutilizar el puerto tras reinicio
        self.socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_servidor.bind((self.host, self.puerto))

        self.salas = {}            # {sala_id: SalaJuego}  — salas activas
        self.jugadores = {}        # {jugador_id: {"sala": sala_id, "socket": socket, "nombre": str}}
        self.nombres_activos = set()  # Nombres de pantalla registrados y en sesión
        self.lock = threading.Lock()  # Mutex para acceso concurrente a estructuras compartidas

        # Catálogo de juegos disponibles: clave = juego_id (str), valor = nombre legible
        self.juegos_disponibles = {
            "1": "Triqui (3 en linea)",
            "3": "Conecta 4"
        }

    @staticmethod
    def _obtener_ip_local():
        """Detecta la IP local real de la interfaz de red activa.

        Usa un socket UDP hacia 8.8.8.8 (sin enviar tráfico real) para forzar
        al SO a seleccionar la interfaz de red correcta y exponer su IP.
        En caso de error (sin red) devuelve '127.0.0.1' como fallback.

        Returns:
            Cadena con la dirección IPv4 de la interfaz activa (p.ej. '192.168.1.10').
        """
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))   # No envía datos; solo fuerza la selección de interfaz
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"


    def _asegurar_entrada(self, nombre):
        """Crea la entrada de estadísticas para un jugador si todavía no existe.

        Se llama antes de incrementar cualquier contador para garantizar que
        el dict del jugador siempre esté inicializado con todos los campos.

        Args:
            nombre: Nombre de pantalla del jugador (puede ser None, en cuyo caso no hace nada).
        """
        if nombre and nombre not in self.estadisticas:
            self.estadisticas[nombre] = {
                "jugadas": 0, "ganadas": 0, "perdidas": 0, "empates": 0
            }

    def registrar_estadisticas_partida(self, sala, ganador_id):
        """Actualiza las estadísticas en memoria al finalizar una partida.

        Incrementa 'jugadas' para ambos jugadores. Si hay ganador, incrementa
        'ganadas' para el ganador y 'perdidas' para el perdedor. En caso de
        empate (ganador_id=None), incrementa 'empates' para ambos.

        Args:
            sala: Instancia SalaJuego con los datos de los jugadores.
            ganador_id: ID del jugador ganador, o None en caso de empate.
        """
        jugador1_id, jugador2_id = list(sala.jugadores.keys())
        nombre1 = sala.jugadores[jugador1_id].get("nombre")
        nombre2 = sala.jugadores[jugador2_id].get("nombre")

        # Garantizar entrada y contabilizar jugada para ambos jugadores
        for nombre in [nombre1, nombre2]:
            if not nombre:
                continue
            self._asegurar_entrada(nombre)
            self.estadisticas[nombre]["jugadas"] += 1

        if ganador_id and ganador_id in sala.jugadores:
            ganador_nombre = sala.jugadores[ganador_id].get("nombre")
            perdedor_id = sala.obtener_oponente(ganador_id)
            perdedor_nombre = sala.jugadores[perdedor_id].get("nombre") if perdedor_id else None

            # Crear entrada si no existía (cubre jugadores que aún no tienen registro)
            self._asegurar_entrada(ganador_nombre)
            self._asegurar_entrada(perdedor_nombre)

            if ganador_nombre:
                self.estadisticas[ganador_nombre]["ganadas"] += 1
            if perdedor_nombre:
                self.estadisticas[perdedor_nombre]["perdidas"] += 1
        else:
            # Empate: sumar 1 a 'empates' de cada jugador
            for nombre in [nombre1, nombre2]:
                self._asegurar_entrada(nombre)
                if nombre:
                    self.estadisticas[nombre]["empates"] += 1

    def iniciar(self):
        """Inicia el servidor y entra en el bucle principal de aceptación de conexiones.

        Las estadísticas se inicializan aquí (en memoria): se reinician cada vez
        que el servidor arranca. Por cada cliente aceptado se lanza un hilo daemon
        que ejecuta manejar_cliente(); el daemon=True garantiza que los hilos no
        impidan el cierre del proceso principal. También se lanza el hilo de beacon
        UDP para el descubrimiento automático de servidores en la red local.
        """
        self.estadisticas = {}   # Estadísticas solo en memoria: se reinician con el servidor
        self.socket_servidor.listen(5)

        # ── Mostrar IP real para que los clientes sepan a dónde conectarse ──
        print("╔══════════════════════════════════════════════╗")
        print("║         SERVIDOR DE JUEGOS MULTIJUGADOR      ║")
        print("╚══════════════════════════════════════════════╝")
        print(f"[SERVER] Servidor en línea en la IP: {self.ip_local}")
        print(f"[SERVER] Puerto TCP : {self.puerto}")
        print(f"[SERVER] Puerto UDP : {PUERTO_BEACON}  (descubrimiento LAN)")
        print("[SERVER] Esperando conexiones...")
        print()

        # Hilo beacon UDP: responde automáticamente a los clientes que buscan servidor
        hilo_beacon = threading.Thread(target=self._beacon_udp, daemon=True)
        hilo_beacon.start()

        while True:
            cliente, direccion = self.socket_servidor.accept()
            print(f"[CONEXION] Nueva conexion desde {direccion}")
            # Hilo daemon: se cierra automáticamente si el proceso principal termina
            hilo = threading.Thread(target=self.manejar_cliente, args=(cliente, direccion))
            hilo.daemon = True
            hilo.start()

    def _beacon_udp(self):
        """Hilo daemon que responde solicitudes de descubrimiento UDP en la red local.

        Escucha en 0.0.0.0:PUERTO_BEACON paquetes con el texto 'DISCOVER_SERVER'.
        Por cada solicitud responde con 'SERVER_RESPONSE:<ip>:<puerto>' al emisor.
        Esto permite que los clientes encuentren el servidor automáticamente sin
        necesidad de conocer su IP de antemano.
        """
        try:
            sock_udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock_udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock_udp.bind(("0.0.0.0", PUERTO_BEACON))
            print(f"[BEACON] Beacon UDP activo en puerto {PUERTO_BEACON}")
            while True:
                try:
                    datos, addr = sock_udp.recvfrom(1024)
                    if datos.decode("utf-8", errors="ignore").strip() == "DISCOVER_SERVER":
                        respuesta = f"SERVER_RESPONSE:{self.ip_local}:{self.puerto}"
                        sock_udp.sendto(respuesta.encode("utf-8"), addr)
                        if DEBUG:
                            print(f"[BEACON] Discovery respondido a {addr}")
                except Exception:
                    pass  # Ignorar paquetes malformados sin detener el beacon
        except Exception as e:
            print(f"[BEACON] Error iniciando beacon UDP: {e}")
            print("[BEACON] El descubrimiento automatico no estara disponible.")

    def manejar_cliente(self, socket_cliente, direccion):
        """Bucle de recepción y enrutamiento de mensajes para un cliente.

        Se ejecuta en un hilo dedicado por cliente. Recibe mensajes del protocolo,
        los despacha al manejador correspondiente según su campo 'tipo' y, al
        terminar (error o desconexión), llama a desconectar_jugador() para limpiar
        las estructuras compartidas.

        Args:
            socket_cliente: Socket TCP del cliente conectado.
            direccion: Tupla (host, puerto) del cliente (para logs).
        """
        jugador_id = str(uuid.uuid4())[:8]
        print(f"[ID] Jugador {jugador_id} conectado desde {direccion}")

        try:
            while True:
                # Esperar el siguiente mensaje del cliente (bloqueante)
                mensaje = Protocolo.recibir(socket_cliente)
                if not mensaje:
                    break  # El cliente se desconectó

                tipo = mensaje.get("tipo", "")
                print(f"[MENSAJE] [{jugador_id}] {tipo}")

                if tipo == "REGISTRAR_NOMBRE":
                    nombre = mensaje["datos"]["nombre"]
                    with self.lock:  # Proteger acceso a nombres_activos
                        if nombre in self.nombres_activos:
                            # El nombre ya lo usa otro jugador conectado
                            Protocolo.enviar(socket_cliente, {
                                "tipo": "ERROR",
                                "datos": {"mensaje": "Nombre ya en uso. Elige otro."}
                            })
                        else:
                            if jugador_id in self.jugadores and self.jugadores[jugador_id].get("nombre"):
                                # El jugador ya tenía nombre: actualizar y liberar el anterior
                                old_name = self.jugadores[jugador_id]["nombre"]
                                if old_name in self.nombres_activos:
                                    self.nombres_activos.remove(old_name)
                                self.jugadores[jugador_id]["nombre"] = nombre

                                # Transferir estadísticas del nombre anterior al nuevo
                                if old_name in self.estadisticas:
                                    old_stats = self.estadisticas.pop(old_name)
                                    if nombre in self.estadisticas:
                                        # El nombre nuevo ya tenía stats: sumar campo a campo
                                        for campo in ("jugadas", "ganadas", "perdidas", "empates"):
                                            self.estadisticas[nombre][campo] = (
                                                self.estadisticas[nombre].get(campo, 0)
                                                + old_stats.get(campo, 0)
                                            )
                                    else:
                                        # Sin historial previo: mover el registro directamente
                                        self.estadisticas[nombre] = old_stats
                            else:
                                # Primera vez que este jugador registra un nombre
                                self.jugadores[jugador_id] = {
                                    "sala": None, "socket": socket_cliente, "nombre": nombre
                                }
                            self.nombres_activos.add(nombre)
                            Protocolo.enviar(socket_cliente, {"tipo": "REGISTRO_EXITOSO"})

                elif tipo == "LISTAR_JUEGOS":
                    self.enviar_lista_juegos(socket_cliente)

                elif tipo == "CREAR_SALA":
                    self.crear_sala(socket_cliente, jugador_id, mensaje["datos"])

                elif tipo == "UNIRSE_SALA":
                    self.unirse_sala(socket_cliente, jugador_id, mensaje["datos"])

                elif tipo == "LISTAR_SALAS":
                    self.enviar_lista_salas(socket_cliente)

                elif tipo == "MOVIMIENTO":
                    if DEBUG:
                        print(f"[DEBUG] Movimiento recibido de {jugador_id}: {mensaje.get('datos', {})}")
                    self.procesar_movimiento(jugador_id, mensaje)

                elif tipo == "RENDIRSE":
                    self.rendirse(jugador_id)

                elif tipo == "ESTADISTICAS":
                    self.enviar_estadisticas(socket_cliente)

                elif tipo == "CHAT":
                    self.enviar_chat(jugador_id, mensaje["datos"]["mensaje"])

        except Exception as e:
            print(f"[ERROR] Error con jugador {jugador_id}: {e}")
        finally:
            # Limpiar la sesión del jugador pase lo que pase
            self.desconectar_jugador(jugador_id)
            try:
                socket_cliente.close()
            except Exception:
                pass

    def enviar_lista_juegos(self, socket_cliente):
        """Envía el catálogo de juegos disponibles al cliente que lo solicitó."""
        Protocolo.enviar(socket_cliente, {
            "tipo": "LISTA_JUEGOS",
            "datos": self.juegos_disponibles
        })

    def crear_sala(self, socket_cliente, jugador_id, datos):
        """Crea una nueva sala de juego y añade al jugador como primer participante.

        Valida que el juego_id sea un número conocido. La normalización a str(int())
        es necesaria porque JSON puede transmitirlo como int o str según el cliente.

        Args:
            socket_cliente: Socket del cliente que crea la sala.
            jugador_id: ID del jugador creador.
            datos: Dict con 'juego_id' (int o str).
        """
        with self.lock:
            # Normalizar a str: JSON convierte claves a str, y el cliente puede
            # enviar int o str segun el camino de codigo. str(int()) valida que
            # sea un numero y lo deja como str consistente con juegos_disponibles.
            try:
                juego_id = str(int(datos["juego_id"]))
            except (ValueError, TypeError):
                Protocolo.enviar(socket_cliente, {
                    "tipo": "ERROR",
                    "datos": {"mensaje": "juego_id invalido"}
                })
                return
            nombre_jugador = self.jugadores.get(jugador_id, {}).get("nombre", f"Jugador_{jugador_id[:4]}")

            if juego_id not in self.juegos_disponibles:
                Protocolo.enviar(socket_cliente, {
                    "tipo": "ERROR",
                    "datos": {"mensaje": "Juego no valido"}
                })
                return

            sala = SalaJuego(juego_id, self.juegos_disponibles[juego_id])
            self.salas[sala.id] = sala

            if sala.agregar_jugador(jugador_id, socket_cliente, nombre_jugador):
                self.jugadores[jugador_id] = {
                    "sala": sala.id, "socket": socket_cliente, "nombre": nombre_jugador
                }
                Protocolo.enviar(socket_cliente, {
                    "tipo": "SALA_CREADA",
                    "datos": {
                        "sala_id": sala.id,
                        "juego": sala.nombre_juego,
                        "estado": sala.estado
                    }
                })
                print(f"[JUEGO] Sala {sala.id} creada por {nombre_jugador}")

    def unirse_sala(self, socket_cliente, jugador_id, datos):
        """Une a un jugador a una sala existente en estado ESPERANDO.

        Si la sala completa su cupo (2 jugadores), llama a iniciar_partida().
        En caso de error (sala no encontrada o llena), notifica al cliente.

        Args:
            socket_cliente: Socket del cliente que se une.
            jugador_id: ID del jugador que solicita unirse.
            datos: Dict con 'sala_id' de la sala destino.
        """
        with self.lock:
            sala_id = datos["sala_id"]
            nombre_jugador = self.jugadores.get(jugador_id, {}).get("nombre", f"Jugador_{jugador_id[:4]}")

            if sala_id not in self.salas:
                Protocolo.enviar(socket_cliente, {
                    "tipo": "ERROR",
                    "datos": {"mensaje": "Sala no encontrada"}
                })
                return

            sala = self.salas[sala_id]

            if sala.agregar_jugador(jugador_id, socket_cliente, nombre_jugador):
                self.jugadores[jugador_id] = {
                    "sala": sala.id, "socket": socket_cliente, "nombre": nombre_jugador
                }

                nombres_seguros = {
                    jid: info["nombre"] or "Jugador"
                    for jid, info in sala.jugadores.items()
                }

                Protocolo.enviar(socket_cliente, {
                    "tipo": "UNIDO_SALA",
                    "datos": {
                        "sala_id": sala.id,
                        "juego": sala.nombre_juego,
                        "estado": sala.estado,
                        "jugadores": list(sala.jugadores.keys()),
                        "nombres": nombres_seguros
                    }
                })

                if sala.estado == "JUGANDO":
                    self.iniciar_partida(sala)
            else:
                Protocolo.enviar(socket_cliente, {
                    "tipo": "ERROR",
                    "datos": {"mensaje": "Sala llena o no disponible"}
                })

    def iniciar_partida(self, sala):
        """Inicia la partida y notifica a los jugadores"""
        # El turno inicial ya fue establecido por sala.juego.iniciar():
        # Triqui → jugadores_ids[0] recibe X y empieza primero.
        # Conecta4 → jugadores_ids[0] recibe R y empieza primero.
        turno = sala.juego.turno
        print(f"[INICIO] Partida en sala {sala.id}. Primer turno: {turno}")

        for jid, datos in sala.jugadores.items():
            rival_id = sala.obtener_oponente(jid)
            rival_nombre = sala.jugadores[rival_id]["nombre"] if rival_id else "Rival"
            Protocolo.enviar(datos["socket"], {
                "tipo": "PARTIDA_INICIADA",
                "datos": {
                    "tu_jugador_id": jid,
                    "rival_id": rival_id,
                    "rival_nombre": rival_nombre,
                    "turno": turno,
                    "tablero": sala.juego.obtener_vista(jid)
                }
            })

    def procesar_movimiento(self, jugador_id, mensaje):
        """Valida el turno y delega el movimiento al juego; luego notifica a ambos jugadores."""
        # Ignorar si el jugador no está registrado en el servidor
        if jugador_id not in self.jugadores:
            if DEBUG:
                print(f"[DEBUG] procesar_movimiento: jugador {jugador_id} no encontrado")
            return

        # Obtener la sala donde está jugando este jugador
        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id) if sala_id else None

        # Solo procesar si la sala existe y la partida está en curso
        if not sala or sala.estado != "JUGANDO":
            if DEBUG:
                print(f"[DEBUG] procesar_movimiento: sala invalida o no jugando (sala={sala_id}, estado={sala.estado if sala else 'N/A'})")
            return

        # Rechazar el movimiento si no es el turno de este jugador
        if sala.juego.turno != jugador_id:
            if DEBUG:
                print(f"[DEBUG] No es turno de {jugador_id}, turno actual={sala.juego.turno}")
            Protocolo.enviar(self.jugadores[jugador_id]["socket"], {
                "tipo": "ERROR",
                "datos": {"mensaje": "No es tu turno"}
            })
            return

        movimiento = mensaje["datos"]["movimiento"]
        if DEBUG:
            print(f"[DEBUG] Procesando movimiento '{movimiento}' de {jugador_id} en sala {sala_id}")

        # Pasar el movimiento al juego para que lo valide y lo aplique
        valido, resultado = sala.juego.procesar_movimiento(jugador_id, movimiento)
        if DEBUG:
            print(f"[DEBUG] Resultado: valido={valido}, resultado={resultado}")

        if valido:
            if resultado.get("terminado"):
                # La partida terminó: notificar a ambos jugadores y limpiar la sala
                sala.estado = "TERMINADO"
                ganador = resultado.get("ganador")
                print(f"[TERMINADO] Sala {sala.id}. Ganador: {ganador}")
                self.registrar_estadisticas_partida(sala, ganador)
                sala.broadcast({
                    "tipo": "JUEGO_TERMINADO",
                    "datos": {
                        "ganador": ganador,
                        "razon": resultado.get("razon", ""),
                        "tablero_final": sala.juego.obtener_vista_publica()
                    }
                })
                # Limpiar sala de memoria una vez notificados ambos jugadores
                self._terminar_sala(sala_id)
            else:
                # La partida continúa: enviar el tablero actualizado a cada jugador
                for jid in sala.jugadores:
                    print(f"[MENSAJE] Enviando ACTUALIZACION a {jid}")
                    Protocolo.enviar(sala.jugadores[jid]["socket"], {
                        "tipo": "ACTUALIZACION",
                        "datos": {
                            "tablero": sala.juego.obtener_vista(jid),
                            "turno": sala.juego.turno,
                            "ultimo_movimiento": {
                                "jugador": jugador_id,
                                "movimiento": movimiento,
                                "resultado": resultado
                            }
                        }
                    })
        else:
            # Movimiento inválido: notificar solo al jugador que lo envió
            print(f"[ERROR] Movimiento invalido de {jugador_id}: {movimiento} - {resultado.get('error', '')}")
            Protocolo.enviar(self.jugadores[jugador_id]["socket"], {
                "tipo": "ERROR",
                "datos": {"mensaje": resultado.get("error", "Movimiento invalido")}
            })

    def enviar_lista_salas(self, socket_cliente):
        """Envía solo las salas que aún esperan un segundo jugador."""
        salas_disponibles = {}
        with self.lock:
            for sala_id, sala in self.salas.items():
                # Solo incluir salas en espera con exactamente 1 jugador
                if sala.estado == "ESPERANDO" and len(sala.jugadores) == 1:
                    creador = list(sala.jugadores.values())[0]["nombre"] or "Desconocido"
                    salas_disponibles[sala_id] = {
                        "juego": sala.nombre_juego,
                        "jugadores": len(sala.jugadores),
                        "creador": creador
                    }

        Protocolo.enviar(socket_cliente, {
            "tipo": "LISTA_SALAS",
            "datos": salas_disponibles
        })

    def enviar_chat(self, jugador_id, mensaje):
        """Procesa y retransmite un mensaje de chat dentro de la sala del jugador.

        Aplica un truncado a 200 caracteres y un filtro básico de palabras ofensivas.
        Si el mensaje empieza con '/stats', responde con las estadísticas del rival
        en lugar de hacer broadcast a la sala.

        Args:
            jugador_id: ID del jugador que envía el mensaje.
            mensaje: Texto del mensaje (puede ser un comando /stats).
        """
        # Ignorar mensajes de jugadores no registrados
        if jugador_id not in self.jugadores:
            return

        # Limitar la longitud del mensaje para evitar spam
        mensaje = mensaje[:200]
        # Filtrar palabras ofensivas reemplazándolas por ***
        ofensivas = ["palabra1", "palabra2"]
        for bad in ofensivas:
            mensaje = re.sub(f"(?i){bad}", "***", mensaje)

        # Si el mensaje es el comando /stats, responder con estadísticas del rival
        if mensaje.startswith("/stats"):
            sala_id = self.jugadores[jugador_id].get("sala")
            if sala_id:
                sala = self.salas.get(sala_id)
                if sala:
                    oponente = sala.obtener_oponente(jugador_id)
                    if oponente:
                        nombre_op = self.jugadores[oponente].get("nombre")
                        stats_op = self.estadisticas.get(nombre_op, {})
                        v = stats_op.get("ganadas", 0)
                        p = stats_op.get("jugadas", 0)
                        pct = (v / p * 100) if p > 0 else 0  # Porcentaje de victorias
                        stats_str = f"[ESTADISTICAS] {nombre_op}: Partidas: {p} | Victorias: {v} | %: {pct:.1f}%"
                        Protocolo.enviar(self.jugadores[jugador_id]["socket"], {
                            "tipo": "STATS_RESPONSE",
                            "datos": {"mensaje": stats_str}
                        })
            return  # No hacer broadcast del comando

        # Mensaje normal: enviarlo a todos los jugadores de la sala
        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id)

        if sala:
            nombre = self.jugadores[jugador_id].get("nombre", "Jugador")
            timestamp = datetime.now().strftime("%H:%M:%S")  # Hora del mensaje
            sala.broadcast({
                "tipo": "CHAT",
                "datos": {
                    "jugador": nombre,
                    "mensaje": mensaje,
                    "timestamp": timestamp
                }
            })

    def enviar_estadisticas(self, socket_cliente):
        """Envia las estadisticas globales al cliente"""
        Protocolo.enviar(socket_cliente, {
            "tipo": "ESTADISTICAS_REPORTE",
            "datos": self.estadisticas
        })

    def rendirse(self, jugador_id):
        """Procesa la rendición: el oponente gana automáticamente."""
        if jugador_id not in self.jugadores:
            return

        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id)

        if sala and sala.estado == "JUGANDO":
            sala.estado = "TERMINADO"
            # El ganador es el jugador que NO se rindió
            ganador = sala.obtener_oponente(jugador_id)
            print(f"[RENDICION] Jugador {jugador_id} se rindio en sala {sala.id}")
            self.registrar_estadisticas_partida(sala, ganador)
            # Notificar a ambos jugadores el resultado
            sala.broadcast({
                "tipo": "JUEGO_TERMINADO",
                "datos": {
                    "ganador": ganador,
                    "razon": "rendicion",
                    "jugador_rendido": jugador_id
                }
            })
            # Limpiar sala de memoria una vez notificados ambos jugadores
            self._terminar_sala(sala_id)

    def _terminar_sala(self, sala_id):
        """Elimina una sala terminada de self.salas y desvincula a sus jugadores.
        Permite que ambos jugadores puedan crear o unirse a nuevas salas.
        """
        with self.lock:
            sala = self.salas.get(sala_id)
            if not sala:
                return  # ya fue eliminada (p.ej. por desconexion)
            for jid in sala.jugadores:
                if jid in self.jugadores:
                    self.jugadores[jid]["sala"] = None
            del self.salas[sala_id]
            print(f"[LIMPIEZA] Sala {sala_id} eliminada tras fin de partida")

    def desconectar_jugador(self, jugador_id):
        """Elimina al jugador del servidor y avisa a su oponente si había partida en curso."""
        with self.lock:
            if jugador_id not in self.jugadores:
                return

            sala_id = self.jugadores[jugador_id].get("sala")
            nombre = self.jugadores[jugador_id].get("nombre")
            print(f"[DESCONEXION] Jugador {jugador_id} desconectado")

            # Liberar el nombre para que otro jugador pueda usarlo
            if nombre:
                if nombre in self.nombres_activos:
                    self.nombres_activos.remove(nombre)

            if sala_id and sala_id in self.salas:
                sala = self.salas[sala_id]
                oponente = sala.obtener_oponente(jugador_id)
                if oponente and oponente in self.jugadores:
                    # Desvincular al oponente de la sala para que pueda unirse a otra
                    self.jugadores[oponente]["sala"] = None
                    try:
                        # Notificar al oponente que el rival se fue
                        Protocolo.enviar(self.jugadores[oponente]["socket"], {
                            "tipo": "JUGADOR_DESCONECTADO",
                            "datos": {"jugador_id": jugador_id}
                        })
                    except Exception:
                        pass

                # Eliminar la sala del registro activo
                del self.salas[sala_id]
                print(f"[ELIMINADO] Sala {sala_id} eliminada")

            # Eliminar al jugador del registro del servidor
            del self.jugadores[jugador_id]


if __name__ == "__main__":
    servidor = ServidorJuegos()
    servidor.iniciar()
