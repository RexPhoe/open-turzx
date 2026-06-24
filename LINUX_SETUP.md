# Open-Turzx - Guía de Configuración para Linux

## ✅ Estado Actual

El proyecto **Open-Turzx** ha sido **adaptado exitosamente para Linux**. Todos los componentes funcionan correctamente:

- ✅ Python 3.14.4 (requería ≥ 3.10)
- ✅ Entorno virtual configurado en `.venv/`
- ✅ Todas las dependencias instaladas
- ✅ Módulos importan sin errores
- ✅ Dispositivo USB detectado (VID: 0x1CBE, PID: 0x0028)
- ✅ Sensores del sistema funcionando (CPU, RAM, red, etc.)
- ✅ Aplicación ejecutándose en modo headless (sin display gráfico)

## 📋 Requisitos Instalados

### Dependencias del Sistema (libusb)

```bash
libusb 1.0.29 ✓ Detectado
```

### Dependencias Python

```
pyusb==1.3.1              # Comunicación USB
pycryptodome==3.23.0      # Encriptación DES-CBC
Pillow==12.2.0            # Procesamiento de imágenes
psutil==7.2.2             # Sensores del sistema
PySide6==6.11.1           # UI (Qt)
shiboken6==6.11.1         # Binding Qt
```

## 🚀 Ejecución

### Opción 1: Script Automático (recomendado)

```bash
cd $HOME/repos/open-turzx
./run_open-turzx.sh             # Inicia el daemon (icono en bandeja)
./run_open-turzx_settings.sh    # Abre directamente el editor de ajustes
```

Los scripts activan automáticamente el entorno virtual, esperan a que el sistema de bandeja
esté listo (StatusNotifierWatcher en Hyprland/Waybar) y configuran el entorno correctamente.
No requieren manipular manualmente variables de Qt o libusb.

### Opción 2: Línea de Comandos

```bash
cd $HOME/repos/open-turzx
source .venv/bin/activate
python -m open_turzx
```

### Opción 3: Con Display Gráfico (si hay servidor X11/Wayland)

```bash
# Con display gráfico disponible, la UI de tray se mostrará automáticamente
export DISPLAY=:0  # Ajusta según tu sesión
./run_open-turzx.sh
```

## 🔐 Permisos USB (Importante)

Por defecto, el acceso a dispositivos USB requiere permisos. Para ejecutar sin `sudo`:

```bash
# Crear regla udev
echo 'SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="0028", MODE="0666"' | \
  sudo tee /etc/udev/rules.d/99-turzx.rules

# Recargar reglas
sudo udevadm control --reload-rules
sudo udevadm trigger

# Reconectar el dispositivo USB
```

Si no configuras las reglas, deberás ejecutar con:

```bash
sudo ./run_open-turzx.sh
```

## ⚡ Sensor de Consumo en Vatios (peculiaridades)

El backend **Power** expone tres sensores: `power.cpu_w`, `power.gpu_w` y
`power.system_w` (consumo total **estimado** del equipo). No es una medida a la
pared: por software puro no es posible. Se calcula como:

```
power.system_w = cpu_w + gpu_w + baseline
```

mezclando lecturas **reales** (donde el sistema las expone) con **estimaciones**:

| Componente | Fuente real | Fallback (estimación) |
|---|---|---|
| `power.gpu_w` | NVIDIA NVML · hwmon `amdgpu` · Afterburner (Win) | — |
| `power.cpu_w` | Linux RAPL · hwmon zenpower/amd_energy · Afterburner (Win) | `idle + carga%·(TDP−idle)` |
| baseline | — | constante (RAM, placa, discos, ventiladores, pérdidas de PSU) |

La GPU NVIDIA da potencia **real sin configurar nada**. La **peculiaridad está
en la CPU**: en Linux el contador RAPL es `root`-only por defecto.

### Activar la lectura REAL de la CPU (RAPL)

`/sys/class/powercap/intel-rapl:*/energy_uj` tiene permisos `0400 root`
(CVE-2020-8694). Sin el paso siguiente, `power.cpu_w` usa la **estimación**
por carga/TDP, no una medida. Para activar la medida real:

```bash
# Instala /etc/udev/rules.d/99-open-turzx-rapl.rules, recarga udev
# y aplica el permiso de inmediato para el arranque actual.
sudo bash scripts/install_rapl_access.sh
```

Comprobar que funcionó (debe imprimir un número, no "Permission denied"):

```bash
cat /sys/class/powercap/intel-rapl:0/energy_uj
```

Después **reinicia Open-Turzx** para que el sensor tome RAPL (sin tocar código).
La regla udev se re-aplica en cada arranque, así que el cambio persiste.

