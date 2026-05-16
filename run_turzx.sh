#!/bin/bash
# Script para ejecutar TURZX en Linux

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/turzx/.venv"

# Activar entorno virtual
if [ -f "$VENV_DIR/bin/activate" ]; then
    source "$VENV_DIR/bin/activate"
else
    echo "ERROR: Entorno virtual no encontrado en $VENV_DIR" >&2
    exit 1
fi

# Detectar version de Python dinamicamente
PY_VER=$("$VENV_DIR/bin/python" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
QT_PLUGINS="$VENV_DIR/lib/python${PY_VER}/site-packages/PySide6/Qt/plugins"
QT_LIBS="$VENV_DIR/lib/python${PY_VER}/site-packages/PySide6/Qt/lib"

# Configurar variables para Qt en Wayland
if [ -d "$QT_PLUGINS" ]; then
    export QT_QPA_PLATFORM_PLUGIN_PATH="$QT_PLUGINS"
fi
if [ -d "$QT_LIBS" ]; then
    export LD_LIBRARY_PATH="$QT_LIBS:$LD_LIBRARY_PATH"
fi

# Ejecutar aplicacion
echo "Iniciando TURZX en Linux..."
echo "Dispositivo: TURZX 2.8\" USB Screen"
python -m turzx "$@"
