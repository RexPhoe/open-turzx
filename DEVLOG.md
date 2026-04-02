# TURZX 2.8" — Development Log (Improvement Loop)

> Este archivo es el registro cronológico del proyecto.
> Se actualiza en cada sesión de trabajo.
> Objetivo: evitar repetir errores, recuperar contexto rápido.

---

## ESTADO GLOBAL DEL PROYECTO

| Aspecto | Estado | Detalle |
|---|---|---|
| Protocolo DES-CBC | ✅ Validado | key=IV=`b"slv3tuzx"`, CBC, PKCS7 |
| Comunicacion USB | ✅ Funciona | EP 0x01 OUT / EP 0x81 IN (Bulk), status 200 |
| Renderizado imagen | ✅ **FUNCIONA** | CMD 101 (SEND_JPEG), no CMD 102 |
| Rotacion pantalla | ✅ Corregido | Rotate 180 en software (panel montado al reves) |
| App daemon + tray | 🔧 Phase 1 | Estructura creada, PySide6, sensores psutil |
| Visual editor | ⏳ Phase 2 | Drag-and-drop de elementos en canvas 480x480 |
| Dynamic profiles | ⏳ Phase 3 | Cambio automatico segun programa activo |
| BOB (avatar virtual) | ⏳ Phase 4 | Personaje animado con IA — experimental |
| Compatibilidad Linux | 🔧 En progreso | libusb + psutil + PySide6 = cross-platform |
| Device se bloquea | ⚠️ Confirmado | Secuencias largas (>5-6 cmds) bloquean firmware |

**FASE ACTUAL: Phase 1 — Daemon + Static Monitor**

