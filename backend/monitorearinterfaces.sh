#!/bin/bash
# =============================================================================
#  monitorearinterfaces.sh  --  CONSUMIDOR del monitoreo de interfaces
# =============================================================================
#  Lee el archivo que deja verificarinterfaces.sh, lo interpreta y escribe
#  cuatro archivos que la interfaz grafica lee cada segundo.
#
#  Uso:
#    monitorearinterfaces.sh <datos> <estado1> <trafico1> <estado2> <trafico2>
#
#  estadoN.txt   ->  1 = UP, 0 = DOWN
#  traficoN.txt  ->  "<bits_in> <bits_out>"
#
#  Separar productor y consumidor tiene una ventaja concreta: si el router
#  tarda 4 segundos en responder, el consumidor sigue refrescando con el
#  ultimo dato conocido y la ventana no se congela.
# =============================================================================

DATOS="$1"
ESTADO1="$2"
TRAFICO1="$3"
ESTADO2="$4"
TRAFICO2="$5"

if [ -z "$TRAFICO2" ]; then
    echo "Uso: $0 <datos> <estado1> <trafico1> <estado2> <trafico2>" >&2
    exit 1
fi

# Escribe el estado y el trafico de una interfaz.
#   $1 = linea leida   $2 = archivo de estado   $3 = archivo de trafico
procesar() {
    linea="$1"
    archivo_estado="$2"
    archivo_trafico="$3"

    # tr -d '\r' quita el retorno de carro que mete RouterOS al final de cada
    # linea. Sin esto la comparacion con "true" nunca se cumplia, porque el
    # valor real era "true\r".
    estado=$(echo "$linea" | tr -d '\r' | cut -d " " -f3)
    rx=$(echo "$linea" | tr -d '\r' | cut -d " " -f4)
    tx=$(echo "$linea" | tr -d '\r' | cut -d " " -f5)

    # Las comillas alrededor de $estado son obligatorias: si el archivo aun
    # no existe la variable queda vacia y, sin comillas, el test da un error
    # de sintaxis y el bucle muere en silencio.
    if [ "$estado" = "true" ]; then
        echo 1 > "$archivo_estado"
        echo "${rx:-0} ${tx:-0}" > "$archivo_trafico"
    else
        echo 0 > "$archivo_estado"
        echo "0 0" > "$archivo_trafico"
    fi
}

while true
do
    if [ -s "$DATOS" ]; then
        linea1=$(grep "^DATO 1" "$DATOS" 2>/dev/null | tail -n1)
        linea2=$(grep "^DATO 2" "$DATOS" 2>/dev/null | tail -n1)

        [ -n "$linea1" ] && procesar "$linea1" "$ESTADO1" "$TRAFICO1"
        [ -n "$linea2" ] && procesar "$linea2" "$ESTADO2" "$TRAFICO2"
    fi

    sleep 1
done
