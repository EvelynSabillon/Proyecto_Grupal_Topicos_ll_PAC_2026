#!/bin/bash
# =============================================================================
#  monitorearip.sh  --  CONSUMIDOR del monitoreo ICMP
# =============================================================================
#  Lee la ultima linea que dejo verificarconexion.sh y escribe el semaforo:
#
#      estado.txt  ->  1 = el router responde, 0 = no responde
#
#  Uso:  monitorearip.sh <ip> <archivo_datos> <archivo_estado>
#
#  QUE CAMBIO RESPECTO A LA VERSION ANTERIOR
#  El script original hacia esto:
#
#      valor1=$(tail -n1 datos.txt | cut -d " " -f6)
#      valor2=$(tail -n1 datos.txt | cut -d " " -f6)
#      if [ $valor1 == "ttl=64" ] ; then ... elif [ $valor2 == "Unreachable" ]
#
#  valor1 y valor2 ejecutaban EXACTAMENTE el mismo comando, asi que la rama
#  de "Unreachable" no podia cumplirse nunca. Ademas comparaba contra
#  "ttl=64" exacto, cuando el TTL cambia segun el equipo y los saltos de red
#  (64, 63, 128...), y los tests sin comillas reventaban con el archivo
#  vacio.
#
#  Aqui se busca el patron  ttl=  en cualquier posicion y con cualquier
#  valor, y ademas se confirma con un ping directo para no dar por buena una
#  linea antigua que hubiera quedado en el archivo.
# =============================================================================

IP="$1"
DATOS="$2"
ESTADO="$3"

if [ -z "$ESTADO" ]; then
    echo "Uso: $0 <ip> <archivo_datos> <archivo_estado>" >&2
    exit 1
fi

while true
do
    if [ -s "$DATOS" ]; then
        ultima=$(tail -n1 "$DATOS" 2>/dev/null | tr -d '\r')

        # -i para aceptar tanto ttl= como TTL=, segun la version de ping
        if echo "$ultima" | grep -qi "ttl="; then
            # Confirmacion: que el dato no sea de hace un rato
            if ping -c 1 -W 2 "$IP" > /dev/null 2>&1; then
                echo 1 > "$ESTADO"
            else
                echo 0 > "$ESTADO"
            fi
        else
            # Cubre "Unreachable", "100% packet loss" y "sin respuesta"
            echo 0 > "$ESTADO"
        fi
    fi

    sleep 1
done
