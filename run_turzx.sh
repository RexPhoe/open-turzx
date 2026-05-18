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

# Eliminar override de estilo Qt si interfiere con PySide6
if [ "${QT_STYLE_OVERRIDE:-}" = "kvantum" ]; then
    unset QT_STYLE_OVERRIDE
fi

# PySide6 gestiona sus propias librerias y plugins Qt internamente.
# NO establecer LD_LIBRARY_PATH o QT_QPA_PLATFORM_PLUGIN_PATH manualmente:
# hacerlo fuerza al linker a cargar las librerias empaquetadas de PySide6
# (ffmpeg, icu, qt) y puede causar conflictos con las del sistema que
# se manifiestan como cuelgues al abrir ventanas Qt.

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
