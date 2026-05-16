#!/bin/bash
# Script para ejecutar TURZX en Linux

set -e

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/turzx/.venv"

# Activar entorno virtual
source "$VENV_DIR/bin/activate"

# Configurar variables para Qt en Wayland
export QT_QPA_PLATFORM_PLUGIN_PATH="$VENV_DIR/lib/python3.14/site-packages/PySide6/Qt/plugins"
export LD_LIBRARY_PATH="$VENV_DIR/lib/python3.14/site-packages/PySide6/Qt/lib:$LD_LIBRARY_PATH"

# Ejecutar aplicación
echo "Iniciando TURZX en Linux..."
echo "Dispositivo: TURZX 2.8\" USB Screen"
python -m turzx "$@"
