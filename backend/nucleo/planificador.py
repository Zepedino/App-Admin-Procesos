"""Planificador de tareas (APScheduler).

PRD seccion 6: "Un job que falla reintenta y avisa; jamás falla en silencio."
PRD seccion 4.2: cargas masivas solo entre 22:00 y 07:00 hora de Chile.

Este envoltorio existe para que ningún módulo registre un job sin manejo de error
ni sin quedar listado en /sistema/jobs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from backend.nucleo.config import obtener_config
from backend.nucleo.contexto import como, como_job
from backend.nucleo.eventos import BUS, Eventos
from backend.nucleo.logging import obtener_logger
from backend.nucleo.modelo_base import ahora_utc

log = obtener_logger(__name__)


@dataclass
class EjecucionJob:
    """Resultado de una ejecución. Se muestra en /sistema/jobs."""

    job_id: str
    inicio: datetime
    fin: datetime | None = None
    ok: bool | None = None
    error: str | None = None
    detalle: dict = field(default_factory=dict)

    @property
    def duracion_seg(self) -> float | None:
        return (self.fin - self.inicio).total_seconds() if self.fin else None


class Planificador:
    """Envoltorio de APScheduler con bitácora y aviso ante fallo."""

    def __init__(self) -> None:
        self._scheduler: BackgroundScheduler | None = None
        self._jobs: dict[str, dict] = {}
        self._ultimas: dict[str, EjecucionJob] = {}

    # --- Registro ------------------------------------------------------------

    def registrar_cron(
        self,
        job_id: str,
        funcion: Callable[[], object],
        *,
        descripcion: str,
        hora: int | str | None = None,
        minuto: int | str = 0,
        dia_semana: str | None = None,
    ) -> None:
        """Job por horario. La hora va en la zona local configurada."""
        kwargs: dict = {"minute": minuto, "timezone": obtener_config().tz}
        if hora is not None:
            kwargs["hour"] = hora
        if dia_semana:
            kwargs["day_of_week"] = dia_semana
        self._registrar(job_id, funcion, CronTrigger(**kwargs), descripcion)

    def registrar_intervalo(
        self, job_id: str, funcion: Callable[[], object], *, descripcion: str, horas: float
    ) -> None:
        self._registrar(job_id, funcion, IntervalTrigger(hours=horas), descripcion)

    def _registrar(self, job_id: str, funcion, trigger, descripcion: str) -> None:
        if job_id in self._jobs:
            raise ValueError(f"job duplicado: {job_id}")
        self._jobs[job_id] = {
            "funcion": funcion,
            "trigger": trigger,
            "descripcion": descripcion,
        }
        log.info("job registrado", extra={"job": job_id, "trigger": str(trigger)})

    # --- Ejecución -----------------------------------------------------------

    def ejecutar(self, job_id: str) -> EjecucionJob:
        """Ejecuta un job ahora, con bitácora. Es el hook de `cli run-job`."""
        entrada = self._jobs.get(job_id)
        if entrada is None:
            raise KeyError(f"job desconocido: {job_id}")

        ejecucion = EjecucionJob(job_id=job_id, inicio=ahora_utc())
        self._ultimas[job_id] = ejecucion
        log.info("job iniciado", extra={"job": job_id})
        try:
            with como(como_job(job_id)):
                resultado = entrada["funcion"]()
            ejecucion.ok = True
            if isinstance(resultado, dict):
                ejecucion.detalle = resultado
            log.info("job terminado", extra={"job": job_id, "detalle": ejecucion.detalle})
        except Exception as exc:
            ejecucion.ok = False
            ejecucion.error = f"{type(exc).__name__}: {exc}"
            log.exception("job falló", extra={"job": job_id})
            # Nunca en silencio: el fallo se convierte en evento y M10 lo notifica.
            BUS.emitir(
                Eventos.JOB_FALLIDO, origen="planificador", job_id=job_id, error=ejecucion.error
            )
        finally:
            ejecucion.fin = ahora_utc()
        return ejecucion

    # --- Ciclo de vida -------------------------------------------------------

    def iniciar(self) -> None:
        if self._scheduler is not None:
            return
        self._scheduler = BackgroundScheduler(timezone=obtener_config().tz)
        for job_id, e in self._jobs.items():
            self._scheduler.add_job(
                self.ejecutar,
                trigger=e["trigger"],
                args=[job_id],
                id=job_id,
                name=e["descripcion"],
                max_instances=1,      # sin solapamiento: importa para la cuota de API
                coalesce=True,        # si se acumularon disparos, uno solo
                misfire_grace_time=3600,
            )
        self._scheduler.start()
        log.info("planificador iniciado", extra={"jobs": len(self._jobs)})

    def detener(self) -> None:
        if self._scheduler is not None:
            self._scheduler.shutdown(wait=False)
            self._scheduler = None

    # --- Introspección -------------------------------------------------------

    def listar(self) -> list[dict]:
        salida = []
        for job_id, e in sorted(self._jobs.items()):
            ultima = self._ultimas.get(job_id)
            proxima = None
            if self._scheduler is not None:
                j = self._scheduler.get_job(job_id)
                proxima = getattr(j, "next_run_time", None)
            salida.append(
                {
                    "id": job_id,
                    "descripcion": e["descripcion"],
                    "trigger": str(e["trigger"]),
                    "proxima_ejecucion": proxima,
                    "ultima": ultima,
                }
            )
        return salida

    def existe(self, job_id: str) -> bool:
        return job_id in self._jobs


PLANIFICADOR = Planificador()
