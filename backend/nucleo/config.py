"""Configuración única del sistema, leída de variables de entorno.

Nada de credenciales en el código (PRD §6 Seguridad). Todo valor operativo
—cuotas, ventanas horarias, delays del scraper— es configurable sin tocar código,
porque son exactamente los parámetros que hay que ajustar en producción.
"""

from __future__ import annotations

import functools
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# backend/nucleo/config.py -> backend/nucleo -> backend -> raiz del proyecto
RAIZ_PROYECTO = Path(__file__).resolve().parents[2]
ARCHIVO_ENV = RAIZ_PROYECTO / ".env"


def _opciones(prefijo: str) -> SettingsConfigDict:
    """Opciones comunes de todo bloque de configuracion.

    Las clases anidadas tambien tienen que leer el .env: sin esto, funcionan
    con variables de entorno reales pero ignoran el archivo, y el sintoma
    (el sistema sigue en modo fixtures con el ticket puesto) no es evidente.
    """
    return SettingsConfigDict(
        env_prefix=prefijo,
        env_file=ARCHIVO_ENV,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class ConfigMercadoPublico(BaseSettings):
    """PRD §4.2 — límites operativos. Respetarlos es requisito, no sugerencia."""

    model_config = _opciones("MP_")

    ticket: str = ""
    base_url: str = "https://api.mercadopublico.cl/servicios/v1/publico/"
    cuota_diaria: int = 10_000
    umbral_degradacion: float = 0.80
    ventana_batch_inicio: int = 22
    ventana_batch_fin: int = 7
    timeout_seg: float = 45.0
    reintentos: int = 3
    cache_ttl_activas_min: int = 240
    cache_ttl_cerradas_dias: int = 30

    @property
    def hay_ticket(self) -> bool:
        return bool(self.ticket.strip())

    @property
    def umbral_llamadas(self) -> int:
        """Número de llamadas a partir del cual el sistema degrada."""
        return int(self.cuota_diaria * self.umbral_degradacion)


class ConfigScraper(BaseSettings):
    """PRD RF-2.3 — política del scraper. Requisito, no recomendación."""

    model_config = _opciones("SCRAPER_")

    habilitado: bool = False
    user_agent: str = "sgl-ito-serviu/0.1"
    contacto_email: str = ""
    delay_seg: float = 5.0
    max_licitaciones_dia: int = 10
    respetar_robots: bool = True

    @property
    def user_agent_completo(self) -> str:
        """User-agent identificable con correo de contacto (RF-2.3)."""
        if self.contacto_email:
            return f"{self.user_agent} (+mailto:{self.contacto_email})"
        return self.user_agent


class ConfigLLM(BaseSettings):
    """PRD §4.4 — la IA resume y pre-clasifica, no decide."""

    model_config = _opciones("LLM_")

    provider: str = "null"
    rpm: int = 10
    max_requests_dia: int = 1000


class ConfigGemini(BaseSettings):
    model_config = _opciones("GEMINI_")

    api_key: str = ""
    modelo: str = "gemini-2.5-flash"


class ConfigStorage(BaseSettings):
    model_config = _opciones("STORAGE_")

    backend: str = "local"
    local_raiz: str = "datos/files"


class ConfigNotificaciones(BaseSettings):
    model_config = _opciones("NOTIFY_")

    backends: str = "consola"

    @property
    def backends_lista(self) -> list[str]:
        return [b.strip() for b in self.backends.split(",") if b.strip()]


class Config(BaseSettings):
    """Configuración raíz. Se obtiene siempre con `obtener_config()`."""

    model_config = SettingsConfigDict(
        env_file=RAIZ_PROYECTO / ".env",
        env_file_encoding="utf-8",
        env_prefix="APP_",
        extra="ignore",
    )

    env: str = "dev"
    secret_key: str = "dev-inseguro-cambiar"
    timezone: str = "America/Santiago"
    #: Nivel de log. Vacio = automatico (DEBUG en dev, INFO en produccion).
    #: El lanzador lo baja a WARNING para que su propia salida se lea.
    log_nivel: str = ""
    database_url: str = Field(
        default="sqlite+pysqlite:///datos/data/sgl.sqlite3",
        validation_alias="DATABASE_URL",
    )

    mp: ConfigMercadoPublico = Field(default_factory=ConfigMercadoPublico)
    scraper: ConfigScraper = Field(default_factory=ConfigScraper)
    llm: ConfigLLM = Field(default_factory=ConfigLLM)
    gemini: ConfigGemini = Field(default_factory=ConfigGemini)
    storage: ConfigStorage = Field(default_factory=ConfigStorage)
    notificaciones: ConfigNotificaciones = Field(default_factory=ConfigNotificaciones)

    @field_validator("database_url")
    @classmethod
    def _normalizar_url_bd(cls, v: str) -> str:
        """Supabase y Render entregan `postgres://` o `postgresql://`.

        SQLAlchemy 2 necesita un driver explícito; fijamos psycopg 3.
        """
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+psycopg://", 1)
        elif v.startswith("postgresql://"):
            v = v.replace("postgresql://", "postgresql+psycopg://", 1)
        return v

    @property
    def es_produccion(self) -> bool:
        return self.env == "prod"

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def raiz(self) -> Path:
        return RAIZ_PROYECTO

    def ruta(self, relativa: str) -> Path:
        """Resuelve una ruta relativa a la raíz del proyecto."""
        p = Path(relativa)
        return p if p.is_absolute() else RAIZ_PROYECTO / p


@functools.lru_cache(maxsize=1)
def obtener_config() -> Config:
    """Config única del proceso. Cacheada; en tests usar `obtener_config.cache_clear()`."""
    return Config()
