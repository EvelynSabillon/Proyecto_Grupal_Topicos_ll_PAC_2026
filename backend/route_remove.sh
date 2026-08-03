#!/bin/bash
# =============================================================================
#  route_remove.sh
# =============================================================================
#  Elimina una ruta estatica. El static=yes protege las rutas que el
#   propio router genera para sus interfaces.
#
#  Opciones de ssh y por que:
#    -T                   sin pseudo-terminal: la salida sale limpia
#    -o BatchMode=yes     si la llave falla, corta en vez de pedir password
#                         y dejar la ventana colgada esperando para siempre
#    -o ConnectTimeout=N  no espera indefinidamente a un router apagado
#    -o LogLevel=ERROR    quita el ruido de "added to known hosts"
# =============================================================================

ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/usuario/.ssh/mikrotik_tea_key admin@192.168.56.121 'ip route remove [find dst-address=192.168.10.0/24 static=yes]'
