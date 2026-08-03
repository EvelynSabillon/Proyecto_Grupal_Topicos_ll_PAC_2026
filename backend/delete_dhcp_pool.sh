#!/bin/bash
# =============================================================================
#  delete_dhcp_pool.sh
# =============================================================================
#  Paso 2 al eliminar el DHCP: el pool.
# Cada vez que se pulsa el boton
#  correspondiente, la funcion ejecutar() de
#  mikrotik_system_customtkinter.py lo vuelve a escribir con los datos que
#  haya puesto el usuario en el formulario, y despues lo lanza con bash
#  capturando la respuesta del router.
# =============================================================================

ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/usuario/.ssh/mikrotik_tea_key admin@192.168.56.121 'ip pool remove [find name=dhcp_pool]'
