#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$HOME/repos/open-turzx"
RUN_SCRIPT="$PROJECT_DIR/run_open-turzx.sh"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/open-turzx"
LOG_FILE="$LOG_DIR/monitor.log"

mkdir -p "$LOG_DIR"

log() {
    printf '%s %s\n' "$(date --iso-8601=seconds)" "$*" >>"$LOG_FILE"
}

is_open_turzx_running() {
    pgrep -f '[-]m open_turzx' >/dev/null 2>&1 \
        || pgrep -f '(^|[ /])[o]pen-turzx($| )' >/dev/null 2>&1
}

if is_open_turzx_running; then
    log "already running"
    exit 0
fi

if [ ! -x "$RUN_SCRIPT" ]; then
    log "ERROR: run script is not executable: $RUN_SCRIPT"
    exit 1
fi

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export DBUS_SESSION_BUS_ADDRESS="${DBUS_SESSION_BUS_ADDRESS:-unix:path=$XDG_RUNTIME_DIR/bus}"

# Timers/cron do not inherit the graphical session. Reuse Hyprland's env.
for proc in Hyprland waybar; do
    pid="$(pgrep -n -x "$proc" 2>/dev/null || true)"
    if [ -n "$pid" ] && [ -r "/proc/$pid/environ" ]; then
        while IFS='=' read -r key value; do
            case "$key" in
                DISPLAY|WAYLAND_DISPLAY|XDG_CURRENT_DESKTOP|XDG_SESSION_TYPE|QT_QPA_PLATFORM|GDK_BACKEND|DBUS_SESSION_BUS_ADDRESS|XDG_RUNTIME_DIR)
                    export "$key=$value"
                    ;;
            esac
        done < <(tr '\0' '\n' <"/proc/$pid/environ")
        break
    fi
done

if [ -z "${WAYLAND_DISPLAY:-}${DISPLAY:-}" ]; then
    log "ERROR: no graphical session detected"
    exit 1
fi

log "starting Open-Turzx service"
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XDG_CURRENT_DESKTOP XDG_SESSION_TYPE QT_QPA_PLATFORM GDK_BACKEND DBUS_SESSION_BUS_ADDRESS XDG_RUNTIME_DIR
systemctl --user start open-turzx.service
