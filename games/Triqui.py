from .juego_base import JuegoBase


class Triqui(JuegoBase):
    def __init__(self):
        super().__init__()
        self.tablero = [" "] * 9
        self.simbolos = {}  # {jugador_id: 'X' o 'O'}

    def iniciar(self, jugadores_ids):
        super().iniciar(jugadores_ids)
        self.simbolos = {jugadores_ids[0]: "X", jugadores_ids[1]: "O"}
        self.turno = jugadores_ids[0]  # X empieza

    def procesar_movimiento(self, jugador_id, movimiento):
        print(f"[DEBUG] Triqui.procesar_movimiento: jugador={jugador_id}, movimiento={movimiento}")
        try:
            pos = int(movimiento) - 1
            if pos < 0 or pos > 8:
                return False, {"error": "Posición inválida (1-9)"}

            if self.tablero[pos] != " ":
                return False, {"error": "Casilla ocupada"}

            # Colocar símbolo
            self.tablero[pos] = self.simbolos[jugador_id]

            # Verificar victoria
            ganador = self.verificar_ganador()
            if ganador:
                self.estado = "TERMINADO"
                self.ganador = (
                    jugador_id  # El jugador que hizo el movimiento es el ganador
                )
                return True, {
                    "terminado": True,
                    "ganador": self.ganador,
                    "movimiento": movimiento,
                }

            # Verificar empate
            if " " not in self.tablero:
                self.estado = "TERMINADO"
                return True, {
                    "terminado": True,
                    "ganador": None,
                    "razon": "empate",
                    "movimiento": movimiento,
                }

            # Cambiar turno al otro jugador

            for j in self.jugadores:
                if j != jugador_id:
                    self.turno = j
                    break

            return True, {"valido": True, "movimiento": movimiento}
        except ValueError:
            return False, {"error": "Movimiento debe ser número (1-9)"}
        # movimiento: posición 1-9 (más intuitivo para el usuario)

    def verificar_ganador(self):
        # Combinaciones ganadoras (índices 0-8)
        lineas = [
            [0, 1, 2],
            [3, 4, 5],
            [6, 7, 8],  # filas
            [0, 3, 6],
            [1, 4, 7],
            [2, 5, 8],  # columnas
            [0, 4, 8],
            [2, 4, 6],  # diagonales
        ]

        for linea in lineas:
            if (
                self.tablero[linea[0]] != " "
                and self.tablero[linea[0]]
                == self.tablero[linea[1]]
                == self.tablero[linea[2]]
            ):
                return self.tablero[linea[0]]
        return None

    def obtener_vista(self, jugador_id):
        return {
            "tipo": "triqui",
            "tablero": self.tablero.copy(),
            "tu_simbolo": self.simbolos.get(jugador_id, "?"),
            "turno": self.turno,
            "jugadores": self.jugadores,
        }

    def obtener_vista_publica(self):
        return {"tipo": "triqui", "tablero": self.tablero.copy()}
