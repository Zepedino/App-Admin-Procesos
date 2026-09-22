"""Roles y permisos (PRD §3).

"3 a 10 usuarios. No se necesita arquitectura de escala; sí control de acceso
por rol, porque hay datos de multas y remuneraciones."

El permiso es la unidad, no el rol: así se puede mover una capacidad entre roles
sin cazar condicionales por todo el código.
"""

from __future__ import annotations

from enum import StrEnum

from sgl.core.errors import PermisoDenegado


class Rol(StrEnum):
    GERENCIA = "gerencia"
    LICITACIONES = "licitaciones"
    ITO = "ito"
    FINANZAS = "finanzas"
    ADMIN = "admin"


class Permiso(StrEnum):
    # Radar y licitaciones
    VER_RADAR = "ver_radar"
    EDITAR_PERFIL_INTERES = "editar_perfil_interes"
    DESCARTAR_LICITACION = "descartar_licitacion"
    DECIDIR_GO_NO_GO = "decidir_go_no_go"          # solo Gerencia (PRD §3)

    # Contratos y ejecución
    VER_CONTRATOS = "ver_contratos"
    VER_CONTRATOS_PROPIOS = "ver_contratos_propios"
    EDITAR_CONTRATO = "editar_contrato"
    GESTIONAR_PUESTA_EN_MARCHA = "gestionar_puesta_en_marcha"

    # Dinero
    VER_ESTADOS_PAGO = "ver_estados_pago"
    EDITAR_ESTADOS_PAGO = "editar_estados_pago"
    VER_GARANTIAS = "ver_garantias"
    VER_FLUJO_CAJA = "ver_flujo_caja"

    # Datos restringidos — PRD §3: "Único que ve costos de personal y rentabilidad"
    VER_REMUNERACIONES = "ver_remuneraciones"
    VER_RENTABILIDAD = "ver_rentabilidad"

    # Multas
    VER_MULTAS = "ver_multas"
    REGISTRAR_MULTA = "registrar_multa"

    # Terreno
    REGISTRAR_VISITA = "registrar_visita"
    REGISTRAR_HORAS = "registrar_horas"

    # Sistema
    ADMINISTRAR = "administrar"
    VER_AUDITORIA = "ver_auditoria"
    EDITAR_PROCEDIMIENTOS = "editar_procedimientos"


#: Matriz de permisos. Es la traducción literal de la tabla del PRD §3.
#: Cambiar quién puede qué se hace AQUÍ y en ningún otro lugar.
PERMISOS_POR_ROL: dict[Rol, set[Permiso]] = {
    Rol.GERENCIA: set(Permiso),  # "Todo. Aprueba go/no-go."
    Rol.LICITACIONES: {
        Permiso.VER_RADAR,
        Permiso.EDITAR_PERFIL_INTERES,
        Permiso.DESCARTAR_LICITACION,
        Permiso.VER_CONTRATOS,
        Permiso.EDITAR_PROCEDIMIENTOS,
        # No ve remuneraciones ni rentabilidad (PRD §3).
    },
    Rol.ITO: {
        Permiso.VER_CONTRATOS_PROPIOS,
        Permiso.GESTIONAR_PUESTA_EN_MARCHA,
        Permiso.REGISTRAR_VISITA,
        Permiso.REGISTRAR_HORAS,
        Permiso.VER_MULTAS,
    },
    Rol.FINANZAS: {
        Permiso.VER_CONTRATOS,
        Permiso.VER_ESTADOS_PAGO,
        Permiso.EDITAR_ESTADOS_PAGO,
        Permiso.VER_GARANTIAS,
        Permiso.VER_FLUJO_CAJA,
        Permiso.VER_MULTAS,
        Permiso.REGISTRAR_MULTA,
        # Ve la caja, no el costo del personal.
    },
    Rol.ADMIN: {
        Permiso.ADMINISTRAR,
        Permiso.VER_AUDITORIA,
        Permiso.EDITAR_PROCEDIMIENTOS,
        Permiso.VER_RADAR,
        Permiso.EDITAR_PERFIL_INTERES,
    },
}


def permisos_de(rol: Rol | str) -> set[Permiso]:
    try:
        return PERMISOS_POR_ROL[Rol(rol)]
    except ValueError:
        return set()


def puede(rol: Rol | str, permiso: Permiso) -> bool:
    return permiso in permisos_de(rol)


def exigir(rol: Rol | str, permiso: Permiso) -> None:
    """Corta la operación si el rol no tiene el permiso."""
    if not puede(rol, permiso):
        raise PermisoDenegado(
            f"el rol '{rol}' no tiene el permiso '{permiso}'", rol=str(rol), permiso=str(permiso)
        )
