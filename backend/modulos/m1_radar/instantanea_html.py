"""Instantanea navegable de la aplicacion en un solo archivo HTML.

PARA QUE: que alguien abra un archivo y recorra la aplicacion como si
estuviera corriendo —misma barra lateral, mismas pantallas, mismos datos— sin
instalar Python, sin levantar el servidor y sin ticket. Para mostrar el avance.

COMO: no se reescribe el HTML a mano. Se piden las paginas reales a la
aplicacion con el cliente de pruebas de FastAPI, se recorta el contenido de
cada una y se pegan todas en un documento con la navegacion resuelta en
JavaScript. Usar las plantillas de verdad es lo que garantiza que la
instantanea se vea igual que la aplicacion y que no se desincronice cuando la
aplicacion cambie.

QUE FUNCIONA Y QUE NO:
  - Navegar entre secciones: si.
  - Los enlaces a Mercado Publico: si, son los reales.
  - Filtros, botones y formularios: no. Es una copia estatica, y la pagina lo
    dice en pantalla en vez de dejar que alguien haga clic y no pase nada.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from backend.nucleo.logging import obtener_logger
from backend.nucleo.tiempo import ahora_local

log = obtener_logger(__name__)


@dataclass(frozen=True)
class Pantalla:
    """Una vista de la aplicacion dentro de la instantanea."""

    id: str
    ruta: str
    titulo: str
    grupo: str


#: Las pantallas que se capturan, en el orden de la barra lateral real.
PANTALLAS = (
    Pantalla("inicio", "/", "Inicio", ""),
    Pantalla("bandeja", "/radar/", "Bandeja del día", "RADAR (M1)"),
    Pantalla("licitaciones", "/radar/licitaciones", "Licitaciones", "RADAR (M1)"),
    Pantalla("perfiles", "/radar/perfiles", "Perfiles de interés", "RADAR (M1)"),
    Pantalla("organismos", "/radar/organismos", "Organismos", "RADAR (M1)"),
    Pantalla("sincronizaciones", "/radar/sincronizaciones", "Sincronizaciones", "RADAR (M1)"),
    Pantalla("procedimientos", "/procesos/", "Procedimientos", "PROCESOS (M0)"),
    Pantalla("revision", "/procesos/revision-semanal", "Revisión semanal", "PROCESOS (M0)"),
    Pantalla("modulos", "/sistema/modulos", "Módulos", "SISTEMA"),
    Pantalla("jobs", "/sistema/jobs", "Tareas programadas", "SISTEMA"),
    Pantalla("auditoria", "/sistema/auditoria", "Auditoría", "SISTEMA"),
)

RE_PRINCIPAL = re.compile(
    r'<main class="principal">(.*?)</main>', re.DOTALL
)


def _capturar(cliente, pantalla: Pantalla) -> str:
    """Pide una pagina y devuelve solo el contenido de <main>."""
    respuesta = cliente.get(pantalla.ruta + ("&" if "?" in pantalla.ruta else "?") + "limpio=1")
    if respuesta.status_code != 200:
        log.warning(
            "pantalla no capturada",
            extra={"ruta": pantalla.ruta, "http": respuesta.status_code},
        )
        return (
            '<div class="vacio">Esta pantalla no se pudo capturar '
            f"(HTTP {respuesta.status_code}).</div>"
        )
    encontrado = RE_PRINCIPAL.search(respuesta.text)
    if not encontrado:
        return '<div class="vacio">Esta pantalla no se pudo capturar.</div>'
    return encontrado.group(1)


def _inertizar(html: str) -> str:
    """Deja inertes los controles que necesitarian un servidor detras.

    Se desactivan en vez de borrarse: forman parte de lo que hay que mostrar
    («aqui se descarta con motivo»), pero un boton que parece funcionar y no
    hace nada es peor que uno visiblemente apagado.
    """
    # Los formularios no envian a ninguna parte.
    html = re.sub(r"<form\b[^>]*>", '<form onsubmit="return false" class="inerte">', html)
    # Inputs, selects y botones quedan deshabilitados.
    html = re.sub(r"<(input|select|textarea|button)\b", r"<\1 disabled", html)
    # Los enlaces internos de la aplicacion no llevan a ningun lado aqui; los
    # externos (Mercado Publico) se dejan intactos, que son los que importan.
    def _enlace(m: re.Match[str]) -> str:
        destino = m.group(1)
        if destino.startswith("http"):
            return m.group(0)
        return '<a class="inerte-enlace" href="#"'

    html = re.sub(r'<a\s+href="([^"]*)"', _enlace, html)
    return html


def construir(*, contenido_solo: bool = False) -> str:
    from fastapi.testclient import TestClient

    from backend.app import crear_app
    from backend.plantillas import DIRECTORIO_ESTATICOS

    app = crear_app(iniciar_planificador=False)
    secciones: list[str] = []

    with TestClient(app) as cliente:
        for i, pantalla in enumerate(PANTALLAS):
            cuerpo = _inertizar(_capturar(cliente, pantalla))
            oculto = "" if i == 0 else " hidden"
            secciones.append(
                f'<section class="pantalla" id="p-{pantalla.id}"{oculto}>{cuerpo}</section>'
            )

    css = (DIRECTORIO_ESTATICOS / "css" / "app.css").read_text(encoding="utf-8")

    nav: list[str] = []
    grupo_actual = None
    for i, p in enumerate(PANTALLAS):
        if p.grupo != grupo_actual:
            grupo_actual = p.grupo
            if p.grupo:
                nav.append(f'<div class="nav-grupo">{p.grupo}</div>')
        activo = " activo" if i == 0 else ""
        nav.append(
            f'<a href="#{p.id}" class="enlace-pantalla{activo}" '
            f'data-pantalla="{p.id}">{p.titulo}</a>'
        )

    fecha = ahora_local().strftime("%d-%m-%Y %H:%M")
    documento = PLANTILLA.format(
        css=css, nav="\n".join(nav), secciones="\n".join(secciones), fecha=fecha
    )

    if contenido_solo:
        return documento
    return (
        '<!doctype html>\n<html lang="es">\n<head>\n<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "</head>\n<body>\n" + documento + "\n</body>\n</html>\n"
    )


def exportar(destino: Path, *, contenido_solo: bool = False) -> dict:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = construir(contenido_solo=contenido_solo)
    destino.write_text(texto, encoding="utf-8")
    resumen = {
        "archivo": str(destino),
        "kb": round(destino.stat().st_size / 1024),
        "pantallas": len(PANTALLAS),
    }
    log.info("instantanea generada", extra=resumen)
    return resumen


PLANTILLA = """<title>Radar de Licitaciones ITO</title>
<meta name="claude:viewport-fit-sides" content="cover">
<style>
{css}

