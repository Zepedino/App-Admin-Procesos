"""INICIAR LA APLICACION.

Ejecuta este archivo y la aplicacion se abre en el navegador. Nada mas.

    - En Windows: doble clic en "Iniciar aplicacion.bat"
    - En VS Code o PyCharm: boton Run sobre este archivo
    - En una terminal: python iniciar.py

La primera vez tarda un par de minutos porque instala lo que necesita. Las
siguientes es cuestion de segundos.

Para detenerla: Ctrl+C en la ventana, o simplemente cierrala.

------------------------------------------------------------------------------
Este archivo usa SOLO la libreria estandar de Python, a proposito: tiene que
poder ejecutarse ANTES de que nada este instalado. Si aqui dentro apareciera un
`import fastapi`, el arranque fallaria justo en el caso que este script existe
para resolver.
"""

from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
VENV = RAIZ / ".venv"
PYTHON_MINIMO = (3, 11)
PUERTO_PREFERIDO = 8000
MARCA_INSTALACION = VENV / ".dependencias-instaladas"


# --- Presentacion ------------------------------------------------------------

def _color(texto: str, codigo: str) -> str:
    """Color solo si la terminal lo soporta; si no, texto plano."""
    if os.environ.get("NO_COLOR") or not sys.stdout.isatty():
        return texto
    return f"\033[{codigo}m{texto}\033[0m"


def titulo(texto: str) -> None:
    print()
    print(_color(f"  {texto}", "1;36"))
    print(_color("  " + "-" * len(texto), "36"))


def paso(texto: str) -> None:
    print(f"  {_color('>', '36')} {texto}")


def ok(texto: str) -> None:
    print(f"  {_color('OK', '1;32')} {texto}")


def aviso(texto: str) -> None:
    print(f"  {_color('!', '1;33')}  {texto}")


def error(texto: str) -> None:
    print(f"  {_color('ERROR', '1;31')} {texto}")


def explicar_y_salir(titulo_error: str, *lineas: str) -> None:
    """Termina explicando que hacer, no solo que fallo.

    Un mensaje de error que no dice cual es el siguiente paso deja a quien no
    programa exactamente igual de atascado que antes.
    """
    print()
    error(titulo_error)
    print()
    for linea in lineas:
        print(f"     {linea}")
    print()
    _esperar_antes_de_cerrar()
    sys.exit(1)


def _esperar_antes_de_cerrar() -> None:
    """Evita que la ventana se cierre de golpe al hacer doble clic."""
    if sys.stdin and sys.stdin.isatty():
        try:
            input("  Pulsa Enter para cerrar esta ventana...")
        except (EOFError, KeyboardInterrupt):
            pass


# --- Entorno -----------------------------------------------------------------

def python_del_venv() -> Path:
    if platform.system() == "Windows":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def estamos_en_el_venv() -> bool:
    try:
        return Path(sys.executable).resolve() == python_del_venv().resolve()
    except OSError:
        return False


def verificar_version_python() -> None:
    if sys.version_info < PYTHON_MINIMO:
        actual = f"{sys.version_info.major}.{sys.version_info.minor}"
        explicar_y_salir(
            f"Se necesita Python {PYTHON_MINIMO[0]}.{PYTHON_MINIMO[1]} o superior. "
            f"Tienes la {actual}.",
            "Descarga la ultima version desde https://www.python.org/downloads/",
            "Durante la instalacion, marca la casilla 'Add Python to PATH'.",
        )


def crear_venv_si_falta() -> None:
    """El entorno virtual aisla las dependencias del resto del computador."""
    if python_del_venv().exists():
        return
    titulo("Preparando el entorno (solo la primera vez)")
    paso("Creando entorno virtual en .venv ...")
    try:
        subprocess.run(
            [sys.executable, "-m", "venv", str(VENV)],
            check=True,
            capture_output=True,
            text=True,
        )
    except subprocess.CalledProcessError as exc:
        explicar_y_salir(
            "No se pudo crear el entorno virtual.",
            f"Detalle: {(exc.stderr or exc.stdout or '').strip()[:300]}",
            "",
            "Causa habitual: falta el modulo venv. En Linux se instala con",
            "  sudo apt install python3-venv",
        )
    ok("Entorno virtual creado")