> **⚠️ Riesgos / por qué es opcional**
> - **Requiere `root` una vez** para instalar la regla udev.
> - Hace el contador RAPL **legible por todos**, reabriendo **CVE-2020-8694**:
>   un canal lateral de potencia que, en teoría, permite inferir secretos
>   (p. ej. claves criptográficas) de otros procesos por análisis de consumo.
> - Tradeoff **aceptable en un equipo personal de un solo usuario**; **no lo
>   apliques en máquinas compartidas/multiusuario**.
> - Revertir: `sudo rm /etc/udev/rules.d/99-open-turzx-rapl.rules` y reiniciar
>   (el kernel restaura `0400 root`).
> - Sin la regla, **todo sigue funcionando**: el dato de CPU es solo una estimación.

### Ajustes de la estimación (variables de entorno)

Solo afectan al camino de estimación (cuando no hay sensor real de CPU):

| Variable | Defecto | Significado |
|---|---|---|
| `OPEN_TURZX_CPU_TDP` | 65 | Presupuesto de potencia sostenida de la CPU (W) |
| `OPEN_TURZX_CPU_IDLE` | 8 | Potencia de la CPU en reposo (W) |
| `OPEN_TURZX_POWER_BASELINE` | 40 | Resto del sistema: RAM, placa, discos, ventiladores, PSU (W) |

## 🛠️ Cambios Realizados para Linux

### Archivo: `open_turzx/daemon.py`

Se agregó soporte para ejecución headless (sin display gráfico):

1. **Detección de display**: Verifica `DISPLAY` y `WAYLAND_DISPLAY`
2. **Platform plugin automático**: Usa `offscreen` si no hay display
3. **Tray condicional**: Solo se muestra si hay servidor gráfico disponible
4. **Logs en consola**: Los mensajes se imprimen si la tray no está disponible

### Ejemplo de Detección Automática

```python
if sys.platform == "linux" or sys.platform == "linux2":
    has_display = bool(os.environ.get("DISPLAY")) or \
                  bool(os.environ.get("WAYLAND_DISPLAY"))
    if not has_display:
        os.environ["QT_QPA_PLATFORM"] = "offscreen"
```

## 📊 Verificación del Estado

Para verificar que todo funciona correctamente:

```bash
cd $HOME/repos/open-turzx
source .venv/bin/activate
python /tmp/test_turzx.py
```

Resultado esperado:
```
============================================================
Open-Turzx Linux Compatibility Test
============================================================

1. Platform Detection:
   sys.platform: linux ✓

2. Testing imports:
   ✓ ConfigManager
   ✓ TurzxDevice
   ✓ SensorManager
   ✓ ForegroundSensor (Linux detection)
   ✓ Renderer

3. Testing foreground window detection:
   ✓ Foreground window: '...'

4. Testing sensor reading (psutil):
   ✓ CPU: XX% | RAM: XX%

5. Checking USB device access:
   ✓ USB devices found: N
   ✓ TURZX device found: DEVICE ID 1cbe:0028
```

## 🎯 Próximos Pasos

### Opcional: Mejorar Detección de Aplicación Activa

Para que la detección de aplicación en primer plano funcione correctamente en Linux, instala `xdotool`:

```bash
# Arch Linux
sudo pacman -S xdotool

# Ubuntu/Debian
sudo apt install xdotool

# Fedora
sudo dnf install xdotool
```

Sin `xdotool`, la aplicación seguirá funcionando pero la detección de ventana activa (para modo reactivo) no funcionará.

### Opcional: Soporte para GPU NVIDIA

Si tienes GPU NVIDIA y deseas monitoreo de CUDA:

```bash
source .venv/bin/activate
pip install -e ".[gpu]"
```

Esto instala `pynvml` para lectura de sensores NVIDIA.

## 🐧 Distribuciones Soportadas

El código se ha probado y es compatible con:

- ✅ Arch Linux (entorno actual: Hyprland Wayland)
- ✅ Ubuntu/Debian (con libusb)
- ✅ Fedora (con libusb)
- ✅ Cualquier distro con libusb 1.0 y Python 3.10+

## 📝 Troubleshooting

### Error: "No module named 'open_turzx'"

```bash
# Asegúrate de estar en el entorno virtual correcto
source .venv/bin/activate
# Reinstala en modo editable
pip install -e .
```

### Error: "libusb not found"

```bash
# Arch Linux
sudo pacman -S libusb

# Ubuntu/Debian
sudo apt install libusb-1.0-0

# Fedora
sudo dnf install libusb
```

### Error: "Access denied (insufficient permissions)"

Configura las reglas udev como se describe arriba, o ejecuta con `sudo`.

### Pantalla negra o sin salida

Esto es esperado en modo headless. Verifica los logs:

```bash
python -m open_turzx 2>&1 | tee open-turzx.log
```

### Warning "invalid style override 'kvantum' passed" al iniciar

PySide6 solo incluye los estilos Qt `Fusion` y `Windows` — no tiene el plugin de Kvantum.
Entornos como Hyprland/Omarchy establecen `QT_STYLE_OVERRIDE=kvantum` globalmente.
Open-Turzx **elimina este override automáticamente** antes de crear su `QApplication`,
por lo que el warning desaparece desde esta versión.

