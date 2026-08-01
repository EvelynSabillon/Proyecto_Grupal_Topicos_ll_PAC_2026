#!/bin/bash
# =============================================================================
#  delete_dhcp_pool.sh
# =============================================================================
#  Paso 2 al eliminar el DHCP: el pool.
#
#  ESTE ARCHIVO LO GENERA LA APLICACION. La version que ves aqui es de
#  REFERENCIA, con valores de ejemplo, para que se pueda leer el backend sin
#  necesidad de ejecutar el programa. Cada vez que se pulsa el boton
#  correspondiente, la funcion ejecutar() de
#  mikrotik_system_customtkinter.py lo vuelve a escribir con los datos que
#  haya puesto el usuario en el formulario, y despues lo lanza con bash
#  capturando la respuesta del router.
#
#  Opciones de ssh y por que:
#    -T                   sin pseudo-terminal: la salida sale limpia
#    -o BatchMode=yes     si la llave falla, corta en vez de pedir password
#                         y dejar la ventana colgada esperando para siempre
#    -o ConnectTimeout=N  no espera indefinidamente a un router apagado
#    -o LogLevel=ERROR    quita el ruido de "added to known hosts"
# =============================================================================

ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/usuario/.ssh/mikrotik_tea_key admin@192.168.56.121 'ip pool remove [find name=dhcp_pool]'