**Protocolo resuelto (2026-04-02):**
- CMD 101 (`SEND_JPEG`) muestra imagen; CMD 102 es aceptado pero NO renderiza
- Panel montado 180 invertido — se corrige con `img.rotate(180)` en software
- ReadFlush debe ir DESPUES del read (como C#), no antes del write
- Secuencia: `SET_DATETIME(2) -> PREPARE -> CMD 101 -> ... -> SET_DATETIME(0) -> COMMIT`

## PLAN DE FASES

### Phase 1 — Daemon + Static Monitor (ACTUAL)
Daemon con tray icon que muestra sensores del sistema en la pantalla.
- [x] Driver USB validado (protocol.py, device.py, images.py)
- [x] Estructura del proyecto limpia
- [x] Sistema de sensores cross-platform (psutil + pynvml)
- [x] Renderer: layout JSON -> imagen 480x480
- [x] ConfigManager: load/save layouts
- [x] Daemon con QThread render loop
- [x] Tray icon con menu (Start/Pause, Settings, Quit)
- [x] Ventana Settings con preview live y lista de sensores
- [ ] Probar ejecucion completa (daemon + device real)
- [ ] Ajustar layout default con datos reales
- [ ] Publicar en GitHub

### Phase 2 — Visual Editor
Editor drag-and-drop para disenar layouts.
- [ ] QGraphicsScene canvas 480x480
- [ ] Arrastrar elementos (texto, sensor, imagen)
- [ ] Mover X/Y libremente
- [ ] Control Z-order (delante/detras)
- [ ] Editar propiedades (font, color, formato)
- [ ] Selector de fondo (color solido, imagen, video en bucle)
- [ ] Guardar/cargar configuraciones
- [ ] Frecuencia de actualizacion por layout

### Phase 3 — Dynamic Profiles
La pantalla cambia automaticamente segun el programa activo.
- [ ] Detectar programa/juego en primer plano
- [ ] Asociar layouts a programas
- [ ] Transicion automatica al cambiar de app
- [ ] Fallback a layout por defecto

### Phase 4 — BOB (Experimental)
Avatar virtual animado que vive en la pantalla.
- [ ] Personaje/fantasma con animaciones
- [ ] Reacciones a acciones del usuario
- [ ] Sistema de emociones
- [ ] Conexion con agente de IA para controlar comportamiento

---

## Sesión 2026-03-29

### Contexto recuperado
- Revisión completa del estado tras sesión anterior
- Re-evaluación estratégica del proyecto

### Decisiones tomadas
1. **Prioridad 1 cambiada**: Captura USB con `usbmon` (Linux) de la app oficial
2. No se replantea desde 0 — protocolo correcto, falta verificar flujo real
3. Compatibilidad Linux establecida como requisito
4. Se crea el sistema de bucle de mejora (este archivo)

### Restructura del proyecto
```
TURZX/
├── DEVLOG.md              ← Este archivo
├── pyproject.toml         ← Dependencias (Linux-first)
├── turzx/
│   ├── protocol.py        ← DES, construcción de paquetes (puro, sin USB)
│   ├── device.py          ← I/O USB (Linux-first, libusb sistema)
│   └── images.py          ← Helpers PIL
├── tools/
│   ├── poc.py             ← Test runner principal
│   └── capture_analysis.py← Análisis de capturas usbmon
└── legacy/                ← Código histórico (referencia)
```

### Próximos pasos (ordenados por prioridad)
- [ ] **BLOQUEANTE**: Capturar tráfico USB con `usbmon` + Wireshark (app oficial en Windows o Wine)
- [x] ~~Verificar si device es `Is207Lcd`~~ -> DESCARTADO, device es `_220E` (USB bulk)
- [ ] Verificar write completo del JPEG (device limpio, sin secuencias extra)
- [ ] Probar envío header+JPEG como writes separados
- [ ] Probar secuencia alternativa con `EndpointType.Interrupt` en lectura

### Errores conocidos y soluciones
*(Ninguno nuevo esta sesión)*

---

## Sesion 2026-04-02

### Contexto
- Device accesible en Windows (app oficial cerrada)
- Objetivo: avanzar autónomamente sin captura USB

### Hallazgos principales

#### 1. Hipotesis Is207Lcd DESCARTADA
- `_2DF1` (Is207Lcd=true) usa **SerialPortStream**, protocolo sin DES, header 0x80
- `_220E` (nuestro device) usa USB bulk, DES-CBC, header 512B encriptado
- Confirmado en `Monitor.cs:16874` y `-.cs:9599` vs `-.cs:34549`
- `_2DF1` usa CMDs 200/201/202/204 (completamente diferentes a 101/102)
- Esto elimina la hipotesis principal que teniamos

#### 2. Comunicacion USB funciona desde Windows
- pyproject.toml fix: `setuptools.backends.legacy:build` -> `setuptools.build_meta`
- libusb DLL en `.venv/Lib/site-packages/libusb/_platform/windows/x86_64/libusb-1.0.dll`
- Unicode fix: reemplazar caracteres `->` y `-` (cp1252 no soporta Unicode arrows/dashes)
- `poc.py validate` PASS: encryption validada, garbage timeout correcto

#### 3. Device info
```
USB 2.0, Bulk IN/OUT, wMaxPacketSize=512
Firmware: turzx_0001_0024
Serial: 290b9dc1b0aa4202
Manufacturer: TURZX, Product: TURZX1.0
Device fields (LE): [0, 0, 0, 832, 124, 708]
Storage: 0 bytes
Busy flag: 0
```

#### 4. poc.py init: todos los comandos OK, pantalla NO muestra nada
```
QUERY           -> cmd=10  st=0xC8 OK
SET_DATETIME(2) -> cmd=51  st=0xC8 OK
DISPLAY_CONFIG  -> cmd=125 st=0xC8 OK
PREPARE         -> cmd=52  st=0xC8 OK
FRAME (black)   -> cmd=102 st=0xC8 OK  <- pantalla no muestra nada
FRAME (pattern) -> cmd=102 st=0xC8 OK  <- pantalla no muestra nada
```

#### 5. Diagnostico profundo revelo problemas
- Enviar muchos comandos seguidos (QUERY + DEV_INFO + INIT_1 + WAKE + BACKLIGHT + BRIGHTNESS + SET_DT + DISPLAY_CONFIG) causa que el device deje de responder desde CMD 125 en adelante
- **CMD 102 solo escribio 3584 bytes de 4743 esperados** (write truncado!)
- Device quedo irrecuperable: USB reset + clear halt no ayudan, necesita replug fisico
- Esto fue DESPUES de que el device ya estaba en mal estado

#### 6. Pipe policies del C# (WinUSB)
- UNICA policy: PIPE_TRANSFER_TIMEOUT = 1000ms en ambos endpoints
- NO hay RAW_IO, SHORT_PACKET_TERMINATE, etc.
- Write: single buffer completo (512 header + N JPEG), timeout 2000ms
- Read: 512 bytes, timeout 2000ms, **ReadFlush() despues de cada read**
- Thread-safe con Monitor.Enter/Exit

#### 7. Formato de respuesta del device (NO encriptado)
```
[0]   cmd_echo (mismo cmd que enviaste)
[1]   status (0xC8 = 200 = OK)
[2-3] magic? (0xD2 0x6D para QUERY, varía)
[4-7] timestamp? (LE, varía)
[8+]  datos (string para QUERY, campos LE para DEV_INFO)
```

### Hipotesis pendientes de verificar

1. **Write truncado**: PyUSB puede no estar enviando el JPEG completo
   - En test limpio (poc.py init) no verificamos el return value de write
   - En diag.py trunco a 3584B pero el device ya estaba en mal estado
   - NECESITA: test con device limpio que imprima bytes escritos

2. **Envio en dos partes**: Tal vez header y JPEG deben ser writes separados
   - C# usa single write pero el driver WinUSB puede manejar diferente a libusb
   - NECESITA: probar `write(header)` + `write(jpeg)` por separado

3. **ReadFlush**: C# llama ReadFlush() despues de cada read
   - Nuestro `drain()` se llama ANTES del write, no despues del read
   - Podria importar si hay datos residuales que confunden el siguiente comando

4. **Secuencia faltante**: Tal vez hay un comando POST-imagen que no estamos enviando
   - La app oficial podria enviar algo adicional despues de CMD 102
   - Solo se puede verificar con captura USB

### Archivos modificados esta sesion
- `pyproject.toml` - fix build backend
- `turzx/device.py` - unicode arrows -> ASCII
- `tools/poc.py` - unicode arrows/dashes -> ASCII
- `tools/diag.py` - NUEVO: diagnostico profundo (causo device stuck)
- `tools/diag2.py` - NUEVO: diagnostico limpio (no ejecutado por device stuck)

### ERROR: Device se bloquea con secuencias largas
**Sintoma:** Despues de enviar ~8 comandos seguidos, el device deja de responder a todo.
**Causa:** Posiblemente el device tiene un buffer limitado o entra en modo error.
**Solucion temporal:** Desconectar y reconectar USB fisicamente.
**Nota:** USB reset + clear endpoint halt NO recuperan el device.

### ERROR: USB controller disabled requiere reboot
**Sintoma:** Intentamos resetear el device por software. `pnputil /remove-device` funciono,
pero el device no volvio tras scan porque el firmware estaba colgado. Intentamos deshabilitar
el controlador PCI AMD USB 3.20 (`PCI\VEN_1022&DEV_43FC&SUBSYS_11421B21&REV_01\6&10F1CCD4&0&00600011`).
Windows lo deshabilito pero exige reboot para re-habilitarlo.
**Solucion:** Reboot obligatorio. El controlador quedo pendiente de reinicio.
**Leccion:** Para futuras sesiones, NO enviar secuencias largas de comandos (>5-6) sin pausa.
El `tools/diag.py` es peligroso: enviar QUERY+DEV_INFO+INIT_1+WAKE+BACKLIGHT+BRIGHTNESS+SET_DT+DISPLAY_CONFIG seguidos bloqueo el firmware.

### Scripts de reset USB creados
- `tools/reset_usb.ps1` - Disable/enable device (necesita admin, NO funciona si firmware colgado)
- `tools/reset_usb_hard.ps1` - Remove device + reset root hub (hub no se puede deshabilitar)
- `tools/reset_usb_controller.ps1` - Disable/enable PCI controller (funciona pero requiere reboot)

### Proximos pasos (prioridad para siguiente sesion, POST-REBOOT)
1. **Verificar device vuelve OK**: `python tools/poc.py validate`
2. **Ejecutar `tools/diag2.py`** - verificar bytes escritos EXACTOS en CMD 102 con device limpio
3. Probar envio split (header + JPEG como writes separados)
4. Agregar drain/flush DESPUES del read, como hace el C#
5. Si nada funciona: **captura USB es imprescindible** para ver que hace la app oficial

---

## Errores resueltos (historico)

### ERROR: Encryption / Basura → READ TIMEOUT
**Síntoma:** Device no responde (timeout) a ciertos paquetes.
**Causa:** Paquete no cifrado correctamente, key incorrecta, o trailer 0xA1/0x1A faltantes.
**Solución:** DES-CBC con key=IV=`b"slv3tuzx"`, PKCS7 padding 500→504B, frame 512B con `[510]=0xA1 [511]=0x1A`.
**Nota crítica:** Status 200 (0xC8) = "paquete desencriptado OK", NO = "comando ejecutado correctamente".

### ERROR: libusb DLL path hardcodeado a Windows
**Síntoma:** `ImportError` o `USBError` en Linux al intentar comunicarse con el device.
**Causa:** `turzx_lib.py` buscaba la DLL en `.venv/Lib/site-packages/libusb/_platform/windows/`.
**Solución:** En Linux, libusb es librería del sistema. `usb.backend.libusb1.get_backend()` sin argumentos funciona si `libusb` está instalado (`pacman -S libusb`).

### ERROR: Device no encontrado / "Device in use"
**Síntoma:** `usb.core.find()` retorna None.
**Causa:** App oficial TURZX corriendo (toma el device), o falta de permisos udev en Linux.
**Solución Windows:** Cerrar app TURZX antes de ejecutar scripts.
**Solución Linux:** Regla udev: `SUBSYSTEM=="usb", ATTR{idVendor}=="1cbe", ATTR{idProduct}=="0028", MODE="0666"` en `/etc/udev/rules.d/99-turzx.rules`.

---

## Conocimiento del protocolo (resumen ejecutivo)

```
Device: VID=0x1CBE, PID=0x0028, firmware "turzx_0001_0024"
Resolución: 480×480 px, JPEG quality 95

Paquete comando (512B):
  [0-503]  DES-CBC encrypt(500B plaintext, key=IV="slv3tuzx", PKCS7)
  [504-509] 0x00
  [510]    0xA1
  [511]    0x1A

Header plaintext 500B:
  [0]    cmd_id
  [1]    0x00
  [2]    0x1A (magic)
  [3]    0x6D (magic)
  [4-7]  timestamp LE uint32 (ms desde ayer medianoche UTC)
  [8+]   datos del comando

Paquete imagen (512 + N bytes):
  Header 512B (CMD=101 SEND_JPEG, data en [8-11] BE = jpeg_len) + JPEG raw
  NOTA: CMD 102 (SEND_FRAME) es aceptado pero NO renderiza en este modelo.

Secuencia de trabajo VALIDADA:
  CMD 51 SET_DATETIME(mode=2)
  → CMD 52 PREPARE → CMD 101 SEND_JPEG → (repeat PREPARE + CMD 101)
  → CMD 51 SET_DATETIME(mode=0) → CMD 123 COMMIT

Rotacion: El panel esta montado 180 grados invertido.
  Se rota la imagen en software (PIL img.rotate(180)) antes de JPEG encode.
```

---

## Notas de arquitectura

### Clases de device en el C# (RESUELTO 2026-04-02)
El C# tiene 4 clases: `_220E` (WinUSB), `_22C1` (WCH), `_2DF1` (207LCD serial), `ⴾ` (HID).
Routing en `Monitor.cs:16874`. **Nuestro device es `_220E` (USB bulk).** `_2DF1` DESCARTADA (usa serial).

### ¿Por qué Arch Linux es mejor para este proyecto?
1. `usbmon` kernel module: captura USB nativa sin instalar nada extra
2. `libusb` sistema: sin DLLs, sin Zadig, sin reemplazar drivers
3. `wireshark` con filtro USB: análisis inmediato del tráfico
4. Sin WinUSB/libusb-win32 ambigüedad en los pipe policies

---

## Sesion 2026-04-02 (tarde) — PANTALLA FUNCIONANDO

### Contexto
- Device accesible en Windows tras reboot
- Todas las hipotesis de la sesion anterior pendientes de verificar
- `poc.py validate` PASS: encriptacion OK, garbage timeout OK

### DESCUBRIMIENTO CLAVE: CMD 101 vs CMD 102

**CMD 101 (`SEND_JPEG`) renderiza imagenes en pantalla.**
**CMD 102 (`SEND_FRAME`) es aceptado (status 0xC8) pero NO renderiza.**

Esto explica por que durante semanas el device aceptaba todo pero no mostraba nada:
estabamos usando CMD 102 (documentado en el C# como el comando de video frame).
Para este modelo de 2.8" se necesita CMD 101 (static JPEG).

### Hipotesis descartadas en esta sesion

1. **Write truncado**: DESCARTADO. Write completo (4743/4743, 38830/38830 etc.)
2. **Split write necesario**: DESCARTADO. Single write funciona correctamente.
3. **ReadFlush timing**: Cambiado drain() de antes-del-write a despues-del-read (como C#),
   pero esto por si solo no era el problema.
4. **Endpoint Interrupt vs Bulk**: DESCARTADO. Endpoints son Bulk (tipo 2).
   C# fuerza `EndpointType.Interrupt` pero no cambia el tipo real de transferencia.
5. **DISPLAY_CONFIG necesario**: No se requiere para renderizar.
6. **Secuencia larga de init**: DESCARTADO. Init minimo (SET_DATETIME) es suficiente.

### Hallazgo: Panel rotado 180 grados

Panel fisico montado 180 grados invertido respecto al origen JPEG.
Se corrige con `PIL Image.rotate(180)` antes de JPEG encode.
Integrado en `images.py:to_jpeg(rotate=180)`.

`CMD 125 SET_DISPLAY_CONFIG` con `rotation=2` fue aceptado (0xC8) pero sin efecto visible.

### Secuencia de trabajo VALIDADA

```
1. SET_DATETIME(mode=2)                  # Inicia sesion
2. PREPARE                               # Prepara buffer
3. SEND_JPEG (CMD 101, 512B hdr + JPEG)  # Imagen aparece en pantalla
4. (repetir 2-3 para mas frames)
5. SET_DATETIME(mode=0)                  # Finaliza
6. COMMIT (CMD 123)                      # Cierra sesion
```

### Tests ejecutados y resultados

| Test | Descripcion | Resultado |
|------|------------|-----------|
| diag5.py d | Endpoint descriptors | EP IN/OUT = BULK, maxPacket=512 |
| diag5.py a | CMD 102 rojo | Write OK, pantalla NO cambia |
| diag5.py b | Split write CMD 102 | Write OK, pantalla NO cambia |
| diag5.py c | CMD 101 azul | **Pantalla muestra AZUL** |
| inline | CMD 101 rojo | **Pantalla muestra ROJO** |
| inline | CMD 101 test pattern | **Texto visible, rotado 180** |
| inline | rotate(180) + CMD 101 | **Texto correcto** |
| API full | init + prepare + send_frame | **Funciona** |

### Cambios en el codigo

**`turzx/device.py`:**
- `transact()`: drain() movido de antes-del-write a despues-del-read (match C# ReadFlush)
- `send_frame()`: ahora usa CMD 101 (`SEND_JPEG`) en lugar de CMD 102
- `send_frame_102()`: nuevo metodo para CMD 102 (legacy, no renderiza en 2.8")
- `init_sequence()`: simplificado a solo SET_DATETIME(2)

**`turzx/images.py`:**
- `to_jpeg()`: nuevo parametro `rotate=180` por defecto

**`tools/diag5.py`:** NUEVO script de diagnostico con tests A-H individuales

### Proximos pasos sugeridos

1. Probar con imagenes reales (fotos, wallpapers) para verificar calidad
2. Medir latencia de envio de frames (para streaming de system monitor)
3. Implementar streaming continuo (loop de PREPARE+SEND_JPEG con metricas)
4. Probar en Linux/Arch ahora que el protocolo esta validado
5. Investigar CMD 102 en modelos mas grandes (21") — puede ser para video
6. Backlight control — validar CMD 13/14 para brillo
7. Standby/Wake — CMD 11/12 para ahorro de energia

### Leccion aprendida

Status 0xC8 (200) del device NO significa "comando ejecutado visible".
Solo significa "paquete desencriptado y comando reconocido".
CMD 102 retorna 0xC8 pero no renderiza. **Siempre verificar efecto visual, no solo status.**

---

## Sesion 2026-04-02 (noche) — Reestructuracion: de PoC a App Final

### Contexto
- Pantalla funcionando perfectamente (verificado con test_text.py: texto renderizado OK)
- Protocolo 100% validado, no quedan hipotesis pendientes
- Decision: pasar de PoC a aplicacion final con daemon + tray + sensores

### Limpieza realizada

**Eliminado:**
- `tools/` completo: poc.py, diag.py, diag2-5.py, capture_analysis.py, test_text.py, reset_usb*.ps1
- `legacy/` completo: C# decompilado, turing-smart-screen-python, venvs, PoCs antiguos

**Justificacion:** Todo el conocimiento extraido de legacy esta documentado en este DEVLOG
y codificado en `turzx/protocol.py` y `turzx/device.py`. Los scripts de tools eran
diagnosticos de un solo uso, algunos peligrosos (diag.py bloqueaba el device).

### Nueva estructura del proyecto

```
TURZX/
├── DEVLOG.md                  # Bucle de mejora constante
├── pyproject.toml             # Build config, dependencias, entry points
├── .gitignore
├── turzx/
│   ├── __init__.py            # Package + re-exports
│   ├── __main__.py            # python -m turzx
│   ├── protocol.py            # DES-CBC, paquetes, constantes (puro, sin I/O)
│   ├── device.py              # USB I/O, comandos alto nivel
│   ├── images.py              # Helpers PIL (to_jpeg, solid, test_pattern)
│   ├── config.py              # Layout dataclasses + ConfigManager (JSON)
│   ├── renderer.py            # Layout + sensors → imagen 480x480
│   ├── daemon.py              # Daemon principal, render thread, entry point
│   ├── tray.py                # QSystemTrayIcon + menu contextual
│   ├── sensors/
│   │   ├── __init__.py
│   │   ├── base.py            # SensorReading, SensorBackend, SensorManager
│   │   ├── cpu.py             # CPU usage, freq, temp (psutil)
│   │   ├── gpu.py             # GPU usage, VRAM, temp (pynvml, opcional)
│   │   ├── memory.py          # RAM usage (psutil)
│   │   ├── disk.py            # Disk usage (psutil)
│   │   ├── network.py         # Network throughput (psutil)
│   │   └── system.py          # Battery, uptime (psutil)
│   └── ui/
│       ├── __init__.py
│       ├── main_window.py     # Ventana Settings con preview live
│       ├── editor.py          # [Phase 2] Editor drag-and-drop
│       └── preview.py         # [Phase 2] Preview widget embebido
├── configs/                   # Development defaults
└── assets/                    # Iconos, recursos
```

### Decisiones de arquitectura

1. **PySide6 (Qt)**: Framework unico para tray + config window + editor visual futuro.
   QGraphicsScene sera ideal para el editor drag-and-drop de Phase 2.

2. **psutil**: Sensores cross-platform (CPU, RAM, disk, network, battery).
   GPU via pynvml (NVIDIA) como dependencia opcional.

3. **Layouts como JSON**: Cada layout define background + elementos posicionados (x,y,z)
   con tipo (text/sensor/image), fuente, color, formato. Almacenados en
   `~/.config/turzx/layouts/` (Linux) o `%APPDATA%/turzx/layouts/` (Windows).

4. **Daemon con QThread**: Render loop en thread separado, Qt event loop en main thread.
   Comunicacion via signals/slots. Device reconnect automatico si falla.

5. **Separacion de responsabilidades**:
   - `protocol.py` — paquetes, crypto (sin I/O)
   - `device.py` — USB write/read
   - `sensors/` — lectura de sensores del sistema
   - `config.py` — persistencia de layouts
   - `renderer.py` — composicion visual
   - `daemon.py` — orquestacion
   - `tray.py` — interaccion con usuario
   - `ui/` — ventanas de configuracion

### Leccion: Limpiar antes de escalar

El proyecto acumulo 11 scripts de test, una carpeta legacy de >100 archivos, y multiples
venvs. Todo ese ruido dificultaba entender el estado real. Limpiar ANTES de empezar
la nueva fase fue la decision correcta: ahora cada archivo tiene un proposito claro.
