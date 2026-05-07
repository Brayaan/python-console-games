#!/bin/bash
# Servidor — muestra la IP local al iniciar para que los clientes puedan conectarse
gnome-terminal -- bash -c "python3 run_server.py; echo ''; read -p 'Presiona enter para salir...'"