#!/usr/bin/env bash
# Doble clic (macOS) o ./iniciar.sh en Linux.
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 iniciar.py "$@"
else
  echo "No se encontro python3. Instalalo desde https://www.python.org/downloads/"
  read -r -p "Pulsa Enter para cerrar..."
fi
