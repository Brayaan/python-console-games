# Juego de Triqui (Tres en Línea) para el servidor multijugador.
from .juego_base import JuegoBase


class Triqui(JuegoBase):
    """Gestiona una partida de Triqui entre dos jugadores."""

    def __init__(self):
        super().__init__()
        self.tablero = [" "] * 9   # 9 casillas vacías (cuadrícula 3x3)
        self.simbolos = {}          # Guarda qué símbolo usa cada jugador

    def iniciar(self, jugadores_ids):
        """Asigna símbolos y define quién empieza."""
        super().iniciar(jugadores_ids)
        # El primer jugador usa X, el segundo usa O
        self.simbolos = {jugadores_ids[0]: "X", jugadores_ids[1]: "O"}
        self.turno = jugadores_ids[0]  # X siempre empieza

    def procesar_movimiento(self, jugador_id, movimiento):
        """Valida y aplica la jugada; retorna (válido, resultado)."""
        print(f"[DEBUG] Triqui.procesar_movimiento: jugador={jugador_id}, movimiento={movimiento}")
        try:
            pos = int(movimiento) - 1  # El usuario ingresa 1-9; internamente usamos 0-8

            # Verificar que la posición esté dentro del tablero
            if pos < 0 or pos > 8:
                return False, {"error": "Posición inválida (1-9)"}

            # Verificar que la casilla no esté ya ocupada
            if self.tablero[pos] != " ":
                return False, {"error": "Casilla ocupada"}

            # Poner el símbolo del jugador en la casilla elegida
            self.tablero[pos] = self.simbolos[jugador_id]

            # Comprobar si este movimiento ganó la partida
            ganador = self.verificar_ganador()
            if ganador:
                self.estado = "TERMINADO"
                self.ganador = jugador_id
                return True, {
                    "terminado": True,
                    "ganador": self.ganador,
                    "movimiento": movimiento,
                }

            # Comprobar empate: si no queda ningún espacio libre
            if " " not in self.tablero:
                self.estado = "TERMINADO"
                return True, {
                    "terminado": True,
                    "ganador": None,
                    "razon": "empate",
                    "movimiento": movimiento,
                }

            # Pasar el turno al otro jugador
            for j in self.jugadores:
                if j != jugador_id:
                    self.turno = j
                    break

            return True, {"valido": True, "movimiento": movimiento}
        except ValueError:
            # El jugador ingresó algo que no es número
            return False, {"error": "Movimiento debe ser número (1-9)"}

    def verificar_ganador(self):
        """Revisa si alguna línea (fila, columna o diagonal) está completa."""
        # Todas las combinaciones ganadoras posibles en un tablero 3x3
        lineas = [
            [0, 1, 2], [3, 4, 5], [6, 7, 8],  # filas
            [0, 3, 6], [1, 4, 7], [2, 5, 8],  # columnas
            [0, 4, 8], [2, 4, 6],              # diagonales
        ]

        for linea in lineas:
            # Si las tres casillas tienen el mismo símbolo (y no están vacías), hay ganador
            if (
                self.tablero[linea[0]] != " "
                and self.tablero[linea[0]]
                == self.tablero[linea[1]]
                == self.tablero[linea[2]]
            ):
                return self.tablero[linea[0]]  # Devuelve 'X' u 'O'
        return None  # No hay ganador todavía

    def obtener_vista(self, jugador_id):
        """Devuelve el estado del tablero personalizado para un jugador."""
        return {
            "tipo": "triqui",
            "tablero": self.tablero.copy(),  # Copia para que el cliente no modifique el original
            "tu_simbolo": self.simbolos.get(jugador_id, "?"),
            "turno": self.turno,
            "jugadores": self.jugadores,
        }

    def obtener_vista_publica(self):
        """Devuelve el tablero final para mostrarlo a ambos jugadores al terminar."""
        return {"tipo": "triqui", "tablero": self.tablero.copy()}
