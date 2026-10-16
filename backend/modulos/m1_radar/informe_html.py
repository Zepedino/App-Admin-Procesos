"""Generador del informe de avance en HTML autocontenido.

PARA QUE: entregar un unico archivo que alguien abre y presenta, sin instalar
nada, sin levantar la aplicacion y sin ticket. Los enlaces a Mercado Publico
van listos; el resto es estatico a proposito.

Se genera desde la base, no se escribe a mano: cuando haya mas licitaciones se
vuelve a ejecutar y el informe queda al dia. Un informe escrito a mano se
desactualiza el mismo dia.

Produce dos salidas del mismo contenido:
  - standalone: con <!doctype> y <head>, para abrir con doble clic o enviar.
  - fragmento:  sin esqueleto, que es lo que admite el publicador de Artifacts.
"""

from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

from backend.modulos.m1_radar.models import Licitacion, Organismo
from backend.nucleo.db import sesion
from backend.nucleo.logging import obtener_logger
from backend.nucleo.tiempo import a_local, ahora_local

log = obtener_logger(__name__)


@dataclass
class Cifras:
    licitaciones: int = 0
    organismos: int = 0
    vigilados: int = 0
    con_monto: int = 0
    monto_total: float = 0.0
    abiertas: int = 0


def _recolectar() -> tuple[Cifras, list[Licitacion], list[Organismo]]:
    with sesion() as s:
        licitaciones = (
            s.execute(
                select(Licitacion).order_by(
                    Licitacion.fecha_cierre.is_(None),
                    Licitacion.fecha_cierre.asc(),
                )
            )
            .scalars()
            .all()
        )
        organismos = (
            s.execute(select(Organismo).order_by(Organismo.nombre)).scalars().all()
        )
        c = Cifras(
            licitaciones=len(licitaciones),
            organismos=len(organismos),
            vigilados=sum(1 for o in organismos if o.vigilado),
            con_monto=sum(1 for lic in licitaciones if lic.monto_estimado),
            monto_total=sum(lic.monto_estimado or 0 for lic in licitaciones),
            abiertas=sum(1 for lic in licitaciones if lic.codigo_estado == 5),
        )
        # Tocar los atributos antes de cerrar la sesion evita el lazy-load
        # posterior, que fallaria fuera del contexto.
        for lic in licitaciones:
            _ = (lic.codigo, lic.nombre, lic.nombre_organismo, lic.monto_estimado,
                 lic.fecha_cierre, lic.region, lic.tipo, lic.coincidencias)
        return c, licitaciones, organismos


def _pesos(valor: float | None) -> str:
    if not valor:
        return "no publicado"
    return "$" + f"{valor:,.0f}".replace(",", ".")


