#!/bin/bash
# =============================================================================
#  delete_dhcp_server.sh
# =============================================================================
#  Paso 1 al eliminar el DHCP: el servidor primero, porque el pool no
#   se puede borrar mientras este en uso.
#
#  Opciones de ssh y por que:
#    -T                   sin pseudo-terminal: la salida sale limpia
#    -o BatchMode=yes     si la llave falla, corta en vez de pedir password
#                         y dejar la ventana colgada esperando para siempre
#    -o ConnectTimeout=N  no espera indefinidamente a un router apagado
#    -o LogLevel=ERROR    quita el ruido de "added to known hosts"
# =============================================================================

ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/usuario/.ssh/mikrotik_tea_key admin@192.168.56.121 'ip dhcp-server remove [find name=dhcp_server]'
