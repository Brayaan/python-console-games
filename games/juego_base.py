# Contrato (interfaz abstracta) que deben implementar todos los juegos del servidor
class JuegoBase:

    def __init__(self):
        self.turno  = None         # ID del jugador con el turno actual (estado compartido entre hilos)
        self.estado = "ESPERANDO"  # maquina de estados: ESPERANDO → JUGANDO → TERMINADO
        self.jugadores = []        # lista de IDs asignados por el servidor al conectarse
        self.ganador = None

    def iniciar(self, jugadores_ids):
        # Transicion de estado al unirse el segundo jugador; llamado desde el hilo del servidor
        self.jugadores = jugadores_ids
        self.estado = "JUGANDO"

    def procesar_movimiento(self, jugador_id, movimiento):
        # Retorna (valido: bool, resultado: dict); debe ser implementado por cada juego
        raise NotImplementedError

    def obtener_vista(self, jugador_id):
        # Vista personalizada por jugador; se serializa a JSON y se envia por socket
        raise NotImplementedError

    def obtener_vista_publica(self):
        # Vista final compartida; se transmite a ambos jugadores al terminar la partida
        raise NotImplementedError
