#!/usr/bin/env python3
# Punto de entrada del proceso servidor: instancia y lanza el socket TCP en 0.0.0.0:8888
from server.servidor import ServidorJuegos

if __name__ == "__main__":
    servidor = ServidorJuegos(host='0.0.0.0', puerto=8888)
    servidor.iniciar()
