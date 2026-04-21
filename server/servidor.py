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


class SalaJuego:
    """Representa una sala de juego con 2 jugadores"""

    def __init__(self, juego_id, nombre_juego):
        self.id = str(uuid.uuid4())[:8]
        self.juego_id = juego_id
        self.nombre_juego = nombre_juego
        self.jugadores = {}  # {id: {"socket": socket, "nombre": nombre}}
        self.estado = "ESPERANDO"  # ESPERANDO, JUGANDO, TERMINADO
        self.juego = None

        if juego_id == "1":
            self.juego = Triqui()
        elif juego_id == "3":
            self.juego = Conecta4()

    def agregar_jugador(self, jugador_id, socket_cliente, nombre):
        if len(self.jugadores) < 2:
            self.jugadores[jugador_id] = {"socket": socket_cliente, "nombre": nombre}
            if len(self.jugadores) == 2:
                self.estado = "JUGANDO"
                self.juego.iniciar(list(self.jugadores.keys()))
                print(f"[JUEGO] Sala {self.id} lista para jugar")
            return True
        return False

    def obtener_oponente(self, jugador_id):
        for jid in self.jugadores:
            if jid != jugador_id:
                return jid
        return None

    def broadcast(self, mensaje, excluir=None):
        """Envía un mensaje a todos los jugadores de la sala"""
        for jid, datos in self.jugadores.items():
            if excluir and jid == excluir:
                continue
            try:
                if datos["socket"]:
                    Protocolo.enviar(datos["socket"], mensaje)
            except Exception:
                pass


