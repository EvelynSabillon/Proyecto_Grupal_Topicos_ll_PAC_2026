"""
===============================================================================
 CONTROL MIKROTIK ROUTER
 Administracion de un router MikroTik (RouterOS) desde Python sobre Linux
===============================================================================

 ARQUITECTURA
 ------------
 El archivo esta dividido en dos capas, separadas logicamente y marcadas con
 los banners de seccion:

   BACKEND   (secciones 1 a 6)
       Todo lo que sabe hablar con el router. Ninguna de estas funciones
       importa customtkinter ni dibuja nada: reciben datos, ejecutan
       comandos por SSH y devuelven (ok, titulo, detalle).

   FRONTEND  (secciones 7 a 9)
       Todo lo que sabe dibujar ventanas. No arma un solo comando de
       RouterOS: le pide al backend que lo haga y muestra el resultado.

 COMO HABLA CON EL ROUTER
 ------------------------
       FRONTEND (customtkinter)
            |  llama a las operaciones del backend
            v
       BACKEND / operaciones      valida, ejecuta, VERIFICA
            |
            v
       ejecutar(archivo.sh, comando)
            |  escribe el script en backend/ y lo lanza con bash
            v
       ssh -i <llave> <usuario>@<ip> 'comando de RouterOS'
            |
            v
       RouterOS  ->  la respuesta se CAPTURA y se interpreta

 Los scripts .sh no son decorativos: son el backend de shell scripting que
 pide el enunciado, y quedan en disco como evidencia auditable de lo que se
 le mando al router.
===============================================================================
"""

import os
import subprocess
import time
from datetime import datetime

# La interfaz grafica se importa de forma opcional. Asi este mismo archivo
# se puede importar como modulo desde otro programa
try:
    import customtkinter as ctk
    from tkinter import messagebox, END
    HAY_GUI = True
except ImportError:
    ctk = None
    messagebox = None
    END = None
    HAY_GUI = False

try:
    from PIL import Image
    HAY_PIL = True
except ImportError:
    HAY_PIL = False


# =============================================================================
#  SECCION 0 - CONFIGURACION
# =============================================================================
#  Lo unico que hay que tocar para mover el proyecto a otra maquina o a otro
#  router son las constantes de este bloque.
#
#  Las rutas NO estan escritas a mano: se calculan a partir de donde esta
#  este archivo.
# =============================================================================

# --- Datos del router --------------------------------------------------------
IP = "192.168.88.1"                       # IP del router MikroTik
USUARIO = "admin"                           # usuario SSH de RouterOS
LLAVE = os.path.expanduser("/home/topicos/.ssh/mikrotik_tea_key")   # llave privada
TIMEOUT = 5                                 # segundos antes de darlo por muerto

# --- Interfaces que se monitorean por defecto -------------------------------
INTERFAZ_1 = "ether1"
INTERFAZ_2 = "ether2"

# --- Apariencia --------------------------------------------------------------
APARIENCIA = "light"        # "light", "dark" o "system"
TEMA = "dark-blue"          # "blue", "green" o "dark-blue"
REFRESCO_MS = 1000          # cada cuanto se repinta el monitoreo

# --- Rutas del proyecto (se calculan solas) ----------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(BASE_DIR, "backend")    # scripts .sh
ASSETS_DIR = os.path.join(BASE_DIR, "assets")      # imagenes del semaforo
RUNTIME_DIR = os.path.join(BASE_DIR, "runtime")    # archivos temporales
BACKUPS_DIR = os.path.join(BASE_DIR, "Backups")    # respaldos traidos del router

for _carpeta in (BACKEND_DIR, RUNTIME_DIR, BACKUPS_DIR):
    if not os.path.isdir(_carpeta):
        os.makedirs(_carpeta)

# --- Archivos que escriben los scripts de monitoreo en segundo plano ---------
F_ESTADO_ICMP = os.path.join(RUNTIME_DIR, "estado.txt")
F_DATOS_PING = os.path.join(RUNTIME_DIR, "datosconexion.txt")
F_DATOS_INTERFACES = os.path.join(RUNTIME_DIR, "datosinterfaces.txt")
F_ESTADO_1 = os.path.join(RUNTIME_DIR, "estado1.txt")
F_ESTADO_2 = os.path.join(RUNTIME_DIR, "estado2.txt")
F_TRAFICO_1 = os.path.join(RUNTIME_DIR, "trafico1.txt")
F_TRAFICO_2 = os.path.join(RUNTIME_DIR, "trafico2.txt")

# --- Scripts de monitoreo ----------------------------------------------------
SH_VERIFICAR_CONEXION = os.path.join(BACKEND_DIR, "verificarconexion.sh")
SH_MONITOREAR_IP = os.path.join(BACKEND_DIR, "monitorearip.sh")
SH_VERIFICAR_INTERFACES = os.path.join(BACKEND_DIR, "verificarinterfaces.sh")
SH_MONITOREAR_INTERFACES = os.path.join(BACKEND_DIR, "monitorearinterfaces.sh")

# --- Datos de conexion guardados ---------------------------------------------
#  Las constantes de arriba son los valores POR DEFECTO. Si el usuario cambia
#  la IP, el usuario o la ruta de la llave desde la ventana "Conexion y llaves
#  SSH", la eleccion se guarda en este archivo y se vuelve a cargar en el
#  siguiente arranque. Asi no hay que editar el codigo para pasar de un router
#  a otro, ni para que cada integrante del equipo lo use en su maquina.
CONEXION_INI = os.path.join(BASE_DIR, "conexion.ini")


def cargar_conexion():
    """Lee conexion.ini y sustituye los valores por defecto si existe.

    Formato del archivo, una clave por linea:
        ip = 192.168.56.121
        usuario = admin
        llave = ~/.ssh/mikrotik_tea_key

    Se hace a mano en vez de con configparser para que el archivo sea lo mas
    simple posible y se pueda editar con cualquier editor de texto.
    """
    global IP, USUARIO, LLAVE

    if not os.path.isfile(CONEXION_INI):
        return

    try:
        with open(CONEXION_INI, "r", encoding="utf-8") as pf:
            for linea in pf:
                linea = linea.strip()
                if not linea or linea.startswith("#") or "=" not in linea:
                    continue
                clave, valor = linea.split("=", 1)
                clave, valor = clave.strip().lower(), valor.strip()
                if not valor:
                    continue
                if clave == "ip":
                    IP = valor
                elif clave == "usuario":
                    USUARIO = valor
                elif clave == "llave":
                    LLAVE = os.path.expanduser(valor)
    except OSError:
        # Si el archivo esta corrupto o no se puede leer, se sigue con los
        # valores por defecto en vez de impedir que la aplicacion arranque.
        pass


cargar_conexion()



# =============================================================================
#  SECCION 1 - BACKEND - INTERPRETACION DE LAS RESPUESTAS DEL ROUTER
# =============================================================================
#  RouterOS no usa codigos de salida: cuando rechaza un comando, el ssh
#  termina igual con returncode 0 y la queja viaja en el TEXTO de la
#  respuesta. Por eso no basta con mirar el returncode; hay que leer lo que
#  dijo el router.
#
#  Se distinguen tres situaciones porque al usuario le sirven mensajes
#  distintos en cada una:
#     1. No hay router           -> "revisa que este encendido"
#     2. Hay router pero dijo no -> se le muestra literalmente su respuesta
#     3. Ya estaba hecho         -> no es un fallo, el estado buscado ya esta
# =============================================================================

# Marcas que aparecen cuando el router RECHAZA un comando
ERRORES = (
    "failure", "error", "expected", "no such item", "invalid",
    "cannot", "input does not match", "bad command", "ambiguous",
    "syntax error",
)

# Marcas de que el problema no es el comando, sino que el router NO RESPONDE
CONEXION = (
    "connection timed out", "no route to host", "connection refused",
    "could not resolve", "host key verification", "connection closed",
    "permission denied", "operation timed out", "network is unreachable",
    "broken pipe", "no such file or directory",
)

# Respuestas que significan "ya estaba hecho", no "salio mal"
YA_EXISTE = ("already exists", "such name exists", "already have", "already has")


def es_error_conexion(salida):
    """True si la salida indica que no se pudo llegar al router."""
    if not salida:
        return False
    bajo = salida.lower()
    for marca in CONEXION:
        if marca in bajo:
            return True
    return False


def hubo_fallo(salida):
    """True si la respuesta contiene alguna marca de error.

    Incluye los errores de conexion: si el router no contesto, el comando
    tampoco se ejecuto, asi que no puede darse por bueno.
    """
    if not salida:
        return False
    bajo = salida.lower()
    for marca in ERRORES:
        if marca in bajo:
            return True
    return es_error_conexion(salida)


def ya_existia(salida):
    """True si el router dice que lo que se queria crear ya estaba."""
    if not salida:
        return False
    bajo = salida.lower()
    for marca in YA_EXISTE:
        if marca in bajo:
            return True
    return False


# =============================================================================
#  SECCION 2 - BACKEND - VALIDACION DE LO QUE ESCRIBE EL USUARIO
# =============================================================================
#
#  Aqui todo pasa por dos filtros: primero se comprueba que tenga la forma
#  correcta (validar_*), y despues se escapa para el shell (escapar).
# =============================================================================

import re  # noqa: E402  (se importa aqui para que quede junto a su seccion)

RE_IP = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$")
RE_CIDR = re.compile(r"^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})/(\d{1,2})$")
RE_NOMBRE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")

# En un comentario se permiten espacios, pero NO los caracteres que tienen
# significado para el shell:  ' " ` $ ; & | < > \ ( ) salto de linea
RE_COMENTARIO = re.compile(r"^[A-Za-z0-9 _.,:/#+()\-]{0,60}$")


def _octetos_validos(partes):
    """True si los 4 numeros de una IP estan entre 0 y 255."""
    for p in partes:
        # Rechaza 010 y 00: no son octetos validos y confunden al router
        if len(p) > 1 and p[0] == "0":
            return False
        if not 0 <= int(p) <= 255:
            return False
    return True


def limpiar(valor):
    """Quita espacios sobrantes. Atajo para no repetir .strip()."""
    return (valor or "").strip()


def validar_ip(valor):
    """Valida una IP suelta. Devuelve (ok, mensaje_de_error)."""
    valor = limpiar(valor)
    m = RE_IP.match(valor)
    if not m:
        return False, "Formato de IP invalido. Ejemplo: 192.168.56.1"
    if not _octetos_validos(m.groups()):
        return False, "Los numeros de la IP deben estar entre 0 y 255."
    return True, ""


def validar_cidr(valor):
    """Valida una direccion con mascara, tipo 192.168.56.1/24."""
    valor = limpiar(valor)
    m = RE_CIDR.match(valor)
    if not m:
        return False, "Formato invalido. Debe llevar mascara. Ejemplo: 192.168.56.1/24"
    if not _octetos_validos(m.groups()[:4]):
        return False, "Los numeros de la IP deben estar entre 0 y 255."
    if not 0 <= int(m.group(5)) <= 32:
        return False, "La mascara debe estar entre 0 y 32."
    return True, ""


def validar_rango(valor):
    """Valida el rango del pool DHCP: 192.168.56.100-192.168.56.150."""
    valor = limpiar(valor)
    if valor.count("-") != 1:
        return False, "Formato invalido. Ejemplo: 192.168.56.100-192.168.56.150"

    inicio, fin = valor.split("-")
    for parte in (inicio, fin):
        ok, msg = validar_ip(parte)
        if not ok:
            return False, "En el rango: " + msg

    # Que el inicio no sea mayor que el fin: el router lo acepta y despues el
    # pool no reparte nada, que es peor que un error claro aqui.
    if [int(x) for x in inicio.split(".")] > [int(x) for x in fin.split(".")]:
        return False, "La IP inicial del rango es mayor que la final."
    return True, ""


def validar_nombre(valor, que="nombre"):
    """Valida un identificador: identity, nombre de pool, de servidor DHCP."""
    valor = limpiar(valor)
    if not valor:
        return False, "El " + que + " no puede estar vacio."
    if not RE_NOMBRE.match(valor):
        return False, ("El " + que + " solo admite letras, numeros, punto, guion "
                       "y guion bajo (maximo 32 caracteres).")
    return True, ""


def validar_interfaz(valor):
    """Valida el nombre de una interfaz: ether1, wlan1, bridge-lan..."""
    valor = limpiar(valor)
    if not valor:
        return False, "Debes seleccionar una interfaz."
    if not RE_NOMBRE.match(valor):
        return False, "Nombre de interfaz invalido. Ejemplo: ether2"
    return True, ""


def validar_comentario(valor):
    """Valida un comentario. Admite espacios pero no metacaracteres."""
    if not RE_COMENTARIO.match(valor or ""):
        return False, ("El comentario no admite estos caracteres: ' \" ` $ ; & | "
                       "< > \\ . Maximo 60 caracteres.")
    return True, ""


def validar_lista_dns(valor):
    """Valida uno o varios DNS separados por coma: 8.8.8.8,8.8.4.4."""
    valor = limpiar(valor)
    if not valor:
        return False, "Debes indicar al menos un servidor DNS."
    for parte in valor.split(","):
        ok, msg = validar_ip(parte.strip())
        if not ok:
            return False, "En la lista de DNS: " + msg
    return True, ""


def escapar(valor):
    """Escapa un texto para meterlo entre comillas simples en el shell.

    El comando que se manda al router viaja asi:
        ssh ... 'ip address add comment="loquesea"'
    Una comilla simple dentro cerraria la cadena antes de tiempo. El truco
    estandar de bash es cerrar, poner una comilla escapada y volver a abrir:
        '  ->  '\\''
    """
    return str(valor).replace("'", "'\\''")


# =============================================================================
#  SECCION 3 - BACKEND - COMUNICACION CON EL ROUTER
# =============================================================================
#  Todo lo que sale hacia el router pasa por una de estas dos funciones:
#
#      ejecutar(archivo_sh, comando)  -> para CAMBIAR algo en el router
#      consultar(comando)             -> para PREGUNTAR algo al router
#
#  QUE CAMBIO RESPECTO A LA VERSION ANTERIOR
#  Antes se usaba os.system(), que ejecuta el comando y tira la salida a la
#  basura. Como consecuencia la aplicacion mostraba "operacion exitosa"
#  Ahora ejecutar() devuelve (ok, salida) y quien llama decide.
# =============================================================================

def _ssh(comando_router):
    """Arma la linea ssh completa para un comando de RouterOS.

    Opciones que se usan y por que:
      -T                     no pide pseudo-terminal: la salida sale limpia
      -o BatchMode=yes       si la llave falla, corta en vez de quedarse
                             pidiendo password y colgar la ventana para siempre
      -o ConnectTimeout=N    no espera indefinidamente a un router apagado
      -o LogLevel=ERROR      quita el ruido de "added to known hosts"
    """
    return (
        "ssh -T"
        " -o BatchMode=yes"
        " -o ConnectTimeout=" + str(TIMEOUT) +
        " -o LogLevel=ERROR"
        " -i " + LLAVE +
        " " + USUARIO + "@" + IP +
        " '" + escapar(comando_router) + "'"
    )


