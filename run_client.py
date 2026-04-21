#!/usr/bin/env python3
# Punto de entrada del cliente: acepta host y puerto por linea de comandos
from client.cliente import ClienteJuegos
import sys

if __name__ == "__main__":
    host   = sys.argv[1] if len(sys.argv) > 1 else 'localhost'
    puerto = int(sys.argv[2]) if len(sys.argv) > 2 else 8888

    cliente = ClienteJuegos(host, puerto)
    cliente.iniciar()