### El contador de FPS muestra 0 aunque MangoHud esté activo

Si MangoHud está en pantalla pero no escribe logs:
1. El directorio `/tmp/turzx_logs/` debe existir **antes** de lanzar el juego.
   Open-Turzx lo crea al iniciarse — si el juego arrancó antes que Open-Turzx, reinicia el juego.
2. Verifica que `~/.config/MangoHud/MangoHud.conf` contenga `autostart_log=1`.
   Open-Turzx lo crea automáticamente, pero solo si MangoHud no tiene ya esa clave.
3. En juegos dentro de contenedores pressure-vessel (Steam Runtime), el `/tmp` del host
   es compartido — `/tmp/turzx_logs/` es visible dentro del contenedor sin configuración extra.

## 📞 Información del Dispositivo

- **Nombre**: TURZX 2.8" USB Screen
- **VendorID**: 0x1CBE
- **ProductID**: 0x0028
- **Resolución**: 480×480 px
- **Tipo**: USB 2.0 Bulk
- **Firmware**: turzx_0001_0024

## 🎮 Contador de FPS en Juegos (MangoHud)

Open-Turzx puede mostrar los FPS de juegos en Linux a través de **MangoHud**.

### Requisitos

```bash
# Instalar MangoHud
sudo apt install mangohud        # Debian/Ubuntu
sudo dnf install mangohud        # Fedora
sudo pacman -S mangohud          # Arch
```

### Configuración automática (recomendado)

Al iniciarse, Open-Turzx crea automáticamente `~/.config/MangoHud/MangoHud.conf` con la configuración mínima de logging si no existe o si no contiene `autostart_log`:

```ini
autostart_log=1
log_interval=100
output_folder=/tmp/turzx_logs
```

Esto **no sobreescribe** ninguna configuración existente del overlay — solo añade la sección de logging si falta.

### Configuración manual (por juego)

Para forzar el logging en un juego concreto desde Lutris/Steam:

**Opción A — Log dedicado en /tmp/turzx_logs** (recomendado):
```
MANGOHUD=1 MANGOHUD_CONFIG=fps_only,alpha=0,background_alpha=0,font_size=1,log_interval=100,autostart_log,output_folder=/tmp/turzx_logs mangohud %command%
```

**Opción B — Auto-detección**: Sin `output_folder`, MangoHud >=0.8.3 escribe los logs en `$HOME/{programa}_{fecha}.csv`. Open-Turzx los detecta automáticamente, pero la Opción A es más limpia.

**Nota importante**: MangoHud >=0.8.3 **ignora** el parámetro `output_file` (obsoleto). Usa `output_folder` en su lugar.

### Ejemplo Steam

En las opciones de lanzamiento del juego:
```
MANGOHUD=1 MANGOHUD_CONFIG=fps_only,alpha=0,background_alpha=0,font_size=1,log_interval=100,autostart_log,output_folder=/tmp/turzx_logs mangohud %command%
```

### Cómo funciona

Open-Turzx comprueba en orden:
1. El archivo `/tmp/turzx_fps.log` (log dedicado)
2. El directorio `/tmp/turzx_logs/` (recomendado para Open-Turzx)
3. El directorio `~/mangohud_logs/` (logs por defecto de MangoHud)
4. CSV recientes en `$HOME` y `/tmp`
5. Memoria compartida de MangoHud

Si MangoHud está corriendo pero no hay juego activo, mostrará **0 FPS**.

## 🚀 Inicio Automático del Sistema

Open-Turzx incluye una opción en **Settings → Startup** para iniciar automáticamente al arrancar el sistema.

Esto usa el estándar **XDG Autostart** (compatible con GNOME, KDE, XFCE, Hyprland y otros):
- Al activar: se crea `~/.config/autostart/open-turzx.desktop` (arranque automático)
- También se crea `~/.local/share/applications/open-turzx.desktop` (asociación de app ID para Qt/Wayland)
- Al desactivar: se eliminan ambos archivos

### Configuración manual

Si prefieres gestionarlo manualmente, puedes crear `~/.config/autostart/open-turzx.desktop`:
```ini
[Desktop Entry]
Type=Application
Name=Open-Turzx
Comment=Open-Turzx - driver for the TURZX 2.8" USB Screen
Exec=$HOME/repos/open-turzx/run_open-turzx.sh
StartupNotify=false
Terminal=false
Categories=Utility;
X-GNOME-Autostart-enabled=true
```

## ✨ Conclusión

Open-Turzx ahora es **completamente funcional en Linux**. La aplicación:

1. Se inicia sin errores
2. Detecta el dispositivo USB
3. Lee todos los sensores del sistema
4. Se adapta automáticamente a entornos con o sin display gráfico
5. Mantiene total compatibilidad con Windows (código original preservado)

¡Listo para usar! 🎉