class ServidorJuegos:

    def __init__(self, host="0.0.0.0", puerto=8888):
        self.host = host
        self.puerto = puerto
        self.socket_servidor = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket_servidor.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket_servidor.bind((self.host, self.puerto))

        self.salas = {}       # {sala_id: SalaJuego}
        self.jugadores = {}   # {jugador_id: {"sala": sala_id, "socket": socket}}
        self.nombres_activos = set()
        self.lock = threading.Lock()

        self.juegos_disponibles = {
            "1": "Triqui (3 en linea)",
            "3": "Conecta 4"
        }


    def _asegurar_entrada(self, nombre):
        """Crea la entrada de estadisticas para un jugador si todavia no existe."""
        if nombre and nombre not in self.estadisticas:
            self.estadisticas[nombre] = {
                "jugadas": 0, "ganadas": 0, "perdidas": 0, "empates": 0
            }

    def registrar_estadisticas_partida(self, sala, ganador_id):
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

            # Crear entrada si no existia (cubre jugadores sin nombre en el dict aun)
            self._asegurar_entrada(ganador_nombre)
            self._asegurar_entrada(perdedor_nombre)

            if ganador_nombre:
                self.estadisticas[ganador_nombre]["ganadas"] += 1
            if perdedor_nombre:
                self.estadisticas[perdedor_nombre]["perdidas"] += 1
        else:
            # Empate
            for nombre in [nombre1, nombre2]:
                self._asegurar_entrada(nombre)
                if nombre:
                    self.estadisticas[nombre]["empates"] += 1

    def iniciar(self):
        self.estadisticas = {}  # estadisticas solo en memoria, se reinician con el servidor
        self.socket_servidor.listen(5)
        print(f"[SERVER] Servidor iniciado en {self.host}:{self.puerto}")
        print("[SERVER] Esperando conexiones...")

        while True:
            cliente, direccion = self.socket_servidor.accept()
            print(f"[CONEXION] Nueva conexion desde {direccion}")
            hilo = threading.Thread(target=self.manejar_cliente, args=(cliente, direccion))
            hilo.daemon = True
            hilo.start()

    def manejar_cliente(self, socket_cliente, direccion):
        """Maneja la comunicacion con un cliente"""
        jugador_id = str(uuid.uuid4())[:8]
        print(f"[ID] Jugador {jugador_id} conectado desde {direccion}")

        try:
            while True:
                mensaje = Protocolo.recibir(socket_cliente)
                if not mensaje:
                    break

                tipo = mensaje.get("tipo", "")
                print(f"[MENSAJE] [{jugador_id}] {tipo}")

                if tipo == "REGISTRAR_NOMBRE":
                    nombre = mensaje["datos"]["nombre"]
                    with self.lock:
                        if nombre in self.nombres_activos:
                            Protocolo.enviar(socket_cliente, {
                                "tipo": "ERROR",
                                "datos": {"mensaje": "Nombre ya en uso. Elige otro."}
                            })
                        else:
                            if jugador_id in self.jugadores and self.jugadores[jugador_id].get("nombre"):
                                old_name = self.jugadores[jugador_id]["nombre"]
                                if old_name in self.nombres_activos:
                                    self.nombres_activos.remove(old_name)
                                self.jugadores[jugador_id]["nombre"] = nombre

                                # Transferir estadisticas del nombre anterior al nuevo
                                if old_name in self.estadisticas:
                                    old_stats = self.estadisticas.pop(old_name)
                                    if nombre in self.estadisticas:
                                        # El nombre nuevo ya tenia stats: sumar campo a campo
                                        for campo in ("jugadas", "ganadas", "perdidas", "empates"):
                                            self.estadisticas[nombre][campo] = (
                                                self.estadisticas[nombre].get(campo, 0)
                                                + old_stats.get(campo, 0)
                                            )
                                    else:
                                        # Sin historial previo: mover directamente
                                        self.estadisticas[nombre] = old_stats
                            else:
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
            self.desconectar_jugador(jugador_id)
            try:
                socket_cliente.close()
            except Exception:
                pass

    def enviar_lista_juegos(self, socket_cliente):
        Protocolo.enviar(socket_cliente, {
            "tipo": "LISTA_JUEGOS",
            "datos": self.juegos_disponibles
        })

    def crear_sala(self, socket_cliente, jugador_id, datos):
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
        """Procesa un movimiento de un jugador"""
        if jugador_id not in self.jugadores:
            if DEBUG:
                print(f"[DEBUG] procesar_movimiento: jugador {jugador_id} no encontrado")
            return

        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id) if sala_id else None

        if not sala or sala.estado != "JUGANDO":
            if DEBUG:
                print(f"[DEBUG] procesar_movimiento: sala invalida o no jugando (sala={sala_id}, estado={sala.estado if sala else 'N/A'})")
            return

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
        valido, resultado = sala.juego.procesar_movimiento(jugador_id, movimiento)
        if DEBUG:
            print(f"[DEBUG] Resultado: valido={valido}, resultado={resultado}")

        if valido:
            if resultado.get("terminado"):
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
            print(f"[ERROR] Movimiento invalido de {jugador_id}: {movimiento} - {resultado.get('error', '')}")
            Protocolo.enviar(self.jugadores[jugador_id]["socket"], {
                "tipo": "ERROR",
                "datos": {"mensaje": resultado.get("error", "Movimiento invalido")}
            })

    def enviar_lista_salas(self, socket_cliente):
        """Envia la lista de salas disponibles"""
        salas_disponibles = {}
        with self.lock:
            for sala_id, sala in self.salas.items():
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
        """Envia un mensaje de chat a la sala"""
        if jugador_id not in self.jugadores:
            return

        mensaje = mensaje[:200]
        ofensivas = ["palabra1", "palabra2"]
        for bad in ofensivas:
            mensaje = re.sub(f"(?i){bad}", "***", mensaje)

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
                        pct = (v / p * 100) if p > 0 else 0
                        stats_str = f"[ESTADISTICAS] {nombre_op}: Partidas: {p} | Victorias: {v} | %: {pct:.1f}%"
                        Protocolo.enviar(self.jugadores[jugador_id]["socket"], {
                            "tipo": "STATS_RESPONSE",
                            "datos": {"mensaje": stats_str}
                        })
            return

        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id)

        if sala:
            nombre = self.jugadores[jugador_id].get("nombre", "Jugador")
            timestamp = datetime.now().strftime("%H:%M:%S")
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
        """Jugador se rinde"""
        if jugador_id not in self.jugadores:
            return

        sala_id = self.jugadores[jugador_id].get("sala")
        sala = self.salas.get(sala_id)

        if sala and sala.estado == "JUGANDO":
            sala.estado = "TERMINADO"
            ganador = sala.obtener_oponente(jugador_id)
            print(f"[RENDICION] Jugador {jugador_id} se rindio en sala {sala.id}")
            self.registrar_estadisticas_partida(sala, ganador)
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
        """Limpia cuando un jugador se desconecta"""
        with self.lock:
            if jugador_id not in self.jugadores:
                return

            sala_id = self.jugadores[jugador_id].get("sala")
            nombre = self.jugadores[jugador_id].get("nombre")
            print(f"[DESCONEXION] Jugador {jugador_id} desconectado")

            if nombre:
                if nombre in self.nombres_activos:
                    self.nombres_activos.remove(nombre)

            if sala_id and sala_id in self.salas:
                sala = self.salas[sala_id]
                oponente = sala.obtener_oponente(jugador_id)
                if oponente and oponente in self.jugadores:
                    self.jugadores[oponente]["sala"] = None
                    try:
                        Protocolo.enviar(self.jugadores[oponente]["socket"], {
                            "tipo": "JUGADOR_DESCONECTADO",
                            "datos": {"jugador_id": jugador_id}
                        })
                    except Exception:
                        pass

                del self.salas[sala_id]
                print(f"[ELIMINADO] Sala {sala_id} eliminada")

            del self.jugadores[jugador_id]


if __name__ == "__main__":
    servidor = ServidorJuegos()
    servidor.iniciar()