/* --- Añadidos propios de la instantánea estática ----------------------- */

.cinta {{
  background: var(--acento-suave);
  border-bottom: 1px solid var(--acento);
  color: var(--acento-fuerte);
  font-size: .82rem;
  padding-block: .55rem;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  display: flex; gap: .5rem; align-items: baseline; flex-wrap: wrap;
}}
.cinta strong {{ font-weight: 650; }}
.cinta .fecha {{ margin-left: auto; color: var(--texto-tenue); font-size: .78rem; }}

.pantalla[hidden] {{ display: none !important; }}

/* Controles sin servidor detrás: visibles, pero claramente apagados. */
.inerte button, .inerte input, .inerte select, .inerte textarea,
button[disabled], input[disabled], select[disabled] {{
  opacity: .45; cursor: not-allowed;
}}
.inerte-enlace {{ color: inherit; text-decoration: none; cursor: default; }}
.inerte-enlace:hover {{ text-decoration: none; }}

/* El enlace a Mercado Público sí funciona: que se note. */
td.ajustado a[href^="http"], .cod a[href^="http"] {{
  color: var(--acento); text-decoration: none;
}}
td.ajustado a[href^="http"]:hover {{ text-decoration: underline; }}
</style>

<div class="cinta">
  <strong>Copia estática para presentación.</strong>
  <span>Se navega entre secciones y los enlaces a Mercado Público funcionan.
    Los filtros y botones están apagados porque no hay servidor detrás.</span>
  <span class="fecha">Datos al {fecha}</span>
</div>

<div class="app">
  <aside class="lateral">
    <div class="marca">
      <strong>SGL</strong>
      <span>Licitaciones y contratos · ITO</span>
    </div>
    <nav class="nav">
      {nav}
    </nav>
    <div class="pila tenue pequeno" style="margin-top:auto">
      <span>v0.1.0</span>
      <span>instantánea</span>
    </div>
  </aside>

  <main class="principal">
    {secciones}
  </main>
</div>

<script>
(function () {{
  var enlaces = document.querySelectorAll('.enlace-pantalla');
  var pantallas = document.querySelectorAll('.pantalla');

  function mostrar(id) {{
    pantallas.forEach(function (p) {{ p.hidden = (p.id !== 'p-' + id); }});
    enlaces.forEach(function (a) {{
      a.classList.toggle('activo', a.dataset.pantalla === id);
    }});
    window.scrollTo(0, 0);
  }}

  enlaces.forEach(function (a) {{
    a.addEventListener('click', function (e) {{
      e.preventDefault();
      var id = a.dataset.pantalla;
      mostrar(id);
      // Hash simple para poder enlazar a una sección concreta.
      history.replaceState(null, '', '#' + id);
    }});
  }});

  var inicial = (location.hash || '').replace('#', '');
  if (inicial && document.getElementById('p-' + inicial)) mostrar(inicial);
}})();
</script>
"""
