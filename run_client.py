#!/usr/bin/env python3
# Archivo de arranque del cliente.
# Ejecutar: python run_client.py [host] [puerto]
from client.cliente import ClienteJuegos
import sys

if __name__ == "__main__":
    # Leer host y puerto desde la línea de comandos; usar valores por defecto si no se pasan
    host   = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    puerto = int(sys.argv[2]) if len(sys.argv) > 2 else 8888

    # Crear el cliente y lanzar la aplicación
    cliente = ClienteJuegos(host, puerto)
    cliente.iniciar()
