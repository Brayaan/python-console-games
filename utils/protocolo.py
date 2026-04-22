# Protocolo de comunicación entre cliente y servidor.
# Cada mensaje se envía como: 4 bytes de longitud + contenido JSON.
import json
import struct


class Protocolo:
    """Maneja el envío y recepción de mensajes JSON sobre TCP."""

    @staticmethod
    def enviar(socket, mensaje):
        """Convierte el mensaje a JSON y lo envía con su longitud al inicio."""
        try:
            if mensaje is None:
                return False  # No enviar mensajes vacíos
            datos = json.dumps(mensaje).encode('utf-8')  # Convertir dict a texto JSON en bytes
            longitud = struct.pack('>I', len(datos))      # 4 bytes que indican cuántos bytes vienen después
            socket.send(longitud + datos)                 # Enviar cabecera + contenido juntos
            return True
        except Exception:
            return False  # Si falla el envío, devolver False sin romper el programa

    @staticmethod
    def recibir(socket):
        """Lee y reconstruye un mensaje completo enviado por el protocolo."""
        try:
            raw_longitud = socket.recv(4)       # Leer los primeros 4 bytes para saber el tamaño del mensaje
            if not raw_longitud:
                return None                     # El socket se cerró
            longitud = struct.unpack('>I', raw_longitud)[0]  # Convertir los 4 bytes a un número entero
            if longitud > 1048576:              # Rechazar mensajes mayores a 1 MB (protección básica)
                return None
            datos = b''
            while len(datos) < longitud:        # TCP puede partir el mensaje; leer en partes hasta completarlo
                chunk = socket.recv(min(4096, longitud - len(datos)))
                if not chunk:
                    return None                 # Conexión interrumpida a mitad del mensaje
                datos += chunk
            return json.loads(datos.decode('utf-8'))  # Convertir el texto JSON de vuelta a dict
        except Exception:
            return None  # Si algo falla, devolver None sin romper el programa