def _firma_dependencias() -> str:
    """Huella de pyproject.toml: si cambia, hay que reinstalar.

    Evita reinstalar en cada arranque (lento) sin arriesgarse a quedar con
    dependencias viejas cuando alguien agrega una libreria al proyecto.
    """
    archivo = RAIZ / "pyproject.toml"
    if not archivo.exists():
        return ""
    import hashlib

    return hashlib.sha256(archivo.read_bytes()).hexdigest()


def instalar_dependencias_si_hace_falta() -> None:
    firma = _firma_dependencias()
    if MARCA_INSTALACION.exists() and MARCA_INSTALACION.read_text(encoding="utf-8") == firma:
        return

    titulo("Instalando lo que la aplicacion necesita")
    aviso("Esto puede tardar uno o dos minutos. Solo ocurre la primera vez.")
    aviso("Veras pasar muchas lineas: es normal, esta descargando librerias.")
    print()

    python = str(python_del_venv())
    comandos = [
        ([python, "-m", "pip", "install", "--upgrade", "pip"], "Actualizando pip"),
        ([python, "-m", "pip", "install", "-e", ".[dev]"], "Instalando dependencias"),
    ]
    for comando, descripcion in comandos:
        paso(descripcion + " ...")
        # Sin capturar la salida a proposito: durante dos minutos de descarga,
        # una pantalla congelada parece un cuelgue. Ademas, si algo falla, el
        # error de pip queda a la vista en vez de resumido en una linea vacia.
        resultado = subprocess.run(comando, check=False)
        if resultado.returncode != 0:
            explicar_y_salir(
                f"Fallo al ejecutar: {descripcion}",
                "El detalle esta en las lineas de arriba.",
                "",
                "Causa mas habitual: sin conexion a internet o detras de un proxy.",
                "Si el problema persiste, borra la carpeta .venv y vuelve a ejecutar:",
                "se recrea sola.",
            )
        print()

    MARCA_INSTALACION.write_text(firma, encoding="utf-8")
    ok("Dependencias instaladas")


def reejecutar_dentro_del_venv() -> None:
    """Relanza este mismo script con el Python del entorno virtual.

    Asi da igual con que Python se haya abierto el archivo: el trabajo real
    siempre ocurre dentro del entorno aislado.
    """
    python = str(python_del_venv())
    try:
        resultado = subprocess.run(
            [python, str(Path(__file__).resolve()), *sys.argv[1:]], check=False
        )
        sys.exit(resultado.returncode)
    except KeyboardInterrupt:
        sys.exit(0)


# --- Configuracion y datos ---------------------------------------------------

def crear_env_si_falta() -> None:
    destino = RAIZ / ".env"
    plantilla = RAIZ / ".env.example"
    if destino.exists() or not plantilla.exists():
        return
    shutil.copyfile(plantilla, destino)
    ok("Archivo .env creado a partir de .env.example")
    aviso("Cuando tengas el ticket de Mercado Publico, escribelo en .env (MP_TICKET).")


def preparar_base_de_datos() -> None:
    """Crea las tablas y los datos iniciales si la base esta vacia.

    Es idempotente: ejecutarlo mil veces no duplica nada.
    """
    from backend.app import _importar_modelos
    from backend.consola import _cargar_semilla
    from backend.nucleo.db import obtener_motor
    from backend.nucleo.modelo_base import Base

    _importar_modelos()
    motor = obtener_motor()
    from sqlalchemy import inspect

    ya_existia = bool(inspect(motor).get_table_names())
    Base.metadata.create_all(motor)

    if not ya_existia:
        paso("Creando la base de datos y los datos iniciales ...")
        _cargar_semilla()
        ok("Base de datos lista")


