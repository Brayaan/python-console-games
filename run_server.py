#!/usr/bin/env python3
# Archivo de arranque del servidor.
# Ejecutar: python run_server.py
from server.servidor import ServidorJuegos

if __name__ == "__main__":
    # Crear el servidor escuchando en todas las interfaces de red, puerto 8888
    servidor = ServidorJuegos(host='0.0.0.0', puerto=8888)
    servidor.iniciar()  # Entrar al bucle de aceptación de conexiones
