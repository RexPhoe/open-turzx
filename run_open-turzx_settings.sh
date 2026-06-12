#!/bin/bash
# Abre Open-Turzx directamente en la ventana de ajustes.

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$PROJECT_DIR/run_open-turzx.sh" --settings
