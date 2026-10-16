"""Adaptador de la API de Mercado Público (ChileCompra).

Único lugar del sistema autorizado a hacer HTTP contra api.mercadopublico.cl.
Verificado contra respuestas reales; ver pruebas/fixtures/api/.

Restricciones que este archivo hace cumplir (PRD seccion 4.2):
  - 10.000 solicitudes/día por ticket, contadas antes de llamar.
  - Caché por recurso, con TTL según estado de la licitación.
  - Reintentos con backoff ante fallos transitorios (la plataforma es beta).
  - Ventana 22:00-07:00 para cargas masivas.

Cuando ChileCompra publique el portal API unificado, se escribe otro adaptador
al lado y se cambia la fábrica. Este archivo se borra sin tocar nada más.
"""

from __future__ import annotations

import json
import time
from datetime import date, timedelta
from typing import Any

import httpx

from backend.conectores.mercado_publico.base import (
    EstadoCuota,
    EstadoLicitacion,
    LicitacionDetalle,
    LicitacionResumen,
    ProcurementProvider,
)
from backend.conectores.mercado_publico.cache import CACHE
from backend.conectores.mercado_publico.cuota import CUOTA
from backend.conectores.mercado_publico.modelos import LlamadaAPI
from backend.nucleo.config import obtener_config
from backend.nucleo.db import sesion
from backend.nucleo.errors import (
    ErrorDeConfiguracion,
    ProveedorNoDisponible,
    RespuestaInesperada,
)
from backend.nucleo.logging import obtener_logger
from backend.nucleo.texto import normalizar
from backend.nucleo.tiempo import formato_fecha_mp

log = obtener_logger(__name__)

#: Códigos HTTP que justifican reintentar. El resto es un problema nuestro.
HTTP_REINTENTABLES = {429, 500, 502, 503, 504}

#: TTL del listado por fecha. Un día pasado ya no cambia; hoy sí.
TTL_LISTADO_DIA_PASADO = timedelta(days=30)
TTL_LISTADO_HOY = timedelta(hours=4)


