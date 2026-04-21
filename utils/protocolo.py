# Protocolo de mensajes sobre TCP: cabecera de longitud (4 bytes) + payload JSON
import json
import struct

class Protocolo:

    @staticmethod
    def enviar(socket, mensaje):
        # Serializa a JSON y antepone longitud en big-endian (framing sobre stream TCP)
        try:
            if mensaje is None:
                return False
            datos = json.dumps(mensaje).encode('utf-8')
            longitud = struct.pack('>I', len(datos))  # 4 bytes big-endian = cabecera de longitud
            socket.send(longitud + datos)             # escritura atomica al buffer del socket
            return True
        except Exception:
            return False

    @staticmethod
    def recibir(socket):
        # Lee la cabecera de 4 bytes (bloqueante) para saber cuantos bytes esperar
        try:
            raw_longitud = socket.recv(4)          # recv() bloqueante: el hilo cede la CPU
            if not raw_longitud:
                return None
            longitud = struct.unpack('>I', raw_longitud)[0]
            if longitud > 1048576:                 # limite 1 MB: proteccion contra DoS / OOM
                return None
            datos = b''
            while len(datos) < longitud:           # TCP puede fragmentar; se reensambla el mensaje completo
                chunk = socket.recv(min(4096, longitud - len(datos)))
                if not chunk:
                    return None
                datos += chunk
            return json.loads(datos.decode('utf-8'))
        except Exception:
            return None
