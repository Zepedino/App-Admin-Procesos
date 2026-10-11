"""Servicios de M1 - Radar de oportunidades.

Aqui vive la logica que toca base de datos y proveedor. El filtrado puro esta en
`filtro.py`; la separacion permite testear las reglas de negocio sin montar nada.

Estrategia de consumo de cuota (PRD seccion 4.2), que es la decision de diseno
central de este modulo:

  1. UNA llamada trae el listado del dia. Verificado: 1.214 licitaciones el
     04-09-2026, con solo cuatro campos por licitacion.
  2. El filtro por nombre descarta la enorme mayoria sin gastar nada mas.
  3. Solo las candidatas gastan una llamada de detalle cada una.

Sin este embudo, sincronizar un dia costaria 1.215 llamadas de las 10.000
diarias y tres dias agotarian el ticket.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.conectores.mercado_publico import obtener_proveedor
from backend.conectores.mercado_publico.base import LicitacionDetalle
from backend.conectores.mercado_publico.cuota import CUOTA
from backend.modulos.m1_radar.filtro import (
    PerfilEvaluable,
    Veredicto,
    evaluar_contra_perfiles,
    evaluar_texto,
)
from backend.modulos.m1_radar.models import (
    CambioDetectado,
    EstadoSeguimiento,
    Licitacion,
    MotivoDescarte,
    Organismo,
    OrigenLicitacion,
    PerfilInteres,
    SincronizacionDia,
)
from backend.nucleo.auditoria import registrar
from backend.nucleo.contexto import actor_o_sistema
from backend.nucleo.db import sesion
from backend.nucleo.errors import CuotaAgotada, NoEncontrado, ReglaDeNegocioViolada
from backend.nucleo.eventos import BUS, Eventos
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc
from backend.nucleo.tiempo import ahora_local

log = obtener_logger(__name__)

#: Campos cuyo cambio importa lo suficiente para alertar (RF-1.4).
#: Que muevan el cierre o cambien el monto no es un detalle: cambia la decision.
CAMPOS_CRITICOS = {
    "fecha_cierre": "Fecha de cierre",
    "monto_estimado": "Monto estimado",
    "codigo_estado": "Estado en el portal",
    "fecha_fin_preguntas": "Cierre de preguntas",
    "fecha_pub_respuestas": "Publicacion de respuestas",
    "fecha_apertura_tecnica": "Apertura tecnica",
}

CAMPOS_SEGUIDOS = {
    **CAMPOS_CRITICOS,
    "nombre": "Nombre",
    "descripcion": "Descripcion",
    "fecha_adjudicacion": "Fecha de adjudicacion",
    "fecha_visita_terreno": "Visita a terreno",
    "tipo_pago": "Modalidad de pago",
}


@dataclass
class ResultadoSincronizacion:
    """Lo que hizo una sincronizacion. Se guarda y se muestra."""

    dia: date
    total_api: int = 0
    candidatas: int = 0
    nuevas: int = 0
    actualizadas: int = 0
    detalles_pedidos: int = 0
    cambios_detectados: int = 0
    omitidas_por_cuota: int = 0
    errores: list[str] = field(default_factory=list)

    def a_dict(self) -> dict:
        return {
            "dia": self.dia.isoformat(),
            "total_api": self.total_api,
            "candidatas": self.candidatas,
            "nuevas": self.nuevas,
            "actualizadas": self.actualizadas,
            "detalles_pedidos": self.detalles_pedidos,
            "cambios_detectados": self.cambios_detectados,
            "omitidas_por_cuota": self.omitidas_por_cuota,
            "errores": self.errores,
        }


# --- Perfiles ----------------------------------------------------------------


def perfiles_activos(s: Session) -> list[PerfilEvaluable]:
    filas = s.execute(select(PerfilInteres).where(PerfilInteres.activo.is_(True))).scalars().all()
    return [PerfilEvaluable.desde_modelo(p) for p in filas]


# --- Organismos --------------------------------------------------------------


def obtener_o_crear_organismo(s: Session, detalle: LicitacionDetalle) -> Organismo | None:
    comprador = detalle.comprador
    if not comprador.codigo_organismo:
        return None

    organismo = s.execute(
        select(Organismo).where(Organismo.codigo_mp == comprador.codigo_organismo)
    ).scalar_one_or_none()

    if organismo is None:
        organismo = Organismo(
            codigo_mp=comprador.codigo_organismo,
            nombre=comprador.nombre_organismo or comprador.codigo_organismo,
            rut=comprador.rut_unidad or None,
            region=comprador.region_unidad or None,
            comuna=comprador.comuna_unidad or None,
        )
        s.add(organismo)
        s.flush()
        log.info(
            "organismo nuevo",
            extra={"codigo": organismo.codigo_mp, "nombre": organismo.nombre[:60]},
        )
    return organismo


# --- Mapeo detalle -> modelo -------------------------------------------------


def _valores_desde_detalle(detalle: LicitacionDetalle) -> dict:
    f = detalle.fechas
    return {
        "nombre": detalle.nombre,
        "descripcion": detalle.descripcion or None,
        "nombre_organismo": detalle.comprador.nombre_organismo or None,
        "region": detalle.comprador.region_unidad or None,
        "comuna": detalle.comprador.comuna_unidad or None,
        "tipo": str(detalle.tipo),
        "codigo_estado": detalle.codigo_estado,
        "estado_texto": detalle.estado_texto or None,
        "monto_estimado": detalle.monto_estimado,
        "naturaleza_monto": int(detalle.naturaleza_monto) if detalle.naturaleza_monto else None,
        "moneda": detalle.moneda,
        "visibilidad_monto": detalle.visibilidad_monto,
        "fecha_publicacion": f.publicacion,
        "fecha_cierre": f.cierre,
        "fecha_fin_preguntas": f.fin_preguntas,
        "fecha_pub_respuestas": f.publicacion_respuestas,
        "fecha_apertura_tecnica": f.apertura_tecnica,
        "fecha_adjudicacion": f.adjudicacion or f.estimada_adjudicacion,
        "fecha_visita_terreno": f.visita_terreno,
        "obras": detalle.obras,
        "toma_razon": detalle.toma_razon,
        "subcontratacion": detalle.subcontratacion,
        "es_renovable": detalle.es_renovable,
        "tipo_pago": detalle.tipo_pago or None,
    }


def _detectar_cambios(s: Session, licitacion: Licitacion, valores: dict) -> list[CambioDetectado]:
    """RF-1.4: compara lo guardado con lo nuevo y registra el diff.

    Solo se comparan campos de CAMPOS_SEGUIDOS: si comparamos todo, el ruido
    entierra la senal y nadie mira las alertas.
    """
    cambios: list[CambioDetectado] = []
    momento = ahora_utc()

    for campo, etiqueta in CAMPOS_SEGUIDOS.items():
        anterior = getattr(licitacion, campo, None)
        nuevo = valores.get(campo)
        if anterior == nuevo:
            continue
        if anterior is None and nuevo is None:
            continue

        cambio = CambioDetectado(
            licitacion_id=licitacion.id,
            campo=campo,
            valor_anterior=str(anterior) if anterior is not None else None,
            valor_nuevo=str(nuevo) if nuevo is not None else None,
            detectado_en=momento,
            critico=campo in CAMPOS_CRITICOS,
        )
        s.add(cambio)
        cambios.append(cambio)
        log.info(
            "cambio detectado en licitacion",
            extra={
                "codigo": licitacion.codigo,
                "campo": etiqueta,
                "anterior": str(anterior)[:60],
                "nuevo": str(nuevo)[:60],
                "critico": cambio.critico,
            },
        )

    return cambios


def guardar_detalle(
    s: Session,
    detalle: LicitacionDetalle,
    *,
    origen: OrigenLicitacion = OrigenLicitacion.RADAR,
    veredicto: Veredicto | None = None,
) -> tuple[Licitacion, bool, list[CambioDetectado]]:
    """Crea o actualiza una licitacion. Devuelve (licitacion, era_nueva, cambios).

    Es el unico camino por el que un detalle entra al sistema, venga del radar,
    de un codigo pegado (RF-5.1) o de la ingesta de correo (RF-10.3).
    """
    licitacion = s.execute(
        select(Licitacion).where(Licitacion.codigo == detalle.codigo)
    ).scalar_one_or_none()

    valores = _valores_desde_detalle(detalle)
    organismo = obtener_o_crear_organismo(s, detalle)
    es_nueva = licitacion is None
    cambios: list[CambioDetectado] = []

    # Hallazgo 8 / RF-1.2: organismo en lista negra.
    #
    # Se guarda igual, pero entra ya descartada y con motivo: no ensucia la
    # bandeja del dia y a la vez queda en las estadisticas de descarte, que es
    # lo que RF-1.5 necesita para saber en seis meses si el criterio sirve.
    # Borrarla sin registro haria invisible una decision de negocio.
    en_lista_negra = bool(organismo is not None and organismo.lista_negra)

    if es_nueva:
        licitacion = Licitacion(
            codigo=detalle.codigo,
            origen=origen,
            estado_seguimiento=(
                EstadoSeguimiento.DESCARTADA if en_lista_negra else EstadoSeguimiento.NUEVA
            ),
            motivo_descarte=MotivoDescarte.ORGANISMO_EXCLUIDO if en_lista_negra else None,
            detalle_descarte=(
                f"Organismo en lista negra: {organismo.motivo_lista_negra or 'sin motivo escrito'}"
                if en_lista_negra
                else None
            ),
            descartada_por="sistema:lista_negra" if en_lista_negra else None,
            descartada_en=ahora_utc() if en_lista_negra else None,
            detectada_en=ahora_utc(),
            **valores,
        )
        s.add(licitacion)
        s.flush()
    else:
        cambios = _detectar_cambios(s, licitacion, valores)
        for campo, valor in valores.items():
            setattr(licitacion, campo, valor)

    licitacion.organismo_id = organismo.id if organismo else None
    licitacion.detalle_obtenido_en = ahora_utc()
    licitacion.json_crudo = detalle.crudo

    if veredicto is not None:
        licitacion.puntaje_perfil = veredicto.puntaje
        licitacion.coincidencias = veredicto.a_dict()

    s.flush()

    if es_nueva and en_lista_negra:
        # No se emite "detectada": nadie debe recibir un aviso por algo que el
        # sistema acaba de descartar solo. Se emite el descarte, que es lo que
        # realmente paso, y asi queda en la auditoria y en las estadisticas.
        registrar(
            s,
            accion="descartar_automatico",
            entidad="Licitacion",
            entidad_id=licitacion.codigo,
            campo="estado_seguimiento",
            valor_nuevo=EstadoSeguimiento.DESCARTADA,
            motivo=f"organismo en lista negra: {licitacion.nombre_organismo}",
            modulo="m1_radar",
        )
        BUS.emitir(
            Eventos.LICITACION_DESCARTADA,
            origen="m1_radar",
            codigo=licitacion.codigo,
            motivo=str(MotivoDescarte.ORGANISMO_EXCLUIDO),
            por="sistema:lista_negra",
        )
    elif es_nueva:
        BUS.emitir(
            Eventos.LICITACION_DETECTADA,
            origen="m1_radar",
            codigo=licitacion.codigo,
            nombre=licitacion.nombre,
            organismo=licitacion.nombre_organismo,
            puntaje=licitacion.puntaje_perfil,
            fecha_cierre=licitacion.fecha_cierre,
        )
    for cambio in cambios:
        BUS.emitir(
            Eventos.LICITACION_CAMBIO,
            origen="m1_radar",
            codigo=licitacion.codigo,
            campo=cambio.campo,
            valor_anterior=cambio.valor_anterior,
            valor_nuevo=cambio.valor_nuevo,
            critico=cambio.critico,
        )

    return licitacion, es_nueva, cambios


# --- Sincronizacion ----------------------------------------------------------


def sincronizar_dia(dia: date, *, limite_detalles: int | None = None) -> ResultadoSincronizacion:
    """RF-1.1: sincroniza las licitaciones con movimiento en una fecha.

    `limite_detalles` acota cuantos detalles se piden; es la valvula de seguridad
    para la primera carga historica, donde es facil quemar la cuota sin querer.
    """
    proveedor = obtener_proveedor()
    resultado = ResultadoSincronizacion(dia=dia)

    log.info("sincronizacion iniciada", extra={"dia": dia.isoformat(), "proveedor": proveedor.nombre})

    try:
        listado = proveedor.licitaciones_del_dia(dia)
    except CuotaAgotada as exc:
        resultado.errores.append(str(exc))
        _registrar_sincronizacion(resultado, ok=False)
        raise
    resultado.total_api = len(listado)

    # --- Fase de lectura: transaccion CORTA, sin red dentro -----------------
    #
    # Importante: esta transaccion se cierra ANTES del bucle de llamadas HTTP.
    # Mantenerla abierta durante la red bloqueaba la base: el contador de cuota
    # (CUOTA.reservar) abre su propia transaccion en cada llamada, y con SQLite
    # las dos se esperaban mutuamente hasta agotar el timeout. El sintoma era
    # "database is locked" y solo se guardaba la primera licitacion de cada dia.
    with sesion() as s:
        perfiles = perfiles_activos(s)
        if not perfiles:
            # Sin perfil no hay radar. Decirlo en vez de traer 1.214 detalles.
            resultado.errores.append(
                "no hay perfiles de interes activos: configura uno en /radar/perfiles"
            )
            log.error("sincronizacion sin perfiles de interes activos")
            _registrar_sincronizacion(resultado, ok=False)
            return resultado

        conocidos = set(s.execute(select(Licitacion.codigo)).scalars().all())

        # Paso 1: filtro barato por nombre. Aqui se decide en que se gasta cuota.
        candidatas: list[tuple[str, Veredicto]] = []
        for resumen in listado:
            mejor = max(
                (evaluar_texto(p, resumen.nombre) for p in perfiles),
                key=lambda v: (v.candidata, v.puntaje),
            )
            if mejor.candidata:
                candidatas.append((resumen.codigo, mejor))

        resultado.candidatas = len(candidatas)
        log.info(
            "filtro por nombre aplicado",
            extra={"total": len(listado), "candidatas": len(candidatas)},
        )

        # RF-1.3: lo ya visto no vuelve a pedir detalle salvo que siga abierto.
        pendientes = [(c, v) for c, v in candidatas if c not in conocidos]
        a_refrescar = [
            (c, v) for c, v in candidatas
            if c in conocidos and _conviene_refrescar(s, c)
        ]

    cola = pendientes + a_refrescar
    if limite_detalles is not None:
        resultado.omitidas_por_cuota = max(0, len(cola) - limite_detalles)
        cola = cola[:limite_detalles]

    # --- Fase de red: una transaccion corta POR licitacion ------------------
    #
    # Guardar una licitacion por transaccion tiene otra ventaja sobre la version
    # anterior: si la API falla a mitad de la cola, lo ya descargado queda
    # guardado en vez de perderse con el rollback. La cuota gastada no vuelve.
    for codigo, veredicto_nombre in cola:
        if not CUOTA.hay_disponible(1) and proveedor.en_vivo:
            resultado.omitidas_por_cuota += 1
            continue
        try:
            detalle = proveedor.detalle(codigo)
            resultado.detalles_pedidos += 1
        except CuotaAgotada as exc:
            resultado.errores.append(str(exc))
            log.error("cuota agotada durante la sincronizacion", extra={"codigo": codigo})
            break
        except Exception as exc:
            resultado.errores.append(f"{codigo}: {type(exc).__name__}: {exc}")
            log.exception("no se pudo obtener el detalle", extra={"codigo": codigo})
            continue

        if detalle is None:
            continue

        # Paso 3: reevaluar con el detalle completo, que trae items,
        # categorias UNSPSC, region y monto.
        veredicto, _ = evaluar_contra_perfiles(perfiles, detalle)
        if not veredicto.candidata:
            # El nombre prometia y el detalle no. Se guarda igual: sirve para
            # medir la precision del filtro y afinar el perfil (RF-1.5).
            veredicto.palabras_encontradas = veredicto_nombre.palabras_encontradas

        try:
            with sesion() as s:
                _, es_nueva, cambios = guardar_detalle(s, detalle, veredicto=veredicto)
                resultado.nuevas += int(es_nueva)
                resultado.actualizadas += int(not es_nueva)
                resultado.cambios_detectados += len(cambios)
        except Exception as exc:
            resultado.errores.append(f"{codigo}: al guardar: {type(exc).__name__}: {exc}")
            log.exception("no se pudo guardar la licitacion", extra={"codigo": codigo})

    _registrar_sincronizacion(resultado, ok=not resultado.errores)
    log.info("sincronizacion terminada", extra=resultado.a_dict())
    return resultado


def _conviene_refrescar(s: Session, codigo: str) -> bool:
    """Decide si vale una llamada refrescar una licitacion ya conocida.

    Refrescar todo lo conocido cada noche agotaria la cuota sin aportar: una
    licitacion cerrada o descartada ya no cambia nada para nosotros.
    """
    licitacion = s.execute(
        select(Licitacion).where(Licitacion.codigo == codigo)
    ).scalar_one_or_none()
    if licitacion is None:
        return True
    if licitacion.estado_seguimiento == EstadoSeguimiento.DESCARTADA:
        return False
    if licitacion.codigo_estado not in (None, 5):
        return False
    if CUOTA.en_modo_degradado():
        # Degradacion (PRD seccion 4.2): solo lo que cierra en menos de 48 horas.
        if licitacion.fecha_cierre is None:
            return False
        return licitacion.fecha_cierre <= ahora_utc() + timedelta(hours=48)
    return True


def _registrar_sincronizacion(resultado: ResultadoSincronizacion, *, ok: bool) -> None:
    with sesion() as s:
        fila = s.execute(
            select(SincronizacionDia).where(SincronizacionDia.dia == resultado.dia)
        ).scalar_one_or_none()
        if fila is None:
            fila = SincronizacionDia(dia=resultado.dia, ejecutado_en=ahora_utc())
            s.add(fila)
        fila.ejecutado_en = ahora_utc()
        fila.total_api = resultado.total_api
        fila.nuevas = resultado.nuevas
        fila.candidatas = resultado.candidatas
        fila.detalles_pedidos = resultado.detalles_pedidos
        fila.ok = ok
        fila.error = "; ".join(resultado.errores)[:2000] or None


def importar_por_codigo(
    codigo: str, *, origen: OrigenLicitacion = OrigenLicitacion.CODIGO_PEGADO
) -> Licitacion:
    """RF-5.1 via 2: pegar un codigo y traer la licitacion aunque nunca haya
    pasado por el radar.

    Es tambien la forma de cargar los casos historicos de la fase 0 del PRD.
    """
    codigo = codigo.strip().upper()
    if not codigo:
        raise ReglaDeNegocioViolada("el codigo de licitacion no puede estar vacio")

    detalle = obtener_proveedor().detalle(codigo, forzar_refresco=True)
    if detalle is None:
        raise NoEncontrado(f"la licitacion {codigo} no existe en Mercado Publico", codigo=codigo)

    with sesion() as s:
        perfiles = perfiles_activos(s)
        veredicto = evaluar_contra_perfiles(perfiles, detalle)[0] if perfiles else None
        licitacion, es_nueva, _ = guardar_detalle(
            s, detalle, origen=origen, veredicto=veredicto
        )
        registrar(
            s,
            accion="importar",
            entidad="Licitacion",
            entidad_id=licitacion.codigo,
            motivo=f"importada por codigo ({origen})",
            modulo="m1_radar",
        )
        log.info(
            "licitacion importada por codigo",
            extra={"codigo": codigo, "nueva": es_nueva, "origen": str(origen)},
        )
        return licitacion


# --- Acciones del usuario ----------------------------------------------------


def marcar_interesa(s: Session, codigo: str) -> Licitacion:
    """RF-2.2: marcar como interesa encola la descarga de anexos en M2."""
    licitacion = _obtener(s, codigo)
    licitacion.estado_seguimiento = EstadoSeguimiento.INTERESA
    licitacion.responsable = actor_o_sistema().identificador
    registrar(
        s,
        accion="marcar_interesa",
        entidad="Licitacion",
        entidad_id=codigo,
        modulo="m1_radar",
    )
    BUS.emitir(
        Eventos.LICITACION_MARCADA_INTERESA,
        origen="m1_radar",
        codigo=codigo,
        nombre=licitacion.nombre,
    )
    return licitacion


def descartar(
    s: Session, codigo: str, motivo: MotivoDescarte, detalle_texto: str = ""
) -> Licitacion:
    """RF-1.5: descarte con motivo tipificado obligatorio.

    El motivo no es opcional a proposito: en seis meses estos datos dicen si los
    criterios sirven, y sin ellos la conversacion vuelve a ser de opiniones.
    """
    licitacion = _obtener(s, codigo)
    if motivo not in set(MotivoDescarte):
        raise ReglaDeNegocioViolada(f"motivo de descarte no valido: {motivo}")
    if motivo == MotivoDescarte.OTRO and not detalle_texto.strip():
        raise ReglaDeNegocioViolada(
            "el motivo 'Otro' exige una explicacion escrita: si no, no sirve para analizar"
        )

    actor = actor_o_sistema()
    licitacion.estado_seguimiento = EstadoSeguimiento.DESCARTADA
    licitacion.motivo_descarte = motivo
    licitacion.detalle_descarte = detalle_texto.strip() or None
    licitacion.descartada_por = actor.identificador
    licitacion.descartada_en = ahora_utc()

    registrar(
        s,
        accion="descartar",
        entidad="Licitacion",
        entidad_id=codigo,
        campo="estado_seguimiento",
        valor_nuevo=EstadoSeguimiento.DESCARTADA,
        motivo=f"{motivo}: {detalle_texto}".strip(": "),
        modulo="m1_radar",
    )
    BUS.emitir(
        Eventos.LICITACION_DESCARTADA,
        origen="m1_radar",
        codigo=codigo,
        motivo=str(motivo),
        por=actor.identificador,
    )
    return licitacion


def _obtener(s: Session, codigo: str) -> Licitacion:
    licitacion = s.execute(
        select(Licitacion).where(Licitacion.codigo == codigo.strip().upper())
    ).scalar_one_or_none()
    if licitacion is None:
        raise NoEncontrado(f"licitacion {codigo} no encontrada", codigo=codigo)
    return licitacion


# --- Consultas para la UI ----------------------------------------------------


def bandeja_del_dia(s: Session, *, horas_cierre_proximo: int = 72) -> dict:
    """RF-1.6: lo nuevo, lo que cambio, lo que cierra pronto.

    Es la primera pantalla del encargado de licitaciones. Si esta pantalla no
    responde "que tengo que mirar hoy", el sistema no sirve.
    """
    ahora = ahora_utc()
    limite = ahora + timedelta(hours=horas_cierre_proximo)

    nuevas = (
        s.execute(
            select(Licitacion)
            .where(Licitacion.estado_seguimiento == EstadoSeguimiento.NUEVA)
            .order_by(Licitacion.puntaje_perfil.desc().nullslast(), Licitacion.fecha_cierre)
            .limit(100)
        )
        .scalars()
        .all()
    )

    cambios = (
        s.execute(
            select(CambioDetectado)
            .where(CambioDetectado.visto_en.is_(None))
            .order_by(CambioDetectado.critico.desc(), CambioDetectado.detectado_en.desc())
            .limit(50)
        )
        .scalars()
        .all()
    )

    cierran_pronto = (
        s.execute(
            select(Licitacion)
            .where(
                Licitacion.fecha_cierre.is_not(None),
                Licitacion.fecha_cierre > ahora,
                Licitacion.fecha_cierre <= limite,
                Licitacion.estado_seguimiento.notin_(
                    [EstadoSeguimiento.DESCARTADA, EstadoSeguimiento.PERDIDA]
                ),
            )
            .order_by(Licitacion.fecha_cierre)
        )
        .scalars()
        .all()
    )

    return {
        "nuevas": nuevas,
        "cambios": cambios,
        "cierran_pronto": cierran_pronto,
        "horas_cierre_proximo": horas_cierre_proximo,
    }


def estadisticas_descarte(s: Session, *, dias: int = 180) -> list[tuple[str, int]]:
    """RF-1.5: en 6 meses estos datos dicen si los criterios sirven."""
    desde = ahora_utc() - timedelta(days=dias)
    filas = s.execute(
        select(Licitacion.motivo_descarte, func.count(Licitacion.id))
        .where(
            Licitacion.motivo_descarte.is_not(None),
            Licitacion.descartada_en >= desde,
        )
        .group_by(Licitacion.motivo_descarte)
        .order_by(func.count(Licitacion.id).desc())
    ).all()
    return [(m, c) for m, c in filas]


def resumen_radar(s: Session) -> dict:
    """Contadores para el encabezado. Una consulta agrupada, no ocho."""
    por_estado = dict(
        s.execute(
            select(Licitacion.estado_seguimiento, func.count(Licitacion.id)).group_by(
                Licitacion.estado_seguimiento
            )
        ).all()
    )
    ultima = s.execute(
        select(SincronizacionDia).order_by(SincronizacionDia.ejecutado_en.desc()).limit(1)
    ).scalar_one_or_none()
    return {
        "total": sum(por_estado.values()),
        "por_estado": por_estado,
        "ultima_sincronizacion": ultima,
        "cuota": CUOTA.estado(),
    }


def dias_sin_sincronizar(s: Session, *, ventana: int = 14) -> list[date]:
    """Detecta huecos: si un dia no se sincronizo, no lo sabemos por omision."""
    hoy = ahora_local().date()
    esperados = {hoy - timedelta(days=i) for i in range(1, ventana + 1)}
    hechos = set(
        s.execute(
            select(SincronizacionDia.dia).where(SincronizacionDia.ok.is_(True))
        ).scalars().all()
    )
    return sorted(esperados - hechos)