def importar_procedimientos() -> None:
    """RF-0.1: publica el PROCESO.md de cada modulo dentro de la aplicacion."""
    from backend.modulos.m0_procesos.services import importar_desde_paquetes

    resumen = importar_desde_paquetes(RAIZ / "backend" / "modulos")
    nuevos = resumen["creados"] + resumen["actualizados"]
    if nuevos:
        ok(f"Procedimientos actualizados ({nuevos})")


# --- Red ---------------------------------------------------------------------

def puerto_libre(preferido: int = PUERTO_PREFERIDO) -> int:
    """Devuelve el primer puerto disponible desde el preferido.

    Si el 8000 esta ocupado por otra cosa, la app arranca igual en el 8001 en
    vez de fallar con un error que no le dice nada a nadie.
    """
    for puerto in range(preferido, preferido + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("127.0.0.1", puerto)) != 0:
                return puerto
    explicar_y_salir(
        "No hay puertos libres entre el 8000 y el 8019.",
        "Cierra otras aplicaciones que puedan estar usandolos y vuelve a intentar.",
    )
    return preferido  # inalcanzable; mantiene contento al verificador de tipos


def abrir_navegador_cuando_responda(url: str, puerto: int) -> None:
    """Abre el navegador recien cuando el servidor acepta conexiones.

    Abrirlo antes muestra una pagina de error y hace pensar que algo fallo.
    """

    def esperar() -> None:
        for _ in range(100):  # hasta ~20 segundos
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex(("127.0.0.1", puerto)) == 0:
                    time.sleep(0.4)
                    webbrowser.open(url)
                    return
            time.sleep(0.2)

    threading.Thread(target=esperar, daemon=True).start()


# --- Arranque ----------------------------------------------------------------

def levantar_servidor(puerto: int, *, recarga: bool) -> None:
    import uvicorn

    url = f"http://localhost:{puerto}"

    titulo("Aplicacion en marcha")
    print(f"  Abre esta direccion:  {_color(url, '1;36')}")
    print(f"  Para detenerla:       {_color('Ctrl+C', '1;33')}")
    print()

    abrir_navegador_cuando_responda(url, puerto)

    try:
        uvicorn.run(
            "backend.app:app",
            host="127.0.0.1",
            port=puerto,
            reload=recarga,
            log_level="warning",   # los mensajes de la app ya salen por su logger
            access_log=False,
        )
    except KeyboardInterrupt:
        pass
    finally:
        print()
        ok("Aplicacion detenida")


def main() -> None:
    print()
    print(_color("  SGL - Sistema de Gestion de Licitaciones y Contratos", "1;37"))
    print(_color("  Consultora ITO / SERVIU", "37"))

    # Silencia el detalle tecnico salvo que se pida con --detalle: quien abre
    # esto por doble clic necesita leer los mensajes del lanzador, no cien
    # lineas de DEBUG del planificador de tareas.
    if "--detalle" not in sys.argv:
        os.environ.setdefault("APP_LOG_NIVEL", "WARNING")

    verificar_version_python()
    crear_venv_si_falta()
    instalar_dependencias_si_hace_falta()

    # A partir de aqui hacen falta las dependencias instaladas, asi que si no
    # estamos dentro del entorno virtual, relanzamos y este proceso termina.
    if not estamos_en_el_venv():
        reejecutar_dentro_del_venv()
        return

    crear_env_si_falta()

    titulo("Preparando los datos")
    try:
        preparar_base_de_datos()
        importar_procedimientos()
    except Exception as exc:
        explicar_y_salir(
            "No se pudo preparar la base de datos.",
            f"Detalle: {type(exc).__name__}: {exc}",
            "",
            "Si el problema persiste, borra la carpeta datos/data y vuelve a ejecutar:",
            "se recreara desde cero (se pierden los datos de prueba, no el codigo).",
        )
    ok("Todo listo")

    puerto = puerto_libre()
    if puerto != PUERTO_PREFERIDO:
        aviso(f"El puerto {PUERTO_PREFERIDO} estaba ocupado; se usa el {puerto}.")

    levantar_servidor(puerto, recarga="--recarga" in sys.argv or "--reload" in sys.argv)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        print("  Cancelado.")
        sys.exit(0)
