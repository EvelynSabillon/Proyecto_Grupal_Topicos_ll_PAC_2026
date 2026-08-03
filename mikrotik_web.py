"""
===============================================================================
 CONTROL MIKROTIK ROUTER  --  VERSION WEB (Flask)
===============================================================================

 PARA QUE SIRVE ESTE ARCHIVO
 ---------------------------
 Es una SEGUNDA interfaz para el mismo proyecto. Hace exactamente lo mismo
 que la aplicacion de escritorio, pero desde el navegador, y sirve para
 demostrar en la practica que la separacion Frontend/Backend es real:

   mikrotik_system_customtkinter.py
        SECCIONES 1-6  BACKEND   <---- este archivo lo importa y lo reusa TAL CUAL
        SECCIONES 7-9  FRONTEND de escritorio (CustomTkinter)

   mikrotik_web.py
        FRONTEND web (Flask + HTML)

 se llama desde la ventana de escritorio:
        ok, titulo, detalle = mk.op_crear_ip(direccion, interfaz, comentario)

 COMO SE EJECUTA
 ---------------
     pip install flask
     python3 mikrotik_web.py
     se abre en el navegador:   http://localhost:5000
===============================================================================
"""

from flask import Flask, request, redirect, url_for, jsonify, render_template_string

# El backend completo, reutilizado sin tocar nada.
import mikrotik_system_customtkinter as mk


app = Flask(__name__)

# Puerto y direccion de escucha. 0.0.0.0 permite entrar desde otra maquina
HOST = "0.0.0.0"
PUERTO = 5000
PERMITIR_LLAVES_REMOTO = False


# =============================================================================
#  ESTADO DE LA PAGINA
# =============================================================================
#  Se usa el patron POST -> redirect -> GET para que al recargar la pagina el
#  navegador no repita la ultima operacion contra el router.

_ultimo = {"ok": None, "titulo": "", "detalle": ""}


def guardar(terna):
    """Guarda el (ok, titulo, detalle) que devolvio el backend."""
    _ultimo["ok"], _ultimo["titulo"], _ultimo["detalle"] = terna
    return redirect(url_for("index"))


def guardar_consulta(titulo, texto):
    """Guarda el resultado de una consulta (nunca es un fallo)."""
    _ultimo["ok"] = True
    _ultimo["titulo"] = titulo
    _ultimo["detalle"] = texto or "(sin datos)"
    return redirect(url_for("index"))


def campo(nombre):
    """Lee un campo del formulario, ya sin espacios sobrantes."""
    return (request.form.get(nombre) or "").strip()


# =============================================================================
#  PLANTILLA HTML
# =============================================================================

