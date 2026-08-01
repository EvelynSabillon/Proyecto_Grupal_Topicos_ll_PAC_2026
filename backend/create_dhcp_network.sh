#!/bin/bash
# Generado automaticamente por la aplicacion. No editar a mano:
# se sobrescribe en cada ejecucion. Queda en disco como evidencia
# de lo que se le mando al router.
ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/topicos/.ssh/mikrotik_tea_key admin@192.168.88.1 'ip dhcp-server network add address=192.168.200.0/24 gateway=192.168.200.1 dns-server=8.8.8.8'
