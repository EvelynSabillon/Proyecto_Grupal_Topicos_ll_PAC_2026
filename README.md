# Control MikroTik Router

Aplicación en **Python** con interfaz gráfica **CustomTkinter** para administrar un router **MikroTik (RouterOS)** desde **Linux** mediante **SSH**, con el backend implementado en **Shell Scripting**.

[Máquina Virtual Configurada Utilizada en el Proyecto](https://drive.google.com/file/d/1t0Vjvz0_PlpObGKnDVnOmiwsnXt656cn/view?usp=sharing)
---

## Integrantes del grupo

| # | Integrante                           | Tema de exposición                                    |
|---|--------------------------------------|-------------------------------------------------------|
| 1 | *Fernando Josue Rivera Sosa*         | Instalación del sistema operativo Linux               |
| 2 | *Kenneth Adrian Ramirez Mendez*      | Instalación del sistema operativo MikroTik (RouterOS) |
| 3 | *Fernando Jose Castro Lopez*         | Protocolo SSH y generación de llaves criptográficas   |
| 4 | *Obed Esau Molina Sandoval*          | Comandos principales de MikroTik                      |
| 5 | *Erick Ronaldo Mendez Alvarado*      | Conexión física y lógica con el router MikroTik       |
| 6 | *Eugene Kelly Wu Leiva*              | Scripts de automatización y monitoreo                 |
| 7 | *Evelyn Andrea Sabillon Limas*       | Interfaz gráfica en Python (Frontend y Backend)       |

---

## Descripción del proyecto

La aplicación administra un router MikroTik sin necesidad de entrar a WinBox ni a la consola del router. Todo se hace desde una ventana en Linux, y cada operación viaja al router por SSH usando autenticación con llave pública.

### Funcionalidades

| Requisito                                                                     | Dónde está                              |
|-------------------------------------------------------------------------------|-----------------------------------------|
| Asignar el nombre (Identity) del router                                       | Ventana principal → *Save*              |
| Crear una dirección IP                                                        | Ventana principal → *Save IP*           |
| Eliminar una dirección IP                                                     | Ventana principal → *DELETE*            |
| Crear un servidor DHCP                                                        | Botón *Server DHCP* → *CREAR DHCP*      |
| Eliminar un servidor DHCP                                                     | Botón *Server DHCP* → *ELIMINAR DHCP*   |
| Configurar servidores DNS                                                     | Botón *Servidor DNS* → *Configurar DNS* |
| Eliminar la configuración de DNS                                              | Botón *Servidor DNS* → *Eliminar DNS*   |
| Crear rutas estáticas                                                         | Botón *IP Routes* → *CREAR RUTA*        |
| Eliminar rutas estáticas                                                      | Botón *IP Routes* → *ELIMINAR RUTA*     |
| Monitorear **dos** interfaces en tiempo real (estado Up/Down, tráfico in/out) | Botón *Monitoreo de Interfaces*         |
| Crear un respaldo (Backup)                                                    | Botón *Respaldos* → *Crear Respaldo*    |
| Listar los respaldos existentes                                               | Botón *Respaldos* → *Listar Respaldos*  |
| **Generar el par de llaves SSH e instalarlo en el router**                    | Botón *Conexión y llaves SSH*           |

Extras sobre el mínimo pedido: eliminar respaldos, monitoreo ICMP del router, consultas de pool / DHCP / network / rutas / interfaces, prueba de conexión y verificación automática de cada operación.

---

## Arquitectura

El proyecto está organizado en **dos capas separadas lógicamente** dentro de `mikrotik_system_customtkinter.py`, marcadas con banners de sección:

```
  ┌──────────────────────────────────────────────────────────┐
  │  FRONTEND   secciones 7 a 9                              │
  │  CustomTkinter: ventanas, formularios, panel RESULTADO   │
  │  No arma ni un solo comando de RouterOS.                 │
  └──────────────────────────┬───────────────────────────────┘
                             │  op_*(...)  →  (ok, titulo, detalle)
  ┌──────────────────────────▼───────────────────────────────┐
  │  BACKEND    secciones 1 a 6                              │
  │   1. Interpretación de las respuestas del router         │
  │   2. Validación de lo que escribe el usuario             │
  │   3. Comunicación SSH: ejecutar() / consultar()          │
  │   4. Consultas al router                                 │
  │   5. Operaciones de administración                       │
  │  5B. Autenticación SSH (generar e instalar las llaves)   │
  │   6. Monitoreo en segundo plano                          │
  └──────────────────────────┬───────────────────────────────┘
                             │  escribe y lanza backend/*.sh
  ┌──────────────────────────▼───────────────────────────────┐
  │  SHELL SCRIPTING          backend/*.sh                   │
  │  ssh -i <llave> <usuario>@<ip> 'comando de RouterOS'     │
  └──────────────────────────┬───────────────────────────────┘
                             ▼
                          RouterOS
```
 **`mikrotik_web.py` Es una interfaz web completa que hace exactamente lo mismo desde el navegador, y su código no contiene ni un solo comando de RouterOS, ni una línea de `ssh`, ni una validación. Todo lo importa:

```python
import mikrotik_system_customtkinter as mk
...
ok, titulo, detalle = mk.op_crear_ip(direccion, interfaz, comentario)
```

Para que eso fuera posible, el frontend de escritorio está dentro de `if __name__ == "__main__":`. Al ejecutar el archivo directamente se abre la ventana; al importarlo, no se abre nada y solo queda disponible el backend. Si mañana se corrige un error en el backend, **las dos interfaces quedan corregidas a la vez**, porque hay una sola copia de la lógica.

### Detalle clave

Toda operación de escritura pasa por `ejecutar()`, que escribe el comando en un script `.sh`, lo lanza con `bash` y **captura la respuesta del router**. RouterOS no usa códigos de salida —cuando rechaza un comando, el `ssh` termina igual con código 0 y la queja viaja en el texto—, así que la respuesta se interpreta con `hubo_fallo()` y `es_error_conexion()`.

Además cada operación **verifica la post-condición**: después de crear una IP se le pregunta al router si la IP está; después de crear un DHCP se consulta el campo `invalid` del servidor; después de crear un respaldo se comprueba que el archivo llegó al PC y que no pesa 0 bytes.

### Estructura de archivos

```
.
├── mikrotik_system_customtkinter.py   Aplicación de escritorio (backend + frontend)
├── mikrotik_web.py                    Interfaz web alternativa (reusa el mismo backend)
├── conexion.ini                       IP, usuario y llave (lo escribe la propia app)
├── README.md
├── requirements.txt
├── backend/                           19 scripts de shell
│   │
│   │   — Monitoreo (fijos, se ejecutan en segundo plano) —
│   ├── verificarinterfaces.sh         productor  – consulta las 2 interfaces
│   ├── monitorearinterfaces.sh        consumidor – escribe estado y tráfico
│   ├── verificarconexion.sh           productor  – ping al router
│   ├── monitorearip.sh                consumidor – escribe el semáforo ICMP
│   │
│   │   — Administración (los reescribe la aplicación en cada uso) —
│   ├── routername.sh                  identity
│   ├── create_IP.sh                   crear IP
│   ├── IPDelete.sh                    eliminar IP
│   ├── create_ip_interface.sh         DHCP paso 0 – IP en la interfaz
│   ├── create_dhcp_pool.sh            DHCP paso 1 – pool
│   ├── create_dhcp_server.sh          DHCP paso 2 – servidor
│   ├── create_dhcp_network.sh         DHCP paso 3 – red y DNS
│   ├── delete_dhcp_server.sh          eliminar DHCP – servidor
│   ├── delete_dhcp_pool.sh            eliminar DHCP – pool
│   ├── delete_dhcp_network.sh         eliminar DHCP – red
│   ├── configurar_dns.sh              configurar DNS del router
│   ├── eliminar_dns.sh                eliminar DNS del router
│   ├── route_add.sh                   crear ruta estática
│   ├── route_remove.sh                eliminar ruta estática
│   └── respaldoMK.sh                  crear el respaldo en el router
├── assets/                            Imágenes del semáforo (on/off/gris)
├── runtime/                           Archivos temporales del monitoreo
└── Backups/                           Respaldos traídos del router
```

Sobre los 15 scripts de administración: la versión incluida en el repositorio es de **referencia**, con valores de ejemplo, para que el backend se pueda leer sin necesidad de ejecutar el programa. La función `ejecutar()` los **reescribe** con los datos del formulario cada vez que se pulsa el botón correspondiente, y después los lanza con `bash` capturando la respuesta del router. Por eso, después de usar la aplicación, git los mostrará como modificados: es lo esperado.

Ese diseño tiene una ventaja, en `backend/` queda el comando exacto que se le mandó al router en cada operación.


## Requisitos

### Hardware y red

- PC o Maquina Virtual con **Linux**
- Router **MikroTik** accesible por red (en este proyecto: `192.168.56.121`) Modelo hAP lite
- Usuario SSH en el router (en este proyecto: `admin`)

### Software

- **Python 3.8** o superior: `sudo apt-get install python3 python3-pip`
- **Tkinter** — en Debian/Ubuntu: `sudo apt-get install python3-tk idle`
- **CustomTkinter**: `pip install customtkinter`
- **Pillow** y **Flask** — `sudo apt-get install python3-pil python3-flask`
			   `sudo apt install -y python3-pil.imagetk`
- **OpenSSH client** (`ssh`, `scp`) — `sudo apt install openssh-client`
- **iputils-ping** para el monitoreo ICMP — `sudo apt install iputils-ping`
- **falkon** un navegador para visualizar la parte web: `sudo apt-get install falkon -y`
- **xrdp y xfce4** para tener una interfaz grafica en el servidor con linux: `sudo apt install xfce4 xfce4-goodies -y`
                                                                             `sudo apt install xrdp -y`
                                                                             `sudo systemctl status xrdp`
                                                                             `sudo adduser xrdp ssl-cert`
- Par de llaves SSH configurado en el router

---

## Instalación

### 1. Copiar el proyecto

Puede ir en cualquier carpeta y con cualquier usuario: las rutas se calculan solas a partir de la ubicación del archivo `.py`.

```bash
cd ~/Escritorio
# copiar o clonar aquí la carpeta del proyecto
cd Control-MikroTik
```

### 2. Instalar las dependencias de Python

```bash
sudo apt install python3-tk openssh-client iputils-ping
sudo apt-get install python3-pil python3-flask
sudo apt-get install python3 python3-pip
sudo apt install -y python3-pil.imagetk
pip install customtkinter
```
Se puede usar tambien el archivo  `pip install -r requirements.txt` para instalar Pillow, Flask y customtkinter


### 3. Configurar la autenticación SSH — desde la propia aplicación

 Está tanto en el escritorio (botón **Conexión y llaves SSH**) como en la web (pestaña del mismo nombre, accesible solo desde `localhost`). Los cuatro bloques son los mismos:

1. **Datos de conexión** — escribir la IP del router, el usuario y dónde va la llave. *Guardar y probar*. Queda guardado en `conexion.ini`, así que no hay que tocar el código ni repetirlo en cada arranque.
2. **Paso 1 — Generar llaves.** Equivale a `ssh-keygen -t rsa -b 4096 -f ~/.ssh/mikrotik_tea_key -N ""`. La privada queda con permisos 600 automáticamente.
3. **Paso 2 — Copiar al router.** Pide la contraseña del router (la única vez en todo el proyecto que hace falta) y hace el `scp` de la llave pública más el `/user ssh-keys import` dentro de RouterOS.
4. **Paso 3 — Probar autenticación.** Entra al router con la llave y confirma que ya no pide contraseña.

El botón **HACER TODO DE UNA VEZ** encadena los tres pasos.

Si se prefiere hacerlo a mano, los comandos equivalentes son:

```bash
ssh-keygen -t rsa -b 4096 -f ~/.ssh/mikrotik_tea_key -N ""
chmod 600 ~/.ssh/mikrotik_tea_key
scp ~/.ssh/mikrotik_tea_key.pub admin@192.168.56.121:/
ssh admin@192.168.56.121 "/user ssh-keys import public-key-file=mikrotik_tea_key.pub user=admin"
ssh -i ~/.ssh/mikrotik_tea_key admin@192.168.56.121 "system identity print"
```

#### Cómo se resuelve la contraseña del `scp`

Es el único momento del proyecto en que hace falta la contraseña del router: la llave todavía no está instalada, así que `scp` no puede autenticarse con ella. Y `ssh`/`scp`, por diseño, **no leen la contraseña de la entrada estándar ni de una variable de entorno**: la piden directamente al terminal.

La solución habitual es la herramienta `sshpass`, pero tiene dos problemas: es una dependencia más, y sobre todo pone la contraseña en la línea de comandos, donde queda visible para cualquier usuario de la máquina con un simple `ps aux`.

En su lugar se usa el módulo **`pty` de la biblioteca estándar de Python**. `pty.fork()` crea un terminal falso, se lanza `scp` dentro de él, y cuando `scp` escribe `password:` se le responde por ese terminal. Para `scp` es indistinguible de una persona escribiendo. La contraseña viaja solo por memoria: nunca pasa por la línea de comandos, ni por un archivo, ni queda en el historial.

### 4. Valores por defecto (opcional)

Si se prefiere fijarlos en el código en vez de usar la ventana, están al principio de `mikrotik_system_customtkinter.py`, en la **SECCIÓN 0**:

```python
IP = "192.168.56.121"                                    # IP del router
USUARIO = "admin"                                        # usuario SSH de RouterOS
LLAVE = os.path.expanduser("~/.ssh/mikrotik_tea_key")    # llave privada
TIMEOUT = 5                                              # segundos de espera

INTERFAZ_1 = "ether1"                                    # interfaces del monitoreo
INTERFAZ_2 = "ether2"
```

Son solo los **valores por defecto**: si existe `conexion.ini`, lo que diga ese archivo manda.

### 5. Dar permiso de ejecución a los scripts

```bash
chmod +x backend/*.sh
```

---

## Manual de ejecución

```bash
python3 mikrotik_system_customtkinter.py
```

### Recorrido de la ventana principal

Al arrancar, la aplicación se conecta al router, llena los combobox con las interfaces y las IPs reales, y muestra el resultado en el panel **RESULTADO**. Si el router no responde, la ventana abre igual y lo explica.

**Todos los resultados —incluidos los errores literales que devuelve el router— aparecen en el panel RESULTADO.**

| Acción                                  | Pasos                                                                                                                     |
|-----------------------------------------|---------------------------------------------------------------------------------------------------------------------------|
| **Configurar la conexión y las llaves** | Botón *Conexión y llaves SSH*. Es lo primero que hay que hacer sin la llave instalada, ningún otro módulo funciona.       |
| **Probar la conexión**                  | Botón *Probar conexión*. Es lo primero que conviene pulsar antes de una demostración.                                     |
| **Cambiar el nombre del router**        | Escribir en *Router Name* → *Save*                                                                                        |
| **Crear una IP**                        | *IP Address* (con máscara, ej. `192.168.56.10/24`), elegir *Interface*, *Comment* opcional → *Save IP*                    |
| **Eliminar una IP**                     | Elegirla en *Eliminar IP* → *DELETE* → confirmar                                                                          |
| **Crear un DHCP**                       | *Server DHCP*. El gateway debe ser la IP de la interfaz y el rango debe caer dentro de la red → *CREAR DHCP*              |
| **Eliminar un DHCP**                    | *Server DHCP* → elegir servidor, pool y red → *ELIMINAR DHCP*                                                             |
| **Configurar el DNS**                   | *Servidor DNS* → escribir los servidores separados por coma, marcar *Allow Remote Requests* si se quiere *Configurar DNS* |
| **Eliminar el DNS**                     | *Servidor DNS* → *Eliminar DNS* → confirmar                                                                               |
| **Crear una ruta**                      | *IP Routes* → *Dst-Address*, *Gateway*, comentario opcional → *CREAR RUTA*                                                |
| **Eliminar una ruta**                   | *IP Routes* → elegirla en el combo → *ELIMINAR RUTA*                                                                      |
| **Crear un respaldo**                   | *Respaldos* → *Crear Respaldo*. Se guarda en el router y se copia a `Backups/`                                            |
| **Listar respaldos**                    | *Respaldos* → *Listar Respaldos* (los de este equipo)                                                                     |
| **Monitorear dos interfaces**           | *Monitoreo de Interfaces* → elegir las dos interfaces → marcar *Enable / Disable*                                         |

### Monitoreo

Al marcar *Enable / Disable* arrancan cuatro scripts en segundo plano:

```
verificarinterfaces.sh  ──►  datosinterfaces.txt  ──►  monitorearinterfaces.sh
                                                              │
                                                              ▼
                                            estado1/2.txt, trafico1/2.txt
                                                              │
                                                              ▼
                                                    la ventana los lee cada 1 s

verificarconexion.sh    ──►  datosconexion.txt    ──►  monitorearip.sh  ──►  estado.txt
```

La ventana **no consulta al router**: solo lee esos archivos. Por eso la interfaz nunca se congela aunque el router tarde en responder. Al desmarcar la casilla o cerrar la ventana, los scripts se detienen solos.

---

---

## Versión web (opcional)

La misma aplicación, desde el navegador.

### Instalación y ejecución

```bash
pip install flask
python3 mikrotik_web.py
```

Abrir en el navegador: `http://localhost:5000`
(o `http://<IP-de-esta-PC>:5000` desde otra máquina de la red)

### Qué incluye

Todas las funcionalidades de la versión de escritorio

Las dos interfaces comparten `conexion.ini`.

La página de monitoreo arranca **los mismos scripts de shell** que la versión de escritorio y consulta un endpoint JSON (`/api/monitoreo`) una vez por segundo. Igual que la ventana, el navegador no habla con el router: solo lee los archivos que dejan los scripts.

### Aviso de seguridad

El servidor **no lleva autenticación**: cualquiera que llegue al puerto 5000 puede administrar el router. Para restringirlo a la máquina local, cambiar `HOST = "0.0.0.0"` por `HOST = "127.0.0.1"` al principio de `mikrotik_web.py`.

**La página de llaves SSH tiene una protección extra.** Pide la contraseña del router y puede sustituir la llave del equipo, así que por defecto solo responde a peticiones que vengan de la propia máquina:

```python
PERMITIR_LLAVES_REMOTO = False   # al principio de mikrotik_web.py
```

Desde otra máquina de la red, esa página muestra un aviso explicando cómo habilitarla en vez del formulario, y sus rutas POST quedan bloqueadas. El resto de la aplicación sigue accesible desde toda la red con normalidad. Ponerlo en `True` la habilita para cualquiera que llegue al puerto.

---

## Solución de problemas

| Síntoma                                             | Causa probable                                                                                            |
|-----------------------------------------------------|-----------------------------------------------------------------------------------------------------------|
| 1. *Sin conexión con el router* al abrir            | El router está apagado, el cable desconectado, o la IP de la SECCIÓN 0 no es la correcta                  |
| 2. `Permission denied (publickey)`                  | La llave no está importada en el router, o le faltan permisos.                                            |
|                                                     | Botón *Conexión y llaves SSH* → *Corregir permisos (600)*, y si sigue, repetir el *Paso 2*                |
| 3. `UNPROTECTED PRIVATE KEY FILE`                   | La llave privada la pueden leer otros usuarios. Botón *Conexión y llaves SSH* → *Corregir permisos (600)* |
| 4. El router rechaza la contraseña en el Paso 2     | Es la contraseña del usuario de **RouterOS** (`admin` por defecto), no la del PC Linux                    |
| 5. *SERVIDOR INVÁLIDO* al crear el DHCP             | La interfaz no tiene IP, o el gateway no pertenece a la red indicada                                      |
| 6. Los combobox salen vacíos                        | No hay conexión con el router. Pulsar *Probar conexión* y luego *Refrescar listas*                        |
| 7. El monitoreo se queda en *Esperando datos…*      | Las interfaces elegidas no existen en el router, o la llave SSH no funciona sin contraseña                |
| 8. `ModuleNotFoundError: No module named 'tkinter'` | Falta el paquete del sistema: `sudo apt install python3-tk`                                               |

