#!/bin/bash
# =============================================================================
#  verificarinterfaces.sh  --  PRODUCTOR del monitoreo de interfaces
# =============================================================================
#  Pregunta al router, una vez por segundo, el estado y el trafico de DOS
#  interfaces, y deja la respuesta en un archivo de texto.
#
#  Uso:
#    verificarinterfaces.sh <llave> <usuario> <ip> <if1> <if2> <timeout> <salida>
#
#  Formato de cada linea que escribe:
#      DATO <1|2> <true|false> <bits_in> <bits_out>
#
#  POR QUE ESCRIBE EN .tmp Y DESPUES HACE mv
#  El consumidor lee este archivo cada segundo. Si escribieramos directo,
#  podria leerlo justo a la mitad y quedarse con media linea. En Linux, mv
#  dentro del mismo sistema de archivos es una operacion atomica: el
#  consumidor ve el archivo viejo completo o el nuevo completo, nunca uno a
#  medias.
#
#  POR QUE UNA SOLA SESION SSH PARA LAS DOS INTERFACES
#  Abrir dos conexiones ssh por segundo satura al router y desincroniza las
#  lecturas. Con una sola sesion, los dos datos corresponden al mismo
#  instante.
# =============================================================================

LLAVE="$1"
USUARIO="$2"
IP="$3"
IF1="$4"
IF2="$5"
TIMEOUT="${6:-5}"
SALIDA="$7"

if [ -z "$SALIDA" ]; then
    echo "Uso: $0 <llave> <usuario> <ip> <if1> <if2> <timeout> <salida>" >&2
    exit 1
fi

TMP="${SALIDA}.tmp"

# --- Comando de RouterOS -----------------------------------------------------
# Se comprueba con [:len [/interface find name=...]] que la interfaz exista
# antes de pedirle el trafico.
CMD=":local n1 \"$IF1\"; :local n2 \"$IF2\";"
CMD="$CMD :if ([:len [/interface find name=\$n1]] > 0) do={"
CMD="$CMD /interface monitor-traffic interface=\$n1 once do={"
CMD="$CMD :put (\"DATO 1 \" . [:tostr [/interface get \$n1 running]] . \" \""
CMD="$CMD . [:tostr \$\"rx-bits-per-second\"] . \" \" . [:tostr \$\"tx-bits-per-second\"])"
CMD="$CMD }} else={ :put \"DATO 1 noexiste 0 0\" };"
CMD="$CMD :if ([:len [/interface find name=\$n2]] > 0) do={"
CMD="$CMD /interface monitor-traffic interface=\$n2 once do={"
CMD="$CMD :put (\"DATO 2 \" . [:tostr [/interface get \$n2 running]] . \" \""
CMD="$CMD . [:tostr \$\"rx-bits-per-second\"] . \" \" . [:tostr \$\"tx-bits-per-second\"])"
CMD="$CMD }} else={ :put \"DATO 2 noexiste 0 0\" };"

# --- Bucle -------------------------------------------------------------------
while true
do
    ssh -T \
        -o BatchMode=yes \
        -o ConnectTimeout="$TIMEOUT" \
        -o LogLevel=ERROR \
        -i "$LLAVE" "$USUARIO@$IP" "$CMD" > "$TMP" 2>/dev/null

    # Se comprueba el codigo de salida Y que la respuesta traiga lineas DATO.
    if [ $? -ne 0 ] || ! grep -q "^DATO " "$TMP" 2>/dev/null; then
        # El router no respondio o respondio otra cosa: se marcan las dos
        # interfaces como caidas en vez de dejar el dato anterior congelado,
        # que daria la falsa impresion de que todo sigue bien.
        printf 'DATO 1 sinconexion 0 0\nDATO 2 sinconexion 0 0\n' > "$TMP"
    fi

    mv -f "$TMP" "$SALIDA"
    sleep 1
done
