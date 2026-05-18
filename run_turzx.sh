#!/bin/bash
# Script para ejecutar TURZX en Linux

set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/turzx/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"

# Activar entorno virtual de forma explicita. En autostart no dependemos de la shell.
if [ -x "$VENV_PYTHON" ]; then
    export VIRTUAL_ENV="$VENV_DIR"
    export PATH="$VENV_DIR/bin:$PATH"
    unset PYTHONHOME
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
    export LD_LIBRARY_PATH="$QT_LIBS:${LD_LIBRARY_PATH:-}"
fi
if [ "${QT_STYLE_OVERRIDE:-}" = "kvantum" ]; then
    unset QT_STYLE_OVERRIDE
fi

# En Hyprland/Omarchy Waybar publica el watcher de bandeja unos segundos despues
# del autostart. Si TURZX arranca antes, Qt no registra el icono y no hay ajustes.
if [ -n "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ] && command -v busctl >/dev/null 2>&1; then
    for _ in $(seq 1 30); do
        if busctl --user status org.kde.StatusNotifierWatcher >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# Ejecutar aplicacion
echo "Iniciando TURZX en Linux..."
echo "Dispositivo: TURZX 2.8\" USB Screen"
cd "$PROJECT_DIR"
exec "$VENV_PYTHON" -m turzx "$@"