BASE = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{ titulo_pagina }}</title>
<style>
  :root { --barra:#00B4D8; --panel:#F5F7FA; --borde:#D0D5DD; --tinta:#1a1a2e; }
  * { box-sizing: border-box; }
  body { margin:0; font-family:Arial, Helvetica, sans-serif; background:#fff;
         color:var(--tinta); }
  header { background:var(--barra); color:#fff; padding:14px 20px; text-align:center; }
  header h1 { margin:0; font-size:20px; letter-spacing:.5px; }
  .sub { text-align:center; color:#666; font-size:13px; margin:10px 0 4px; }
  .nav { text-align:center; margin-bottom:16px; }
  .nav a { display:inline-block; margin:0 6px; padding:7px 16px; background:#000;
           color:#fff; text-decoration:none; border-radius:6px; font-size:13px; }
  .nav a.activo { background:var(--barra); }
  .wrap { max-width:1180px; margin:0 auto; padding:0 20px 40px; }
  .rejilla { display:grid; grid-template-columns:repeat(auto-fit,minmax(340px,1fr));
             gap:16px; }
  .tarjeta { background:var(--panel); border:1px solid var(--borde);
             border-radius:10px; padding:18px 20px 22px; }
  .tarjeta h2 { margin:0 0 4px; font-size:15px; }
  .tarjeta p.ayuda { margin:0 0 14px; color:#666; font-size:12px; line-height:1.5; }
  label { display:block; font-size:13px; margin:10px 0 4px; }
  input[type=text], input[type=password], select { width:100%; padding:8px 10px; font-size:13px;
        border:1px solid var(--borde); border-radius:6px; background:#fff; }
  .fila { display:flex; gap:8px; align-items:center; margin-top:8px; }
  .fila label { margin:0; }
  button { margin-top:14px; padding:9px 16px; background:#000; color:#fff;
           border:0; border-radius:6px; font-size:13px; font-weight:bold;
           cursor:pointer; }
  button:hover { background:#333; }
  button.crear { color:#2ecc71; }
  button.borrar { color:#ff5a5a; }
  .grupo-botones { display:flex; flex-wrap:wrap; gap:8px; }
  .grupo-botones form { margin:0; }
  h3.seccion { margin:26px 0 10px; font-size:15px; }
  .resultado { margin-top:26px; }
  .resultado h3 { margin:0 0 6px; font-size:15px; }
  pre { background:#fff; border:1px solid var(--borde); border-radius:8px;
        padding:14px; font-family:Consolas,"DejaVu Sans Mono",monospace;
        font-size:12.5px; line-height:1.5; white-space:pre-wrap;
        word-break:break-word; max-height:340px; overflow:auto; margin:0; }
  pre.ok { border-left:5px solid #1a7f37; }
  pre.error { border-left:5px solid #a01313; }
  .aviso { background:#FFF6E5; border:1px solid #F0C674; border-radius:8px;
           padding:10px 14px; font-size:12.5px; margin-bottom:16px; }
  .peligro { background:#FDECEC; border:1px solid #E08A8A; border-left:5px solid #a01313;
             border-radius:8px; padding:12px 16px; font-size:12.5px;
             line-height:1.6; margin-bottom:16px; }
  code { background:#eef1f5; padding:1px 5px; border-radius:4px;
         font-family:Consolas,"DejaVu Sans Mono",monospace; }
</style>
</head>
<body>
<header><h1>CONTROL MIKROTIK ROUTER</h1></header>
<div class="sub">Router: {{ usuario }}@{{ ip }} &nbsp;|&nbsp; llave: {{ llave }}</div>
<div class="nav">
  <a href="{{ url_for('index') }}" class="{{ 'activo' if pagina=='inicio' }}">Administracion</a>
  <a href="{{ url_for('monitoreo') }}" class="{{ 'activo' if pagina=='monitoreo' }}">Monitoreo de interfaces</a>
  <a href="{{ url_for('llaves') }}" class="{{ 'activo' if pagina=='llaves' }}">Conexion y llaves SSH</a>
</div>
<div class="wrap">
{{ cuerpo|safe }}
</div>
</body>
</html>"""


CUERPO_INICIO = """
{% if not conectado %}
<div class="aviso">
  <b>Sin conexion con el router.</b> Las listas desplegables saldran vacias.
  Revisa que el router este encendido y vuelve a cargar la pagina.
</div>
{% endif %}

<div class="rejilla">

  <!-- ------------------------------------------------ NOMBRE DEL ROUTER -->
  <div class="tarjeta">
    <h2>Nombre del router (Identity)</h2>
    <p class="ayuda">Letras, numeros, punto, guion y guion bajo. Sin espacios.</p>
    <form method="post" action="{{ url_for('set_nombre') }}">
      <label>Nuevo nombre</label>
      <input type="text" name="nombre" placeholder="Ej: UNAH-CORTES">
      <div class="grupo-botones">
        <button class="crear" type="submit">Asignar nombre</button>
      </div>
    </form>
    <form method="post" action="{{ url_for('consultar_nombre') }}">
      <button type="submit">Consultar nombre</button>
    </form>
  </div>

  <!-- --------------------------------------------------- DIRECCIONES IP -->
  <div class="tarjeta">
    <h2>Direcciones IP</h2>
    <p class="ayuda">La direccion debe llevar mascara. El comentario es opcional.</p>
    <form method="post" action="{{ url_for('crear_ip') }}">
      <label>IP / mascara</label>
      <input type="text" name="direccion" placeholder="Ej: 192.168.56.10/24">
      <label>Interfaz</label>
      <select name="interfaz">
        {% for i in interfaces %}<option value="{{ i }}">{{ i }}</option>{% endfor %}
      </select>
      <label>Comentario</label>
      <input type="text" name="comentario" placeholder="Opcional">
      <button class="crear" type="submit">Crear IP</button>
    </form>
    <form method="post" action="{{ url_for('eliminar_ip') }}"
          onsubmit="return confirm('Se va a eliminar la direccion seleccionada. Continuar?');">
      <label>Eliminar IP</label>
      <select name="direccion">
        {% for d, i in ips %}<option value="{{ d }}">{{ d }} &mdash; {{ i }}</option>{% endfor %}
      </select>
      <button class="borrar" type="submit">Eliminar IP</button>
    </form>
    <form method="post" action="{{ url_for('consultar_ips') }}">
      <button type="submit">Consultar IPs</button>
    </form>
  </div>

  <!-- ---------------------------------------------------- CREAR EL DHCP -->
  <div class="tarjeta">
    <h2>Crear servidor DHCP</h2>
    <p class="ayuda">El gateway debe ser la IP de la interfaz y el rango debe caer
       dentro de la red. Si no, el router crea el servidor pero no reparte nada.</p>
    <form method="post" action="{{ url_for('crear_dhcp') }}">
      <label>Interfaz</label>
      <select name="interfaz">
        {% for i in interfaces %}<option value="{{ i }}">{{ i }}</option>{% endfor %}
      </select>
      <label>IP de la interfaz</label>
      <input type="text" name="ip_interfaz" value="192.168.200.1/24">
      <label>Nombre del pool</label>
      <input type="text" name="pool" value="dhcp_pool">
      <label>Rango de IPs</label>
      <input type="text" name="rango" value="192.168.200.100-192.168.200.150">
      <label>Nombre del servidor</label>
      <input type="text" name="servidor" value="dhcp_server">
      <label>Red (address)</label>
      <input type="text" name="red" value="192.168.200.0/24">
      <label>Gateway</label>
      <input type="text" name="gateway" value="192.168.200.1">
      <label>DNS que reparte (opcional)</label>
      <input type="text" name="dns" value="8.8.8.8">
      <button class="crear" type="submit">Crear DHCP</button>
    </form>
  </div>

  <!-- ------------------------------------------------- ELIMINAR EL DHCP -->
  <div class="tarjeta">
    <h2>Eliminar servidor DHCP</h2>
    <p class="ayuda">Se elimina en este orden: servidor, pool y red. El pool no
       se puede borrar mientras un servidor lo este usando.</p>
    <form method="post" action="{{ url_for('eliminar_dhcp') }}"
          onsubmit="return confirm('Se va a eliminar el servidor DHCP seleccionado. Continuar?');">
      <label>Servidor</label>
      <select name="servidor">
        {% for d in servidores %}<option value="{{ d }}">{{ d }}</option>{% endfor %}
      </select>
      <label>Pool</label>
      <select name="pool">
        <option value="">(ninguno)</option>
        {% for p in pools %}<option value="{{ p }}">{{ p }}</option>{% endfor %}
      </select>
      <label>Red</label>
      <select name="red">
        <option value="">(ninguna)</option>
        {% for r in redes %}<option value="{{ r }}">{{ r }}</option>{% endfor %}
      </select>
      <button class="borrar" type="submit">Eliminar DHCP</button>
    </form>
    <h3 class="seccion">Consultas</h3>
    <div class="grupo-botones">
      <form method="post" action="{{ url_for('consultar', que='pool') }}">
        <button type="submit">Pools</button></form>
      <form method="post" action="{{ url_for('consultar', que='dhcp') }}">
        <button type="submit">Servidores</button></form>
      <form method="post" action="{{ url_for('consultar', que='network') }}">
        <button type="submit">Redes</button></form>
    </div>
  </div>

  <!-- ------------------------------------------------------------- DNS -->
  <div class="tarjeta">
    <h2>Servicio DNS del router</h2>
    <p class="ayuda">Configura <code>/ip dns</code> del router. Varios servidores
       se separan con coma y sin espacios.</p>
    <form method="post" action="{{ url_for('configurar_dns') }}">
      <label>Servidores DNS</label>
      <input type="text" name="servidores" value="{{ dns_actual }}"
             placeholder="Ej: 8.8.8.8,8.8.4.4">
      <div class="fila">
        <input type="checkbox" name="remoto" id="remoto" style="width:auto"
               {{ 'checked' if remoto_actual }}>
        <label for="remoto">Allow Remote Requests</label>
      </div>
      <button class="crear" type="submit">Configurar DNS</button>
    </form>
    <div class="grupo-botones">
      <form method="post" action="{{ url_for('eliminar_dns') }}"
            onsubmit="return confirm('Se va a borrar la configuracion DNS del router. Continuar?');">
        <button class="borrar" type="submit">Eliminar DNS</button></form>
      <form method="post" action="{{ url_for('consultar', que='dns') }}">
        <button type="submit">Consultar DNS</button></form>
    </div>
  </div>

  <!-- -------------------------------------------------- RUTAS ESTATICAS -->
  <div class="tarjeta">
    <h2>Rutas estaticas</h2>
    <p class="ayuda">Solo se listan las rutas estaticas. Las que crea el propio
       router para sus interfaces no se pueden borrar.</p>
    <form method="post" action="{{ url_for('crear_ruta') }}">
      <label>Destino (dst-address)</label>
      <input type="text" name="destino" placeholder="Ej: 192.168.10.0/24">
      <label>Gateway</label>
      <input type="text" name="gateway" placeholder="Ej: 192.168.56.1">
      <label>Comentario</label>
      <input type="text" name="comentario" placeholder="Opcional">
      <button class="crear" type="submit">Crear ruta</button>
    </form>
    <form method="post" action="{{ url_for('eliminar_ruta') }}"
          onsubmit="return confirm('Se va a eliminar la ruta seleccionada. Continuar?');">
      <label>Eliminar ruta</label>
      <select name="destino">
        {% for r in rutas %}<option value="{{ r }}">{{ r }}</option>{% endfor %}
      </select>
      <button class="borrar" type="submit">Eliminar ruta</button>
    </form>
    <form method="post" action="{{ url_for('consultar', que='rutas') }}">
      <button type="submit">Consultar rutas</button>
    </form>
  </div>

  <!-- ------------------------------------------------------- RESPALDOS -->
  <div class="tarjeta">
    <h2>Respaldos</h2>
    <p class="ayuda">El respaldo se crea en el router y se copia a la carpeta
       Backups de este equipo. La lista de abajo son los de este equipo.</p>
    <div class="grupo-botones">
      <form method="post" action="{{ url_for('crear_respaldo') }}"
            onsubmit="return confirm('Se va a crear un respaldo del router. Continuar?');">
        <button class="crear" type="submit">Crear respaldo</button></form>
      <form method="post" action="{{ url_for('consultar', que='respaldos') }}">
        <button type="submit">Listar respaldos</button></form>
      <form method="post" action="{{ url_for('consultar', que='respaldos_router') }}">
        <button type="submit">Ver los del router</button></form>
    </div>
    <form method="post" action="{{ url_for('eliminar_respaldo') }}"
          onsubmit="return confirm('Se va a eliminar el archivo seleccionado de este equipo. Continuar?');">
      <label>Respaldo guardado</label>
      <select name="nombre">
        {% for b in respaldos %}<option value="{{ b }}">{{ b }}</option>{% endfor %}
      </select>
      <button class="borrar" type="submit">Eliminar respaldo</button>
    </form>
  </div>

</div>

<div class="resultado">
  <h3>RESULTADO</h3>
  <pre class="{{ 'ok' if ok else ('error' if ok is not none else '') }}">{% if titulo %}== {{ titulo }} ==

{% endif %}{{ detalle }}</pre>
</div>
"""


CUERPO_MONITOREO = """
<div class="tarjeta" style="margin-bottom:16px">
  <h2>Monitoreo de dos interfaces en tiempo real</h2>
  <p class="ayuda">Al activarlo arrancan en segundo plano los mismos scripts de
     shell que usa la version de escritorio. Esta pagina no consulta al router:
     solo lee cada segundo los archivos que dejan esos scripts.</p>
  <form method="post" action="{{ url_for('monitoreo_iniciar') }}">
    <div class="rejilla" style="grid-template-columns:repeat(auto-fit,minmax(200px,1fr))">
      <div>
        <label>Interfaz 1</label>
        <select name="if1">
          {% for i in interfaces %}
          <option value="{{ i }}" {{ 'selected' if i==if1 }}>{{ i }}</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label>Interfaz 2</label>
        <select name="if2">
          {% for i in interfaces %}
          <option value="{{ i }}" {{ 'selected' if i==if2 }}>{{ i }}</option>
          {% endfor %}
        </select>
      </div>
    </div>
    <div class="grupo-botones">
      <button class="crear" type="submit">Iniciar monitoreo</button>
    </div>
  </form>
  <form method="post" action="{{ url_for('monitoreo_detener') }}">
    <button class="borrar" type="submit">Detener monitoreo</button>
  </form>
</div>

<div class="rejilla">
  <div class="tarjeta">
    <h2 id="n1">{{ if1 }}</h2>
    <p style="font-size:26px;margin:12px 0 6px" id="e1">Esperando datos...</p>
    <pre style="border:0;background:transparent;padding:0" id="t1">Trafico IN :  --
Trafico OUT:  --</pre>
  </div>
  <div class="tarjeta">
    <h2 id="n2">{{ if2 }}</h2>
    <p style="font-size:26px;margin:12px 0 6px" id="e2">Esperando datos...</p>
    <pre style="border:0;background:transparent;padding:0" id="t2">Trafico IN :  --
Trafico OUT:  --</pre>
  </div>
</div>

<div class="tarjeta" style="margin-top:16px">
  <h2>Alcance del router (ping ICMP a {{ ip }})</h2>
  <p style="font-size:20px;margin:10px 0 0" id="icmp">Esperando datos...</p>
</div>

<script>
// Se consulta el endpoint JSON una vez por segundo y solo se cambia el texto
// de los elementos ya existentes: nunca se crean nodos nuevos. Es el mismo
// criterio que en la version de escritorio, donde los widgets se crean una
// sola vez y solo se les actualiza el contenido.
function pintar(idEstado, idTrafico, d) {
  var e = document.getElementById(idEstado);
  var t = document.getElementById(idTrafico);
  if (d.estado === "1")      { e.textContent = "UP";   e.style.color = "#1a7f37"; }
  else if (d.estado === "0") { e.textContent = "DOWN"; e.style.color = "#a01313"; }
  else                       { e.textContent = "Esperando datos..."; e.style.color = "#666"; }
  t.textContent = "Trafico IN :  " + d.rx + "\\nTrafico OUT:  " + d.tx;
}

function refrescar() {
  fetch("{{ url_for('api_monitoreo') }}")
    .then(function (r) { return r.json(); })
    .then(function (j) {
      document.getElementById("n1").textContent = j.if1;
      document.getElementById("n2").textContent = j.if2;
      pintar("e1", "t1", j.i1);
      pintar("e2", "t2", j.i2);
      var ic = document.getElementById("icmp");
      if (j.icmp === "1")      { ic.textContent = "EL ROUTER RESPONDE";    ic.style.color = "#1a7f37"; }
      else if (j.icmp === "0") { ic.textContent = "EL ROUTER NO RESPONDE"; ic.style.color = "#a01313"; }
      else                     { ic.textContent = "Esperando datos...";    ic.style.color = "#666"; }
    })
    .catch(function () { /* si el servidor no responde, se reintenta al segundo */ });
}

refrescar();
setInterval(refrescar, 1000);
</script>
"""


def pagina(titulo_pagina, cuerpo_plantilla, pagina_activa, **datos):
    """Renderiza el cuerpo y lo mete dentro de la plantilla base."""
    cuerpo = render_template_string(cuerpo_plantilla, **datos)
    return render_template_string(
        BASE,
        titulo_pagina=titulo_pagina,
        cuerpo=cuerpo,
        pagina=pagina_activa,
        usuario=mk.USUARIO,
        ip=mk.IP,
        llave=mk.LLAVE,
    )


# =============================================================================
#  PAGINA DE ADMINISTRACION
# =============================================================================

@app.route("/")
def index():
    """Pagina principal. Llena las listas con datos reales del router."""
    conectado, _ = mk.hay_conexion()

    dns_actual = mk.get_dns_router() if conectado else ""
    remoto = "yes" in mk.print_dns().lower() if conectado else False

    return pagina(
        "Control MikroTik Router", CUERPO_INICIO, "inicio",
        conectado=conectado,
        interfaces=mk.get_interfaces() if conectado else [],
        ips=mk.get_ips_con_interfaz() if conectado else [],
        servidores=mk.get_dhcp_servers() if conectado else [],
        pools=mk.get_pools() if conectado else [],
        redes=mk.get_redes_dhcp() if conectado else [],
        rutas=mk.get_rutas_estaticas() if conectado else [],
        respaldos=mk.listar_respaldos(),
        dns_actual=dns_actual,
        remoto_actual=remoto,
        ok=_ultimo["ok"],
        titulo=_ultimo["titulo"],
        detalle=_ultimo["detalle"] or "Pulsa cualquier boton. Aqui apareceran los "
                                      "resultados, incluidos los errores que devuelva el router.",
    )


# --- Identity ---------------------------------------------------------------

@app.route("/nombre", methods=["POST"])
def set_nombre():
    return guardar(mk.op_set_nombre(campo("nombre")))


@app.route("/nombre/consultar", methods=["POST"])
def consultar_nombre():
    return guardar_consulta("Nombre actual del router", mk.print_identity())


# --- Direcciones IP ---------------------------------------------------------

@app.route("/ip/crear", methods=["POST"])
def crear_ip():
    return guardar(mk.op_crear_ip(campo("direccion"), campo("interfaz"),
                                  campo("comentario")))


@app.route("/ip/eliminar", methods=["POST"])
def eliminar_ip():
    return guardar(mk.op_eliminar_ip(campo("direccion")))


@app.route("/ip/consultar", methods=["POST"])
def consultar_ips():
    return guardar_consulta("Direcciones IP del router", mk.print_ips())


# --- DHCP -------------------------------------------------------------------

@app.route("/dhcp/crear", methods=["POST"])
def crear_dhcp():
    return guardar(mk.op_crear_dhcp(
        campo("interfaz"), campo("ip_interfaz"), campo("pool"), campo("rango"),
        campo("servidor"), campo("red"), campo("gateway"), campo("dns")))


@app.route("/dhcp/eliminar", methods=["POST"])
def eliminar_dhcp():
    return guardar(mk.op_eliminar_dhcp(campo("servidor"), campo("pool"),
                                       campo("red")))


# --- DNS --------------------------------------------------------------------

@app.route("/dns/configurar", methods=["POST"])
def configurar_dns():
    # Una casilla no marcada no se envia en el formulario, de ahi el 'in'
    remoto = "remoto" in request.form
    return guardar(mk.op_configurar_dns(campo("servidores"), remoto))


@app.route("/dns/eliminar", methods=["POST"])
def eliminar_dns():
    return guardar(mk.op_eliminar_dns())


# --- Rutas ------------------------------------------------------------------

@app.route("/ruta/crear", methods=["POST"])
def crear_ruta():
    return guardar(mk.op_crear_ruta(campo("destino"), campo("gateway"),
                                    campo("comentario")))


@app.route("/ruta/eliminar", methods=["POST"])
def eliminar_ruta():
    return guardar(mk.op_eliminar_ruta(campo("destino")))


# --- Respaldos --------------------------------------------------------------

@app.route("/respaldo/crear", methods=["POST"])
def crear_respaldo():
    return guardar(mk.op_crear_respaldo())


@app.route("/respaldo/eliminar", methods=["POST"])
def eliminar_respaldo():
    return guardar(mk.op_eliminar_respaldo(campo("nombre")))


# --- Consultas --------------------------------------------------------------

@app.route("/consultar/<que>", methods=["POST"])
def consultar(que):
    """Todas las consultas en un solo endpoint."""
    tabla = {
        "pool": ("Pools de direcciones", mk.print_pools),
        "dhcp": ("Servidores DHCP", mk.print_dhcp_servers),
        "network": ("Redes DHCP", mk.print_dhcp_networks),
        "dns": ("Configuracion DNS del router", mk.print_dns),
        "rutas": ("Tabla de rutas del router", mk.print_rutas),
        "interfaces": ("Interfaces del router", mk.print_interfaces),
        "respaldos": ("Respaldos en este equipo", mk.listar_respaldos_texto),
        "respaldos_router": ("Respaldos en el router", mk.print_backups_router),
    }
    if que not in tabla:
        return guardar_consulta("Consulta desconocida", "No existe la consulta: " + que)
    titulo, funcion = tabla[que]
    return guardar_consulta(titulo, funcion())


# =============================================================================
#  PAGINA DE MONITOREO
# =============================================================================

_monitor = {"if1": mk.INTERFAZ_1, "if2": mk.INTERFAZ_2, "activo": False}


@app.route("/monitoreo")
def monitoreo():
    conectado, _ = mk.hay_conexion()
    interfaces = mk.get_interfaces() if conectado else [_monitor["if1"], _monitor["if2"]]
    return pagina("Monitoreo de interfaces", CUERPO_MONITOREO, "monitoreo",
                  interfaces=interfaces,
                  if1=_monitor["if1"], if2=_monitor["if2"], ip=mk.IP)


@app.route("/monitoreo/iniciar", methods=["POST"])
def monitoreo_iniciar():
    if1, if2 = campo("if1"), campo("if2")

    # Las mismas validaciones que en la version de escritorio, tomadas del
    # backend: no se duplica ni la expresion regular.
    for valor in (if1, if2):
        ok, _ = mk.validar_interfaz(valor)
        if not ok:
            return redirect(url_for("monitoreo"))

    if if1 == if2:
        return redirect(url_for("monitoreo"))

    _monitor["if1"], _monitor["if2"], _monitor["activo"] = if1, if2, True
    mk.iniciar_monitoreo(if1, if2)
    return redirect(url_for("monitoreo"))


@app.route("/monitoreo/detener", methods=["POST"])
def monitoreo_detener():
    _monitor["activo"] = False
    mk.detener_monitoreo()
    return redirect(url_for("monitoreo"))


@app.route("/api/monitoreo")
def api_monitoreo():
    """Devuelve el estado actual en JSON. Lo consulta el navegador cada segundo.

    Igual que la ventana de escritorio, aqui NO se habla con el router: solo
    se leen los archivos que dejan los scripts de shell en runtime/.
    """
    def leer(archivo_estado, archivo_trafico):
        trafico = mk.leer_runtime(archivo_trafico).split()
        return {
            "estado": mk.leer_runtime(archivo_estado),
            "rx": mk.formato_trafico(trafico[0] if len(trafico) > 0 else "0"),
            "tx": mk.formato_trafico(trafico[1] if len(trafico) > 1 else "0"),
        }

    return jsonify({
        "activo": _monitor["activo"],
        "if1": _monitor["if1"],
        "if2": _monitor["if2"],
        "i1": leer(mk.F_ESTADO_1, mk.F_TRAFICO_1),
        "i2": leer(mk.F_ESTADO_2, mk.F_TRAFICO_2),
        "icmp": mk.leer_runtime(mk.F_ESTADO_ICMP),
    })


CUERPO_LLAVES = """
{% if not permitido %}
<div class="peligro">
  <b>Esta pagina solo se puede usar desde el propio equipo.</b><br><br>
  Estas entrando desde <code>{{ remoto }}</code>, y esta seccion pide la
  contrasena del router y puede sustituir la llave del equipo. Como el
  servidor no lleva autenticacion, esta limitada a <code>localhost</code>.
  <br><br>
  Abre <code>http://localhost:{{ puerto }}/llaves</code> en el navegador de la
  maquina donde corre el servidor, o usa la aplicacion de escritorio.
  <br><br>
  Si aun asi quieres habilitarla para toda la red, cambia al principio de
  <code>mikrotik_web.py</code>:
  <br><code>PERMITIR_LLAVES_REMOTO = True</code>
</div>
{% else %}

<div class="peligro">
  <b>Aviso.</b> Esta pagina pide la contrasena del router y puede sustituir la
  llave del equipo. El servidor no lleva autenticacion y va por HTTP sin
  cifrar: usala solo en la red del laboratorio.
</div>

<div class="rejilla">

  <!-- --------------------------------------------- DATOS DE CONEXION -->
  <div class="tarjeta">
    <h2>Datos de conexion del router</h2>
    <p class="ayuda">Se guardan en <code>conexion.ini</code>, junto al programa,
       y los usan por igual esta web y la aplicacion de escritorio.</p>
    <form method="post" action="{{ url_for('llaves_conexion') }}">
      <label>IP del router</label>
      <input type="text" name="ip" value="{{ ip }}">
      <label>Usuario</label>
      <input type="text" name="usuario" value="{{ usuario }}">
      <label>Llave privada</label>
      <input type="text" name="llave" value="{{ llave }}">
      <button class="crear" type="submit">Guardar y probar</button>
    </form>
  </div>

  <!-- ---------------------------------------------------- ESTADO -->
  <div class="tarjeta">
    <h2>Estado actual</h2>
    <p class="ayuda">Lo mismo que muestra la ventana de escritorio.</p>
    <pre class="{{ 'ok' if autentica else 'error' }}">{{ estado }}</pre>
    <form method="post" action="{{ url_for('llaves_probar') }}">
      <button type="submit">Probar autenticacion</button>
    </form>
  </div>

  <!-- ------------------------------------------------ PASO 1 -->
  <div class="tarjeta">
    <h2>Paso 1 &mdash; Generar el par de llaves</h2>
    <p class="ayuda">Equivale a
       <code>ssh-keygen -t rsa -b 4096 -f &lt;llave&gt; -N ""</code>.
       La privada se queda en este equipo y no se comparte nunca; la publica
       es la que va al router. La privada queda con permisos 600.</p>
    <form method="post" action="{{ url_for('llaves_generar') }}"
          onsubmit="return confirm('Se va a generar un par de llaves. Si marcaste sobrescribir, la llave actual se pierde y el router dejara de reconocerte hasta hacer el paso 2. Continuar?');">
      <label>Tamano</label>
      <select name="bits">
        <option value="4096">4096</option>
        <option value="3072">3072</option>
        <option value="2048">2048</option>
      </select>
      <div class="fila">
        <input type="checkbox" name="sobrescribir" id="sob" style="width:auto">
        <label for="sob">Sobrescribir si ya existe</label>
      </div>
      <button class="crear" type="submit">1. Generar llaves</button>
    </form>
    <form method="post" action="{{ url_for('llaves_ver') }}">
      <button type="submit">Ver llave publica</button>
    </form>
  </div>

  <!-- ------------------------------------------------ PASO 2 -->
  <div class="tarjeta">
    <h2>Paso 2 &mdash; Copiar la llave al router</h2>
    <p class="ayuda">Unico momento de todo el proyecto en que hace falta la
       contrasena del router: la llave todavia no esta instalada. Se usa una
       sola vez y no se guarda en ningun sitio.</p>
    <form method="post" action="{{ url_for('llaves_copiar') }}">
      <label>Contrasena de {{ usuario }} en el router</label>
      <input type="password" name="password" autocomplete="off">
      <button class="crear" type="submit">2. Copiar al router</button>
    </form>
    <form method="post" action="{{ url_for('llaves_todo') }}"
          onsubmit="return confirm('Se va a generar un par de llaves NUEVO, copiarlo al router y comprobar el acceso. La llave anterior se pierde. Continuar?');">
      <label>Hacer los tres pasos de una vez</label>
      <input type="password" name="password" autocomplete="off"
             placeholder="Contrasena del router">
      <button class="crear" type="submit">Hacer todo de una vez</button>
    </form>
  </div>

  <!-- ------------------------------------------------ PASO 3 -->
  <div class="tarjeta">
    <h2>Paso 3 &mdash; Comprobar y mantenimiento</h2>
    <p class="ayuda">ssh RECHAZA una llave privada que puedan leer otros
       usuarios del sistema. Es la causa mas comun de
       <code>Permission denied</code>.</p>
    <div class="grupo-botones">
      <form method="post" action="{{ url_for('llaves_probar') }}">
        <button type="submit">3. Probar autenticacion</button></form>
      <form method="post" action="{{ url_for('llaves_permisos') }}">
        <button type="submit">Corregir permisos (600)</button></form>
    </div>
  </div>

</div>
{% endif %}

<div class="resultado">
  <h3>RESULTADO</h3>
  <pre class="{{ 'ok' if ok else ('error' if ok is not none else '') }}">{% if titulo %}== {{ titulo }} ==

{% endif %}{{ detalle }}</pre>
</div>
"""


# =============================================================================
#  PAGINA DE LLAVES SSH
# =============================================================================

def _llaves_permitido():
    """True si la peticion puede usar la seccion de llaves."""
    if PERMITIR_LLAVES_REMOTO:
        return True
    return request.remote_addr in ("127.0.0.1", "::1", "localhost")


def _guardar_llaves(terna):
    """Guarda el resultado y vuelve a la pagina de llaves."""
    _ultimo["ok"], _ultimo["titulo"], _ultimo["detalle"] = terna
    return redirect(url_for("llaves"))


def _bloqueado():
    """Respuesta cuando la peticion viene de fuera y no esta permitido."""
    _ultimo["ok"] = False
    _ultimo["titulo"] = "Acceso no permitido"
    _ultimo["detalle"] = ("Esta seccion solo se puede usar desde el propio "
                          "equipo (localhost).")
    return redirect(url_for("llaves"))


@app.route("/llaves")
def llaves():
    permitido = _llaves_permitido()
    return pagina(
        "Conexion y llaves SSH", CUERPO_LLAVES, "llaves",
        permitido=permitido,
        remoto=request.remote_addr,
        puerto=PUERTO,
        ip=mk.IP, usuario=mk.USUARIO, llave=mk.LLAVE,
        estado=mk.texto_estado_llaves() if permitido else "",
        autentica=mk.estado_llaves()["autentica"] if permitido else False,
        ok=_ultimo["ok"],
        titulo=_ultimo["titulo"],
        detalle=_ultimo["detalle"] or "Aqui apareceran los resultados.",
    )


@app.route("/llaves/conexion", methods=["POST"])
def llaves_conexion():
    if not _llaves_permitido():
        return _bloqueado()
    return _guardar_llaves(mk.op_guardar_conexion(campo("ip"), campo("usuario"),
                                                  campo("llave")))


@app.route("/llaves/generar", methods=["POST"])
def llaves_generar():
    if not _llaves_permitido():
        return _bloqueado()
    try:
        bits = int(campo("bits"))
    except ValueError:
        bits = 4096
    return _guardar_llaves(mk.op_generar_llaves(bits,
                                                "sobrescribir" in request.form))


@app.route("/llaves/copiar", methods=["POST"])
def llaves_copiar():
    if not _llaves_permitido():
        return _bloqueado()
    # La contrasena se usa aqui y se descarta: no se guarda ni se vuelve a
    # mandar al navegador en ningun momento.
    return _guardar_llaves(mk.op_copiar_llave_al_router(campo("password")))


@app.route("/llaves/todo", methods=["POST"])
def llaves_todo():
    """Encadena los tres pasos, parando en cuanto uno falle."""
    if not _llaves_permitido():
        return _bloqueado()

    password = campo("password")
    if not password:
        return _guardar_llaves((False, "Falta la contrasena",
                                "Para hacerlo todo de una vez hace falta la "
                                "contrasena del router."))

    ok, titulo, detalle = mk.op_generar_llaves(4096, True)
    if not ok:
        return _guardar_llaves((ok, titulo, detalle))

    ok2, titulo2, detalle2 = mk.op_copiar_llave_al_router(password)
    return _guardar_llaves((ok2, titulo2,
                            "Paso 1: " + titulo + "\n\n" + detalle2))


@app.route("/llaves/probar", methods=["POST"])
def llaves_probar():
    if not _llaves_permitido():
        return _bloqueado()
    return _guardar_llaves(mk.op_probar_autenticacion())


@app.route("/llaves/permisos", methods=["POST"])
def llaves_permisos():
    if not _llaves_permitido():
        return _bloqueado()
    return _guardar_llaves(mk.op_corregir_permisos())


@app.route("/llaves/ver", methods=["POST"])
def llaves_ver():
    if not _llaves_permitido():
        return _bloqueado()
    return _guardar_llaves(mk.op_ver_llave_publica())


# =============================================================================
#  ARRANQUE
# =============================================================================

if __name__ == "__main__":
    print("=" * 66)
    print(" CONTROL MIKROTIK ROUTER  -  version web")
    print(" Router:  " + mk.USUARIO + "@" + mk.IP)
    print(" Abrir en el navegador:  http://localhost:" + str(PUERTO))
    print(" Llaves SSH: " + ("accesible desde toda la red (PERMITIR_LLAVES_REMOTO=True)"
                             if PERMITIR_LLAVES_REMOTO else "solo desde localhost"))
    print(" Para detener el servidor:  Ctrl+C")
    print("=" * 66)
    try:
        app.run(host=HOST, port=PUERTO, debug=False)
    finally:
        # Que no queden scripts de monitoreo corriendo al cerrar el servidor
        mk.detener_monitoreo()