def ejecutar(archivo_sh, comando_router):
    """Escribe el script .sh, lo ejecuta con bash y devuelve (ok, salida).

    ok es True solo si bash termino bien Y el router no se quejo.
    """
    ruta = os.path.join(BACKEND_DIR, archivo_sh)

    contenido = (
        "#!/bin/bash\n"
        "# Generado automaticamente por la aplicacion. No editar a mano:\n"
        "# se sobrescribe en cada ejecucion. Queda en disco como evidencia\n"
        "# de lo que se le mando al router.\n"
        + _ssh(comando_router) + "\n"
    )

    try:
        with open(ruta, "w", encoding="utf-8") as pf:
            pf.write(contenido)
        os.chmod(ruta, 0o755)
    except OSError as e:
        return False, "No se pudo escribir el script " + archivo_sh + ": " + str(e)

    try:
        proc = subprocess.Popen(["bash", ruta],
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        salida = proc.communicate()[0].decode("utf-8", "replace").strip()
    except OSError as e:
        return False, "No se pudo ejecutar bash: " + str(e)

    ok = (proc.returncode == 0) and not hubo_fallo(salida)
    return ok, salida


def correr_pasos(pasos):
    """Ejecuta una lista de pasos y devuelve (todo_ok, reporte).

    Cada paso es una tupla:  (titulo, archivo_sh, comando [, tolerar])

    NO se detiene en el primer fallo: sigue con los demas y reporta el estado
    de cada uno, para que en pantalla se vea exactamente donde se rompio.

    Si `tolerar` es True y el router contesta que la cosa ya existe, el paso
    se marca YA EXISTIA y no cuenta como fallo: el estado que se buscaba ya
    esta puesto, que es lo que importa.
    """
    lineas = []
    todo_ok = True

    for paso in pasos:
        titulo, archivo, comando = paso[0], paso[1], paso[2]
        tolerar = paso[3] if len(paso) > 3 else False

        ok, salida = ejecutar(archivo, comando)

        if ok:
            estado = "OK"
        elif tolerar and ya_existia(salida):
            estado = "YA EXISTIA"
        else:
            estado = "FALLO"
            todo_ok = False

        lineas.append(titulo.ljust(30, ".") + " " + estado)
        if estado == "FALLO" and salida:
            lineas.append("      el router dijo: " + salida.replace("\n", " "))

    return todo_ok, "\n".join(lineas)


def consultar(comando_router):
    """Pregunta algo al router y devuelve su respuesta como texto.

    NUNCA lanza excepcion: si el ssh falla devuelve el texto del error. Antes
    varias consultas usaban check_output pelado y, con el router apagado,
    reventaban la aplicacion entera con una excepcion sin capturar.
    """
    try:
        salida = subprocess.check_output(_ssh(comando_router), shell=True,
                                         stderr=subprocess.STDOUT)
        return salida.decode("utf-8", "replace").strip()
    except subprocess.CalledProcessError as e:
        return e.output.decode("utf-8", "replace").strip()
    except OSError as e:
        return "No se pudo ejecutar ssh: " + str(e)


def hay_conexion():
    """Devuelve (ok, detalle). Se llama antes de cada accion.

    Sirve para que un router apagado produzca un mensaje claro en vez de un
    fallo raro a mitad de una secuencia de cuatro comandos.
    """
    prueba = consultar("system identity print")
    if not prueba or es_error_conexion(prueba):
        return False, (prueba or "el router no respondio nada")
    return True, prueba


def find_addr(valor):
    """Devuelve el [find ...] que de verdad encuentra una direccion.

    En RouterOS  [find address=192.168.56.0/24]  NO encuentra nada: address
    es de tipo prefijo, no texto, y la comparacion directa falla en silencio.
    Como un remove sobre un find vacio tampoco da error, el boton parecia
    funcionar y no borraba nada.

    La forma correcta es convertir el campo a texto con :tostr antes de
    comparar.
    """
    return '[find where [:tostr $address]="' + valor + '"]'


# =============================================================================
#  SECCION 4 - BACKEND - CONSULTAS AL ROUTER
# =============================================================================
#  Las funciones get_* devuelven listas de Python y sirven para llenar los
#  combobox del frontend. Las print_* devuelven el texto tal cual lo imprime
#  RouterOS y se muestran en el panel RESULTADO.
# =============================================================================

def get_interfaces():
    """Lista TODAS las interfaces del router, tengan IP o no.

    Antes se listaban solo las que ya tenian IP, sacandolas de /ip address.
    Eso hacia imposible ponerle la primera IP a una interfaz libre desde el
    combobox, que es justo el caso mas comun.
    """
    salida = consultar(":foreach i in=[/interface find] do={"
                       ":put [/interface get $i name]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_ips():
    """Lista las direcciones IP como texto 'x.x.x.x/nn'."""
    salida = consultar(":foreach i in=[/ip address find] do={"
                       ":put [:tostr [/ip address get $i address]]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_ips_con_interfaz():
    """Lista pares (direccion, interfaz) en UNA sola consulta.

    Antes se hacian dos consultas por separado y se emparejaban por posicion
    con dos diccionarios. Si una interfaz tenia dos IPs, las llaves repetidas
    se pisaban y el emparejamiento salia mal: por eso el boton de eliminar
    llegaba a borrar la IP equivocada.
    """
    salida = consultar(
        ":foreach i in=[/ip address find] do={"
        ':put ([:tostr [/ip address get $i address]] . "|" . '
        '[:tostr [/ip address get $i interface]])}')
    if hubo_fallo(salida):
        return []

    pares = []
    for linea in salida.splitlines():
        linea = linea.strip()
        if "|" in linea:
            direccion, interfaz = linea.split("|", 1)
            pares.append((direccion.strip(), interfaz.strip()))
    return pares


def get_dhcp_servers():
    """Nombres de los servidores DHCP configurados."""
    salida = consultar(":foreach i in=[/ip dhcp-server find] do={"
                       ":put [/ip dhcp-server get $i name]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_pools():
    """Nombres de los pools de direcciones."""
    salida = consultar(":foreach i in=[/ip pool find] do={"
                       ":put [/ip pool get $i name]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_redes_dhcp():
    """Redes DHCP como texto 'x.x.x.x/nn'."""
    salida = consultar(":foreach i in=[/ip dhcp-server network find] do={"
                       ":put [:tostr [/ip dhcp-server network get $i address]]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_rutas_estaticas():
    """Destinos de las rutas estaticas.

    Se filtra por `static` porque las rutas que el router genera solo (las de
    sus propias interfaces) no se pueden borrar, y ofrecerlas en el combobox
    de eliminar solo produce errores confusos.
    """
    salida = consultar(":foreach i in=[/ip route find where static] do={"
                       ":put [:tostr [/ip route get $i dst-address]]}")
    if hubo_fallo(salida):
        return []
    return [x for x in salida.split() if x]


def get_rutas_detalle():
    """Texto legible 'destino via gateway', una ruta por linea."""
    salida = consultar(
        ":foreach i in=[/ip route find where static] do={"
        ':put ([:tostr [/ip route get $i dst-address]] . " via " . '
        '[:tostr [/ip route get $i gateway]])}')
    if hubo_fallo(salida):
        return ""
    return salida


def get_dns_router():
    """Servidores DNS configurados en el router."""
    salida = consultar(":put [:tostr [/ip dns get servers]]")
    if hubo_fallo(salida):
        return ""
    return salida.strip()

def lista_dns(texto):
    """Convierte a conjunto una lista de DNS venga como venga.
    El usuario escribe  8.8.8.8,8.8.4.4  pero el router devuelve el array
    con  :tostr  y lo une con punto y coma:  8.8.8.8;8.8.4.4 . Comparar las
    dos cadenas tal cual daba siempre distinto y la operacion se reportaba
    como fallida aunque el DNS hubiera quedado bien puesto.
    """
    return set(p for p in re.split(r"[;,\s]+", texto or "") if p)


# --- Comprobaciones de existencia -------------------------------------------

def existe_ip(direccion):
    """True si el router tiene esa direccion IP exacta."""
    r = consultar(':put [:tostr [/ip address find where [:tostr $address]="'
                  + direccion + '"]]')
    return bool(r) and not hubo_fallo(r)


def existe_red_dhcp(red):
    """True si existe una red DHCP con esa direccion.

    Hace falta porque un `set` sobre un find vacio no da error ni salida: sin
    esta comprobacion la ventana anunciaria exito sobre una red inexistente.
    """
    r = consultar(':put [:tostr [/ip dhcp-server network find where '
                  '[:tostr $address]="' + red + '"]]')
    return bool(r) and not hubo_fallo(r)


def existe_ruta_estatica(destino):
    """True si existe una ruta estatica hacia ese destino."""
    r = consultar(':put [:tostr [/ip route find dst-address=' + destino +
                  ' static=yes]]')
    return bool(r) and not hubo_fallo(r)


def dhcp_server_de_interfaz(interfaz):
    """Nombre del servidor DHCP que ya ocupa esa interfaz, o cadena vacia.

    RouterOS solo admite UN servidor DHCP por interfaz. Sin esta comprobacion
    el segundo intento fallaba con un mensaje que no explicaba nada.
    """
    r = consultar(":foreach i in=[/ip dhcp-server find interface=" + interfaz +
                  "] do={:put [/ip dhcp-server get $i name]}")
    if not r or hubo_fallo(r):
        return ""
    partes = r.strip().split()
    return partes[0] if partes else ""

def dhcp_server_invalido(nombre):
    """Estado real del servidor DHCP: 'true', 'false', 'no existe' o el error.

    Verificacion de post-condicion: que los comandos no den error NO basta.
    El router puede aceptar los cuatro pasos y aun asi marcar el servidor
    como invalid si la interfaz no tiene IP o el gateway no pertenece a la
    red. En ese caso el servidor existe pero no reparte nada.
    """
    r = consultar(':put [:tostr [/ip dhcp-server get [find name=' + nombre +
                  '] invalid]]')
    bajo = (r or "").lower()
    if "no such item" in bajo:
        return "no existe"
    if bajo in ("true", "false"):
        return bajo
    return r


# --- Consultas en crudo para el panel RESULTADO ------------------------------

def print_identity():
    return consultar("system identity print")


def print_ips():
    return consultar("ip address print")


def print_dns():
    return consultar("ip dns print")


def print_rutas():
    return consultar("ip route print")


def print_dhcp_servers():
    return consultar("ip dhcp-server print")


def print_dhcp_networks():
    return consultar("ip dhcp-server network print")


def print_pools():
    return consultar("ip pool print")


def print_backups_router():
    return consultar("file print where type=backup")


def print_interfaces():
    return consultar("interface print")


# =============================================================================
#  SECCION 5 - BACKEND - OPERACIONES DE ADMINISTRACION
# =============================================================================
#  Cada funcion de esta seccion sigue siempre los mismos cinco pasos:
#     1. valida lo que escribio el usuario
#     2. comprueba que el router este vivo
#     3. ejecuta el comando (o la secuencia de comandos)
#     4. VERIFICA que el cambio quedara aplicado de verdad
#     5. devuelve (ok, titulo, detalle) para que la ventana lo muestre
#
#  El paso 4 es el que faltaba en la version anterior y el que hace que la
#  aplicacion no mienta.
# =============================================================================

def _sin_router():
    """Devuelve la terna de error si el router no responde, o None si si."""
    ok, detalle = hay_conexion()
    if ok:
        return None
    return (False, "Sin conexion con el router",
            "No se pudo contactar a " + IP + ".\n\n"
            "Detalle:\n" + detalle + "\n\n"
            "Revisa que el router este encendido, que el cable de red este\n"
            "conectado y que la llave " + LLAVE + " sea la correcta.")


def _fallo(titulo, salida):
    """Convierte una salida de error en (ok, titulo, detalle).

    Distingue 'el router dijo que no' de 'no hay router', porque al usuario le
    sirven acciones distintas en cada caso.
    """
    if es_error_conexion(salida):
        return (False, "Sin conexion con el router",
                "Se perdio la conexion con " + IP + " a mitad de la operacion.\n\n"
                "Detalle:\n" + salida)
    return (False, titulo, "El router respondio:\n" + (salida or "(sin respuesta)"))


# ------------------------------- IDENTITY ------------------------------------

def op_set_nombre(nombre):
    """Asigna el nombre (identity) del router."""
    ok, msg = validar_nombre(nombre, "nombre del router")
    if not ok:
        return False, "Nombre invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    nombre = limpiar(nombre)
    ok, salida = ejecutar("routername.sh", "system identity set name=" + nombre)
    if not ok:
        return _fallo("No se pudo asignar el nombre", salida)

    # Verificacion: se lo preguntamos al router en vez de confiar
    actual = consultar(":put [/system identity get name]").strip()
    if actual != nombre:
        return (False, "El nombre no quedo aplicado",
                "Se pidio '" + nombre + "' pero el router reporta '" + actual + "'.")

    return (True, "Nombre asignado",
            "El router se llama ahora: " + nombre + "\n\n" + print_identity())


# ----------------------------- DIRECCIONES IP --------------------------------

def op_crear_ip(direccion, interfaz, comentario):
    """Agrega una direccion IP a una interfaz."""
    ok, msg = validar_cidr(direccion)
    if not ok:
        return False, "Direccion invalida", msg
    ok, msg = validar_interfaz(interfaz)
    if not ok:
        return False, "Interfaz invalida", msg
    ok, msg = validar_comentario(comentario)
    if not ok:
        return False, "Comentario invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    direccion, interfaz = limpiar(direccion), limpiar(interfaz)
    comentario = limpiar(comentario)

    if existe_ip(direccion):
        return (False, "Esa IP ya existe",
                "El router ya tiene la direccion " + direccion + ".\n\n" + print_ips())

    # Sin este if se mandaba comment= vacio y el router rechazaba el comando
    cmd = "ip address add address=" + direccion + " interface=" + interfaz
    if comentario:
        cmd = cmd + ' comment="' + comentario + '"'

    ok, salida = ejecutar("create_IP.sh", cmd)
    if not ok:
        return _fallo("No se pudo crear la IP", salida)

    if not existe_ip(direccion):
        return (False, "La IP no aparece en el router",
                "El comando no dio error pero " + direccion +
                " no esta en la lista.\n\n" + print_ips())

    return (True, "Direccion IP creada",
            "IP " + direccion + " en la interfaz " + interfaz + "\n\n" + print_ips())


def op_eliminar_ip(direccion):
    """Elimina una IP buscandola POR DIRECCION, no por numero de fila.

    La version anterior hacia  ip address remove N , donde N era la posicion
    de la interfaz dentro de una lista. Si una interfaz tenia dos IPs, las
    llaves repetidas del diccionario se pisaban y se borraba la IP equivocada.
    """
    ok, msg = validar_cidr(direccion)
    if not ok:
        return False, "Direccion invalida", msg

    sin = _sin_router()
    if sin:
        return sin

    direccion = limpiar(direccion)

    if not existe_ip(direccion):
        return (False, "No existe esa IP",
                "El router no tiene la direccion " + direccion + ".\n\n" + print_ips())

    ok, salida = ejecutar("IPDelete.sh",
                          "ip address remove " + find_addr(direccion))
    if not ok:
        return _fallo("No se pudo eliminar la IP", salida)

    # Un remove sobre un find vacio no da error: sin esta comprobacion un
    # dedazo se veria exactamente igual que un exito.
    if existe_ip(direccion):
        return (False, "La IP sigue en el router",
                "El comando no dio error pero " + direccion +
                " todavia aparece.\n\n" + print_ips())

    return (True, "Direccion IP eliminada",
            "Se elimino " + direccion + "\n\n" + print_ips())


# ------------------------------ SERVIDOR DHCP --------------------------------

def op_crear_dhcp(interfaz, ip_interfaz, pool, rango, servidor, red, gateway, dns):
    """Crea un servidor DHCP completo en cuatro pasos y verifica el resultado.

    Los cuatro pasos son necesarios y en este orden:
        0. IP en la interfaz  -> sin ella el servidor nace INVALID
        1. Pool de direcciones
        2. Servidor DHCP apuntando al pool
        3. Red con gateway y DNS

    La version anterior no hacia el paso 0, y su dhcp.sh tenia la
    concatenacion mal escrita ("ranges="+$1 le manda al router
    ranges=+192.168...), ademas del nombre del pool fijo, lo que impedia
    crear un segundo servidor.
    """
    for valor, validador, etiqueta in (
            (interfaz, validar_interfaz, "Interfaz"),
            (ip_interfaz, validar_cidr, "IP de la interfaz"),
            (rango, validar_rango, "Rango del pool"),
            (red, validar_cidr, "Red"),
            (gateway, validar_ip, "Gateway")):
        ok, msg = validador(valor)
        if not ok:
            return False, "Dato invalido", etiqueta + ": " + msg

    for valor, etiqueta in ((pool, "nombre del pool"),
                            (servidor, "nombre del servidor")):
        ok, msg = validar_nombre(valor, etiqueta)
        if not ok:
            return False, "Dato invalido", msg

    dns = limpiar(dns)
    if dns:
        ok, msg = validar_lista_dns(dns)
        if not ok:
            return False, "DNS invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    interfaz, ip_interfaz = limpiar(interfaz), limpiar(ip_interfaz)
    pool, rango = limpiar(pool), limpiar(rango)
    servidor, red, gateway = limpiar(servidor), limpiar(red), limpiar(gateway)

    # RouterOS solo admite un servidor DHCP por interfaz
    ocupado = dhcp_server_de_interfaz(interfaz)
    if ocupado and ocupado != servidor:
        return (False, "La interfaz ya tiene servidor DHCP",
                interfaz + " ya esta ocupada por el servidor '" + ocupado + "'.\n\n"
                "RouterOS no admite dos servidores DHCP en el mismo puerto.\n"
                "Elimina el anterior con el boton ELIMINAR DHCP y vuelve a\n"
                "intentarlo.")

    cmd_red = "ip dhcp-server network add address=" + red + " gateway=" + gateway
    if dns:
        cmd_red = cmd_red + " dns-server=" + dns

    # tolerar=True: que el pool o la IP ya existan no es un fallo, el estado
    # que buscabamos ya esta puesto.
    pasos = [
        ("0) IP en " + interfaz, "create_ip_interface.sh",
         "ip address add address=" + ip_interfaz + " interface=" + interfaz, True),
        ("1) Pool " + pool, "create_dhcp_pool.sh",
         "ip pool add name=" + pool + " ranges=" + rango, True),
        ("2) Servidor " + servidor, "create_dhcp_server.sh",
         "ip dhcp-server add name=" + servidor + " interface=" + interfaz +
         " address-pool=" + pool + " disabled=no", True),
        ("3) Red y DNS", "create_dhcp_network.sh", cmd_red, True),
    ]

    todo_ok, reporte = correr_pasos(pasos)

    # Verificacion real: le preguntamos al router si el servidor quedo activo
    estado = dhcp_server_invalido(servidor)

    if estado == "false":
        veredicto = "SERVIDOR ACTIVO: el router lo acepta y ya reparte IPs."
    elif estado == "true":
        veredicto = ("SERVIDOR INVALIDO: el router lo creo pero no lo usa.\n"
                     "Causa tipica: la interfaz " + interfaz + " no tiene IP,\n"
                     "o el gateway " + gateway + " no pertenece a la red " + red + ".")
        todo_ok = False
    elif estado == "no existe":
        veredicto = ("EL SERVIDOR '" + servidor + "' NO EXISTE: no se llego a crear.\n"
                     "Mira arriba cual de los pasos fallo.")
        todo_ok = False
    else:
        veredicto = "NO SE PUDO VERIFICAR:\n" + str(estado)
        todo_ok = False

    titulo = "Servidor DHCP creado" if todo_ok else "Servidor DHCP con problemas"
    return (todo_ok, titulo,
            reporte + "\n\nVerificacion en el router:\n" + veredicto +
            "\n\nServidores DHCP:\n" + print_dhcp_servers())


def op_eliminar_dhcp(servidor, pool, red):
    """Elimina servidor, pool y red DHCP, en ese orden.

    El orden importa: el pool no se puede borrar mientras un servidor lo este
    usando. La version anterior solo borraba el servidor y dejaba huerfanos
    el pool y la red, que despues estorbaban al crear el siguiente.
    """
    ok, msg = validar_nombre(servidor, "nombre del servidor")
    if not ok:
        return False, "Dato invalido", msg

    pool, red = limpiar(pool), limpiar(red)
    if pool:
        ok, msg = validar_nombre(pool, "nombre del pool")
        if not ok:
            return False, "Dato invalido", msg
    if red:
        ok, msg = validar_cidr(red)
        if not ok:
            return False, "Red invalida", msg

    sin = _sin_router()
    if sin:
        return sin

    servidor = limpiar(servidor)

    pasos = [("1) Servidor " + servidor, "delete_dhcp_server.sh",
              "ip dhcp-server remove [find name=" + servidor + "]")]
    if pool:
        pasos.append(("2) Pool " + pool, "delete_dhcp_pool.sh",
                      "ip pool remove [find name=" + pool + "]"))
    if red:
        pasos.append(("3) Red " + red, "delete_dhcp_network.sh",
                      "ip dhcp-server network remove " + find_addr(red)))

    todo_ok, reporte = correr_pasos(pasos)

    # Comprobar que de verdad desaparecieron
    avisos = []
    if servidor in get_dhcp_servers():
        avisos.append("El servidor " + servidor + " sigue en el router.")
        todo_ok = False
    if red and existe_red_dhcp(red):
        avisos.append("La red " + red + " sigue en el router.")
        todo_ok = False

    detalle = reporte
    if avisos:
        detalle += "\n\nATENCION:\n" + "\n".join("  - " + a for a in avisos)
    detalle += ("\n\nServidores DHCP:\n" + print_dhcp_servers() +
                "\nRedes DHCP:\n" + print_dhcp_networks())

    return (todo_ok,
            "DHCP eliminado" if todo_ok else "DHCP eliminado con fallos",
            detalle)


# ---------------------------------- DNS --------------------------------------
#  se administra el
#  servicio DNS DEL ROUTER con  /ip dns set servers=... allow-remote-requests=
# -----------------------------------------------------------------------------

def op_configurar_dns(servidores, permitir_remoto):
    """Configura los servidores DNS del router.
    """
    ok, msg = validar_lista_dns(servidores)
    if not ok:
        return False, "DNS invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    servidores = limpiar(servidores)
    remoto = "yes" if permitir_remoto else "no"

    ok, salida = ejecutar("configurar_dns.sh",
                          "ip dns set servers=" + servidores +
                          " allow-remote-requests=" + remoto)
    if not ok:
        return _fallo("No se pudo configurar el DNS", salida)

    # Verificacion DESPUES de aplicar. Se comparan conjuntos porque el router
    # puede devolver los servidores en otro orden.
    actual = get_dns_router()
    esperado = lista_dns(servidores)
    obtenido = lista_dns(actual)

    if esperado != obtenido:
        return (False, "El DNS no quedo como se pidio",
                "Se pidieron: " + servidores + "\n"
                "El router reporta: " + (actual or "(vacio)") + "\n\n" + print_dns())

    return (True, "Servidor DNS configurado",
            "Servidores: " + servidores + "\n"
            "Peticiones remotas: " + remoto + "\n\n" + print_dns())


def op_eliminar_dns():
    """Deja el router sin servidores DNS y sin peticiones remotas."""
    sin = _sin_router()
    if sin:
        return sin

    ok, salida = ejecutar("eliminar_dns.sh",
                          'ip dns set servers="" allow-remote-requests=no')
    if not ok:
        return _fallo("No se pudo eliminar la configuracion DNS", salida)

    actual = get_dns_router()
    if actual:
        return (False, "El DNS sigue configurado",
                "El router todavia reporta: " + actual + "\n\n" + print_dns())

    return (True, "Configuracion DNS eliminada",
            "El router quedo sin servidores DNS.\n\n" + print_dns())


# ----------------------------- RUTAS ESTATICAS -------------------------------

def op_crear_ruta(destino, gateway, comentario):
    """Crea una ruta estatica."""
    ok, msg = validar_cidr(destino)
    if not ok:
        return False, "Destino invalido", msg
    ok, msg = validar_ip(gateway)
    if not ok:
        return False, "Gateway invalido", msg
    ok, msg = validar_comentario(comentario)
    if not ok:
        return False, "Comentario invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    destino, gateway = limpiar(destino), limpiar(gateway)
    comentario = limpiar(comentario)

    cmd = "ip route add dst-address=" + destino + " gateway=" + gateway
    if comentario:
        cmd = cmd + ' comment="' + comentario + '"'

    ok, salida = ejecutar("route_add.sh", cmd)
    if not ok:
        return _fallo("No se pudo crear la ruta", salida)

    if not existe_ruta_estatica(destino):
        return (False, "La ruta no aparece en el router",
                "El comando no dio error pero la ruta hacia " + destino +
                " no esta en la lista.\n\n" + print_rutas())

    return (True, "Ruta estatica creada",
            destino + " via " + gateway + "\n\nRutas estaticas ahora:\n" +
            (get_rutas_detalle() or "(ninguna)"))


def op_eliminar_ruta(destino):
    """Elimina una ruta estatica. No toca las que genera el propio router."""
    ok, msg = validar_cidr(destino)
    if not ok:
        return False, "Destino invalido", msg

    sin = _sin_router()
    if sin:
        return sin

    destino = limpiar(destino)

    if not existe_ruta_estatica(destino):
        return (False, "No existe esa ruta estatica",
                "El router no tiene una ruta estatica hacia " + destino + ".\n\n"
                "Rutas estaticas actuales:\n" + (get_rutas_detalle() or "(ninguna)"))

    # static=yes protege las rutas que el router crea solo para sus interfaces
    ok, salida = ejecutar("route_remove.sh",
                          "ip route remove [find dst-address=" + destino +
                          " static=yes]")
    if not ok:
        return _fallo("No se pudo eliminar la ruta", salida)

    if existe_ruta_estatica(destino):
        return (False, "La ruta sigue en el router",
                "El comando no dio error pero " + destino + " todavia aparece.")

    return (True, "Ruta estatica eliminada",
            "Se elimino " + destino + "\n\nRutas estaticas ahora:\n" +
            (get_rutas_detalle() or "(ninguna)"))


# -------------------------------- RESPALDOS ----------------------------------
#  Se mantiene el comportamiento del proyecto de Fernando: los respaldos se
#  traen al PC y se listan los del PC (no los del router), y ademas se pueden
#  eliminar desde la aplicacion.
# -----------------------------------------------------------------------------

def op_crear_respaldo():
    """Crea el respaldo en el router y lo trae al PC, comprobando cada paso.

    La version anterior lanzaba el script y esperaba 5 segundos fijos antes de
    copiar, sin mirar si algo habia fallado: siempre decia "respaldo creado".
    Aqui se espera a que el archivo aparezca de verdad, y se comprueba que
    llegue al PC y que no pese 0 bytes.
    """
    sin = _sin_router()
    if sin:
        return sin

    nombre = "backup_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    archivo = nombre + ".backup"
    destino = os.path.join(BACKUPS_DIR, archivo)

    # 1) Pedirle al router que lo guarde
    ok, salida = ejecutar("respaldoMK.sh", "system backup save name=" + nombre)
    if not ok:
        return _fallo("No se pudo crear el respaldo", salida)

    # 2) Esperar a que aparezca, en vez de un sleep fijo a ciegas: el router
    #    tarda un momento en escribirlo y ese tiempo no es constante.
    aparecio = False
    for _ in range(10):
        r = consultar(':put [:tostr [/file find name="' + archivo + '"]]')
        if r and not hubo_fallo(r):
            aparecio = True
            break
        time.sleep(1)

    if not aparecio:
        return (False, "El respaldo no aparecio en el router",
                "Se pidio guardar " + archivo + " pero el router no lo muestra\n"
                "despues de 10 segundos.\n\nRespaldos en el router:\n" +
                print_backups_router())

    # 3) Traerlo al PC con scp
    try:
        proc = subprocess.Popen(
            ["scp", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=" + str(TIMEOUT),
             "-i", LLAVE,
             USUARIO + "@" + IP + ":" + archivo, destino],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        salida_scp = proc.communicate()[0].decode("utf-8", "replace").strip()
    except OSError as e:
        return False, "No se pudo ejecutar scp", str(e)

    # 4) Comprobar que llego y que no esta vacio
    if proc.returncode != 0 or not os.path.exists(destino):
        return (False, "El respaldo quedo en el router pero no se copio",
                "scp respondio:\n" + (salida_scp or "(sin respuesta)") +
                "\n\nEl archivo " + archivo + " si existe en el router.")

    tam = os.path.getsize(destino)
    if tam == 0:
        os.remove(destino)
        return (False, "El respaldo llego vacio",
                "Se copio " + archivo + " pero pesaba 0 bytes, asi que se descarto.")

    return (True, "Respaldo creado",
            "Archivo:  " + archivo + "\n"
            "Guardado: " + destino + "\n"
            "Tamano:   " + str(round(tam / 1024.0, 1)) + " KiB\n\n" +
            listar_respaldos_texto())


def listar_respaldos():
    """Lista los .backup guardados en el PC, del mas nuevo al mas viejo."""
    try:
        archivos = [f for f in os.listdir(BACKUPS_DIR) if f.endswith(".backup")]
    except OSError:
        return []
    archivos.sort(reverse=True)
    return archivos


def listar_respaldos_texto():
    """Texto con nombre, tamano y fecha de cada respaldo guardado en el PC."""
    archivos = listar_respaldos()
    if not archivos:
        return ("Respaldos en este equipo:\n"
                "(todavia no hay ninguno)\n\nCarpeta: " + BACKUPS_DIR)

    lineas = ["Respaldos en este equipo:", "Carpeta: " + BACKUPS_DIR, ""]
    for f in archivos:
        ruta = os.path.join(BACKUPS_DIR, f)
        try:
            tam = os.path.getsize(ruta)
            fecha = datetime.fromtimestamp(os.path.getmtime(ruta))
            lineas.append(f.ljust(34) +
                          (str(round(tam / 1024.0, 1)) + " KiB").rjust(11) +
                          "   " + fecha.strftime("%d/%m/%Y %H:%M"))
        except OSError:
            lineas.append(f + "   (no se pudo leer)")
    return "\n".join(lineas)


def op_eliminar_respaldo(nombre):
    """Borra un respaldo del PC. No toca los del router."""
    nombre = limpiar(nombre)
    if not nombre:
        return False, "Sin seleccion", "No se ha seleccionado ningun respaldo."

    # Nunca construir una ruta con lo que venga de fuera sin comprobarla:
    # un nombre con ../ podria borrar cualquier archivo del sistema.
    if os.path.sep in nombre or nombre.startswith("."):
        return False, "Nombre invalido", "Nombre de respaldo no permitido."

    ruta = os.path.join(BACKUPS_DIR, nombre)
    if not os.path.isfile(ruta):
        return (False, "No existe ese respaldo",
                "No se encontro " + nombre + " en " + BACKUPS_DIR)

    try:
        os.remove(ruta)
    except OSError as e:
        return False, "No se pudo eliminar", str(e)

    return (True, "Respaldo eliminado",
            "Se elimino " + nombre + "\n\n" + listar_respaldos_texto())


# =============================================================================
#  SECCION 5B - BACKEND - AUTENTICACION SSH (llaves publica y privada)
# =============================================================================
#  Este bloque automatiza los tres pasos que antes habia que hacer a mano en
#  la terminal antes de poder usar la aplicacion:
#
#     1. ssh-keygen -t rsa -b 4096 -f ~/.ssh/mikrotik_tea_key
#     2. scp ~/.ssh/mikrotik_tea_key.pub admin@<ip>:/
#     3. (en el router)  /user ssh-keys import
#                          public-key-file=mikrotik_tea_key.pub user=admin
#
#  EL PROBLEMA DEL PASO 2
#  Es el unico momento del proyecto en el que hace falta la CONTRASENA del
#  router: la llave todavia no esta instalada, asi que scp no puede
#  autenticarse con ella. Y ssh y scp, por diseno, no leen la contrasena de
#  la entrada estandar ni de una variable de entorno: la piden directamente
#  al terminal.
#
#  POR QUE NO SE USA sshpass
#  La solucion habitual es la herramienta sshpass, pero tiene dos problemas:
#  es una dependencia mas que instalar, y sobre todo pone la contrasena en la
#  linea de comandos, donde queda visible para cualquier usuario de la
#  maquina con un simple  ps aux .
#
#  QUE SE HACE EN SU LUGAR
#  Se usa el modulo pty de la biblioteca estandar de Python. pty.fork() crea
#  un terminal falso, se lanza scp dentro de el, y cuando scp escribe
#  "password:" se le responde por ese terminal. Para scp es indistinguible de
#  una persona escribiendo. La contrasena viaja solo por memoria: nunca pasa
#  por la linea de comandos, ni por un archivo, ni queda en el historial.
# =============================================================================

import pty
import select
import signal


def _correr_con_password(argv, password, timeout=45):
    """Ejecuta un comando dentro de un terminal falso y le da la contrasena.

    Devuelve (codigo_de_salida, salida_completa).

    Se responde a un maximo de 3 peticiones de contrasena: si el router la
    rechaza, ssh vuelve a preguntar, y sin ese limite el bucle seguiria
    reintentando hasta agotar el timeout.
    """
    try:
        pid, fd = pty.fork()
    except OSError as e:
        return 1, "No se pudo crear el terminal: " + str(e)

    if pid == 0:
        # Proceso hijo: se convierte en scp / ssh / ssh-keygen
        try:
            os.execvp(argv[0], argv)
        except Exception:
            pass
        os._exit(127)

    # Proceso padre: lee lo que escribe el hijo y contesta cuando toca
    salida = []
    enviadas = 0
    inicio = time.time()
    estado = None

    while True:
        if time.time() - inicio > timeout:
            try:
                os.kill(pid, signal.SIGKILL)
                os.waitpid(pid, 0)
            except OSError:
                pass
            salida.append("\n[la operacion tardo mas de " + str(timeout) +
                          " segundos y se cancelo]")
            estado = 1
            break

        try:
            listos, _, _ = select.select([fd], [], [], 0.4)
        except (OSError, ValueError):
            break

        if listos:
            try:
                datos = os.read(fd, 4096)
            except OSError:
                # El hijo cerro el terminal: ha terminado
                break
            if not datos:
                break

            texto = datos.decode("utf-8", "replace")
            salida.append(texto)
            bajo = texto.lower()

            if ("password:" in bajo or "contrasena:" in bajo
                    or "contraseña:" in bajo) and enviadas < 3:
                try:
                    os.write(fd, (password + "\n").encode("utf-8"))
                    enviadas += 1
                except OSError:
                    break

            # Primera conexion: aceptar la huella del host
            elif "(yes/no" in bajo:
                try:
                    os.write(fd, b"yes\n")
                except OSError:
                    break
        else:
            terminado, codigo = os.waitpid(pid, os.WNOHANG)
            if terminado != 0:
                estado = codigo
                break

    try:
        os.close(fd)
    except OSError:
        pass

    if estado is None:
        try:
            _, estado = os.waitpid(pid, 0)
        except OSError:
            estado = 0

    codigo = os.WEXITSTATUS(estado) if os.WIFEXITED(estado) else 1
    texto = "".join(salida)

    # Se quitan las lineas donde solo aparece la peticion de contrasena, para
    # que el informe que ve el usuario quede limpio.
    limpio = "\n".join(l for l in texto.splitlines()
                       if "password" not in l.lower() and l.strip())
    return codigo, limpio.strip()


def op_guardar_conexion(ip, usuario, llave):
    """Cambia la IP, el usuario y la llave, y los deja guardados.

    Los tres valores son globales del modulo: en cuanto se cambian aqui, la
    siguiente llamada a _ssh() ya usa los nuevos. No hace falta reiniciar.

    Se validan antes de tocar nada, para no dejar la aplicacion apuntando a
    una direccion imposible.
    """
    global IP, USUARIO, LLAVE

    ip = limpiar(ip)
    usuario = limpiar(usuario)
    llave = limpiar(llave)

    ok, msg = validar_ip(ip)
    if not ok:
        return False, "IP invalida", msg

    ok, msg = validar_nombre(usuario, "usuario del router")
    if not ok:
        return False, "Usuario invalido", msg

    if not llave:
        return (False, "Falta la ruta de la llave",
                "Indica donde esta (o donde se va a crear) la llave privada.\n"
                "Por ejemplo:  ~/.ssh/mikrotik_tea_key")

    llave = os.path.expanduser(llave)

    if os.path.sep not in llave:
        return (False, "Ruta de llave invalida",
                "La ruta debe ser completa. Ejemplo:  ~/.ssh/mikrotik_tea_key")

    anterior = (IP, USUARIO, LLAVE)
    IP, USUARIO, LLAVE = ip, usuario, llave

    contenido = (
        "# Datos de conexion con el router MikroTik.\n"
        "# Lo escribe la ventana 'Conexion y llaves SSH', pero se puede\n"
        "# editar a mano con cualquier editor de texto.\n"
        "ip = " + ip + "\n"
        "usuario = " + usuario + "\n"
        "llave = " + llave + "\n"
    )

    try:
        with open(CONEXION_INI, "w", encoding="utf-8") as pf:
            pf.write(contenido)
    except OSError as e:
        # Si no se pudo guardar, se deja el cambio activo en esta sesion pero
        # se avisa de que no sobrevivira al cierre.
        return (True, "Datos cambiados, pero sin guardar",
                "Los datos se aplicaron para esta sesion:\n"
                "  " + usuario + "@" + ip + "\n"
                "  llave: " + llave + "\n\n"
                "No se pudo escribir " + CONEXION_INI + ":\n" + str(e) + "\n\n"
                "Al cerrar la aplicacion se volveran a los valores por defecto.")

    cambio = ""
    if anterior != (ip, usuario, llave):
        cambio = ("Antes: " + anterior[1] + "@" + anterior[0] + "\n"
                  "       llave: " + anterior[2] + "\n\n")

    # Se prueba la conexion con los datos nuevos, para que el usuario sepa de
    # inmediato si acerto o no, en vez de descubrirlo en la siguiente accion.
    conecta, detalle = hay_conexion()

    return (True, "Datos de conexion guardados",
            cambio +
            "Ahora: " + usuario + "@" + ip + "\n"
            "       llave: " + llave + "\n\n"
            "Guardado en: " + CONEXION_INI + "\n\n" +
            ("Prueba de conexion: CORRECTA\n\n" + detalle
             if conecta else
             "Prueba de conexion: NO responde todavia.\n\n" + detalle + "\n\n"
             "Si aun no has instalado la llave, hazlo con los pasos 1 y 2 de\n"
             "esta misma ventana."))


def llave_publica():
    """Ruta de la llave publica: la privada mas .pub"""
    return LLAVE + ".pub"


def estado_llaves():
    """Informe del estado actual de las llaves y de la autenticacion.

    Devuelve un diccionario con lo que necesita la ventana para decidir que
    botones tienen sentido en cada momento.
    """
    privada = os.path.isfile(LLAVE)
    publica = os.path.isfile(llave_publica())

    permisos = ""
    if privada:
        try:
            permisos = oct(os.stat(LLAVE).st_mode & 0o777)[2:]
        except OSError:
            permisos = "?"

    autentica = False
    detalle = "No se probo la autenticacion."
    if privada:
        autentica, detalle = hay_conexion()

    return {"privada": privada, "publica": publica, "permisos": permisos,
            "autentica": autentica, "detalle": detalle}


def texto_estado_llaves():
    """Version legible del estado, para el panel RESULTADO."""
    e = estado_llaves()
    lineas = [
        "Llave privada : " + LLAVE,
        "                " + ("EXISTE (permisos " + e["permisos"] + ")"
                              if e["privada"] else "NO EXISTE"),
        "Llave publica : " + llave_publica(),
        "                " + ("EXISTE" if e["publica"] else "NO EXISTE"),
        "",
        "Router        : " + USUARIO + "@" + IP,
        "Autenticacion : " + ("FUNCIONA, no pide contrasena"
                              if e["autentica"] else "NO FUNCIONA"),
    ]
    if not e["autentica"]:
        lineas.append("")
        lineas.append("Detalle:")
        lineas.append(e["detalle"])

    if e["privada"] and e["permisos"] not in ("600", "400"):
        lineas.append("")
        lineas.append("AVISO: la llave privada deberia tener permisos 600.")
        lineas.append("ssh se niega a usar una llave que puedan leer otros usuarios.")

    return "\n".join(lineas)


def op_generar_llaves(bits=4096, sobrescribir=False):
    """Paso 1: genera el par de llaves con ssh-keygen.

    Equivale a:
        ssh-keygen -t rsa -b 4096 -f <LLAVE> -N "" -C "<usuario>@<ip>"

    -N ""  crea la llave sin passphrase. Es lo que hace falta aqui: si la
           llave pidiera passphrase, la aplicacion no podria usarla sin
           intervencion en cada comando.
    """
    if bits not in (2048, 3072, 4096):
        return False, "Tamano invalido", "El tamano debe ser 2048, 3072 o 4096 bits."

    if os.path.isfile(LLAVE) and not sobrescribir:
        return (False, "La llave ya existe",
                "Ya hay una llave privada en:\n  " + LLAVE + "\n\n"
                "Si la sobrescribes, el router dejara de reconocerte hasta que\n"
                "vuelvas a copiar la nueva llave publica.\n\n"
                "Marca la casilla de sobrescribir si es lo que quieres.")

    carpeta = os.path.dirname(LLAVE)
    try:
        if not os.path.isdir(carpeta):
            os.makedirs(carpeta, 0o700)
    except OSError as e:
        return False, "No se pudo crear la carpeta", str(e)

    # ssh-keygen se niega a sobrescribir sin preguntar, asi que se borran antes
    for archivo in (LLAVE, llave_publica()):
        if os.path.isfile(archivo):
            try:
                os.remove(archivo)
            except OSError as e:
                return False, "No se pudo borrar la llave anterior", str(e)

    argv = ["ssh-keygen", "-t", "rsa", "-b", str(bits), "-f", LLAVE,
            "-N", "", "-C", USUARIO + "@" + IP]

    try:
        proc = subprocess.Popen(argv, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        salida = proc.communicate()[0].decode("utf-8", "replace").strip()
    except OSError as e:
        return (False, "No se encontro ssh-keygen",
                "No se pudo ejecutar ssh-keygen: " + str(e) + "\n\n"
                "Instalalo con:  sudo apt install openssh-client")

    if proc.returncode != 0 or not os.path.isfile(LLAVE):
        return False, "No se pudo generar la llave", salida or "(sin respuesta)"

    # Permisos 600: ssh RECHAZA una llave privada que puedan leer otros
    # usuarios del sistema. Es la causa mas comun de "Permission denied".
    try:
        os.chmod(LLAVE, 0o600)
        os.chmod(llave_publica(), 0o644)
    except OSError:
        pass

    return (True, "Par de llaves generado",
            "Se genero un par de llaves RSA de " + str(bits) + " bits.\n\n"
            "Privada (NO se comparte): " + LLAVE + "  [permisos 600]\n"
            "Publica (va al router)  : " + llave_publica() + "\n\n" +
            salida + "\n\n"
            "Siguiente paso: copiar la llave publica al router.")


def op_copiar_llave_al_router(password):
    """Paso 2 y 3: copia la llave publica al router y la importa.

    Equivale a hacer a mano:
        scp <LLAVE>.pub <usuario>@<ip>:/
        ssh <usuario>@<ip> "/user ssh-keys import
                              public-key-file=<archivo> user=<usuario>"

    Es la UNICA operacion de todo el proyecto que necesita la contrasena del
    router, porque la llave todavia no esta instalada.
    """
    if not os.path.isfile(llave_publica()):
        return (False, "No hay llave publica",
                "No existe " + llave_publica() + ".\n\n"
                "Genera primero el par de llaves.")

    if not password:
        return (False, "Falta la contrasena",
                "Para copiar la llave hace falta la contrasena del usuario '" +
                USUARIO + "' en el router.\n\n"
                "Es la unica vez que se necesita: despues de este paso, todo\n"
                "funciona con la llave y no se vuelve a pedir.")

    nombre = os.path.basename(llave_publica())
    reporte = []

    # --- Paso 2: copiar el archivo al router --------------------------------
    argv_scp = ["scp",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=" + str(TIMEOUT),
                "-o", "PubkeyAuthentication=no",   # forzar el uso de contrasena
                llave_publica(),
                USUARIO + "@" + IP + ":/"]

    codigo, salida = _correr_con_password(argv_scp, password)
    reporte.append("1) Copiar " + nombre + " al router".ljust(38, ".") +
                   (" OK" if codigo == 0 else " FALLO"))
    if codigo != 0:
        if "permission denied" in salida.lower():
            return (False, "Contrasena incorrecta",
                    "\n".join(reporte) + "\n\n"
                    "El router rechazo la contrasena del usuario '" + USUARIO + "'.\n\n"
                    "Detalle:\n" + salida)
        return (False, "No se pudo copiar la llave al router",
                "\n".join(reporte) + "\n\nDetalle:\n" +
                (salida or "(sin respuesta)"))

    # --- Paso 3: importarla dentro de RouterOS ------------------------------
    # Este ssh todavia va con contrasena: la llave esta copiada como archivo,
    # pero el router aun no la tiene asociada al usuario.
    argv_ssh = ["ssh", "-T",
                "-o", "StrictHostKeyChecking=accept-new",
                "-o", "ConnectTimeout=" + str(TIMEOUT),
                "-o", "PubkeyAuthentication=no",
                USUARIO + "@" + IP,
                "/user ssh-keys import public-key-file=" + nombre +
                " user=" + USUARIO]

    codigo, salida = _correr_con_password(argv_ssh, password)
    fallo_import = codigo != 0 or hubo_fallo(salida)
    reporte.append("2) Importar la llave en RouterOS".ljust(38, ".") +
                   (" OK" if not fallo_import else " FALLO"))
    if fallo_import:
        return (False, "No se pudo importar la llave en el router",
                "\n".join(reporte) + "\n\n"
                "El archivo si se copio, pero el router no lo acepto.\n\n"
                "Detalle:\n" + (salida or "(sin respuesta)") + "\n\n"
                "Puedes importarla a mano entrando al router:\n"
                "  /user ssh-keys import public-key-file=" + nombre +
                " user=" + USUARIO)

    # --- Verificacion: entrar YA SIN contrasena -----------------------------
    # Es la unica prueba que vale. Que los dos comandos anteriores no dieran
    # error no garantiza que la autenticacion por llave funcione.
    ok, detalle = hay_conexion()
    reporte.append("3) Probar el acceso sin contrasena".ljust(38, ".") +
                   (" OK" if ok else " FALLO"))

    if not ok:
        return (False, "La llave se copio pero el acceso sigue fallando",
                "\n".join(reporte) + "\n\nDetalle:\n" + detalle)

    return (True, "Autenticacion por llave configurada",
            "\n".join(reporte) + "\n\n"
            "Ya se puede entrar al router sin contrasena.\n\n"
            "Respuesta del router:\n" + detalle)


def op_probar_autenticacion():
    """Comprueba que la llave funciona, sin cambiar nada."""
    if not os.path.isfile(LLAVE):
        return (False, "No hay llave privada",
                "No existe " + LLAVE + ".\n\nGenera primero el par de llaves.")

    ok, detalle = hay_conexion()
    if not ok:
        return (False, "La autenticacion por llave no funciona",
                "No se pudo entrar a " + USUARIO + "@" + IP +
                " con la llave.\n\nDetalle:\n" + detalle + "\n\n" +
                texto_estado_llaves())

    return (True, "Autenticacion correcta",
            "Se entro a " + USUARIO + "@" + IP + " con la llave, sin contrasena.\n\n"
            "Respuesta del router:\n" + detalle)


def op_ver_llave_publica():
    """Muestra el contenido de la llave publica, para copiarla a mano."""
    if not os.path.isfile(llave_publica()):
        return (False, "No hay llave publica",
                "No existe " + llave_publica() + ".\n\nGenera primero el par.")
    try:
        with open(llave_publica(), "r", encoding="utf-8") as pf:
            contenido = pf.read().strip()
    except OSError as e:
        return False, "No se pudo leer la llave publica", str(e)

    return (True, "Llave publica",
            llave_publica() + "\n\n" + contenido + "\n\n"
            "Esta es la que va al router. La privada NUNCA se comparte.")


def op_corregir_permisos():
    """Pone la llave privada en 600.

    ssh RECHAZA usar una llave privada que puedan leer otros usuarios del
    sistema, y el mensaje que da ("UNPROTECTED PRIVATE KEY FILE") desconcierta
    bastante la primera vez. Este boton lo arregla en un clic.
    """
    if not os.path.isfile(LLAVE):
        return False, "No hay llave privada", "No existe " + LLAVE
    try:
        os.chmod(LLAVE, 0o600)
    except OSError as e:
        return False, "No se pudieron cambiar los permisos", str(e)
    return (True, "Permisos corregidos",
            "La llave privada quedo con permisos 600.\n\n" + texto_estado_llaves())


# =============================================================================
#  SECCION 6 - BACKEND - MONITOREO EN SEGUNDO PLANO
# =============================================================================
#  El monitoreo NO se hace desde Python: lo hacen cuatro scripts de shell que
#  corren en segundo plano en un esquema productor/consumidor.
#
#      PRODUCTOR                          CONSUMIDOR
#      verificarinterfaces.sh   ---->     monitorearinterfaces.sh
#        pregunta al router               interpreta y escribe
#        y escribe datosinterfaces.txt    estado1/2.txt y trafico1/2.txt
#
#      verificarconexion.sh     ---->     monitorearip.sh
#        hace ping y escribe               interpreta y escribe
#        datosconexion.txt                 estado.txt
#
#  Python solo LEE esos archivos cada segundo y repinta. Asi la interfaz
#  grafica nunca se queda bloqueada esperando a la red.
#
#  El productor escribe en un archivo .tmp y despues hace mv. En Linux el mv
#  dentro del mismo sistema de archivos es atomico, asi que el consumidor
#  nunca llega a leer un archivo a medio escribir.
# =============================================================================

def _lanzar(script, *args):
    """Lanza un script de monitoreo en segundo plano, desatendido."""
    cmd = ["bash", script] + [str(a) for a in args]
    try:
        subprocess.Popen(cmd,
                         stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return True
    except OSError:
        return False


def _matar(script):
    """Mata las instancias de un script de monitoreo.

    El patron entre corchetes  [v]erificar...  evita que el propio pkill se
    encuentre a si mismo en la lista de procesos.
    """
    nombre = os.path.basename(script)
    patron = "[" + nombre[0] + "]" + nombre[1:]
    subprocess.call("pkill -f '" + patron + "'", shell=True,
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def iniciar_monitoreo(interfaz_1, interfaz_2):
    """Arranca los cuatro scripts de monitoreo. Si ya corrian, los reinicia."""
    detener_monitoreo()

    # Limpiar lecturas viejas para no mostrar el estado de la sesion anterior
    for archivo in (F_ESTADO_ICMP, F_DATOS_PING, F_DATOS_INTERFACES,
                    F_ESTADO_1, F_ESTADO_2, F_TRAFICO_1, F_TRAFICO_2):
        try:
            with open(archivo, "w", encoding="utf-8") as pf:
                pf.write("")
        except OSError:
            pass

    _lanzar(SH_VERIFICAR_INTERFACES, LLAVE, USUARIO, IP,
            interfaz_1, interfaz_2, str(TIMEOUT), F_DATOS_INTERFACES)
    _lanzar(SH_MONITOREAR_INTERFACES, F_DATOS_INTERFACES,
            F_ESTADO_1, F_TRAFICO_1, F_ESTADO_2, F_TRAFICO_2)
    _lanzar(SH_VERIFICAR_CONEXION, IP, F_DATOS_PING)
    _lanzar(SH_MONITOREAR_IP, IP, F_DATOS_PING, F_ESTADO_ICMP)


def detener_monitoreo():
    """Detiene todos los scripts de monitoreo."""
    for script in (SH_VERIFICAR_INTERFACES, SH_MONITOREAR_INTERFACES,
                   SH_VERIFICAR_CONEXION, SH_MONITOREAR_IP):
        _matar(script)


def leer_runtime(archivo):
    """Lee un archivo de runtime. Devuelve cadena vacia si aun no existe."""
    try:
        with open(archivo, "r", encoding="utf-8") as pf:
            return pf.read().strip()
    except (IOError, OSError):
        return ""


def formato_trafico(bits):
    """Convierte bits por segundo en un texto legible."""
    try:
        b = int(bits)
    except (ValueError, TypeError):
        return "0 bps"
    if b >= 1000000000:
        return str(round(b / 1000000000.0, 2)) + " Gbps"
    if b >= 1000000:
        return str(round(b / 1000000.0, 2)) + " Mbps"
    if b >= 1000:
        return str(round(b / 1000.0, 2)) + " kbps"
    return str(b) + " bps"


# =============================================================================
#  A PARTIR DE AQUI EMPIEZA EL FRONTEND
# =============================================================================
#  Todo lo que sigue va dentro de  if __name__ == "__main__"  a proposito.
#
#  Ejecutar el archivo directamente  ->  se construye y se abre la ventana.
#  Importarlo desde otro programa    ->  NO se abre nada, solo queda
#                                        disponible el backend.
#
#  Eso es lo que permite que mikrotik_web.py reutilice exactamente las
#  mismas funciones op_* sin duplicar una sola linea de logica, y es la
#  prueba practica de que las dos capas estan de verdad separadas.
# =============================================================================

if __name__ == "__main__":

    if not HAY_GUI:
        raise SystemExit(
            "Falta Tkinter o CustomTkinter.\n"
            "  sudo apt install python3-tk\n"
            "  pip install customtkinter Pillow")



    # =============================================================================
    #  SECCION 7 - FRONTEND - UTILIDADES COMUNES DE LA INTERFAZ
    # =============================================================================
    #  A partir de aqui empieza la capa de presentacion. Nada de lo que sigue
    #  arma comandos de RouterOS: todo se lo pide a las funciones op_* del
    #  backend y se limita a mostrar el resultado.
    # =============================================================================

    ctk.set_appearance_mode(APARIENCIA)
    ctk.set_default_color_theme(TEMA)

    # Paleta y tipografias (se conserva la identidad visual del proyecto original)
    COLOR_BARRA = "#00B4D8"
    COLOR_BOTON = "black"
    COLOR_OK = "green"
    COLOR_BORRAR = "red"
    COLOR_CONSULTA = "white"
    COLOR_FONDO_PANEL = "#F5F7FA"

    v0 = ctk.CTk()
    v0.title("CONTROL MIKROTIK ROUTER")
    v0.geometry("1020x790+180+40")
    v0.minsize(940, 700)

    text_1 = ctk.CTkFont(family="Arial", size=20, weight="bold")
    text_2 = ctk.CTkFont(family="Helvetica", size=15, weight="bold")
    text_3 = ctk.CTkFont(family="Roboto", size=13)
    text_mono = ctk.CTkFont(family="Consolas", size=12)


    def cargar_imagen(nombre, lado=120):
        """Carga una imagen del semaforo desde assets/.

        Se prueba primero .png porque conserva la transparencia y el semaforo se
        ve recortado sobre el fondo del panel; el .gif se deja como alternativa.
        Devuelve None si falta el archivo o si no hay PIL, para que la ventana de
        monitoreo siga funcionando (con texto en vez de luces) en vez de reventar
        al abrirse.
        """
        if not HAY_PIL:
            return None
        for extension in (".png", ".gif"):
            ruta = os.path.join(ASSETS_DIR, nombre + extension)
            if os.path.isfile(ruta):
                try:
                    return ctk.CTkImage(light_image=Image.open(ruta),
                                        dark_image=Image.open(ruta),
                                        size=(lado, lado))
                except Exception:
                    return None
        return None


    def mostrar(titulo, texto):
        """Escribe en el panel RESULTADO de la ventana principal.

        IMPORTANTE: el cuadro de texto se crea UNA sola vez, al final del archivo,
        y aqui solo se le cambia el contenido.

        En la version anterior cada consulta y cada refresco del monitoreo creaba
        un cuadro de texto NUEVO encima del anterior. Con el monitoreo activo eso
        apilaba un widget por segundo -unos 2400 en una demostracion de 40
        minutos- y la aplicacion se degradaba a ojos vista.
        """
        panel_resultado.configure(state="normal")
        panel_resultado.delete("1.0", END)
        panel_resultado.insert(END, "== " + str(titulo) + " ==\n\n" + str(texto))
        panel_resultado.configure(state="disabled")
        panel_resultado.see("1.0")


    def trabajando(texto="Consultando al router, espera un momento..."):
        """Avisa en el panel de que hay una operacion en curso y repinta ya.

        update_idletasks fuerza a Tk a dibujar antes de seguir: sin esto el
        mensaje no se veria, porque la ventana queda congelada mientras el ssh
        hace su viaje de ida y vuelta.
        """
        mostrar("En curso", texto)
        v0.update_idletasks()


    def resultado(terna, ventana=None, cerrar_si_ok=False, al_terminar=None):
        """Muestra el (ok, titulo, detalle) que devolvio el backend.

        Es el unico punto del programa donde se decide si una operacion se
        anuncia como exito o como fallo, y esa decision la toma el backend, no la
        ventana. En la version anterior cada boton mostraba "operacion exitosa"
        sin preguntarle a nadie.
        """
        ok, titulo, detalle = terna
        mostrar(titulo, detalle)

        if ok:
            messagebox.showinfo("INFO", message=titulo,
                                parent=ventana if ventana else v0)
            if callable(al_terminar):
                al_terminar()
            if cerrar_si_ok and ventana is not None:
                ventana.destroy()
        else:
            messagebox.showerror("ERROR", message=titulo,
                                 parent=ventana if ventana else v0)
        return ok


    def nueva_ventana(titulo, geometria):
        """Crea una ventana secundaria ya configurada.

        Ninguna ventana secundaria llama a mainloop(). En la version anterior
        cada Toplevel terminaba con su propio v1.mainloop(), lo que anida bucles
        de eventos de Tk: es incorrecto y podia colgar la aplicacion al cerrar
        las ventanas en cierto orden. Con transient() + grab_set() se consigue el
        comportamiento modal que se buscaba, y de forma correcta.
        """
        win = ctk.CTkToplevel(v0)
        win.title(titulo)
        win.geometry(geometria)
        win.transient(v0)
        win.grab_set()
        win.focus()
        return win


    def etiqueta(padre, texto, x, y, fuente=None):
        """Atajo para colocar una etiqueta."""
        lbl = ctk.CTkLabel(padre, text=texto, font=fuente or text_3)
        lbl.place(x=x, y=y)
        return lbl


    def caja(padre, variable, x, y, ancho=230, pista=""):
        """Atajo para colocar una caja de texto, con su texto de ayuda al lado.

        La ayuda se pone en una etiqueta gris a la derecha y NO con el
        placeholder_text de CustomTkinter. Motivo: CustomTkinter desactiva el
        placeholder en cuanto la caja lleva un textvariable asociado -no puede
        distinguir "vacia" de "con valor"-, y como aqui todas las cajas usan
        textvariable, los ejemplos nunca llegaban a verse.
        """
        ent = ctk.CTkEntry(padre, textvariable=variable, width=ancho)
        ent.place(x=x, y=y)
        if pista:
            ctk.CTkLabel(padre, text=pista, font=text_3,
                         text_color="#8A8F98").place(x=x + ancho + 10, y=y + 2)
        return ent


    def boton(padre, texto, x, y, comando, color_texto=COLOR_CONSULTA,
              ancho=150, fuente=None):
        """Atajo para colocar un boton con el estilo del proyecto."""
        btn = ctk.CTkButton(padre, text=texto, fg_color=COLOR_BOTON,
                            text_color=color_texto, command=comando,
                            width=ancho, font=fuente or text_3)
        btn.place(x=x, y=y)
        return btn


    def combo(padre, variable, valores, x, y, ancho=230):
        """Atajo para colocar un combobox ya preseleccionado."""
        cmb = ctk.CTkComboBox(padre, variable=variable, values=valores or [""],
                              width=ancho, font=text_3)
        cmb.place(x=x, y=y)
        variable.set(valores[0] if valores else "")
        return cmb


    def refrescar_combo(cmb, variable, valores):
        """Recarga un combobox conservando la seleccion si sigue existiendo."""
        valores = valores or []
        anterior = variable.get()
        cmb.configure(values=valores or [""])
        if anterior in valores:
            variable.set(anterior)
        else:
            variable.set(valores[0] if valores else "")


    def confirmar(titulo, mensaje, ventana=None):
        """Pide confirmacion antes de una operacion destructiva."""
        return messagebox.askyesno(titulo, message=mensaje,
                                   parent=ventana if ventana else v0)


    # =============================================================================
    #  SECCION 8 - FRONTEND - VENTANAS DE CADA MODULO
    # =============================================================================

    # ------------------------------------------------------------------ DHCP ----

    def ventana_dhcp():
        """Crear y eliminar servidores DHCP, y consultar pool / server / network."""
        win = nueva_ventana("CONFIGURAR SERVIDOR DHCP", "900x620+260+120")

        trabajando("Leyendo las interfaces del router...")
        interfaces = get_interfaces()
        servidores = get_dhcp_servers()
        pools = get_pools()
        redes = get_redes_dhcp()
        mostrar("Servidor DHCP", "Completa el formulario y pulsa CREAR DHCP.")

        # --- Variables ---
        v_interfaz = ctk.StringVar()
        v_ip_interfaz = ctk.StringVar(value="192.168.200.1/24")
        v_pool = ctk.StringVar(value="dhcp_pool")
        v_rango = ctk.StringVar(value="192.168.200.100-192.168.200.150")
        v_servidor = ctk.StringVar(value="dhcp_server")
        v_red = ctk.StringVar(value="192.168.200.0/24")
        v_gateway = ctk.StringVar(value="192.168.200.1")
        v_dns = ctk.StringVar(value="8.8.8.8")

        v_del_servidor = ctk.StringVar()
        v_del_pool = ctk.StringVar()
        v_del_red = ctk.StringVar()

        # --- Columna izquierda: crear ---
        ctk.CTkLabel(win, text="CREAR SERVIDOR DHCP", font=text_2).place(x=20, y=16)
        ctk.CTkLabel(win, text="Los campos traen valores de ejemplo. El gateway debe ser la IP de la\n"
                               "interfaz y el rango debe caer dentro de la red; si no, no reparte nada.",
                     font=text_3, text_color="#666", justify="left").place(x=20, y=42)

        etiqueta(win, "Interfaz:", 20, 90)
        cmb_interfaz = combo(win, v_interfaz, interfaces, 170, 88)

        etiqueta(win, "IP de la interfaz:", 20, 128)
        caja(win, v_ip_interfaz, 170, 126)

        etiqueta(win, "Nombre del pool:", 20, 166)
        caja(win, v_pool, 170, 164)

        etiqueta(win, "Rango de IPs:", 20, 204)
        caja(win, v_rango, 170, 202)

        etiqueta(win, "Nombre del server:", 20, 242)
        caja(win, v_servidor, 170, 240)

        etiqueta(win, "Red (address):", 20, 280)
        caja(win, v_red, 170, 278)

        etiqueta(win, "Gateway:", 20, 318)
        caja(win, v_gateway, 170, 316)

        etiqueta(win, "DNS (opcional):", 20, 356)
        caja(win, v_dns, 170, 354, pista="Ej: 8.8.8.8")

        def recargar_todo():
            """Vuelve a leer del router lo que alimenta los combobox."""
            refrescar_combo(cmb_interfaz, v_interfaz, get_interfaces())
            refrescar_combo(cmb_del_servidor, v_del_servidor, get_dhcp_servers())
            refrescar_combo(cmb_del_pool, v_del_pool, get_pools())
            refrescar_combo(cmb_del_red, v_del_red, get_redes_dhcp())

        def crear():
            trabajando("Creando el servidor DHCP (son cuatro pasos)...")
            resultado(op_crear_dhcp(v_interfaz.get(), v_ip_interfaz.get(),
                                    v_pool.get(), v_rango.get(), v_servidor.get(),
                                    v_red.get(), v_gateway.get(), v_dns.get()),
                      ventana=win, al_terminar=recargar_todo)

        boton(win, "CREAR DHCP", 170, 400, crear, COLOR_OK, ancho=230, fuente=text_2)

        # --- Columna derecha: eliminar ---
        ctk.CTkLabel(win, text="ELIMINAR SERVIDOR DHCP", font=text_2).place(x=480, y=16)
        ctk.CTkLabel(win, text="Se elimina en este orden: servidor, pool y red. El pool no se\n"
                               "puede borrar mientras un servidor lo este usando.",
                     font=text_3, text_color="#666", justify="left").place(x=480, y=42)

        etiqueta(win, "Servidor:", 480, 90)
        cmb_del_servidor = combo(win, v_del_servidor, servidores, 610, 88, ancho=250)

        etiqueta(win, "Pool:", 480, 128)
        cmb_del_pool = combo(win, v_del_pool, pools, 610, 126, ancho=250)

        etiqueta(win, "Red:", 480, 166)
        cmb_del_red = combo(win, v_del_red, redes, 610, 164, ancho=250)

        def eliminar():
            servidor = v_del_servidor.get()
            if not servidor:
                messagebox.showwarning("AVISO",
                                       message="No hay un servidor DHCP seleccionado.",
                                       parent=win)
                return
            if not confirmar("CONFIRMAR ELIMINACION",
                             "Se va a eliminar:\n\n"
                             "  Servidor: " + servidor + "\n"
                             "  Pool:     " + (v_del_pool.get() or "(ninguno)") + "\n"
                             "  Red:      " + (v_del_red.get() or "(ninguna)") + "\n\n"
                             "Estas seguro?", win):
                return
            trabajando("Eliminando el servidor DHCP...")
            resultado(op_eliminar_dhcp(servidor, v_del_pool.get(), v_del_red.get()),
                      ventana=win, al_terminar=recargar_todo)

        boton(win, "ELIMINAR DHCP", 610, 208, eliminar, COLOR_BORRAR,
              ancho=250, fuente=text_2)

        # --- Consultas ---
        ctk.CTkLabel(win, text="CONSULTAS", font=text_2).place(x=480, y=270)

        def consulta(titulo, funcion):
            def accion():
                trabajando()
                mostrar(titulo, funcion() or "(sin datos)")
            return accion

        boton(win, "Consultar Pool", 480, 306,
              consulta("Pools de direcciones", print_pools), ancho=180)
        boton(win, "Consultar DHCP", 480, 346,
              consulta("Servidores DHCP", print_dhcp_servers), ancho=180)
        boton(win, "Consultar Network", 480, 386,
              consulta("Redes DHCP", print_dhcp_networks), ancho=180)
        boton(win, "Refrescar listas", 680, 306, lambda: (trabajando(), recargar_todo(),
              mostrar("Listas actualizadas", "Se releyeron del router las interfaces,\n"
                      "servidores, pools y redes.")), ancho=180)

        ctk.CTkLabel(win, text="El resultado de las consultas aparece en el panel\n"
                               "RESULTADO de la ventana principal.",
                     font=text_3, text_color="#666", justify="left").place(x=480, y=430)


    # ------------------------------------------------------------------- DNS ----

    def ventana_dns():
        """Configurar, eliminar y consultar el servicio DNS del router.

        Se conserva el comportamiento del proyecto original: aqui se administra
        /ip dns del router (servers y allow-remote-requests). El DNS que reparte
        el servidor DHCP a sus clientes se configura al crear el DHCP.
        """
        win = nueva_ventana("CONFIGURAR SERVIDOR DNS", "620x330+380+220")

        v_servidores = ctk.StringVar()
        v_remoto = ctk.StringVar(value="no")

        ctk.CTkLabel(win, text="SERVICIO DNS DEL ROUTER", font=text_2).place(x=20, y=18)

        etiqueta(win, "Servidores DNS:", 20, 66)
        caja(win, v_servidores, 180, 64, ancho=280, pista="Ej: 8.8.8.8,8.8.4.4")

        etiqueta(win, "Allow Remote Requests:", 20, 108)
        ctk.CTkCheckBox(win, variable=v_remoto, text="", onvalue="yes",
                        offvalue="no").place(x=200, y=108)

        def cargar_actual():
            """Muestra en la caja lo que el router tiene puesto ahora mismo."""
            trabajando("Leyendo la configuracion DNS del router...")
            actual = get_dns_router()
            v_servidores.set(actual)
            mostrar("Configuracion DNS actual", print_dns() or "(sin datos)")

        def configurar():
            trabajando("Aplicando la configuracion DNS...")
            resultado(op_configurar_dns(v_servidores.get(),
                                        v_remoto.get() == "yes"), ventana=win)

        def eliminar():
            if not confirmar("CONFIRMAR ELIMINACION",
                             "Se va a borrar la configuracion DNS del router\n"
                             "(servers vacio y allow-remote-requests=no).\n\n"
                             "Estas seguro?", win):
                return
            trabajando("Eliminando la configuracion DNS...")
            if resultado(op_eliminar_dns(), ventana=win):
                v_servidores.set("")

        def consultar_dns():
            trabajando()
            mostrar("Configuracion DNS del router", print_dns() or "(sin datos)")

        boton(win, "Configurar DNS", 20, 160, configurar, COLOR_OK, ancho=180)
        boton(win, "Eliminar DNS", 215, 160, eliminar, COLOR_BORRAR, ancho=180)
        boton(win, "Consultar DNS", 410, 160, consultar_dns, ancho=180)
        boton(win, "Traer configuracion actual a la caja", 20, 210, cargar_actual,
              ancho=380)

        ctk.CTkLabel(win, text="Los servidores se separan con coma y sin espacios.\n"
                               "El resultado aparece en el panel RESULTADO de la ventana principal.",
                     font=text_3, text_color="#666", justify="left").place(x=20, y=262)


    # --------------------------------------------------------- RUTAS ESTATICAS --

    def ventana_rutas():
        """Crear, eliminar y consultar rutas estaticas."""
        win = nueva_ventana("RUTAS ESTATICAS", "1000x400+250+200")

        trabajando("Leyendo las rutas del router...")
        rutas = get_rutas_estaticas()
        mostrar("Rutas estaticas", get_rutas_detalle() or "(no hay rutas estaticas)")

        v_destino = ctk.StringVar()
        v_gateway = ctk.StringVar()
        v_comentario = ctk.StringVar()
        v_borrar = ctk.StringVar()

        ctk.CTkLabel(win, text="CREAR RUTA ESTATICA", font=text_2).place(x=20, y=18)

        etiqueta(win, "Dst-Address:", 20, 62)
        caja(win, v_destino, 150, 60, pista="Ej: 192.168.10.0/24")

        etiqueta(win, "Gateway:", 20, 100)
        caja(win, v_gateway, 150, 98, pista="Ej: 192.168.56.1")

        etiqueta(win, "Comentario:", 20, 138)
        caja(win, v_comentario, 150, 136, pista="Ej: Ruta hacia la red interna")

        def recargar():
            refrescar_combo(cmb_borrar, v_borrar, get_rutas_estaticas())

        def crear():
            trabajando("Creando la ruta estatica...")
            if resultado(op_crear_ruta(v_destino.get(), v_gateway.get(),
                                       v_comentario.get()),
                         ventana=win, al_terminar=recargar):
                v_destino.set("")
                v_gateway.set("")
                v_comentario.set("")

        boton(win, "CREAR RUTA", 150, 182, crear, COLOR_OK, ancho=230, fuente=text_2)

        # --- Eliminar ---
        ctk.CTkLabel(win, text="ELIMINAR RUTA ESTATICA", font=text_2).place(x=620, y=18)
        ctk.CTkLabel(win, text="Solo aparecen las rutas estaticas. Las que crea el\n"
                               "propio router para sus interfaces no se pueden borrar.",
                     font=text_3, text_color="#666", justify="left").place(x=620, y=44)

        etiqueta(win, "Ruta:", 620, 100)
        cmb_borrar = combo(win, v_borrar, rutas, 680, 98, ancho=280)

        def eliminar():
            destino = v_borrar.get()
            if not destino:
                messagebox.showwarning("AVISO", message="No hay una ruta seleccionada.",
                                       parent=win)
                return
            if not confirmar("CONFIRMAR ELIMINACION",
                             'Se va a eliminar la ruta hacia "' + destino + '".\n\n'
                             "Estas seguro?", win):
                return
            trabajando("Eliminando la ruta...")
            resultado(op_eliminar_ruta(destino), ventana=win, al_terminar=recargar)

        boton(win, "ELIMINAR RUTA", 680, 140, eliminar, COLOR_BORRAR,
              ancho=280, fuente=text_2)

        def consultar_rutas():
            trabajando()
            mostrar("Tabla de rutas del router", print_rutas() or "(sin datos)")

        boton(win, "Consultar todas las rutas", 680, 190, consultar_rutas, ancho=280)
        boton(win, "Refrescar lista", 680, 230,
              lambda: (trabajando(), recargar(),
                       mostrar("Rutas estaticas",
                               get_rutas_detalle() or "(no hay rutas estaticas)")),
              ancho=280)


    # -------------------------------------------------------------- RESPALDOS ---

    def ventana_respaldos():
        """Crear, listar y eliminar respaldos.

        Se conserva el comportamiento del proyecto original: el respaldo se crea
        en el router, se copia al PC y lo que se LISTA son los respaldos
        guardados en el PC (no los del router), con opcion de eliminarlos.
        """
        win = nueva_ventana("RESPALDOS DEL ROUTER", "720x360+340+240")

        v_respaldo = ctk.StringVar()

        ctk.CTkLabel(win, text="RESPALDOS", font=text_2).place(x=20, y=18)
        ctk.CTkLabel(win, text="Crear respaldo guarda una copia en el router y la trae a este\n"
                               "equipo. La lista de abajo son los respaldos de este equipo.",
                     font=text_3, text_color="#666", justify="left").place(x=20, y=44)

        mostrar("Respaldos", listar_respaldos_texto())

        def recargar():
            refrescar_combo(cmb_respaldos, v_respaldo, listar_respaldos())

        def crear():
            if not confirmar("CONFIRMAR RESPALDO",
                             "Se va a crear un respaldo del router y copiarlo a\n" +
                             BACKUPS_DIR + "\n\nContinuar?", win):
                return
            trabajando("Creando el respaldo. Esto puede tardar unos segundos...")
            resultado(op_crear_respaldo(), ventana=win, al_terminar=recargar)

        def listar_pc():
            mostrar("Respaldos en este equipo", listar_respaldos_texto())

        def listar_router():
            trabajando()
            mostrar("Respaldos en el router", print_backups_router() or "(sin datos)")

        boton(win, "Crear Respaldo", 20, 110, crear, COLOR_OK, ancho=200)
        boton(win, "Listar Respaldos", 240, 110, listar_pc, ancho=200)
        boton(win, "Ver los del router", 460, 110, listar_router, ancho=200)

        etiqueta(win, "Respaldo guardado:", 20, 190)
        cmb_respaldos = combo(win, v_respaldo, listar_respaldos(), 20, 220, ancho=380)

        def eliminar():
            nombre = v_respaldo.get()
            if not nombre:
                messagebox.showwarning("AVISO",
                                       message="No se ha seleccionado ningun respaldo.",
                                       parent=win)
                return
            if not confirmar("ELIMINAR RESPALDO",
                             "Se va a eliminar el archivo:\n\n" + nombre + "\n\n"
                             "Solo se borra de este equipo, no del router.\n\n"
                             "Estas seguro?", win):
                return
            resultado(op_eliminar_respaldo(nombre), ventana=win, al_terminar=recargar)

        boton(win, "ELIMINAR RESPALDO", 420, 220, eliminar, COLOR_BORRAR,
              ancho=240, fuente=text_2)


    # -------------------------------------------------------------- MONITOREO ---

    def ventana_monitoreo():
        """Monitoreo en tiempo real de DOS interfaces del router.

        Cumple el requisito del enunciado: dos interfaces a la vez, mostrando
        estado Up/Down, trafico de entrada y trafico de salida. En la version
        anterior solo se podia monitorear una interfaz.

        La ventana no consulta al router: solo LEE cada segundo los archivos que
        dejan los scripts de monitoreo en runtime/. Por eso la interfaz no se
        congela aunque el router tarde en responder.
        """
        win = nueva_ventana("MONITOREO DE INTERFACES", "860x560+280+140")

        trabajando("Leyendo las interfaces del router...")
        interfaces = get_interfaces()
        mostrar("Monitoreo", "Selecciona las dos interfaces y activa el servicio\n"
                             "con la casilla Enable/Disable.")

        img_on = cargar_imagen("on", 110)
        img_off = cargar_imagen("off", 110)
        img_gris = cargar_imagen("gris", 110)
        img_icmp_on = cargar_imagen("on", 46)
        img_icmp_off = cargar_imagen("off", 46)
        img_icmp_gris = cargar_imagen("gris", 46)

        # Se guardan como atributo de la ventana para que el recolector de basura
        # de Python no se lleve las imagenes mientras se estan mostrando.
        win.imagenes = [img_on, img_off, img_gris,
                        img_icmp_on, img_icmp_off, img_icmp_gris]

        v_if1 = ctk.StringVar(value=INTERFAZ_1)
        v_if2 = ctk.StringVar(value=INTERFAZ_2)
        v_check = ctk.StringVar(value="0")

        # Si las interfaces por defecto no existen en este router, se toman las
        # dos primeras que haya, para que la ventana sirva sin tocar el codigo.
        if interfaces:
            if v_if1.get() not in interfaces:
                v_if1.set(interfaces[0])
            if v_if2.get() not in interfaces:
                v_if2.set(interfaces[1] if len(interfaces) > 1 else interfaces[0])

        # --- Barra superior: seleccion de interfaces ---
        ctk.CTkLabel(win, text="Interfaz 1:", font=text_3).place(x=20, y=20)
        cmb1 = ctk.CTkComboBox(win, variable=v_if1, values=interfaces or [""],
                               width=170, font=text_3)
        cmb1.place(x=105, y=18)

        ctk.CTkLabel(win, text="Interfaz 2:", font=text_3).place(x=300, y=20)
        cmb2 = ctk.CTkComboBox(win, variable=v_if2, values=interfaces or [""],
                               width=170, font=text_3)
        cmb2.place(x=385, y=18)

        ck = ctk.CTkCheckBox(win, variable=v_check, text="Enable / Disable",
                             onvalue="1", offvalue="0", font=text_2)
        ck.place(x=600, y=20)

        lbl_servicio = ctk.CTkLabel(win, text="Servicio detenido", font=text_3,
                                    text_color="#a01313")
        lbl_servicio.place(x=600, y=50)

        # --- Paneles de las dos interfaces ---
        def crear_panel(x, titulo_var):
            """Crea el bloque visual de una interfaz y devuelve sus widgets.

            Los widgets se crean UNA sola vez; el refresco solo les cambia el
            texto y la imagen. Es la correccion de la fuga de widgets que tenia
            la version anterior.
            """
            marco = ctk.CTkFrame(win, width=380, height=300, corner_radius=10,
                                 fg_color=COLOR_FONDO_PANEL, border_width=1,
                                 border_color="#D0D5DD")
            marco.place(x=x, y=80)
            marco.pack_propagate(False)

            lbl_nombre = ctk.CTkLabel(marco, text=titulo_var.get(), font=text_2)
            lbl_nombre.place(x=20, y=14)

            lbl_img = ctk.CTkLabel(marco, text="", image=img_gris)
            lbl_img.place(x=135, y=46)

            lbl_estado = ctk.CTkLabel(marco, text="Esperando datos...", font=text_2,
                                      text_color="#666")
            lbl_estado.place(x=20, y=172)

            lbl_rx = ctk.CTkLabel(marco, text="Trafico IN :  --", font=text_mono)
            lbl_rx.place(x=20, y=210)

            lbl_tx = ctk.CTkLabel(marco, text="Trafico OUT:  --", font=text_mono)
            lbl_tx.place(x=20, y=238)

            return {"nombre": lbl_nombre, "img": lbl_img, "estado": lbl_estado,
                    "rx": lbl_rx, "tx": lbl_tx}

        p1 = crear_panel(20, v_if1)
        p2 = crear_panel(440, v_if2)

        # --- Indicador ICMP del router ---
        marco_icmp = ctk.CTkFrame(win, width=800, height=90, corner_radius=10,
                                  fg_color=COLOR_FONDO_PANEL, border_width=1,
                                  border_color="#D0D5DD")
        marco_icmp.place(x=20, y=400)
        marco_icmp.pack_propagate(False)

        ctk.CTkLabel(marco_icmp, text="Alcance del router (ping ICMP a " + IP + ")",
                     font=text_2).place(x=20, y=14)
        lbl_icmp_img = ctk.CTkLabel(marco_icmp, text="", image=img_icmp_gris)
        lbl_icmp_img.place(x=700, y=20)
        lbl_icmp = ctk.CTkLabel(marco_icmp, text="Esperando datos...", font=text_2,
                                text_color="#666")
        lbl_icmp.place(x=20, y=48)

        # --- Bucle de refresco ---
        # El identificador del after se guarda para poder cancelarlo al cerrar la
        # ventana. En la version anterior se usaba una variable global y, si se
        # desactivaba el servicio sin haberlo activado antes, after_cancel(None)
        # lanzaba una excepcion.
        estado_refresco = {"id": None, "activo": False}

        def pintar(panel, archivo_estado, archivo_trafico, nombre_interfaz):
            panel["nombre"].configure(text=nombre_interfaz)

            estado = leer_runtime(archivo_estado)
            trafico = leer_runtime(archivo_trafico).split()
            rx = trafico[0] if len(trafico) > 0 else "0"
            tx = trafico[1] if len(trafico) > 1 else "0"

            if estado == "1":
                panel["img"].configure(image=img_on)
                panel["estado"].configure(text="UP", text_color="#1a7f37")
            elif estado == "0":
                panel["img"].configure(image=img_off)
                panel["estado"].configure(text="DOWN", text_color="#a01313")
            else:
                panel["img"].configure(image=img_gris)
                panel["estado"].configure(text="Esperando datos...", text_color="#666")

            panel["rx"].configure(text="Trafico IN :  " + formato_trafico(rx))
            panel["tx"].configure(text="Trafico OUT:  " + formato_trafico(tx))

        def refrescar():
            if not estado_refresco["activo"]:
                return

            pintar(p1, F_ESTADO_1, F_TRAFICO_1, v_if1.get())
            pintar(p2, F_ESTADO_2, F_TRAFICO_2, v_if2.get())

            icmp = leer_runtime(F_ESTADO_ICMP)
            if icmp == "1":
                lbl_icmp_img.configure(image=img_icmp_on)
                lbl_icmp.configure(text="EL ROUTER RESPONDE", text_color="#1a7f37")
            elif icmp == "0":
                lbl_icmp_img.configure(image=img_icmp_off)
                lbl_icmp.configure(text="EL ROUTER NO RESPONDE", text_color="#a01313")
            else:
                lbl_icmp_img.configure(image=img_icmp_gris)
                lbl_icmp.configure(text="Esperando datos...", text_color="#666")

            estado_refresco["id"] = win.after(REFRESCO_MS, refrescar)

        def activar():
            if1, if2 = v_if1.get(), v_if2.get()

            for valor in (if1, if2):
                ok, msg = validar_interfaz(valor)
                if not ok:
                    messagebox.showwarning("AVISO", message=msg, parent=win)
                    v_check.set("0")
                    return

            if if1 == if2:
                messagebox.showwarning("AVISO",
                                       message="Selecciona dos interfaces distintas.",
                                       parent=win)
                v_check.set("0")
                return

            cmb1.configure(state="disabled")
            cmb2.configure(state="disabled")
            iniciar_monitoreo(if1, if2)

            estado_refresco["activo"] = True
            refrescar()

            lbl_servicio.configure(text="Servicio activo", text_color="#1a7f37")
            mostrar("Monitoreo activo",
                    "Monitoreando " + if1 + " y " + if2 + ".\n\n"
                    "Los scripts verificarinterfaces.sh y monitorearinterfaces.sh\n"
                    "corren en segundo plano y escriben en runtime/. La ventana\n"
                    "solo lee esos archivos cada segundo.")

        def desactivar(avisar=True):
            estado_refresco["activo"] = False
            if estado_refresco["id"] is not None:
                try:
                    win.after_cancel(estado_refresco["id"])
                except Exception:
                    pass
                estado_refresco["id"] = None

            detener_monitoreo()
            cmb1.configure(state="normal")
            cmb2.configure(state="normal")
            lbl_servicio.configure(text="Servicio detenido", text_color="#a01313")

            for panel in (p1, p2):
                panel["img"].configure(image=img_gris)
                panel["estado"].configure(text="Detenido", text_color="#666")
                panel["rx"].configure(text="Trafico IN :  --")
                panel["tx"].configure(text="Trafico OUT:  --")
            lbl_icmp_img.configure(image=img_icmp_gris)
            lbl_icmp.configure(text="Detenido", text_color="#666")

            if avisar:
                mostrar("Monitoreo detenido",
                        "Se detuvieron los scripts de monitoreo.")

        def cambio_check():
            if v_check.get() == "1":
                activar()
            else:
                desactivar()

        ck.configure(command=cambio_check)

        def al_cerrar():
            """Al cerrar la ventana se detienen SIEMPRE los scripts.

            La version anterior impedia cerrar la ventana mientras el servicio
            estuviera activo. Eso protegia de dejar procesos huerfanos, pero era
            incomodo; aqui simplemente se limpian solos.
            """
            desactivar(avisar=False)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", al_cerrar)

        boton(win, "Consultar interfaces", 20, 500,
              lambda: (trabajando(),
                       mostrar("Interfaces del router", print_interfaces() or "(sin datos)")),
              ancho=220)
        boton(win, "Refrescar lista de interfaces", 260, 500,
              lambda: (trabajando(),
                       cmb1.configure(values=get_interfaces() or [""]),
                       cmb2.configure(values=get_interfaces() or [""]),
                       mostrar("Interfaces", "Lista de interfaces actualizada.")),
              ancho=260)


    # ------------------------------------------- CONEXION Y LLAVES SSH ----

    def ventana_llaves_ssh():
        """Datos de conexion + generacion e instalacion de las llaves SSH.

        Automatiza los tres pasos que antes habia que hacer a mano en la
        terminal antes de poder usar la aplicacion:

            1. ssh-keygen -t rsa -b 4096 -f ~/.ssh/mikrotik_tea_key
            2. scp ~/.ssh/mikrotik_tea_key.pub admin@<ip>:/
            3. /user ssh-keys import public-key-file=... user=admin

        Y ademas deja cambiar la IP, el usuario y la ruta de la llave sin
        tocar el codigo, para que el proyecto se pueda usar contra otro router
        o en la maquina de otro integrante del equipo.
        """
        win = nueva_ventana("CONEXION Y LLAVES SSH", "880x700+260+50")

        v_ip = ctk.StringVar(value=IP)
        v_usuario = ctk.StringVar(value=USUARIO)
        v_llave = ctk.StringVar(value=LLAVE)
        v_bits = ctk.StringVar(value="4096")
        v_sobrescribir = ctk.StringVar(value="0")
        v_password = ctk.StringVar()

        ctk.CTkLabel(win, text="CONEXION Y AUTENTICACION POR LLAVE SSH",
                     font=text_2).place(x=20, y=14)
        ctk.CTkLabel(win, text="Todo lo que hace falta para que la aplicacion entre al router sin contrasena.\n"
                               "Los pasos 1 y 2 se hacen una sola vez por equipo.",
                     font=text_3, text_color="#666", justify="left").place(x=20, y=38)

        # =====================================================================
        #  Datos de conexion
        # =====================================================================
        marco_con = ctk.CTkFrame(win, width=840, height=130, corner_radius=10,
                                 fg_color=COLOR_FONDO_PANEL, border_width=1,
                                 border_color="#D0D5DD")
        marco_con.place(x=20, y=84)
        marco_con.pack_propagate(False)

        ctk.CTkLabel(marco_con, text="Datos de conexion del router",
                     font=text_2).place(x=16, y=10)

        ctk.CTkLabel(marco_con, text="IP del router:", font=text_3).place(x=16, y=46)
        ctk.CTkEntry(marco_con, textvariable=v_ip, width=160).place(x=125, y=44)

        ctk.CTkLabel(marco_con, text="Usuario:", font=text_3).place(x=310, y=46)
        ctk.CTkEntry(marco_con, textvariable=v_usuario, width=140).place(x=375, y=44)

        ctk.CTkLabel(marco_con, text="Llave privada:", font=text_3).place(x=16, y=88)
        ctk.CTkEntry(marco_con, textvariable=v_llave, width=440).place(x=125, y=86)

        def guardar_conexion():
            trabajando("Guardando y probando la conexion...")
            ok = resultado(op_guardar_conexion(v_ip.get(), v_usuario.get(),
                                               v_llave.get()), ventana=win)
            if ok:
                # Los globales cambiaron: se repinta todo lo que los muestra
                v_ip.set(IP)
                v_usuario.set(USUARIO)
                v_llave.set(LLAVE)
                lbl_pass.configure(text="Contrasena de " + USUARIO + ":")
                actualizar_cabecera()
                recargar_listas_principal()
                refrescar_estado()

        ctk.CTkButton(marco_con, text="Guardar y probar", fg_color=COLOR_BOTON,
                      text_color=COLOR_OK, command=guardar_conexion, font=text_3,
                      width=190).place(x=630, y=44)
        ctk.CTkLabel(marco_con, text="Se guarda en conexion.ini",
                     font=text_3, text_color="#8A8F98").place(x=630, y=90)

        # =====================================================================
        #  Estado actual
        # =====================================================================
        marco_est = ctk.CTkFrame(win, width=840, height=120, corner_radius=10,
                                 fg_color=COLOR_FONDO_PANEL, border_width=1,
                                 border_color="#D0D5DD")
        marco_est.place(x=20, y=226)
        marco_est.pack_propagate(False)

        ctk.CTkLabel(marco_est, text="Estado actual", font=text_2).place(x=16, y=10)
        lbl_estado = ctk.CTkLabel(marco_est, text="Comprobando...", font=text_mono,
                                  justify="left", text_color="#444")
        lbl_estado.place(x=16, y=38)

        def refrescar_estado(mostrar_en_panel=False):
            """Relee el estado de las llaves y lo pinta.

            Se actualiza la MISMA etiqueta, no se crea una nueva: mismo
            criterio que en el resto de la aplicacion.
            """
            e = estado_llaves()
            lineas = [
                "Llave privada : " + ("existe (permisos " + e["permisos"] + ")"
                                      if e["privada"] else "NO existe"),
                "Llave publica : " + ("existe" if e["publica"] else "NO existe"),
                "Autenticacion : " + ("FUNCIONA, el router no pide contrasena"
                                      if e["autentica"] else "todavia NO funciona"),
            ]
            if e["privada"] and e["permisos"] not in ("600", "400"):
                lineas.append("AVISO: la llave privada deberia estar en 600.")

            lbl_estado.configure(text="\n".join(lineas),
                                 text_color="#1a7f37" if e["autentica"] else "#a01313")

            if mostrar_en_panel:
                mostrar("Estado de la autenticacion SSH", texto_estado_llaves())

        # =====================================================================
        #  Paso 1 - Generar el par de llaves
        # =====================================================================
        ctk.CTkLabel(win, text="Paso 1  -  Generar el par de llaves en este equipo",
                     font=text_2).place(x=20, y=364)
        ctk.CTkLabel(win, text="La privada se queda aqui y no se comparte nunca. La publica es la que va al router.",
                     font=text_3, text_color="#666").place(x=20, y=388)

        ctk.CTkLabel(win, text="Tamano:", font=text_3).place(x=20, y=420)
        ctk.CTkComboBox(win, variable=v_bits, values=["2048", "3072", "4096"],
                        width=110, font=text_3).place(x=90, y=418)

        ctk.CTkCheckBox(win, variable=v_sobrescribir, text="Sobrescribir si ya existe",
                        onvalue="1", offvalue="0", font=text_3).place(x=225, y=420)

        def generar():
            if v_sobrescribir.get() == "1" and os.path.isfile(LLAVE):
                if not confirmar("SOBRESCRIBIR LA LLAVE",
                                 "Se va a borrar la llave actual y crear una nueva.\n\n"
                                 "El router dejara de reconocerte hasta que hagas\n"
                                 "tambien el paso 2.\n\nEstas seguro?", win):
                    return
            trabajando("Generando el par de llaves...")
            resultado(op_generar_llaves(int(v_bits.get()), v_sobrescribir.get() == "1"),
                      ventana=win, al_terminar=refrescar_estado)

        boton(win, "1. Generar llaves", 465, 418, generar, COLOR_OK, ancho=180)
        boton(win, "Ver llave publica", 660, 418,
              lambda: resultado(op_ver_llave_publica(), ventana=win), ancho=180)

        # =====================================================================
        #  Paso 2 - Copiar la llave al router
        # =====================================================================
        ctk.CTkLabel(win, text="Paso 2  -  Copiar la llave publica al router e importarla",
                     font=text_2).place(x=20, y=468)
        ctk.CTkLabel(win, text="Unico momento de todo el proyecto en que hace falta la contrasena del router:\n"
                               "la llave todavia no esta instalada. Se usa una sola vez, no se guarda en ningun\n"
                               "sitio y no pasa por la linea de comandos.",
                     font=text_3, text_color="#666", justify="left").place(x=20, y=492)

        lbl_pass = ctk.CTkLabel(win, text="Contrasena de " + USUARIO + ":", font=text_3)
        lbl_pass.place(x=20, y=556)
        ctk.CTkEntry(win, textvariable=v_password, width=230, show="*").place(x=185, y=554)

        def copiar():
            if not v_password.get():
                messagebox.showwarning("AVISO",
                                       message="Escribe la contrasena del usuario '" +
                                               USUARIO + "' en el router.", parent=win)
                return
            trabajando("Copiando la llave al router e importandola...")
            ok = resultado(op_copiar_llave_al_router(v_password.get()),
                           ventana=win, al_terminar=refrescar_estado)
            if ok:
                # La contrasena se borra en cuanto deja de hacer falta
                v_password.set("")

        boton(win, "2. Copiar al router", 435, 554, copiar, COLOR_OK, ancho=190)

        def todo():
            """Encadena los tres pasos, parando en cuanto uno falle."""
            if not v_password.get():
                messagebox.showwarning("AVISO",
                                       message="Para hacerlo todo de una vez hace falta\n"
                                               "la contrasena del router.", parent=win)
                return
            if not confirmar("CONFIGURAR TODO",
                             "Se va a:\n"
                             "  1. generar un par de llaves nuevo\n"
                             "  2. copiarlo al router e importarlo\n"
                             "  3. comprobar el acceso sin contrasena\n\n"
                             "Si ya habia una llave, se sustituye.\n\nContinuar?", win):
                return

            trabajando("Paso 1 de 3: generando el par de llaves...")
            ok, titulo, detalle = op_generar_llaves(int(v_bits.get()), True)
            if not ok:
                resultado((ok, titulo, detalle), ventana=win)
                return

            trabajando("Paso 2 de 3: copiando la llave al router...")
            terna = op_copiar_llave_al_router(v_password.get())
            refrescar_estado()
            resultado((terna[0], terna[1], "Paso 1: " + titulo + "\n\n" + terna[2]),
                      ventana=win)
            if terna[0]:
                v_password.set("")

        boton(win, "HACER TODO DE UNA VEZ", 640, 554, todo, COLOR_OK, ancho=200)

        # =====================================================================
        #  Paso 3 - Comprobar
        # =====================================================================
        ctk.CTkLabel(win, text="Paso 3  -  Comprobar", font=text_2).place(x=20, y=604)

        def probar():
            trabajando("Probando la autenticacion con la llave...")
            resultado(op_probar_autenticacion(), ventana=win,
                      al_terminar=refrescar_estado)

        def permisos():
            resultado(op_corregir_permisos(), ventana=win,
                      al_terminar=refrescar_estado)

        boton(win, "3. Probar autenticacion", 20, 638, probar, ancho=210)
        boton(win, "Corregir permisos (600)", 245, 638, permisos, ancho=210)
        boton(win, "Refrescar estado", 470, 638,
              lambda: refrescar_estado(mostrar_en_panel=True), ancho=180)

        refrescar_estado()


    # =============================================================================
    #  SECCION 9 - FRONTEND - VENTANA PRINCIPAL
    # =============================================================================

    # --- Barra superior ---
    barra = ctk.CTkFrame(v0, height=46, corner_radius=0, fg_color=COLOR_BARRA)
    barra.pack(side="top", fill="x")
    ctk.CTkLabel(barra, text="CONTROL MIKROTIK ROUTER", font=text_1,
                 text_color="white").pack(pady=8)

    lbl_cabecera = ctk.CTkLabel(
        v0, text="Router: " + USUARIO + "@" + IP + "   |   llave: " + LLAVE,
        font=text_3, text_color="#666")
    lbl_cabecera.pack(pady=(8, 0))


    def actualizar_cabecera():
        """Repinta la linea de datos del router.

        Hace falta porque la IP, el usuario y la llave se pueden cambiar en
        caliente desde la ventana de conexion, sin reiniciar la aplicacion.
        """
        lbl_cabecera.configure(
            text="Router: " + USUARIO + "@" + IP + "   |   llave: " + LLAVE)

    # --- Zona central: dos columnas ---
    central = ctk.CTkFrame(v0, fg_color="transparent")
    central.pack(fill="x", padx=20, pady=(12, 0))

    col_izq = ctk.CTkFrame(central, width=560, height=372, corner_radius=10,
                           fg_color=COLOR_FONDO_PANEL, border_width=1,
                           border_color="#D0D5DD")
    col_izq.pack(side="left", fill="y")
    col_izq.pack_propagate(False)

    col_der = ctk.CTkFrame(central, width=400, height=372, corner_radius=10,
                           fg_color=COLOR_FONDO_PANEL, border_width=1,
                           border_color="#D0D5DD")
    col_der.pack(side="right", fill="y", padx=(16, 0))
    col_der.pack_propagate(False)

    # --- Columna izquierda: nombre del router y direcciones IP ---
    name = ctk.StringVar()
    ipaddress = ctk.StringVar()
    interface = ctk.StringVar()
    comment = ctk.StringVar()
    combo_ip_borrar = ctk.StringVar()

    ctk.CTkLabel(col_izq, text="NOMBRE DEL ROUTER", font=text_2).place(x=20, y=16)

    ctk.CTkLabel(col_izq, text="Router Name:", font=text_3).place(x=20, y=52)
    ctk.CTkEntry(col_izq, textvariable=name, width=250).place(x=140, y=50)
    ctk.CTkLabel(col_izq, text="Ej: UNAH-CORTES", font=text_3,
                 text_color="#8A8F98").place(x=400, y=52)


    def accion_set_nombre():
        trabajando("Asignando el nombre al router...")
        if resultado(op_set_nombre(name.get())):
            name.set("")


    def accion_consultar_nombre():
        trabajando()
        mostrar("Nombre actual del router", print_identity() or "(sin datos)")


    ctk.CTkButton(col_izq, text="Save", fg_color=COLOR_BOTON, text_color=COLOR_OK,
                  command=accion_set_nombre, font=text_3,
                  width=120).place(x=140, y=88)
    ctk.CTkButton(col_izq, text="Consultar Router Name", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=accion_consultar_nombre,
                  font=text_3, width=200).place(x=270, y=88)

    ctk.CTkLabel(col_izq, text="DIRECCION IPv4", font=text_2).place(x=20, y=126)
    ctk.CTkLabel(col_izq, text="La direccion debe llevar mascara. Ej: 192.168.56.10/24",
                 font=text_3, text_color="#8A8F98").place(x=20, y=148)

    ctk.CTkLabel(col_izq, text="IP Address:", font=text_3).place(x=20, y=172)
    ctk.CTkEntry(col_izq, textvariable=ipaddress, width=180).place(x=140, y=170)

    ctk.CTkLabel(col_izq, text="Interface:", font=text_3).place(x=20, y=210)
    cmb_interfaces = ctk.CTkComboBox(col_izq, variable=interface, values=[""],
                                     width=180, font=text_3)
    cmb_interfaces.place(x=140, y=208)

    ctk.CTkLabel(col_izq, text="Comment:", font=text_3).place(x=20, y=248)
    ctk.CTkEntry(col_izq, textvariable=comment, width=180).place(x=140, y=246)
    ctk.CTkLabel(col_izq, text="(opcional)", font=text_3,
                 text_color="#8A8F98").place(x=20, y=268)

    ctk.CTkLabel(col_izq, text="Eliminar IP:", font=text_3).place(x=340, y=172)
    cmb_ips = ctk.CTkComboBox(col_izq, variable=combo_ip_borrar, values=[""],
                              width=190, font=text_3)
    cmb_ips.place(x=340, y=200)

    # Debajo del combo se dice a que interfaz pertenece la IP elegida. Sin esto,
    # con dos direcciones parecidas en interfaces distintas no habia forma de
    # saber cual se estaba a punto de borrar.
    lbl_ip_interfaz = ctk.CTkLabel(col_izq, text="", font=text_3,
                                   text_color="#8A8F98")
    lbl_ip_interfaz.place(x=340, y=232)

    # Diccionario direccion -> interfaz. Se llena al refrescar las listas, para
    # que mostrar la interfaz no cueste una consulta SSH cada vez que el
    # usuario despliega el combo.
    mapa_ip_interfaz = {}


    def actualizar_etiqueta_interfaz(*_):
        """Escribe debajo del combo la interfaz de la IP seleccionada."""
        direccion = combo_ip_borrar.get()
        interfaz = mapa_ip_interfaz.get(direccion, "")
        lbl_ip_interfaz.configure(text=("en la interfaz " + interfaz) if interfaz
                                  else ("" if not direccion else "interfaz desconocida"))


    combo_ip_borrar.trace_add("write", actualizar_etiqueta_interfaz)


    def recargar_listas_principal():
        """Relee del router lo que alimenta los combobox de la ventana principal."""
        refrescar_combo(cmb_interfaces, interface, get_interfaces())

        # Una sola consulta trae la direccion y su interfaz emparejadas, en vez
        # de dos consultas por separado que despues habria que casar por
        # posicion (que es justo lo que fallaba en la version anterior).
        pares = get_ips_con_interfaz()
        mapa_ip_interfaz.clear()
        mapa_ip_interfaz.update(dict(pares))
        refrescar_combo(cmb_ips, combo_ip_borrar, [d for d, _ in pares])
        actualizar_etiqueta_interfaz()


    def accion_crear_ip():
        trabajando("Creando la direccion IP...")
        if resultado(op_crear_ip(ipaddress.get(), interface.get(), comment.get()),
                     al_terminar=recargar_listas_principal):
            ipaddress.set("")
            comment.set("")


    def accion_eliminar_ip():
        direccion = combo_ip_borrar.get()
        if not direccion:
            messagebox.showwarning("AVISO", message="No hay una IP seleccionada.")
            return
        interfaz = mapa_ip_interfaz.get(direccion, "")
        if not confirmar("ELIMINAR IP",
                         "Se va a eliminar la direccion:\n\n"
                         "   " + direccion +
                         (("\n   en la interfaz " + interfaz) if interfaz else "") +
                         "\n\nEstas seguro?"):
            return
        trabajando("Eliminando la direccion IP...")
        resultado(op_eliminar_ip(direccion), al_terminar=recargar_listas_principal)


    def accion_consultar_ips():
        trabajando()
        mostrar("Direcciones IP del router", print_ips() or "(sin datos)")


    ctk.CTkButton(col_izq, text="Save IP", fg_color=COLOR_BOTON, text_color=COLOR_OK,
                  command=accion_crear_ip, font=text_3, width=120).place(x=140, y=284)
    ctk.CTkButton(col_izq, text="DELETE", fg_color=COLOR_BOTON,
                  text_color=COLOR_BORRAR, command=accion_eliminar_ip,
                  font=text_2, width=190).place(x=340, y=258)
    ctk.CTkButton(col_izq, text="Consulta IP", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=accion_consultar_ips,
                  font=text_3, width=190).place(x=340, y=300)

    # --- Columna derecha: modulos ---
    ctk.CTkLabel(col_der, text="MODULOS", font=text_2).place(x=20, y=16)

    ctk.CTkButton(col_der, text="Server DHCP", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_dhcp, font=text_3,
                  width=170, height=34).place(x=20, y=56)
    ctk.CTkButton(col_der, text="Servidor DNS", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_dns, font=text_3,
                  width=170, height=34).place(x=205, y=56)
    ctk.CTkButton(col_der, text="IP Routes", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_rutas, font=text_3,
                  width=170, height=34).place(x=20, y=104)
    ctk.CTkButton(col_der, text="Respaldos", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_respaldos, font=text_3,
                  width=170, height=34).place(x=205, y=104)
    ctk.CTkButton(col_der, text="Monitoreo de Interfaces", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_monitoreo, font=text_2,
                  width=355, height=40).place(x=20, y=152)

    # Boton de la autenticacion SSH. Es el primero que hay que usar en una
    # maquina nueva: sin la llave instalada, ningun otro modulo funciona.
    ctk.CTkButton(col_der, text="Conexion y llaves SSH", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=ventana_llaves_ssh,
                  font=text_2, width=355, height=38).place(x=20, y=202)


    def accion_probar_conexion():
        """Prueba la conexion con el router y lo dice claramente.

        Es lo primero que conviene pulsar en la demostracion: si algo falla, se
        ve aqui y no a mitad de una operacion.
        """
        trabajando("Probando la conexion con " + IP + "...")
        ok, detalle = hay_conexion()
        if ok:
            mostrar("Conexion correcta",
                    "Se pudo contactar a " + USUARIO + "@" + IP + ".\n\n" + detalle)
            messagebox.showinfo("INFO", message="Conexion correcta con el router")
        else:
            mostrar("Sin conexion con el router",
                    "No se pudo contactar a " + IP + ".\n\n"
                    "Detalle:\n" + detalle + "\n\n"
                    "Revisa que el router este encendido, el cable de red y que\n"
                    "la llave " + LLAVE + " exista y tenga permisos 600.")
            messagebox.showerror("ERROR", message="No hay conexion con el router")


    def accion_refrescar():
        trabajando("Releyendo interfaces y direcciones del router...")
        recargar_listas_principal()
        mostrar("Listas actualizadas",
                "Interfaces:\n  " + ("\n  ".join(get_interfaces()) or "(ninguna)") +
                "\n\nDirecciones IP:\n  " + ("\n  ".join(get_ips()) or "(ninguna)"))


    ctk.CTkButton(col_der, text="Probar conexion", fg_color=COLOR_BOTON,
                  text_color=COLOR_OK, command=accion_probar_conexion, font=text_3,
                  width=170, height=34).place(x=20, y=252)
    ctk.CTkButton(col_der, text="Refrescar listas", fg_color=COLOR_BOTON,
                  text_color=COLOR_CONSULTA, command=accion_refrescar, font=text_3,
                  width=170, height=34).place(x=205, y=252)

    ctk.CTkLabel(col_der, text="Todos los resultados, incluidos los errores que\n"
                              "devuelve el router, aparecen abajo en RESULTADO.",
                 font=text_3, text_color="#666", justify="left").place(x=20, y=300)

    # --- Panel RESULTADO ---
    ctk.CTkLabel(v0, text="RESULTADO", font=text_2).pack(anchor="w", padx=24,
                                                         pady=(14, 2))

    panel_resultado = ctk.CTkTextbox(v0, height=230, font=text_mono,
                                     border_width=1, border_color="#D0D5DD",
                                     state="disabled", wrap="none")
    panel_resultado.pack(fill="both", expand=True, padx=20, pady=(0, 16))


    def al_cerrar_app():
        """Antes de cerrar, se matan los scripts de monitoreo.

        Sin esto quedaban procesos de ping y de ssh corriendo en segundo plano
        despues de cerrar la aplicacion.
        """
        detener_monitoreo()
        v0.destroy()


    v0.protocol("WM_DELETE_WINDOW", al_cerrar_app)


    # --- Arranque ----------------------------------------------------------------
    def arranque():
        """Primer contacto con el router, ya con la ventana dibujada.

        Se hace con un after() y no directamente, para que la ventana aparezca de
        inmediato en vez de quedarse en negro los segundos que tarde el primer
        ssh. Si el router no responde, la aplicacion abre igual y lo dice.
        """
        ok, detalle = hay_conexion()
        if ok:
            recargar_listas_principal()
            mostrar("Conectado a " + USUARIO + "@" + IP,
                    detalle + "\n\n"
                    "Interfaces detectadas:\n  " +
                    ("\n  ".join(get_interfaces()) or "(ninguna)") +
                    "\n\nDirecciones IP:\n  " +
                    ("\n  ".join(get_ips()) or "(ninguna)"))
        else:
            mostrar("Sin conexion con el router",
                    "La aplicacion abrio, pero no se pudo contactar a " + IP + ".\n\n"
                    "Detalle:\n" + detalle + "\n\n"
                    "Puedes seguir navegando por las ventanas. Cuando el router\n"
                    "este disponible, pulsa 'Probar conexion' y despues\n"
                    "'Refrescar listas'.")


    v0.after(200, arranque)
    v0.mainloop()