class ProveedorMercadoPublico(ProcurementProvider):
    """Implementación en vivo. Requiere MP_TICKET."""

    nombre = "mercadopublico"
    en_vivo = True

    def __init__(self, cliente: httpx.Client | None = None) -> None:
        cfg = obtener_config()
        if not cfg.mp.hay_ticket:
            raise ErrorDeConfiguracion(
                "MP_TICKET no está configurado. Solicítalo con Clave Única; llega por correo."
            )
        self._cfg = cfg.mp
        self._ultima_llamada: float = 0.0
        self._cliente = cliente or httpx.Client(
            base_url=self._cfg.base_url,
            timeout=self._cfg.timeout_seg,
            headers={
                # User-agent identificable: la API valida por IP y puede
                # restringir según volumen (PRD seccion 4.2).
                "User-Agent": f"sgl-ito-serviu/{_version()} (+consultora ITO)",
                "Accept": "application/json",
            },
            follow_redirects=True,
        )

    # --- Transporte ----------------------------------------------------------

    def _pedir(
        self,
        recurso: str,
        parametros: dict[str, Any],
        *,
        ttl: timedelta | None,
        usar_cache: bool = True,
        clave_esperada: str = "Listado",
    ) -> dict[str, Any]:
        """Una llamada a la API, con caché, cuota, reintentos y bitácora.

        Ningún otro método hace HTTP. Si hay que cambiar la política de red,
        se cambia aquí y afecta a todo el sistema de forma uniforme.
        """
        clave_cache = {k: v for k, v in parametros.items() if k != "ticket"}

        if usar_cache:
            cacheado = CACHE.obtener(recurso, **clave_cache)
            if cacheado is not None:
                self._registrar_llamada(recurso, clave_cache, desde_cache=True)
                return cacheado

        # La cuota se reserva ANTES de llamar: una llamada fallida también
        # consumió cuota del lado de ChileCompra.
        CUOTA.reservar(1)
        self._esperar_turno()

        parametros_completos = {**parametros, "ticket": self._cfg.ticket}
        ultimo_error: Exception | None = None
        inicio = time.monotonic()

        for intento in range(1, self._cfg.reintentos + 1):
            try:
                respuesta = self._cliente.get(recurso, params=parametros_completos)
            except httpx.HTTPError as exc:
                ultimo_error = exc
                log.warning(
                    "fallo de red contra Mercado Público",
                    extra={"recurso": recurso, "intento": intento, "error": str(exc)},
                )
                self._esperar_backoff(intento)
                continue

            if respuesta.status_code in HTTP_REINTENTABLES:
                ultimo_error = ProveedorNoDisponible(
                    f"HTTP {respuesta.status_code}", recurso=recurso
                )
                log.warning(
                    "respuesta reintentable de Mercado Público",
                    extra={
                        "recurso": recurso,
                        "http": respuesta.status_code,
                        "intento": intento,
                    },
                )
                self._esperar_backoff(intento)
                continue

            if respuesta.status_code >= 400:
                self._registrar_llamada(
                    recurso,
                    clave_cache,
                    codigo_http=respuesta.status_code,
                    ok=False,
                    error=respuesta.text[:500],
                    intentos=intento,
                )
                raise RespuestaInesperada(
                    f"la API respondió HTTP {respuesta.status_code}",
                    recurso=recurso,
                    cuerpo=respuesta.text[:200],
                )

            try:
                datos = respuesta.json()
            except json.JSONDecodeError as exc:
                # Señal clásica de mantenimiento del portal: HTML donde debía ir JSON.
                self._registrar_llamada(
                    recurso, clave_cache, codigo_http=respuesta.status_code,
                    ok=False, error="respuesta no es JSON", intentos=intento,
                )
                raise RespuestaInesperada(
                    "la API no devolvió JSON (posible mantenimiento del portal)",
                    recurso=recurso,
                ) from exc

            # La validacion sigue siendo estricta, solo que la clave depende
            # del recurso: licitaciones.json responde "Listado" y
            # Empresas/BuscarComprador responde "listaEmpresas". Relajarla para
            # todos habria perdido la deteccion de cambios de contrato, que es
            # para lo que existe.
            if not isinstance(datos, dict) or clave_esperada not in datos:
                # El contrato cambió. Fallar visible, no adivinar (riesgo seccion 9).
                #
                # Ante un ticket invalido la API responde HTTP 200 con un cuerpo
                # {"Codigo": ..., "Mensaje": ...} en vez de un error HTTP. Ese
                # Mensaje dice exactamente que pasa, asi que se propaga en lugar
                # de tirarlo: es la diferencia entre "algo falló" y "tu ticket
                # no es válido".
                mensaje_api = ""
                if isinstance(datos, dict):
                    mensaje_api = str(datos.get("Mensaje") or datos.get("mensaje") or "")

                self._registrar_llamada(
                    recurso, clave_cache, codigo_http=respuesta.status_code,
                    ok=False,
                    error=f"falta la clave {clave_esperada}. {mensaje_api}".strip(),
                    intentos=intento,
                )
                raise RespuestaInesperada(
                    f"la API respondio: {mensaje_api}" if mensaje_api
                    else f"la respuesta no tiene la forma esperada (falta '{clave_esperada}')",
                    recurso=recurso,
                    claves=list(datos)[:10] if isinstance(datos, dict) else type(datos).__name__,
                )

            duracion_ms = int((time.monotonic() - inicio) * 1000)
            self._registrar_llamada(
                recurso, clave_cache, codigo_http=respuesta.status_code,
                duracion_ms=duracion_ms, intentos=intento,
            )
            if usar_cache and ttl is not None:
                CACHE.guardar(recurso, datos, ttl=ttl, **clave_cache)
            return datos

        # Agotados los reintentos: intentar servir caché vencida antes de rendirse.
        self._registrar_llamada(
            recurso, clave_cache, ok=False,
            error=str(ultimo_error), intentos=self._cfg.reintentos,
        )
        if usar_cache:
            vencido = CACHE.obtener_vencido(recurso, **clave_cache)
            if vencido is not None:
                log.warning(
                    "API no disponible: se sirve caché vencida",
                    extra={"recurso": recurso, "parametros": clave_cache},
                )
                return vencido

        raise ProveedorNoDisponible(
            f"Mercado Público no respondió tras {self._cfg.reintentos} intentos",
            recurso=recurso,
            causa=str(ultimo_error),
        )

    def _esperar_turno(self) -> None:
        """Espacia las llamadas para no gatillar el limite de frecuencia.

        Barato comparado con la alternativa: cada 429 cuesta una llamada de
        cuota mas 2 segundos de backoff, y encima insiste sobre un servicio que
        acaba de pedir que bajemos el ritmo.
        """
        minimo = self._cfg.delay_entre_llamadas_seg
        if minimo <= 0:
            return
        transcurrido = time.monotonic() - self._ultima_llamada
        if transcurrido < minimo:
            time.sleep(minimo - transcurrido)
        self._ultima_llamada = time.monotonic()

    def _esperar_backoff(self, intento: int) -> None:
        """Backoff exponencial simple: 2s, 4s, 8s. Sin jitter porque no hay concurrencia."""
        time.sleep(2**intento)

    def _registrar_llamada(
        self,
        recurso: str,
        parametros: dict[str, Any],
        *,
        codigo_http: int | None = None,
        duracion_ms: int | None = None,
        ok: bool = True,
        error: str | None = None,
        intentos: int = 1,
        desde_cache: bool = False,
    ) -> None:
        """Bitácora de llamadas. Nunca hace fallar la operación principal."""
        try:
            with sesion() as s:
                s.add(
                    LlamadaAPI(
                        recurso=recurso,
                        parametros=json.dumps(parametros, ensure_ascii=False),
                        codigo_http=codigo_http,
                        duracion_ms=duracion_ms,
                        ok=ok,
                        error=error,
                        intentos=intentos,
                        desde_cache=desde_cache,
                    )
                )
        except Exception:  # pragma: no cover - la bitácora no puede tumbar la app
            log.exception("no se pudo registrar la llamada a la API")

    # --- Contrato ProcurementProvider ---------------------------------------

    def licitaciones_del_dia(self, dia: date) -> list[LicitacionResumen]:
        """Verificado: devuelve CodigoExterno, Nombre, CodigoEstado y FechaCierre.

        Nada más. El detalle exige una llamada por código.
        """
        from backend.nucleo.tiempo import ahora_local

        ttl = TTL_LISTADO_HOY if dia >= ahora_local().date() else TTL_LISTADO_DIA_PASADO
        datos = self._pedir("licitaciones.json", {"fecha": formato_fecha_mp(dia)}, ttl=ttl)
        return [LicitacionResumen.desde_api(x) for x in datos.get("Listado") or []]

    def detalle(self, codigo: str, *, forzar_refresco: bool = False) -> LicitacionDetalle | None:
        codigo = codigo.strip().upper()
        if not codigo:
            return None

        if forzar_refresco:
            CACHE.invalidar("licitaciones.json", codigo=codigo)

        # El TTL correcto depende del estado, que solo se conoce tras responder.
        # Se pide sin cachear y se guarda después con el TTL adecuado.
        datos = self._pedir("licitaciones.json", {"codigo": codigo}, ttl=None, usar_cache=False)
        listado = datos.get("Listado") or []
        if not listado:
            return None

        detalle = LicitacionDetalle.desde_api(listado[0])
        CACHE.guardar(
            "licitaciones.json",
            datos,
            ttl=CACHE.ttl_para_licitacion(detalle.codigo_estado),
            codigo=codigo,
        )
        return detalle

    def licitaciones_por_estado(self, estado: EstadoLicitacion) -> list[LicitacionResumen]:
        datos = self._pedir(
            "licitaciones.json", {"estado": int(estado)}, ttl=timedelta(hours=4)
        )
        return [LicitacionResumen.desde_api(x) for x in datos.get("Listado") or []]

    def licitaciones_por_organismo(self, codigo_organismo: str) -> list[LicitacionResumen]:
        """Licitaciones ACTIVAS de un organismo. Base de la vigilancia dirigida.

        `estado=activas` no es opcional: verificado contra la API, pedir solo
        `CodigoOrganismo` devuelve una lista vacía siempre. Con el parámetro,
        el mismo organismo devuelve sus licitaciones abiertas.

        Es la única forma de garantizar que no se escape nada de un organismo
        concreto: el listado por fecha no trae el comprador, así que filtrar
        por "es del SERVIU" en esa pasada es imposible.

        TTL corto: es justo lo que queremos ver cambiar.
        """
        datos = self._pedir(
            "licitaciones.json",
            {"CodigoOrganismo": codigo_organismo, "estado": "activas"},
            ttl=timedelta(hours=6),
        )
        return [LicitacionResumen.desde_api(x) for x in datos.get("Listado") or []]

    def buscar_organismos(self, texto: str = "") -> list[dict[str, str]]:
        """Catálogo de organismos compradores (899 al verificarlo).

        Sirve para encontrar el código de un organismo por su nombre, que es
        como se marca a quién vigilar. Una llamada trae el catálogo completo,
        así que se cachea largo: la lista casi no cambia.
        """
        datos = self._pedir(
            "Empresas/BuscarComprador",
            {},
            ttl=timedelta(days=30),
            clave_esperada="listaEmpresas",
        )
        lista = datos.get("listaEmpresas") or datos.get("Listado") or []
        salida = [
            {"codigo": str(e.get("CodigoEmpresa", "")), "nombre": str(e.get("NombreEmpresa", ""))}
            for e in lista
        ]
        if texto:
            buscado = normalizar(texto)
            salida = [o for o in salida if buscado in normalizar(o["nombre"])]
        return salida

    def ordenes_de_compra_por_proveedor(self, rut_proveedor: str) -> list[dict[str, Any]]:
        """RF-6.2: detectar órdenes de compra nuevas sin digitar."""
        datos = self._pedir(
            "ordenesdecompra.json",
            {"CodigoProveedor": rut_proveedor},
            ttl=timedelta(hours=12),
        )
        return list(datos.get("Listado") or [])

    def estado_cuota(self) -> EstadoCuota:
        return CUOTA.estado()

    def cerrar(self) -> None:
        self._cliente.close()


def _version() -> str:
    from backend import __version__

    return __version__
