# Clase base que deben extender todos los juegos del servidor.
# Define la estructura mínima que cada juego tiene que implementar.
class JuegoBase:
    """Interfaz común para todos los juegos (Triqui, Conecta 4, etc.)."""

    def __init__(self):
        self.turno    = None         # ID del jugador que debe mover ahora
        self.estado   = "ESPERANDO" # Estado actual: ESPERANDO → JUGANDO → TERMINADO
        self.jugadores = []          # Lista con los IDs de los dos jugadores
        self.ganador  = None         # ID del jugador ganador (None si no terminó o hubo empate)

    def iniciar(self, jugadores_ids):
        """Arranca la partida cuando los dos jugadores ya están conectados."""
        self.jugadores = jugadores_ids  # Guardar los IDs de ambos jugadores
        self.estado = "JUGANDO"          # Cambiar estado para permitir movimientos

    def procesar_movimiento(self, jugador_id, movimiento):
        """Valida y aplica un movimiento. Cada juego debe implementar este método."""
        raise NotImplementedError  # Obliga a que los juegos hijos lo definan

    def obtener_vista(self, jugador_id):
        """Devuelve el estado del tablero adaptado para un jugador específico."""
        raise NotImplementedError  # Cada juego decide qué información enviar

    def obtener_vista_publica(self):
        """Devuelve el tablero final que se muestra a ambos jugadores al terminar."""
        raise NotImplementedError  # Cada juego decide el formato del resultado final
