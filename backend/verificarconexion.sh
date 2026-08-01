#!/bin/bash
# =============================================================================
#  verificarconexion.sh  --  PRODUCTOR del monitoreo ICMP
# =============================================================================
#  Hace ping al router una vez por segundo y va guardando el resultado.
#
#  Uso:  verificarconexion.sh <ip> <archivo_de_salida>
#
#  QUE CAMBIO RESPECTO A LA VERSION ANTERIOR
#  Antes se lanzaba  ping <ip> >> datosconexion.txt  sin limite: un ping
#  continuo escribe una linea por segundo, asi que en una demostracion de
#  una hora el archivo pasaba de 3600 lineas y seguia creciendo mientras la
#  aplicacion estuviera abierta. El `tail` sobre ese archivo se volvia cada
#  vez mas lento.
#
#  Ahora se usa  ping -c 1  (un solo paquete por vuelta) y se recorta el
#  archivo cuando pasa de MAX_LINEAS, asi que su tamano queda acotado.
# =============================================================================

IP="$1"
SALIDA="$2"
MAX_LINEAS=300

if [ -z "$SALIDA" ]; then
    echo "Uso: $0 <ip> <archivo_de_salida>" >&2
    exit 1
fi

while true
do
    # -c 1  un solo paquete    -W 2  espera maxima de 2 segundos
    respuesta=$(ping -c 1 -W 2 "$IP" 2>&1 | grep -E "ttl=|TTL=|Unreachable|unreachable|100% packet loss")

    if [ -z "$respuesta" ]; then
        respuesta="sin respuesta de $IP"
    fi

    echo "$(date '+%H:%M:%S') $respuesta" >> "$SALIDA"

    # Recorte periodico para que el archivo no crezca sin fin
    lineas=$(wc -l < "$SALIDA" 2>/dev/null || echo 0)
    if [ "$lineas" -gt "$MAX_LINEAS" ]; then
        tail -n 100 "$SALIDA" > "${SALIDA}.tmp" && mv -f "${SALIDA}.tmp" "$SALIDA"
    fi

    sleep 1
done