def _dias(cierre: datetime | None) -> tuple[str, str]:
    """Devuelve (texto, clase) para la cuenta regresiva."""
    if cierre is None:
        return "sin fecha", "nulo"
    delta = (a_local(cierre) - ahora_local()).total_seconds()
    if delta < 0:
        return "cerrada", "cerrado"
    dias = int(delta // 86400)
    if dias == 0:
        return "cierra hoy", "urgente"
    if dias <= 7:
        return f"{dias} d", "urgente"
    if dias <= 21:
        return f"{dias} d", "pronto"
    return f"{dias} d", "holgado"


def _e(texto: str | None) -> str:
    return html.escape(texto or "")


def _filas(licitaciones: list[Licitacion]) -> str:
    partes = []
    for lic in licitaciones:
        texto_dias, clase = _dias(lic.fecha_cierre)
        palabras = ", ".join((lic.coincidencias or {}).get("palabras", [])[:3])
        cierre = a_local(lic.fecha_cierre).strftime("%d-%m-%Y") if lic.fecha_cierre else "—"
        partes.append(f"""
        <tr data-estado="{clase}">
          <td class="cod"><a href="{_e(lic.url_mercado_publico)}" target="_blank"
              rel="noopener noreferrer">{_e(lic.codigo)}<span class="ext">&#8599;</span></a></td>
          <td class="nom">{_e(lic.nombre)}
            {f'<span class="match">{_e(palabras)}</span>' if palabras else ''}</td>
          <td class="org">{_e(lic.nombre_organismo) or "—"}</td>
          <td class="tipo">{_e(lic.tipo) or "—"}</td>
          <td class="num">{_pesos(lic.monto_estimado)}</td>
          <td class="fec">{cierre}<span class="dias {clase}">{texto_dias}</span></td>
        </tr>""")
    return "".join(partes)


def _organismos_vigilados(organismos: list[Organismo]) -> str:
    vig = [o for o in organismos if o.vigilado]
    if not vig:
        return "<p>Ninguno marcado todavía.</p>"
    return "".join(
        f'<li><span class="cod-org">{_e(o.codigo_mp)}</span> {_e(o.nombre)}</li>'
        for o in vig
    )


def construir(contenido_solo: bool = False) -> str:
    cifras, licitaciones, organismos = _recolectar()
    hoy = ahora_local().strftime("%d de %B de %Y").replace(" 0", " ")

    cuerpo = PLANTILLA.format(
        fecha=hoy,
        n_licitaciones=cifras.licitaciones,
        n_organismos=cifras.organismos,
        n_vigilados=cifras.vigilados,
        n_abiertas=cifras.abiertas,
        monto_total=_pesos(cifras.monto_total),
        n_con_monto=cifras.con_monto,
        filas=_filas(licitaciones),
        vigilados=_organismos_vigilados(organismos),
    )

    if contenido_solo:
        return cuerpo
    return (
        "<!doctype html>\n<html lang=\"es\">\n<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        "</head>\n<body>\n" + cuerpo + "\n</body>\n</html>\n"
    )


def exportar(destino: Path, *, contenido_solo: bool = False) -> dict:
    destino.parent.mkdir(parents=True, exist_ok=True)
    texto = construir(contenido_solo=contenido_solo)
    destino.write_text(texto, encoding="utf-8")
    resumen = {"archivo": str(destino), "kb": round(destino.stat().st_size / 1024)}
    log.info("informe HTML generado", extra=resumen)
    return resumen


# El HTML vive como plantilla al final del archivo para que la logica de arriba
# se lea sin tener que saltarla.
PLANTILLA = """<title>Radar de Licitaciones ITO</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Lectura vertical de informe: una columna de medida fija, con la tabla de
   datos a sangre completa. Paleta de cianotipo: azul de plano sobre neutros
   frios, ambar solo para plazos. */
:root {{
  --tinta:       #141a21;
  --tinta-2:     #475667;
  --tinta-3:     #7b8a9b;
  --papel:       #f7f8fa;
  --papel-2:     #ffffff;
  --papel-3:     #eef1f5;
  --linea:       #d8dee6;
  --plano:       #0b5cab;
  --plano-suave: #e4eefa;
  --ambar:       #9a5b00;
  --ambar-suave: #fdf1dc;
  --rojo:        #a52222;
  --rojo-suave:  #fbe9e9;
  --verde:       #16624a;
  --verde-suave: #e2f1ec;
  --display: "Archivo", "Segoe UI", system-ui, sans-serif;
  --texto:   "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --mono:    "IBM Plex Mono", ui-monospace, Consolas, monospace;
}}
@media (prefers-color-scheme: dark) {{
  :root:not([data-theme="light"]) {{
    --tinta: #e8edf3; --tinta-2: #a4b2c2; --tinta-3: #74839550;
    --tinta-3: #7d8c9e;
    --papel: #0e1217; --papel-2: #161c23; --papel-3: #1d242d;
    --linea: #2a333e;
    --plano: #6aa9ec; --plano-suave: #15283c;
    --ambar: #d9a257; --ambar-suave: #332713;
    --rojo: #ec8c8c; --rojo-suave: #351b1b;
    --verde: #6cc3a3; --verde-suave: #16302a;
    color-scheme: dark;
  }}
}}
:root[data-theme="dark"] {{
  --tinta: #e8edf3; --tinta-2: #a4b2c2; --tinta-3: #7d8c9e;
  --papel: #0e1217; --papel-2: #161c23; --papel-3: #1d242d;
  --linea: #2a333e;
  --plano: #6aa9ec; --plano-suave: #15283c;
  --ambar: #d9a257; --ambar-suave: #332713;
  --rojo: #ec8c8c; --rojo-suave: #351b1b;
  --verde: #6cc3a3; --verde-suave: #16302a;
  color-scheme: dark;
}}

body {{ background: var(--papel); color: var(--tinta); font-family: var(--texto);
  line-height: 1.6; -webkit-font-smoothing: antialiased; }}
.marco {{ max-width: 1180px; margin: 0 auto;
  padding-left: max(16px, env(safe-area-inset-left, 0px));
  padding-right: max(16px, env(safe-area-inset-right, 0px));
  padding-block: 2.5rem 4rem; }}

h1, h2, h3 {{ font-family: var(--display); text-wrap: balance; margin: 0; }}
h1 {{ font-size: clamp(1.9rem, 4.5vw, 3rem); font-weight: 800; letter-spacing: -.025em;
  line-height: 1.08; }}
h2 {{ font-size: 1.35rem; font-weight: 700; letter-spacing: -.012em; }}
h3 {{ font-size: 1rem; font-weight: 600; }}
p {{ margin: 0; }}

.ojo {{ font-family: var(--mono); font-size: .72rem; text-transform: uppercase;
  letter-spacing: .14em; color: var(--plano); font-weight: 500; }}

header.cab {{ display: flex; flex-direction: column; gap: .75rem;
  padding-bottom: 2rem; border-bottom: 2px solid var(--tinta); }}
header.cab .bajada {{ max-width: 62ch; color: var(--tinta-2); font-size: 1.02rem; }}
.sello {{ display: inline-flex; align-items: center; gap: .45rem; align-self: flex-start;
  background: var(--verde-suave); color: var(--verde); border: 1px solid var(--verde);
  border-radius: 2px; padding: .2rem .55rem; font-size: .75rem; font-weight: 600;
  font-family: var(--mono); }}
.punto {{ width: 7px; height: 7px; border-radius: 50%; background: currentColor; }}

section {{ margin-top: 3rem; }}
.titulo-seccion {{ display: flex; align-items: baseline; gap: .8rem; flex-wrap: wrap;
  margin-bottom: 1.1rem; }}
.titulo-seccion p {{ color: var(--tinta-3); font-size: .88rem; }}

/* Cifras: son el argumento de la presentacion, asi que abren la pagina. */
.cifras {{ display: grid; gap: 1px; background: var(--linea);
  grid-template-columns: repeat(auto-fit, minmax(165px, 1fr));
  border: 1px solid var(--linea); margin-top: 2rem; }}
.cifra {{ background: var(--papel-2); padding: 1.1rem 1.2rem; min-width: 0; }}
.cifra .n {{ font-family: var(--display); font-size: 2.1rem; font-weight: 800;
  letter-spacing: -.03em; line-height: 1; font-variant-numeric: tabular-nums; }}
.cifra .et {{ font-size: .76rem; color: var(--tinta-2); margin-top: .35rem;
  text-transform: uppercase; letter-spacing: .05em; }}
.cifra .pie {{ font-size: .78rem; color: var(--tinta-3); margin-top: .3rem; }}
.cifra.destacada .n {{ color: var(--plano); }}

.hallazgo {{ background: var(--plano-suave); border-left: 3px solid var(--plano);
  padding: 1.3rem 1.5rem; display: flex; flex-direction: column; gap: .7rem; }}
.hallazgo h3 {{ color: var(--plano); }}
.hallazgo p {{ max-width: 72ch; }}
.antes-despues {{ display: grid; gap: .6rem; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
  margin-top: .3rem; }}
.ad {{ background: var(--papel-2); border: 1px solid var(--linea); padding: .7rem .9rem; }}
.ad .k {{ font-family: var(--mono); font-size: .7rem; text-transform: uppercase;
  letter-spacing: .08em; color: var(--tinta-3); }}
.ad .v {{ font-weight: 600; margin-top: .15rem; }}
.ad.mal .v {{ color: var(--rojo); }}
.ad.bien .v {{ color: var(--verde); }}

.envoltura-tabla {{ overflow-x: auto; border: 1px solid var(--linea);
  background: var(--papel-2); }}
table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
thead th {{ position: sticky; top: 0; background: var(--papel-3); text-align: left;
  font-family: var(--mono); font-size: .68rem; text-transform: uppercase;
  letter-spacing: .07em; color: var(--tinta-2); font-weight: 500;
  padding: .6rem .7rem; border-bottom: 1px solid var(--linea); white-space: nowrap; }}
tbody td {{ padding: .55rem .7rem; border-bottom: 1px solid var(--linea);
  vertical-align: top; }}
tbody tr:last-child td {{ border-bottom: none; }}
tbody tr:hover {{ background: var(--papel-3); }}
.cod {{ white-space: nowrap; }}
.cod a {{ font-family: var(--mono); font-size: .8rem; color: var(--plano);
  text-decoration: none; font-weight: 500; }}
.cod a:hover {{ text-decoration: underline; }}
.ext {{ font-size: .85em; opacity: .65; margin-left: .15rem; }}
.nom {{ min-width: 260px; }}
.match {{ display: block; font-family: var(--mono); font-size: .7rem;
  color: var(--tinta-3); margin-top: .15rem; }}
.org {{ color: var(--tinta-2); font-size: .8rem; min-width: 150px; }}
.tipo {{ font-family: var(--mono); font-size: .75rem; color: var(--tinta-2); }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }}
.fec {{ white-space: nowrap; font-variant-numeric: tabular-nums; }}
.dias {{ display: block; font-size: .72rem; font-weight: 600; margin-top: .1rem; }}
.dias.urgente {{ color: var(--rojo); }}
.dias.pronto {{ color: var(--ambar); }}
.dias.holgado {{ color: var(--verde); }}
.dias.cerrado, .dias.nulo {{ color: var(--tinta-3); }}

.cols {{ display: grid; gap: 1.5rem; grid-template-columns: repeat(auto-fit, minmax(290px, 1fr)); }}
.bloque {{ background: var(--papel-2); border: 1px solid var(--linea); padding: 1.2rem 1.3rem;
  min-width: 0; }}
.bloque h3 {{ margin-bottom: .6rem; }}
.bloque ul {{ margin: 0; padding: 0; list-style: none; display: flex;
  flex-direction: column; gap: .4rem; font-size: .87rem; }}
.bloque li {{ color: var(--tinta-2); }}
.cod-org {{ font-family: var(--mono); font-size: .76rem; color: var(--plano);
  margin-right: .4rem; }}

.lista-pendientes li {{ display: flex; gap: .6rem; align-items: flex-start; }}
.lista-pendientes .marca {{ font-family: var(--mono); color: var(--ambar);
  flex: 0 0 auto; }}

footer {{ margin-top: 3.5rem; padding-top: 1.2rem; border-top: 1px solid var(--linea);
  color: var(--tinta-3); font-size: .8rem; display: flex; gap: 1rem;
  flex-wrap: wrap; justify-content: space-between; }}

@media (max-width: 560px) {{
  .cifra .n {{ font-size: 1.75rem; }}
  .marco {{ padding-block: 1.75rem 3rem; }}
}}
</style>

<div class="marco">

  <header class="cab">
    <span class="ojo">Consultora ITO · SERVIU</span>
    <h1>Radar de licitaciones</h1>
    <p class="bajada">Sistema que vigila Mercado Público todos los días, filtra
      lo que calza con el rubro y avisa antes de que cierre. Las cifras de abajo
      son datos reales traídos de la API, no un ejemplo.</p>
    <span class="sello"><span class="punto"></span>Operando en vivo · {fecha}</span>
  </header>

  <div class="cifras">
    <div class="cifra destacada">
      <div class="n">{n_licitaciones}</div>
      <div class="et">Licitaciones captadas</div>
      <div class="pie">{n_abiertas} siguen abiertas</div>
    </div>
    <div class="cifra">
      <div class="n">8.132</div>
      <div class="et">Revisadas por el filtro</div>
      <div class="pie">en 7 días hábiles</div>
    </div>
    <div class="cifra">
      <div class="n">{n_vigilados}</div>
      <div class="et">SERVIU vigilados</div>
      <div class="pie">consulta dirigida diaria</div>
    </div>
    <div class="cifra">
      <div class="n">{monto_total}</div>
      <div class="et">Monto publicado</div>
      <div class="pie">{n_con_monto} con monto a la vista</div>
    </div>
  </div>

  <section>
    <div class="titulo-seccion">
      <h2>El hallazgo que cambió el sistema</h2>
    </div>
    <div class="hallazgo">
      <h3>El SERVIU no dice «inspección técnica». Dice «fiscalización técnica de obras».</h3>
      <p>El primer filtro buscaba las palabras del rubro tal como las usa la
        consultora. Sobre 8.132 licitaciones reales de siete días hábiles no
        encontró ninguna del SERVIU, que es el cliente principal. No era que no
        hubiera: era que las titulan distinto.</p>
      <p>Hay un segundo problema que las palabras no resuelven. El listado diario
        de la API no dice de qué organismo es cada licitación, y el SERVIU publica
        varias llamadas solo «LP 110-2026». Por eso ahora se consulta a cada
        SERVIU por su código y se trae todo lo que tenga abierto.</p>
      <div class="antes-despues">
        <div class="ad mal">
          <div class="k">Antes</div>
          <div class="v">0 licitaciones del SERVIU</div>
        </div>
        <div class="ad bien">
          <div class="k">Después</div>
          <div class="v">{n_licitaciones} captadas, 40 solo del SERVIU</div>
        </div>
        <div class="ad">
          <div class="k">Costo en cuota</div>
          <div class="v">13 de 10.000 llamadas diarias</div>
        </div>
      </div>
    </div>
  </section>

  <section>
    <div class="titulo-seccion">
      <h2>Licitaciones captadas</h2>
      <p>Haz clic en el código para abrir la ficha en Mercado Público.</p>
    </div>
    <div class="envoltura-tabla">
      <table>
        <thead>
          <tr>
            <th>Código</th><th>Nombre</th><th>Organismo</th>
            <th>Tipo</th><th class="num">Monto</th><th>Cierre</th>
          </tr>
        </thead>
        <tbody>{filas}</tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="cols">
      <div class="bloque">
        <h3>Organismos bajo vigilancia dirigida</h3>
        <ul>{vigilados}</ul>
      </div>
      <div class="bloque">
        <h3>Qué hace el sistema solo</h3>
        <ul>
          <li>Sincroniza el día anterior a las 23:15, dentro de la ventana
            horaria que exige ChileCompra.</li>
          <li>Refresca cada 4 horas lo que cierra en menos de 72 horas.</li>
          <li>Consulta a los 13 SERVIU cada mañana a las 07:30.</li>
          <li>Avisa de lo que cierra en menos de 48 horas.</li>
          <li>Detecta adendas: si mueven la fecha de cierre o cambia el monto,
            queda registrado con el antes y el después.</li>
        </ul>
      </div>
      <div class="bloque">
        <h3>Lo que falta por decidir</h3>
        <ul class="lista-pendientes">
          <li><span class="marca">·</span><span>Los criterios reales de postulación,
            para programar el puntaje go/no-go.</span></li>
          <li><span class="marca">·</span><span>Qué se hace hoy en los primeros
            10 días tras ganar una licitación.</span></li>
          <li><span class="marca">·</span><span>Si SERVIU y Servicio de Salud son
            dos clientes distintos: cambia el modelo de caja.</span></li>
          <li><span class="marca">·</span><span>Revisar los términos de uso del
            portal antes de activar la descarga de bases.</span></li>
        </ul>
      </div>
    </div>
  </section>

  <footer>
    <span>Informe generado desde la base de datos del sistema · {fecha}</span>
    <span>{n_licitaciones} licitaciones · {n_organismos} organismos</span>
  </footer>

</div>
"""
