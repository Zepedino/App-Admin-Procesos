"""Tests de arquitectura.

Estas reglas son las que mantienen el sistema modular. Un test las hace
exigibles; un parrafo en la documentacion, no. Si uno de estos falla, el
sistema perdio la propiedad que lo hace reparable por partes.

Ver CLAUDE.md, seccion 5.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1] / "src" / "sgl"


def _imports_de(archivo: Path) -> list[str]:
    arbol = ast.parse(archivo.read_text(encoding="utf-8"), filename=str(archivo))
    modulos: list[str] = []
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            modulos += [a.name for a in nodo.names]
        elif isinstance(nodo, ast.ImportFrom) and nodo.module and nodo.level == 0:
            modulos.append(nodo.module)
    return modulos


def _archivos(subcarpeta: str) -> list[Path]:
    return sorted((RAIZ / subcarpeta).rglob("*.py"))


def test_core_no_importa_modulos_ni_providers():
    """El nucleo no sabe que modulos existen; son ellos los que se registran.

    Si el nucleo importa un modulo, quitar ese modulo rompe el arranque completo.
    """
    infracciones = []
    for archivo in _archivos("core"):
        for modulo in _imports_de(archivo):
            if modulo.startswith(("sgl.modules", "sgl.providers")):
                infracciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
    assert not infracciones, "core/ debe ser independiente:\n  " + "\n  ".join(infracciones)


def test_providers_no_importan_modulos():
    """Un adaptador externo no puede depender de logica de negocio."""
    infracciones = []
    for archivo in _archivos("providers"):
        for modulo in _imports_de(archivo):
            if modulo.startswith("sgl.modules"):
                infracciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
    assert not infracciones, "providers/ no debe importar modules/:\n  " + "\n  ".join(infracciones)


def test_modulos_no_se_importan_entre_si():
    """Los modulos se comunican por el bus de eventos, no por imports directos.

    Es lo que permite construir M5 sin tocar M1, y quitar M7 sin romper M3.
    """
    infracciones = []
    for archivo in _archivos("modules"):
        partes = archivo.relative_to(RAIZ / "modules").parts
        if len(partes) < 2:
            continue  # el __init__.py del paquete raiz si conoce a todos
        propio = partes[0]
        for modulo in _imports_de(archivo):
            if not modulo.startswith("sgl.modules."):
                continue
            ajeno = modulo.split(".")[2]
            if ajeno != propio:
                infracciones.append(f"{archivo.relative_to(RAIZ)} importa {modulo}")
    assert not infracciones, (
        "un modulo importa a otro directamente; usa el bus de eventos:\n  "
        + "\n  ".join(infracciones)
    )


def test_solo_el_adaptador_habla_con_mercadopublico():
    """PRD seccion 4.2: toda llamada pasa por ProcurementProvider.

    Si aparece una URL de mercadopublico.cl fuera del adaptador, alguien esta
    saltandose la cuota, la cache y los reintentos.
    """
    permitidos = {
        "providers/procurement/mercadopublico.py",
        "providers/procurement/base.py",
        "cli.py",  # capturar-fixture, documentado y con ticket explicito
        "core/config.py",  # declara la URL base por defecto; no hace llamadas
    }
    infracciones = []
    for archivo in RAIZ.rglob("*.py"):
        relativo = archivo.relative_to(RAIZ).as_posix()
        if relativo in permitidos:
            continue
        texto = archivo.read_text(encoding="utf-8")
        if "api.mercadopublico.cl" in texto:
            infracciones.append(relativo)
    assert not infracciones, (
        "URL de la API fuera del adaptador:\n  " + "\n  ".join(infracciones)
    )


def test_todo_modulo_declara_manifiesto():
    """Cada paquete mN_ expone un MODULO, y el registro los conoce a todos."""
    from sgl.modules import obtener_registro

    registro = obtener_registro()
    ids_registrados = {m.id for m in registro.modulos}

    paquetes = {
        p.name
        for p in (RAIZ / "modules").iterdir()
        if p.is_dir() and p.name.startswith("m") and (p / "__init__.py").exists()
    }
    faltantes = paquetes - ids_registrados
    assert not faltantes, f"paquetes sin registrar en modules/__init__.py: {faltantes}"


def test_los_manifiestos_declaran_requisitos_del_prd():
    """Todo modulo dice que RF cubre. Sin eso no se puede auditar el avance."""
    from sgl.modules import obtener_registro

    sin_requisitos = [m.id for m in obtener_registro().modulos if not m.requisitos]
    assert not sin_requisitos, f"modulos sin requisitos declarados: {sin_requisitos}"


def test_todo_evento_publicado_esta_en_el_catalogo():
    """Los nombres de evento se declaran en Eventos, no como cadenas sueltas.

    Evita que un emisor y un suscriptor difieran por un error de tipeo, que es
    un fallo silencioso: el evento se emite y nadie lo recibe.
    """
    from sgl.core.eventos import Eventos

    catalogo = {
        v for k, v in vars(Eventos).items() if not k.startswith("_") and isinstance(v, str)
    }
    usados: set[str] = set()
    for archivo in RAIZ.rglob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if not isinstance(nodo, ast.Call):
                continue
            funcion = nodo.func
            nombre = getattr(funcion, "attr", None)
            if nombre not in {"emitir", "suscribir"} or not nodo.args:
                continue
            primero = nodo.args[0]
            if isinstance(primero, ast.Constant) and isinstance(primero.value, str):
                usados.add(primero.value)
    fuera = usados - catalogo
    assert not fuera, f"eventos usados como cadena suelta, no estan en Eventos: {fuera}"


@pytest.mark.parametrize(
    "carpeta,archivos_obligatorios",
    [("m0_procesos", ["models.py", "routes.py"]), ("m1_radar", ["models.py", "routes.py", "services.py"])],
)
def test_anatomia_de_modulo(carpeta, archivos_obligatorios):
    """Todos los modulos construidos tienen la misma forma (CLAUDE.md seccion 5)."""
    base = RAIZ / "modules" / carpeta
    faltantes = [a for a in archivos_obligatorios if not (base / a).exists()]
    assert not faltantes, f"{carpeta} no cumple la anatomia: faltan {faltantes}"


def test_todo_modulo_construido_tiene_procedimiento_escrito():
    """RF-0.1: cada flujo del sistema tiene un procedimiento escrito.

    Se aplica a los modulos construidos, no a los planificados: exigirle un
    PROCESO.md a un modulo que todavia no existe seria documentar ficcion.
    """
    from sgl.core.registro import EstadoModulo
    from sgl.modules import obtener_registro

    faltantes = [
        m.id
        for m in obtener_registro().modulos
        if m.estado != EstadoModulo.PLANIFICADO
        and not (RAIZ / "modules" / m.id / "PROCESO.md").exists()
    ]
    assert not faltantes, f"modulos construidos sin PROCESO.md: {faltantes}"
