#!/usr/bin/env python3
# Archivo de arranque del cliente.
# Uso normal   : python run_client.py
#   → muestra el menú de descubrimiento automático de servidores en la LAN.
# Uso directo  : python run_client.py <ip> [puerto]
#   → se conecta directamente sin mostrar el menú de discovery (modo debug).
from client.cliente import ClienteJuegos
import sys

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Conexión directa: se saltea el menú de descubrimiento
        host   = sys.argv[1]
        puerto = int(sys.argv[2]) if len(sys.argv) > 2 else 8888
        cliente = ClienteJuegos(host, puerto)
        if cliente.conectar():
            cliente.registrar_nombre_obligatorio()
            if cliente.nombre_registrado:
                cliente.menu_principal()
    else:
        # Modo normal: descubrimiento automático de servidores en la red
        cliente = ClienteJuegos()
        cliente.iniciar()
