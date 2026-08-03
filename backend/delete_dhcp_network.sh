#!/bin/bash
# =============================================================================
#  delete_dhcp_network.sh
# =============================================================================
#  Paso 3 al eliminar el DHCP: la red.
# =============================================================================

ssh -T -o BatchMode=yes -o ConnectTimeout=5 -o LogLevel=ERROR -i /home/usuario/.ssh/mikrotik_tea_key admin@192.168.56.121 'ip dhcp-server network remove [find where [:tostr $address]="192.168.200.0/24"]'
