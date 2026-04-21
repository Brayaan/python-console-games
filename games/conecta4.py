from .juego_base import JuegoBase

class Conecta4(JuegoBase):
    def __init__(self):
        super().__init__()
        self.filas = 6
        self.columnas = 7
        self.tablero = [[' ' for _ in range(self.columnas)] for _ in range(self.filas)]
        self.simbolos = {}  # {jugador_id: 'R' o 'A'}
    
    def iniciar(self, jugadores_ids):
        super().iniciar(jugadores_ids)
        self.simbolos = {
            jugadores_ids[0]: 'R',
            jugadores_ids[1]: 'A'
        }
        self.turno = jugadores_ids[0]
    
    def procesar_movimiento(self, jugador_id, movimiento):
        try:
            columna = int(movimiento) - 1
            if columna < 0 or columna >= self.columnas:
                return False, {'error': f'Columna inválida (0-{self.columnas-1})'}
            
            # Validar que sea su turno
            if jugador_id != self.turno:
                return False, {'error': 'No es tu turno'}
            
            # Validar que el juego no haya terminado
            if self.estado == "TERMINADO":
                return False, {'error': 'El juego ya terminó'}
            
            # Encontrar la fila disponible (desde abajo)
            for fila in range(self.filas-1, -1, -1):
                if self.tablero[fila][columna] == ' ':
                    self.tablero[fila][columna] = self.simbolos[jugador_id]
                    
                    # Crear el diccionario del movimiento
                    movimiento_info = {
                        'jugador': jugador_id,
                        'columna': columna,
                        'fila': fila,
                        'simbolo': self.simbolos[jugador_id]
                    }
                    
                    # Verificar victoria
                    if self.verificar_victoria(fila, columna, self.simbolos[jugador_id]):
                        self.estado = "TERMINADO"
                        self.ganador = jugador_id
                        return True, {
                            'movimiento': movimiento_info,
                            'terminado': True,
                            'ganador': jugador_id
                        }
                    
                    # Verificar empate (tablero lleno)
                    if self.tablero_lleno():
                        self.estado = "TERMINADO"
                        return True, {
                            'movimiento': movimiento_info,
                            'terminado': True,
                            'ganador': None,
                            'razon': 'empate'
                        }
                    
                    # Cambiar turno
                    if jugador_id == self.jugadores[0]:
                        self.turno = self.jugadores[1]
                    else:
                        self.turno = self.jugadores[0]
                    
                    # Movimiento normal
                    return True, {
                        'movimiento': movimiento_info,
                        'turno': self.turno
                    }
            
            return False, {'error': 'Columna llena'}
                
        except ValueError:
            return False, {'error': 'Movimiento debe ser número'}
    


    def verificar_victoria(self, fila, columna, simbolo):
        """Verifica si hay 4 en línea alrededor de la última jugada"""
        direcciones = [(0,1), (1,0), (1,1), (1,-1)]  # horizontal, vertical, diagonal
        
        for df, dc in direcciones:
            count = 1
            
            # Dirección positiva
            f, c = fila + df, columna + dc
            while 0 <= f < self.filas and 0 <= c < self.columnas and self.tablero[f][c] == simbolo:
                count += 1
                f += df
                c += dc
            
            # Dirección negativa
            f, c = fila - df, columna - dc
            while 0 <= f < self.filas and 0 <= c < self.columnas and self.tablero[f][c] == simbolo:
                count += 1
                f -= df
                c -= dc
            
            if count >= 4:
                return True
        
        return False
    
    def tablero_lleno(self):
        return all(self.tablero[0][c] != ' ' for c in range(self.columnas))
    
    def obtener_vista(self, jugador_id):
        return {
            'tipo': 'conecta4',
            'tablero': [fila.copy() for fila in self.tablero],
            'tu_simbolo': self.simbolos.get(jugador_id, '?'),
            'turno': self.turno,
            'jugadores': self.jugadores,
            'filas': self.filas,
            'columnas': self.columnas
        }
    
    def obtener_vista_publica(self):
        return {
            'tipo': 'conecta4',
            'tablero': [fila.copy() for fila in self.tablero]
        }
