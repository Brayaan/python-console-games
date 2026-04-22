# Juego Conecta 4 para el servidor multijugador.
from .juego_base import JuegoBase


class Conecta4(JuegoBase):
    """Gestiona una partida de Conecta 4 entre dos jugadores."""

    def __init__(self):
        super().__init__()
        self.filas = 6
        self.columnas = 7
        # Crear el tablero vacío como una cuadrícula de 6 filas y 7 columnas
        self.tablero = [[' ' for _ in range(self.columnas)] for _ in range(self.filas)]
        self.simbolos = {}  # Guarda qué símbolo usa cada jugador ('R' o 'A')

    def iniciar(self, jugadores_ids):
        """Asigna símbolos y define quién empieza."""
        super().iniciar(jugadores_ids)
        self.simbolos = {
            jugadores_ids[0]: 'R',   # Primer jugador: Rojo
            jugadores_ids[1]: 'A'    # Segundo jugador: Amarillo
        }
        self.turno = jugadores_ids[0]  # El jugador Rojo siempre empieza

    def procesar_movimiento(self, jugador_id, movimiento):
        """Valida y aplica la jugada; retorna (válido, resultado)."""
        try:
            columna = int(movimiento) - 1  # El usuario ingresa 1-7; internamente usamos 0-6

            # Verificar que la columna exista en el tablero
            if columna < 0 or columna >= self.columnas:
                return False, {'error': f'Columna inválida (0-{self.columnas-1})'}

            # Solo el jugador con el turno puede mover
            if jugador_id != self.turno:
                return False, {'error': 'No es tu turno'}

            # No aceptar movimientos si la partida ya terminó
            if self.estado == "TERMINADO":
                return False, {'error': 'El juego ya terminó'}

            # Recorrer la columna de abajo hacia arriba para encontrar la primera celda libre
            for fila in range(self.filas-1, -1, -1):
                if self.tablero[fila][columna] == ' ':
                    # Colocar la ficha del jugador en la fila más baja disponible
                    self.tablero[fila][columna] = self.simbolos[jugador_id]

                    # Guardar información del movimiento para enviar al cliente
                    movimiento_info = {
                        'jugador': jugador_id,
                        'columna': columna,
                        'fila': fila,
                        'simbolo': self.simbolos[jugador_id]
                    }

                    # Revisar si la ficha recién puesta forma una línea de 4
                    if self.verificar_victoria(fila, columna, self.simbolos[jugador_id]):
                        self.estado = "TERMINADO"
                        self.ganador = jugador_id
                        return True, {
                            'movimiento': movimiento_info,
                            'terminado': True,
                            'ganador': jugador_id
                        }

                    # Revisar si el tablero está lleno (empate)
                    if self.tablero_lleno():
                        self.estado = "TERMINADO"
                        return True, {
                            'movimiento': movimiento_info,
                            'terminado': True,
                            'ganador': None,
                            'razon': 'empate'
                        }

                    # Cambiar el turno al otro jugador
                    if jugador_id == self.jugadores[0]:
                        self.turno = self.jugadores[1]
                    else:
                        self.turno = self.jugadores[0]

                    # Movimiento exitoso, la partida continúa
                    return True, {
                        'movimiento': movimiento_info,
                        'turno': self.turno
                    }

            # Si el bucle terminó sin encontrar celda libre, la columna está llena
            return False, {'error': 'Columna llena'}

        except ValueError:
            # El jugador ingresó algo que no es un número
            return False, {'error': 'Movimiento debe ser número'}

    def verificar_victoria(self, fila, columna, simbolo):
        """Revisa si hay 4 fichas seguidas del mismo símbolo en cualquier dirección."""
        # Las 4 direcciones posibles: horizontal, vertical, diagonal ↗, diagonal ↘
        direcciones = [(0,1), (1,0), (1,1), (1,-1)]

        for df, dc in direcciones:
            count = 1  # Contamos la ficha recién colocada

            # Contar fichas iguales en la dirección positiva
            f, c = fila + df, columna + dc
            while 0 <= f < self.filas and 0 <= c < self.columnas and self.tablero[f][c] == simbolo:
                count += 1
                f += df
                c += dc

            # Contar fichas iguales en la dirección opuesta
            f, c = fila - df, columna - dc
            while 0 <= f < self.filas and 0 <= c < self.columnas and self.tablero[f][c] == simbolo:
                count += 1
                f -= df
                c -= dc

            # Si hay 4 o más fichas seguidas, hay ganador
            if count >= 4:
                return True

        return False

    def tablero_lleno(self):
        """Devuelve True si ya no hay espacio en el tablero (empate)."""
        # Basta revisar la fila superior: si está llena, todo el tablero lo está
        return all(self.tablero[0][c] != ' ' for c in range(self.columnas))

    def obtener_vista(self, jugador_id):
        """Devuelve el estado del tablero personalizado para un jugador."""
        return {
            'tipo': 'conecta4',
            'tablero': [fila.copy() for fila in self.tablero],  # Copia fila por fila para no modificar el original
            'tu_simbolo': self.simbolos.get(jugador_id, '?'),
            'turno': self.turno,
            'jugadores': self.jugadores,
            'filas': self.filas,
            'columnas': self.columnas
        }

    def obtener_vista_publica(self):
        """Devuelve el tablero final para mostrarlo a ambos jugadores al terminar."""
        return {
            'tipo': 'conecta4',
            'tablero': [fila.copy() for fila in self.tablero]
        }
