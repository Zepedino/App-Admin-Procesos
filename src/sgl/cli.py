"""Interfaz de linea de comandos.

Es la herramienta de operacion y diagnostico. Todo lo que hace un job se puede
hacer desde aqui a mano, que es lo que se necesita cuando algo falla a las 23:15
y hay que reponer un dia.

    python -m sgl.cli doctor
    python -m sgl.cli init-db
    python -m sgl.cli sync-dia 2026-09-04 --limite 20
    python -m sgl.cli traer 425-57-LR26
    python -m sgl.cli capturar-fixture 425-57-LR26
    python -m sgl.cli importar-procedimientos
    python -m sgl.cli run-job m1_radar.pull_liviano
    python -m sgl.cli estado
    python -m sgl.cli serve
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from sgl import __version__
from sgl.core.config import obtener_config
from sgl.core.logging import configurar_logging, obtener_logger

log = obtener_logger("sgl.cli")


def _importar_modelos() -> None:
    from sgl.main import _importar_modelos as importar

    importar()


def _parsear_dia(texto: str) -> date:
    """Acepta 2026-09-04 y 04092026, que es el formato de la API."""
    texto = texto.strip()
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return datetime.strptime(texto, "%d%m%Y").date()


# --- Comandos ----------------------------------------------------------------


def cmd_doctor(args: argparse.Namespace) -> int:
    """Verifica que el entorno este en condiciones de operar.

    Se ejecuta antes de culpar al codigo: la mayoria de los problemas de estos
    sistemas son de configuracion, no de logica.
    """
    from sqlalchemy import text

    from sgl.core.db import obtener_motor
    from sgl.providers.llm import obtener_llm
    from sgl.providers.procurement import obtener_proveedor
    from sgl.providers.storage import obtener_storage

    cfg = obtener_config()
    problemas: list[str] = []
    avisos: list[str] = []

    print(f"\n  SGL v{__version__}  ·  entorno: {cfg.env}\n")
    print("  CONFIGURACION")
    print(f"    zona horaria         {cfg.timezone}")
    motor_url = cfg.database_url.split("@")[-1] if "@" in cfg.database_url else cfg.database_url
    print(f"    base de datos        {motor_url}")

    if cfg.es_produccion and cfg.secret_key == "dev-inseguro-cambiar":
        problemas.append("APP_SECRET_KEY sigue con el valor por defecto en produccion")

    print("\n  BASE DE DATOS")
    try:
        with obtener_motor().connect() as c:
            c.execute(text("SELECT 1"))
        print("    conexion             ok")
    except Exception as exc:
        problemas.append(f"no se puede conectar a la base de datos: {exc}")
        print(f"    conexion             FALLA — {exc}")

    print("\n  MERCADO PUBLICO")
    proveedor = obtener_proveedor()
    print(f"    proveedor            {proveedor.nombre}")
    print(f"    datos en vivo        {'si' if proveedor.en_vivo else 'NO (respuestas guardadas)'}")
    if not cfg.mp.hay_ticket:
        avisos.append(
            "MP_TICKET no configurado: se opera con fixtures. "
            "Solicitalo con Clave Unica; llega por correo."
        )
    try:
        cuota = proveedor.estado_cuota()
        print(f"    cuota hoy            {cuota.usadas} / {cuota.tope} ({cuota.porcentaje:.1f}%)")
        if cuota.degradado:
            avisos.append("cuota en modo degradado: solo se refresca lo que cierra en <48h")
    except Exception as exc:
        problemas.append(f"no se pudo leer la cuota: {exc}")

    from sgl.core.tiempo import ahora_local, descripcion_ventana_batch, en_ventana_batch

    print(f"    ventana batch        {descripcion_ventana_batch()} "
          f"(ahora {ahora_local():%H:%M} — {'dentro' if en_ventana_batch() else 'fuera'})")

    print("\n  SCRAPER")
    print(f"    habilitado           {'si' if cfg.scraper.habilitado else 'no'}")
    if cfg.scraper.habilitado and not cfg.scraper.contacto_email:
        problemas.append(
            "el scraper esta habilitado sin SCRAPER_CONTACTO_EMAIL: "
            "RF-2.3 exige user-agent identificable con correo de contacto"
        )

    print("\n  IA")
    llm = obtener_llm()
    print(f"    proveedor            {llm.nombre} ({'disponible' if llm.disponible else 'inactivo'})")

    print("\n  ALMACENAMIENTO")
    try:
        storage = obtener_storage()
        print(f"    backend              {storage.nombre}")
    except Exception as exc:
        problemas.append(f"almacenamiento no disponible: {exc}")

    print("\n  MODULOS")
    from sgl.modules import obtener_registro

    for estado, total in obtener_registro().resumen().items():
        print(f"    {estado:<20} {total}")

    print()
    for aviso in avisos:
        print(f"  [aviso]    {aviso}")
    for problema in problemas:
        print(f"  [PROBLEMA] {problema}")
    if not problemas and not avisos:
        print("  Todo en orden.")
    print()
    return 1 if problemas else 0


def cmd_init_db(args: argparse.Namespace) -> int:
    """Crea las tablas y carga los datos semilla imprescindibles."""
    from sgl.core.db import obtener_motor
    from sgl.core.modelo_base import Base

    _importar_modelos()
    Base.metadata.create_all(obtener_motor())
    print(f"  Tablas creadas: {len(Base.metadata.tables)}")
    for nombre in sorted(Base.metadata.tables):
        print(f"    - {nombre}")

    if args.con_semilla:
        creados = _cargar_semilla()
        print(f"\n  Datos semilla: {creados}")
    return 0


def _cargar_semilla() -> dict:
    """Datos minimos para que el sistema sea usable al primer arranque.

    El perfil de interes se crea a partir de los ejemplos textuales del PRD
    (RF-1.2). Es un punto de partida explicito y editable, no un valor oculto
    en el codigo: hay que ajustarlo con Daniela (pregunta abierta 5).
    """
    from sqlalchemy import select

    from sgl.core.db import sesion
    from sgl.modules.m0_procesos.models import EstadoCicloVida
    from sgl.modules.m1_radar.models import PerfilInteres

    creados = {"perfiles": 0, "estados_ciclo": 0}

    with sesion() as s:
        if not s.execute(select(PerfilInteres)).first():
            s.add(
                PerfilInteres(
                    nombre="ITO y supervision de obras (borrador)",
                    activo=True,
                    descripcion=(
                        "Punto de partida tomado de los ejemplos del PRD RF-1.2. "
                        "AJUSTAR con Daniela: pregunta abierta 5."
                    ),
                    palabras_clave=[
                        "inspeccion tecnica",
                        "inspeccion tecnica de obra",
                        "ITO",
                        "asesoria a la inspeccion",
                        "supervision de obras",
                        "asesoria tecnica",
                    ],
                    palabras_excluidas=["suministro", "arriendo", "provision de", "adquisicion"],
                    categorias_unspsc=["7213", "8110", "8010"],
                    regiones=[],
                    tipos_licitacion=[],
                    umbral_interes=0.5,
                )
            )
            creados["perfiles"] = 1

        if not s.execute(select(EstadoCicloVida)).first():
            # RF-0.2: cada estado del ciclo de vida (PRD seccion 1) con
            # responsable y SLA. Los SLA son propuestas; se ajustan con el equipo.
            etapas = [
                ("deteccion", "Deteccion", "licitaciones", 1),
                ("evaluacion", "Evaluacion", "licitaciones", 3),
                ("decision", "Decision go/no-go", "gerencia", 2),
                ("preparacion", "Preparacion de oferta", "licitaciones", 7),
                ("ofertada", "Ofertada", "licitaciones", None),
                ("adjudicada", "Adjudicada", "gerencia", 2),
                ("puesta_en_marcha", "Puesta en marcha", "ito", 10),
                ("ejecucion", "Ejecucion", "ito", None),
                ("estados_pago", "Estados de pago", "finanzas", 30),
                ("cierre", "Cierre", "finanzas", 30),
            ]
            for orden, (clave, nombre, rol, sla) in enumerate(etapas, start=1):
                s.add(
                    EstadoCicloVida(
                        clave=clave, nombre=nombre, orden=orden,
                        rol_responsable=rol, sla_dias=sla,
                    )
                )
            creados["estados_ciclo"] = len(etapas)

    return creados


def cmd_sync_dia(args: argparse.Namespace) -> int:
    """Sincroniza un dia. Es el paso 1 del arranque del PRD seccion 12."""
    from sgl.modules.m1_radar.services import sincronizar_dia

    _importar_modelos()
    # "ayer" es el de Chile, no el del reloj del servidor: en un host en UTC
    # (Render lo esta) durante la noche chilena serian dias distintos.
    from sgl.core.tiempo import ahora_local

    dia = _parsear_dia(args.dia) if args.dia else (ahora_local().date() - timedelta(days=1))
    resultado = sincronizar_dia(dia, limite_detalles=args.limite)

    print(f"\n  Sincronizacion de {dia.isoformat()}\n")
    print(f"    licitaciones del dia (API)   {resultado.total_api}")
    print(f"    candidatas tras el filtro    {resultado.candidatas}")
    print(f"    detalles pedidos             {resultado.detalles_pedidos}")
    print(f"    nuevas                       {resultado.nuevas}")
    print(f"    actualizadas                 {resultado.actualizadas}")
    print(f"    cambios detectados           {resultado.cambios_detectados}")
    if resultado.omitidas_por_cuota:
        print(f"    omitidas por limite          {resultado.omitidas_por_cuota}")
    for e in resultado.errores:
        print(f"    [error] {e}")
    if resultado.total_api and not resultado.candidatas:
        print(
            "\n    Ninguna candidata. Revisa las palabras clave del perfil en /radar/perfiles."
        )
    print()
    return 1 if resultado.errores else 0


def cmd_traer(args: argparse.Namespace) -> int:
    """RF-5.1: trae una licitacion por codigo, aunque nunca haya pasado por el radar."""
    from sgl.modules.m1_radar.services import importar_por_codigo

    _importar_modelos()
    licitacion = importar_por_codigo(args.codigo)
    print(f"\n  {licitacion.codigo}")
    print(f"    {licitacion.nombre}")
    print(f"    organismo   {licitacion.nombre_organismo}")
    print(f"    estado      {licitacion.estado_texto} ({licitacion.codigo_estado})")
    print(f"    cierre      {licitacion.fecha_cierre}")
    print(f"    monto       {licitacion.monto_estimado}")
    print(f"    puntaje     {licitacion.puntaje_perfil}")
    print()
    return 0


def cmd_capturar_fixture(args: argparse.Namespace) -> int:
    """Guarda una respuesta REAL de la API como fixture.

    Es como se construye el banco de casos de prueba de la fase 0 del PRD:
    5 a 10 licitaciones historicas reales, incluida una adjudicada con sus bases.
    """
    import httpx

    cfg = obtener_config()
    if not cfg.mp.hay_ticket:
        print("  Se necesita MP_TICKET para capturar fixtures desde la API real.")
        return 1

    destino = cfg.ruta("tests/fixtures/api")
    destino.mkdir(parents=True, exist_ok=True)

    if args.dia:
        dia = _parsear_dia(args.dia)
        parametros = {"fecha": dia.strftime("%d%m%Y")}
        nombre = f"licitaciones_fecha_{parametros['fecha']}"
    else:
        parametros = {"codigo": args.codigo.strip().upper()}
        nombre = f"licitacion_{parametros['codigo']}"

    with httpx.Client(base_url=cfg.mp.base_url, timeout=cfg.mp.timeout_seg) as cliente:
        respuesta = cliente.get(
            "licitaciones.json", params={**parametros, "ticket": cfg.mp.ticket}
        )
        respuesta.raise_for_status()
        datos = respuesta.json()

    archivo: Path = destino / f"{nombre}.json"
    archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  Guardado {archivo}  ({archivo.stat().st_size} bytes, "
          f"{len(datos.get('Listado') or [])} registros)")
    return 0


def cmd_importar_procedimientos(args: argparse.Namespace) -> int:
    """RF-0.1: carga el PROCESO.md de cada modulo y lo deja visible en /procesos/."""
    from sgl.modules.m0_procesos.services import importar_desde_paquetes

    _importar_modelos()
    raiz = obtener_config().raiz / "src" / "sgl" / "modules"
    resumen = importar_desde_paquetes(raiz)

    print()
    print(
        f"  Procedimientos: {resumen['creados']} creados, "
        f"{resumen['actualizados']} actualizados, "
        f"{resumen['sin_cambios']} sin cambios"
    )
    print()
    for nombre in resumen["archivos"]:
        print(f"    - {nombre}")
    if not resumen["archivos"]:
        print("    Ningun modulo tiene PROCESO.md todavia.")
    print()
    return 0


def cmd_run_job(args: argparse.Namespace) -> int:
    """Ejecuta un job a mano. Para reponer lo que fallo de noche."""
    from sgl.core.planificador import PLANIFICADOR
    from sgl.main import crear_app

    crear_app(iniciar_planificador=False)

    if not args.job_id:
        print("\n  Jobs disponibles:\n")
        for j in PLANIFICADOR.listar():
            print(f"    {j['id']:<38} {j['descripcion']}")
        print()
        return 0

    ejecucion = PLANIFICADOR.ejecutar(args.job_id)
    print(f"\n  {ejecucion.job_id}: {'ok' if ejecucion.ok else 'FALLO'} "
          f"en {ejecucion.duracion_seg:.1f} s")
    if ejecucion.detalle:
        print(f"    {json.dumps(ejecucion.detalle, ensure_ascii=False, default=str)}")
    if ejecucion.error:
        print(f"    {ejecucion.error}")
    print()
    return 0 if ejecucion.ok else 1


def cmd_estado(args: argparse.Namespace) -> int:
    """Resumen del contenido del sistema."""
    from sqlalchemy import func, select

    from sgl.core.db import sesion
    from sgl.modules.m1_radar.models import Licitacion, Organismo

    _importar_modelos()
    with sesion() as s:
        total = s.execute(select(func.count(Licitacion.id))).scalar_one()
        organismos = s.execute(select(func.count(Organismo.id))).scalar_one()
        por_estado = s.execute(
            select(Licitacion.estado_seguimiento, func.count(Licitacion.id)).group_by(
                Licitacion.estado_seguimiento
            )
        ).all()

    print(f"\n  Licitaciones: {total}   Organismos: {organismos}\n")
    for estado, cantidad in por_estado:
        print(f"    {estado:<18} {cantidad}")
    print()
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run(
        "sgl.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_config=None,  # usamos nuestro logging
    )
    return 0


# --- Parser ------------------------------------------------------------------


def construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sgl",
        description="Sistema Unico de Gestion de Licitaciones y Contratos — ITO / SERVIU",
    )
    parser.add_argument("--version", action="version", version=f"sgl {__version__}")
    sub = parser.add_subparsers(dest="comando", required=True)

    p = sub.add_parser("doctor", help="verifica entorno, conectividad y cuota")
    p.set_defaults(func=cmd_doctor)

    p = sub.add_parser("init-db", help="crea las tablas")
    p.add_argument("--con-semilla", action="store_true", help="carga perfil y ciclo de vida")
    p.set_defaults(func=cmd_init_db)

    p = sub.add_parser("sync-dia", help="sincroniza un dia desde Mercado Publico")
    p.add_argument("dia", nargs="?", help="AAAA-MM-DD o DDMMAAAA (por defecto, ayer)")
    p.add_argument("--limite", type=int, default=None, help="maximo de detalles a pedir")
    p.set_defaults(func=cmd_sync_dia)

    p = sub.add_parser("traer", help="trae una licitacion por codigo")
    p.add_argument("codigo")
    p.set_defaults(func=cmd_traer)

    p = sub.add_parser("capturar-fixture", help="guarda una respuesta real como fixture")
    p.add_argument("codigo", nargs="?", default="")
    p.add_argument("--dia", help="capturar el listado de un dia en vez de un codigo")
    p.set_defaults(func=cmd_capturar_fixture)

    p = sub.add_parser(
        "importar-procedimientos", help="carga los PROCESO.md de cada modulo (RF-0.1)"
    )
    p.set_defaults(func=cmd_importar_procedimientos)

    p = sub.add_parser("run-job", help="ejecuta un job a mano (sin argumentos, los lista)")
    p.add_argument("job_id", nargs="?", default="")
    p.set_defaults(func=cmd_run_job)

    p = sub.add_parser("estado", help="resumen del contenido del sistema")
    p.set_defaults(func=cmd_estado)

    p = sub.add_parser("serve", help="levanta la aplicacion web")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--reload", action="store_true")
    p.set_defaults(func=cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = construir_parser().parse_args(argv)
    configurar_logging(nivel="INFO")
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n  Interrumpido.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
