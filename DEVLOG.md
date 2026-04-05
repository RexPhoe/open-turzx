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
| Rotacion pantalla | ✅ Configurable | Layout.rotation (0/90/180/270), default 180 |
| App daemon + tray | ✅ Phase 1 | PySide6 tray, sensores psutil, render loop |
| Visual editor | ✅ Phase 2 | Drag-and-drop, props panel, fondos, rotacion config |
| Dynamic profiles | ✅ Phase 3 | Tres modos: static, rotative, reactive |
| BOB (avatar virtual) | ⏳ Phase 4 | Personaje animado con IA — experimental |
| Compatibilidad Linux | 🔧 En progreso | libusb + psutil + PySide6 = cross-platform |
| Device se bloquea | ⚠️ Confirmado | Secuencias largas (>5-6 cmds) bloquean firmware |

**FASE ACTUAL: Phase 4 — BOB (pendiente)**

**Protocolo resuelto (2026-04-02):**
- CMD 101 (`SEND_JPEG`) muestra imagen; CMD 102 es aceptado pero NO renderiza
- Panel montado 180 invertido — se corrige con `img.rotate(180)` en software
- ReadFlush debe ir DESPUES del read (como C#), no antes del write
- Secuencia: `SET_DATETIME(2) -> PREPARE -> CMD 101 -> ... -> SET_DATETIME(0) -> COMMIT`

## PLAN DE FASES

### Phase 1 — Daemon + Static Monitor (COMPLETADO)
Daemon con tray icon que muestra sensores del sistema en la pantalla.
- [x] Driver USB validado (protocol.py, device.py, images.py)
- [x] Estructura del proyecto limpia
- [x] Sistema de sensores cross-platform (psutil + pynvml)
- [x] Renderer: layout JSON -> imagen 480x480
- [x] ConfigManager: load/save layouts
- [x] Daemon con QThread render loop
- [x] Tray icon con menu (Start/Pause, Settings, Quit)
- [x] Ventana Settings con preview live y lista de sensores

### Phase 2 — Visual Editor (COMPLETADO)
Editor drag-and-drop para disenar layouts.
- [x] QGraphicsScene canvas 480x480
- [x] Arrastrar elementos (texto, sensor, imagen)
- [x] Mover X/Y libremente
- [x] Control Z-order (delante/detras)
- [x] Editar propiedades (font, color, formato)
- [x] Selector de fondo (color solido, imagen, video en bucle)
- [x] Guardar/cargar configuraciones
- [x] Frecuencia de actualizacion por layout
- [x] Rotacion configurable (0/90/180/270) — editor siempre sin rotar
- [x] Preview live sin rotacion (usa render_image directamente)
- [x] CPU freq fallback via winreg en Windows
- [x] Sensor cpu.freq_mhz adicional

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

---

## Sesion 2026-04-03 — Phase 2 Completo: Editor Visual + Fondos + Rotacion

### Contexto
- Phase 1 funcional (daemon + tray + sensores + renderer)
- Preview mostraba contenido rotado 180° (usaba JPEG del device, no imagen sin rotar)
- No habia editor visual — solo layout JSON manual
- CPU frequency no aparecia en algunos sistemas Windows

### Implementaciones realizadas

#### 1. Editor drag-and-drop (`ui/editor.py`)
- `ElementItem(QGraphicsItem)`: elementos arrastrables con soporte para text/sensor/image
- Posicionamiento anchor-aware (lt, mt, rt, lm, mm, rm, lb, mb, rb)
- `itemChange()` actualiza x,y del LayoutElement en tiempo real al arrastrar
- `EditorScene(QGraphicsScene)`: canvas 480x480, signals element_selected/layout_modified
- `LayoutCanvas(QGraphicsView)`: fit-to-view, re-emite element_selected en mouseRelease

#### 2. Panel de propiedades (`ui/main_window.py` — PropertiesPanel)
- Campos tipo-especificos: text muestra editor de texto, sensor muestra combo de sensor_id + label + format, image muestra file browser
- Controles de estilo: font_size, color (ColorButton con QColorDialog), anchor
- Posicion: spinboxes X/Y/Z
- Acciones: Delete, Duplicate
- Background: radio Solid/Image/Video + color picker + file path browser
- Flag `_updating` para evitar loops de signals

#### 3. ConfigWindow — ventana principal 3 paneles
- Left: Layout selector + Save/Save As + FPS slider + **rotation combo** + add element buttons + sensor list (double-click to add)
- Center: LayoutCanvas + PreviewWidget (live preview cada 2s)
- Right: PropertiesPanel
- QSplitter ajustable

#### 4. Preview corregido (`ui/preview.py`)
- `update_from_pil()`: recibe PIL Image sin rotacion — usado por live preview timer
- Editor y preview siempre muestran contenido sin rotar (orientacion correcta para edicion)

#### 5. Fondos imagen y video
- Renderer soporta backgrounds: solid (color), image (Pillow), video (cv2 frame extraction)
- Video: cv2.VideoCapture con loop automatico, `cleanup()` para liberar recursos
- Dependencia cv2 opcional: `pip install turzx[video]`

#### 6. Rotacion configurable
- `Layout.rotation: int` (0, 90, 180, 270) — default 180° (panel fisico montado invertido)
- `renderer.render()` pasa `layout.rotation` a `to_jpeg(rotate=...)`
- `render_image()` siempre devuelve imagen sin rotar (para editor/preview)
- UI: combo "Device Rotation" en left toolbox con opciones 0°/90°/180°/270°
- Se persiste en JSON layout y se carga al abrir editor

#### 7. CPU frequency fix (`sensors/cpu.py`)
- `_cpu_freq_mhz()`: intenta `psutil.cpu_freq()` primero
- Fallback Windows: lee `HKLM\HARDWARE\DESCRIPTION\System\CentralProcessor\0\~MHz` via `winreg`
- Nuevo sensor `cpu.freq_mhz` ademas del existente `cpu.freq_ghz`

### Archivos modificados
- `config.py`: +Layout.rotation, +LayoutElement.w/.h, +to_dict/from_dict rotation
- `renderer.py`: +render_image(), render() usa layout.rotation, +video background, +cleanup()
- `ui/editor.py`: implementacion completa (era placeholder)
- `ui/main_window.py`: implementacion completa con 3-panel layout + rotation combo
- `ui/preview.py`: implementacion completa con update_from_pil
- `sensors/cpu.py`: +_cpu_freq_mhz() con winreg fallback, +cpu.freq_mhz sensor
- `daemon.py`: +renderer.cleanup() en shutdown()
- `pyproject.toml`: +optional video dependency

### Lecciones aprendidas
1. **Separar render_image() de render()**: La imagen sin rotar es necesaria para editor/preview, la rotada solo para el device. Esta separacion elimina el bug del preview rotado.
2. **psutil.cpu_freq() no es fiable en Windows**: Puede retornar None. El registro de Windows siempre tiene ~MHz disponible.
3. **Flag _updating en panels bidireccionales**: Cuando propiedades y scene se actualizan mutuamente, un flag booleano previene recursion infinita de signals.

---

## Sesion 2026-04-04 — CPU Freq Real-time + Foreground App + Preview Circular

### Contexto
- Phase 2 funcional, pero CPU freq mostraba solo valor base (no turbo)
- Necesidad de detectar aplicacion en primer plano (preparacion Phase 3)
- Preview cuadrado no representaba la pantalla circular real
- Tray ya tenia opcion Quit (verificado en `tray.py:62-64`)

### Implementaciones realizadas

#### 1. CPU frequency real-time con turbo (`sensors/cpu.py`)
- `_cpu_freq_mhz_realtime()` reemplaza `_cpu_freq_mhz()`
- Prioridad 1: `psutil.cpu_freq().current` si devuelve valor dinamico (current != min)
- Prioridad 2 (Windows): WMI `Win32_PerfFormattedData_Counters_ProcessorInformation` que da `PercentofMaximumFrequency` × base_mhz = freq real con turbo
- Prioridad 3: registry `~MHz` como fallback estatico
- Nuevo sensor `cpu.base_mhz` — siempre muestra reloj base para referencia
- `SensorReading.value` ampliado a `float | int | str` para soportar valores textuales

#### 2. Foreground application sensor (`sensors/foreground.py`) — NUEVO
- `app.window_title`: titulo de la ventana activa (truncado a 40 chars)
- `app.process`: nombre del proceso (ej: "firefox.exe", "Code.exe")
- Windows: `ctypes` puro (GetForegroundWindow, GetWindowTextW, QueryFullProcessImageNameW)
- Linux: `xdotool getactivewindow getwindowname`
- Registrado en `SensorManager.register_defaults()`
- Preparacion para Phase 3 (cambio automatico de layout por aplicacion)

#### 3. Preview circular (`ui/preview.py`)
- Ahora es QWidget con paintEvent custom (era QLabel con setPixmap)
- QPainterPath circular como clip mask
- Centra el pixmap escalado dentro del circulo
- Borde ring sutil (60,60,70) para delimitar la pantalla
- Fondo oscuro detras del circulo (#111)
- Simula forma real de la pantalla 2.8" circular

#### 4. Verificacion tray Quit
- La opcion "Quit" ya existia en `tray.py` linea 62-64
- Llama a `daemon.shutdown()` → `QApplication.quit()` — funciona correctamente

### Archivos modificados
- `sensors/cpu.py`: _cpu_freq_mhz_realtime() con WMI turbo, +cpu.base_mhz
- `sensors/foreground.py`: NUEVO — deteccion ventana/proceso activo
- `sensors/base.py`: +foreground en register_defaults, value type widened
- `ui/preview.py`: reescrito como QWidget con circular clip mask

### Lecciones aprendidas
1. **winreg ~MHz es estatico**: Solo da base clock, no refleja turbo/boost. WMI PercentofMaximumFrequency es la forma correcta de obtener freq real en Windows.
2. **ctypes vs pywin32**: ctypes es stdlib, no requiere dependencia extra. Para GetForegroundWindow + GetWindowText + OpenProcess + QueryFullProcessImageName es suficiente.
3. **QWidget.paintEvent > QLabel.setPixmap** para mascaras: QPainterPath.addEllipse + setClipPath permite cualquier forma de recorte.

---

## Sesion 2026-04-04 (tarde) — CPU Freq Turbo Real + Video Background Fix

### Contexto
- CPU freq mostraba siempre 3701 MHz (base) en lugar de frecuencia turbo real (~5000 MHz)
- Video backgrounds no funcionaban: cv2 no instalado + editor usaba QPixmap(path) para video
- CallNtPowerInformation (ntdll) tambien retorna solo base clock, no turbo
- PercentProcessorPerformance via PDH refleja >100% cuando hay turbo boost

### Implementaciones realizadas

#### 1. CPU frequency real-time via PDH (`sensors/cpu.py`)
- **Problema raiz**: `CallNtPowerInformation`, `winreg ~MHz`, y `psutil.cpu_freq()` retornan base clock (3701 MHz), no turbo
- **Solucion**: `_PdhFreqHelper` usa Windows Performance Data Helper (pdh.dll)
  - Lee `\Processor Information(_Total)\% Processor Performance`
  - Este counter da % relativo a base (ej: 133% = turbo activo)
  - Multiplica por base_mhz del registry = frecuencia real
  - Resultado verificado: 4985-5071 MHz en Ryzen 9 7900 (boost spec: 5.4 GHz)
  - Latency: ~0.3ms por lectura, zero deps externas
  - Query PDH se abre una vez en __init__ y se reutiliza
- Eliminada dependencia de `wmi` package (innecesaria)
- Sensores: `cpu.freq_ghz`, `cpu.freq_mhz` (real-time), `cpu.base_mhz` (static)

#### 2. Video background fix (`ui/editor.py` + cv2 setup)
- opencv-python instalado como dependencia
- Editor: `_video_thumbnail()` — extrae primer frame del video como QPixmap via cv2
  - `_apply_background()` ahora tiene path separado para `type=="video"` en lugar de agrupar con image
  - QPixmap no puede cargar .mp4/.avi — necesita cv2 para extraer frame
- Renderer: ya funcionaba correctamente con cv2 (solo faltaba el package)

### Enfoques probados para CPU freq (Windows)

| Metodo | Resultado | Turbo? |
|--------|-----------|--------|
| `psutil.cpu_freq()` | None o base clock | No |
| `winreg ~MHz` | 3701 (base) | No |
| `CallNtPowerInformation(11)` | 3701 (base) | No |
| `Win32_Processor.CurrentClockSpeed` | 3701 (base) | No |
| `Win32_PerfFormatted..PercentofMaximumFrequency` | 100% (no turbo??) | No |
| **PDH `% Processor Performance`** | **133% → 4922 MHz** | **Si** |
| PowerShell Get-CimInstance | 133% pero 900ms latencia | Si pero lento |

### Archivos modificados
- `sensors/cpu.py`: reescrito con _PdhFreqHelper (PDH via ctypes), eliminado WMI
- `ui/editor.py`: +_video_thumbnail(), _apply_background() para video separado de image, +QImage import

### Lecciones aprendidas
1. **PDH es la unica fuente real de turbo freq en Windows**: Todos los demas metodos (winreg, psutil, WMI Win32_Processor, CallNtPowerInformation) retornan base clock. PDH "% Processor Performance" incluye boost/turbo como >100%.
2. **QPixmap no carga video**: Qt no tiene decodificador de video integrado en QPixmap. Para thumbnails de video en el editor hay que usar cv2.VideoCapture → primer frame → QImage.
3. **PDH query reutilizable**: Abrir PdhOpenQuery + PdhAddEnglishCounter una vez en __init__, luego PdhCollectQueryData + PdhGetFormattedCounterValue en cada read() = 0.3ms.

---

## Sesion 2026-04-04 (noche) — Bugfixes: Tray GC, Video Auto-detect, Layout Regen

### Contexto
- Video backgrounds no se reproducian
- Quit no aparecia en el menu contextual del tray
- CPU freq no se veia en la app (aunque funcionaba en tests)

### Diagnostico y root causes

#### 1. Tray Quit/Settings desaparecen (GC)
**Root cause:** `action_settings` y `action_quit` eran variables locales en `_build_menu()`.
PySide6 no siempre mantiene una strong reference desde QMenu a QAction.
Cuando Python hace garbage collection, las acciones desaparecen del menu.
**Fix:** Almacenar como `self._action_settings`, `self._action_quit`, `self._menu`.
Tambien pasamos `menu` como parent de cada QAction.

#### 2. Video backgrounds no funcionaban
**Root cause (multiple):**
- cv2 ya instalado y funcional (verificado en sesion anterior)
- El renderer lee frames correctamente (verificado: pixel test con video azul)
- **Bug real**: El file picker `_pick_bg()` no auto-cambiaba la radio a "Video" al seleccionar .mp4
  - Usuario selecciona video → radio sigue en "Solid" → `_on_bg()` envia type="solid" con path
  - El renderer recibe type="solid" → ignora path → muestra color solido
- **Bug secundario**: cv2 puede fallar con backslashes en Windows path en algunos builds
**Fix:** `_pick_bg()` ahora detecta extension y auto-selecciona radio Image/Video.
Renderer normaliza path con `replace("\\", "/")` antes de pasarlo a cv2.

#### 3. CPU frequency "no aparece"
**Root cause:** El saved `default.json` en `%APPDATA%` no tenia el campo `rotation` (layout viejo).
Pero la frecuencia SI aparecia — verificado end-to-end: 4831-4866 MHz actualizandose.
PDH helper funciona correctamente: init OK, read_mhz devuelve valores turbo.
**Accion:** Regenerado `default.json` con todos los campos actuales (rotation, w, h).
Posible causa: si el usuario tenia un layout custom sin `cpu.freq_ghz`, no se mostraria.

### Archivos modificados
- `tray.py`: QAction almacenados como self._ (prevent GC), +parent en QAction constructor
- `ui/main_window.py`: `_pick_bg()` auto-detect extension → switch radio Image/Video
- `renderer.py`: `_read_video_frame()` normaliza path backslashes para cv2
- `%APPDATA%/turzx/layouts/default.json`: regenerado con rotation=180

### Lecciones aprendidas
1. **PySide6 GC de QAction**: Las QAction creadas como variables locales pueden ser garbage-collected si Python pierde la referencia, incluso si QMenu las tiene como hijos. SIEMPRE almacenar como `self._action_*`.
2. **File picker debe auto-detectar tipo**: Cuando el usuario selecciona un .mp4 y el radio esta en "Solid", el fondo queda como color solido. Auto-switch el radio basado en extension.
3. **Verificar end-to-end antes de asumir bug**: La frecuencia CPU funcionaba perfectamente en tests. El bug era probablemente en el layout del usuario, no en el codigo del sensor.

---

## BUCLE DE MEJORA CONSTANTE — Revision

### Patron de bugs recurrentes
| Tipo | Ejemplo | Prevencion |
|------|---------|------------|
| GC en Qt | QAction, QMenu | Siempre `self._` para widgets que deben persistir |
| Path Windows | Backslashes con cv2 | Normalizar con `.replace("\\", "/")` |
| UI state desync | Radio no cambia con file picker | Auto-switch segun contexto |
| Layout JSON viejo | Campos nuevos no existen | `from_dict` con defaults, regenerar si necesario |
| Dependencia no instalada | cv2 no estaba | Verificar con import en startup |
| API que retorna static | winreg, CallNtPowerInformation | Documentar cual API da datos reales |
| Memoria numpy→QImage | QImage envuelve buffer numpy | `bytes(frame.data)` ANTES de QImage, luego `.copy()` |
| Race condition timers | Timer toca items destruidos | Parar timer ANTES de `scene.clear()` |
| Init ordering | Atributo no existe cuando se lee | Crear dependencias antes de llamar metodos que las usan |

### Reglas derivadas del bucle
1. Todo QAction/QWidget creado en un metodo debe almacenarse como `self._*`
2. File paths siempre normalizados antes de pasar a libs externas (cv2, etc)
3. File dialogs deben auto-configurar el estado de la UI segun el archivo seleccionado
4. Nuevos campos en dataclasses siempre con default → backward-compatible con JSON viejos
5. Verificar sensor pipeline end-to-end antes de buscar bugs en componentes individuales
6. PDH (pdh.dll) es la UNICA fuente real de CPU turbo freq en Windows
7. Layout JSON versionado: `_DEFAULT_LAYOUT_VERSION` en config.py; se regenera si version < actual
8. pynvml importar localmente dentro de read(); FutureWarning por deprecacion del paquete `pynvml`
9. NUNCA pasar numpy `.data` directo a QImage — **siempre** `bytes(frame.data)` primero para crear copia segura
10. Parar timers y cerrar recursos ANTES de destruir items de escena (`.clear()`)
11. En `__init__`, crear atributos/timers que otros metodos usan ANTES de llamar esos metodos
12. Desacoplar FPS de pantalla (24/30/60) de intervalo de sensores (0.2-5.0s) — cachear lecturas y reutilizar entre polls

---

## Sesion 2026-04-04

### Cambios realizados

#### 1. CPU current clock speed — fix definitivo para GUI
**Problema:** El sensor PDH funcionaba en CLI (5270+ MHz) pero no aparecia en la GUI.
**Causa raiz:** El `default.json` guardado era version antigua sin el elemento `cpu.freq_ghz`. ConfigManager solo regenera si el archivo NO existe, asi que el layout viejo persistia.
**Solucion:** Versionado de layouts — `_DEFAULT_LAYOUT_VERSION = 2` en config.py. ConfigManager ahora lee `_version` del JSON y regenera si es menor que la version actual. `Layout.to_dict()` incluye `_version`.

#### 2. GPU metrics — expansion completa (NVIDIA RTX 5080)
**Antes:** Solo 3 sensores basicos (percent, mem_gb, temp).
**Ahora:** 10 sensores GPU completos:
- `gpu.name` — NVIDIA GeForce RTX 5080
- `gpu.percent` — uso GPU %
- `gpu.mem_gb` / `gpu.mem_total_gb` / `gpu.mem_percent` — VRAM
- `gpu.temp` — temperatura
- `gpu.clock_mhz` / `gpu.mem_clock_mhz` — relojes core/memoria
- `gpu.fan` — velocidad ventilador %
- `gpu.power_w` — consumo en W

Cada llamada individual envuelta en try/except para que un sensor que falle no bloquee los demas.
`pynvml` instalado (`pip install pynvml`), ya estaba en optional deps `[gpu]`.

#### 3. Video background auto-play en bucle — REESCRITURA TOTAL
**Problema:** Al seleccionar un video como fondo, solo se mostraba un color solido.
**Diagnostico exhaustivo:**
- cv2 abria los videos ✓, leia frames ✓, codec FFMPEG disponible ✓
- El renderer (PIL) producia imagenes correctas con contenido visual ✓
- Test headless con QGraphicsScene: video se renderizaba correctamente ✓
- Conclusion: NO era problema de codec ni de path, sino de **conversion de memoria numpy→QImage**

**Causa raiz REAL:**
1. `QImage(frame.data, ...)` envuelve la memoria del array numpy SIN copiarla
2. Cuando el frame numpy sale de scope o se reasigna, QImage apunta a memoria liberada
3. Aunque se hacia `.copy()` despues, el timing era fragil — a veces la copia ocurria despues de que numpy liberara la memoria
4. Ademas `load_layout()` llamaba `self.clear()` ANTES de parar el video timer, causando race conditions

**Solucion — reescritura completa del modulo de video:**
- **`_cv2_frame_to_pixmap()`**: Conversion segura BGR→QPixmap — primero `bytes(frame.data)` crea copia del buffer numpy, luego QImage sobre esos bytes, luego `.copy()` para QImage independiente
- **`_VideoBgPlayer`**: Reemplaza `_VideoFrameReader` — clase mas robusta con `is_open` property, logging a stderr, normaliza paths, lee FPS del video para calcular intervalo del timer
- **`EditorScene.load_layout()`**: Ahora detiene video ANTES de `self.clear()` — evita race condition
- **`_apply_background()`**: Logging `[TURZX video]` a stderr para diagnostico
- **`_tick_video()`**: Verifica `is_open` y detiene timer si player cerrado
- **`ConfigWindow._adjust_preview_timer()`**: 100ms para video bg, 2000ms para static

#### 4. Default layout actualizado (version 2)
- Incluye GPU clock, VRAM, power
- Incluye foreground app process
- Mejor distribucion vertical para pantalla circular
- Se regenera automaticamente al detectar version < 2

### Estado de sensores verificado (26 total)
```
cpu.percent: 9.1%    cpu.freq_ghz: 5.27 GHz   cpu.base_mhz: 3701 MHz
cpu.cores: 24        mem.percent: 14.3%         mem.used_gb: 9.0 GB
disk.percent: 33.2%  disk.used_gb: 618.0 GB
net.down_mbps: 0.0   net.up_mbps: 0.0 MB/s
gpu.name: RTX 5080   gpu.percent: 0%            gpu.temp: 34C
gpu.clock_mhz: 2595  gpu.mem_clock_mhz: 15479   gpu.fan: 30%
gpu.power_w: 56.1 W  gpu.mem_gb: 1.2/15.9 GB
app.process: Code.exe  app.window_title: ...
sys.uptime_h: 0h 58m
```

### Lecciones aprendidas
1. **Layouts viejos guardan estado viejo**: Si el default.json ya existe, el ConfigManager no lo regenera. Solucion: versionado de layouts y regeneracion automatica.
2. **Video en canvas Qt necesita timer propio**: QGraphicsPixmapItem no se anima solo — necesita un timer que lea frames y actualice el pixmap periodicamente.
3. **Cada sensor GPU debe tener su propio try/except**: Algunas APIs de NVML fallan en ciertos drivers/GPUs. Envolver individualmente evita que un sensor roto bloquee todos.
4. **QImage NO copia memoria numpy**: `QImage(frame.data, ...)` solo envuelve el buffer — si numpy lo libera, QImage apunta a basura. SIEMPRE hacer `bytes(frame.data)` antes.
5. **Diagnosticar capa por capa**: El video no se veia pero el problema no era codec ni cv2 ni renderer — era la conversion QImage. Testar cada capa aislada (cv2→PIL, cv2→QPixmap, QPixmap→Scene) identifico el bug.
6. **Race condition con timers Qt y `scene.clear()`**: Si un timer actualiza un QGraphicsItem que fue destruido por `clear()`, crashea. Siempre parar timers antes de clear.
7. **Orden de init importa**: `_load_layout()` → `_adjust_preview_timer()` necesita `self._timer`. Crear el timer ANTES de llamar a `_load_layout()`.

#### 5. Dual-cadence architecture — sensor rate vs screen FPS
**Problema:** Antes, un solo valor de "refresh rate" controlaba tanto los FPS de pantalla como la frecuencia de lectura de sensores. Para video backgrounds fluidos se necesitan 24-60 FPS de renderizado, pero leer todos los sensores a 60 Hz es innecesario y costoso.

**Solucion — dos valores independientes:**
- **`screen_fps`** (24/30/60): frecuencia de renderizado de frames y envio al device. Controla fluidez del video background.
- **`refresh_rate`** (0.2–5.0 s): intervalo de actualizacion de datos de sensores. Los valores se cachean y se reutilizan entre lecturas.

**Cambios en config.py:**
- Campo `Layout.screen_fps: int = 24` (nuevo)
- `_DEFAULT_LAYOUT_VERSION` → 3
- `to_dict()` y `from_dict()` incluyen `screen_fps`

**Cambios en daemon.py — `RenderThread` reescrito:**
- Loop principal corre a `screen_fps` (ms = 1000/fps)
- `_cached_values` almacena ultima lectura de sensores
- `_last_sensor_read` timestamp para comparar contra `refresh_rate`
- Solo llama `sensors.read_all()` cuando ha pasado el intervalo de sensores
- Prime cache al inicio del thread para evitar primer frame sin datos

**Cambios en main_window.py — UI dual:**
- "Screen FPS" combo (24/30/60) reemplaza el control unico de FPS
- "Sensor Update" slider (0.2–5.0 s) controla `layout.refresh_rate`
- `_on_fps()` handler: actualiza `layout.screen_fps` + ajusta preview timer
- `_on_rate()` handler: actualiza `layout.refresh_rate` con label en "s"
- `_adjust_preview_timer()`: para video backgrounds, usa `screen_fps` del layout para el intervalo del preview timer
- `_load_layout()` carga ambos valores con blockSignals

**Resultado:** Video a 30 FPS con sensores actualizando cada 1s = fluidez visual sin overhead.

---

## Sesion 2026-04-04 (continuacion) — Video Loop Fix + Save System + Two-Layer Architecture + Unit Conversion + i18n

### Contexto
- Video backgrounds con ciertos codecs (H.265, VP9) fallaban al hacer loop
- Sistema de guardado no persistia correctamente entre reinicios
- Video sincronizado con sensor update en vez de correr independiente
- FPS configurable era innecesario — simplificado a 60 fijo
- Properties panel necesitaba font selection, gradient fill, stroke
- Necesidad de conversion de unidades por sensor y preparacion i18n

### Implementaciones realizadas

#### 1. Video loop fix — reopen on seek failure
**Problema:** `cv2.CAP_PROP_POS_FRAMES = 0` falla en ciertos codecs (H.265, VP9, ciertos MP4).
Despues de varios loops, `read()` devuelve False y el video se congela.

**Solucion:** Tres intentos progresivos:
1. Seek a frame 0 (`set(CAP_PROP_POS_FRAMES, 0)`) + read
2. Si falla: `release()` + reopen `VideoCapture(path)` + read
3. Si sigue fallando: devolver ultimo frame valido cacheado

Aplicado en:
- `renderer.py:_read_video_frame()` (device pipeline)
- `ui/editor.py:_VideoBgPlayer.next_frame_pixmap()` (editor preview)

#### 2. Save system overhaul — 8 bugs corregidos
**Problemas encontrados (analisis exhaustivo):**
1. `_active_name` hardcoded a "default" sin persistencia
2. Combo box no sincronizado con layout activo al abrir
3. `layout_modified` signal sin conectar a auto-save
4. `_auto_save` usaba texto del combo (podia ser nombre corrupto)
5. `_save_layout_as` no actualizaba layout activo
6. Ediciones de elemento no triggerean save
7. Drag positions no triggerean save
8. No habia `state.json` para recordar layout activo entre sesiones

**Solucion — single source of truth:**
- `state.json` en config_dir persiste `active_layout` name
- `config.active_name` property como unica fuente
- `set_active()` persiste a `state.json`
- `layout_modified` signal → `_auto_save()`
- `_auto_save()` usa `config.active_name`
- `mouseReleaseEvent` en LayoutCanvas emite `layout_modified`
- `_on_element_changed` refresh visual + auto-save

#### 3. Two-layer render architecture
**Problema:** Video playback ligado a frecuencia de lectura de sensores.

**Solucion — overlay + background separados:**
- **Overlay (RGBA):** texto, sensores, imagenes. Se reconstruye solo en sensor_rate (1s).
- **Background:** frame de video / imagen / color. Avanza a 60 FPS.
- `render_frame()` = next bg frame + paste cached overlay → JPEG. ~5ms/frame.
- `update_overlay()` = rebuild completo de elementos. ~50ms pero infrecuente.
- Video cacheado a 24fps (VIDEO_FPS_CAP) — entre advances devuelve frame cacheado.

#### 4. FPS simplificado a 60 fijo
- Eliminado combo de FPS (24/30/60)
- `screen_fps` hardcoded a 60 en `Layout.from_dict()` (ignora valor guardado)
- `_DEFAULT_LAYOUT_VERSION` → 4

#### 5. Text styling: gradient + stroke + font family
- `LayoutElement`: +font_family, +gradient/gradient_color/gradient_angle, +stroke_width/stroke_color
- Renderer: gradient via mask—textbbox → gradient image → text mask → composite
- Renderer: stroke via PIL `stroke_width/stroke_fill` params
- Font family: intentar family+.ttf/.otf, fallback a lista de candidatos
- PropertiesPanel: font combo (editable), gradient checkbox + end color + angle, stroke checkbox + width + color

#### 6. Sensor unit conversion system
**Concepto:** Cada sensor tiene una unidad nativa, pero el usuario puede elegir la unidad de visualizacion.
- `display_unit` field en `LayoutElement`
- Mapa de conversiones definido en `sensors/units.py`
- Se aplica la conversion en el renderer al formatear sensor text
- UI: combo de unidades disponibles por tipo de sensor en PropertiesPanel

#### 7. i18n preparation
- `turzx/i18n.py`: funcion `_()` que devuelve el string original (noop initial)
- Todas las etiquetas UI centralizadas — preparado para futuro .po/.json
- Las funciones de traduccion se importan por archivo, no decoran nada

### Auditoria de compatibilidad Linux

**Estado: Sustancialmente compatible.** Todo el codigo Windows-especifico tiene guards `sys.platform`.

| Componente | Estado Linux | Accion necesaria |
|---|---|---|
| USB device (device.py) | ✅ Funciona | libusb sistema + udev rule |
| Config dir (config.py) | ✅ XDG compliant | Ninguna |
| CPU sensors (cpu.py) | ⚠️ Parcial | PDH solo Windows; psutil fallback funciona pero no da turbo freq |
| CPU temp (cpu.py) | ✅ Funciona | `sensors_temperatures()` con coretemp/k10temp |
| GPU sensors (gpu.py) | ✅ pynvml cross-platform | Ninguna (NVIDIA driver necesario) |
| Foreground app (foreground.py) | ⚠️ Parcial | xdotool solo X11, no Wayland; app.process solo Windows |
| Disk (disk.py) | ✅ Guard "/" vs "C:\\" | Ninguna |
| Font list (main_window.py) | ⚠️ Cosmetic | Lista de fonts es Windows-only; en Linux no resuelven |
| System tray (tray.py) | ⚠️ DE-depende | GNOME necesita extension AppIndicator |
| Renderer fonts | ✅ Fallback chain | DejaVuSans/FreeSans/Liberation en la lista |
| Path handling | ✅ Normalizado | `replace("\\", "/")` donde necesario |

**Acciones futuras para Linux parity:**
1. CPU freq real-time: leer `/sys/devices/system/cpu/cpu*/cpufreq/scaling_cur_freq`
2. Foreground Wayland: `swaymsg`/`hyprctl` o D-Bus
3. Foreground process Linux: parse `/proc` basado en PID
4. Font list: usar `fc-list` para detectar fuentes disponibles en runtime
5. Tray GNOME: documentar necesidad de AppIndicator extension

### Actualizacion del bucle de mejora

| Tipo | Ejemplo | Prevencion |
|------|---------|------------|
| Cache corruption | Callers dibujaban sobre bg cacheado | Siempre `.copy()` antes de dibujar sobre cache |
| Dual source of truth | Combo text vs config name | Una unica fuente: `config.active_name` |
| Video codec seek | CAP_PROP_POS_FRAMES falla en H.265/VP9 | Reopen VideoCapture como fallback |
| Over-coupling | Video rate = sensor rate | Separar en dos pipelines independientes |
| State loss | active layout no persistido | `state.json` con write inmediato en `set_active()` |

### Reglas nuevas del bucle
13. Video loop: seek falla en ciertos codecs → reopen VideoCapture como fallback
14. Persistencia de estado: cualquier preferencia del usuario → escribir a disco inmediatamente
15. Single source of truth: never derive critical state from UI widgets — use the data model
16. Two pipelines: visual refresh (60fps) y data refresh (1s) deben ser independientes
17. Unit conversion: el sensor emite en unidad nativa, la conversion es responsabilidad del renderer

---

## Sesion 2026-04-04 (cont.) — Bugfixes, FPS Sensor, Element Selector, Modes Planning

### Contexto
- Font selector no aplicaba correctamente en el renderer (PIL no resuelve family names)
- Arc bars dificiles de colocar (anchor en esquina vs top-left)
- Barras lineales sin opcion de orientacion
- FPS counter mostraba tasa de poll de sensores, no FPS real de juego
- Auto-save impedia revertir cambios y modificaba templates
- Reloj no avanzaba cada segundo (cacheado en overlay)
- Color picker heredaba color del boton padre

### Implementaciones realizadas

#### 1. Font resolution via OS registry (`renderer.py`)
**Problema:** `ImageFont.truetype("Segoe UI", 16)` falla silenciosamente en PIL — no resuelve nombres de familia de fuente.
**Solucion:** `_find_font_file(family)` consulta:
- Windows: `HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts` via `winreg`
- Linux: `fc-match --format=%{file} <family>`

Resuelve "Segoe UI" → `C:\Windows\Fonts\segoeui.ttf`, que PIL si puede abrir.
Cache de resultados en `_font_path_cache`.

#### 2. Arc bar alignment fix (`ui/editor.py`)
**Problema:** Editor usaba bounds centrados (`QRectF(-w/2, -h/2, w, h)`) mientras renderer usaba top-left (`el.x, el.y`).
**Solucion:** Editor cambiado a `QRectF(0, 0, w, h)` — consistente con renderer.

#### 3. Arc bar rotation fix (`ui/editor.py`)
**Problema:** Arc bars se veian rotados 180 grados en el canvas del editor respecto al renderer y la pantalla real.
**Causa:** Qt `drawArc` usa angulos counter-clockwise, PIL `draw.arc` usa clockwise. Ambos desde 3 o'clock.
**Solucion:** Negar los angulos en el editor: `start = -el.bar_start_angle * 16`, `sweep = -el.bar_sweep_angle * 16`.

#### 4. Bar direction support — 4 direcciones
**Config:** `bar_direction: str = "right"` en `LayoutElement` (right/left/down/up)
**Renderer:** Calculo de fill area y angulo de gradiente por direccion.
**Editor:** Preview de 50% fill adaptado a cada direccion.
**UI:** Combo "Direction" visible solo para tipo `bar` (no arc_bar).

#### 5. Manual save system — eliminacion de auto-save
**Problema:** Cada cambio guardaba automaticamente, impidiendo revertir y modificando templates.
**Solucion:**
- Eliminado `_auto_save()` completamente
- Flag `_dirty` en `ConfigWindow` — se activa con cualquier cambio
- Titulo de ventana: `"* TURZX - name"` cuando hay cambios sin guardar
- `QMessageBox` pregunta antes de cambiar layout o cerrar con cambios pendientes
- Solo se guarda al pulsar Save o confirmar en el dialogo

#### 6. Clock/date real-time rendering (`renderer.py`)
**Problema:** `sys.clock` y `sys.date` estaban cacheados en overlay, actualizandose solo cada `refresh_rate` (1-5s). Los segundos no avanzaban fluidamente.
**Solucion:**
- `_REALTIME_SENSORS = frozenset(("sys.clock", "sys.date"))` — conjunto de IDs a excluir del overlay
- `update_overlay()` salta estos sensores
- `render_frame()` dibuja clock/date directamente en cada frame con `datetime.now()`
- `_realtime_elements` lista cacheada en `update_overlay()` para evitar filtrar en cada frame

#### 7. Color picker parent fix (`ui/main_window.py`)
**Problema:** `QColorDialog.getColor(..., self)` donde `self` es `ColorButton` con stylesheet `background:rgb(...)` causaba que el dialogo heredara el color de fondo.
**Solucion:** `QColorDialog.getColor(..., self.window())` — usa la ventana principal como parent.

#### 8. Game FPS sensor via RTSS (`sensors/fps.py`) — NUEVO
**Problema:** El anterior `sys.fps` contaba llamadas a `read()` por segundo — no era FPS real.
`DwmGetCompositionTimingInfo` roto en Win11 24H2 (build 26200+, HRESULT 0x88980090).
ETW requiere admin. D3DKMT sin API publica para FPS.

**Solucion: RTSS (RivaTuner Statistics Server) shared memory**
- RTSS (incluido con MSI Afterburner) expone FPS via segmento de memoria compartida `RTSSSharedMemoryV2`
- Sin privilegios de admin necesarios
- Estructura: header 20 bytes → array de app entries (284 bytes core cada una)
- Cada entry: PID, nombre proceso, timestamps, frame count, frame time
- FPS = `dwFrames * 1000 / (dwTime1 - dwTime0)` o `1000000 / dwFrameTime`
- **Fallback a highest-FPS entry** cuando foreground no esta tracked por RTSS (ej: editor TURZX en primer plano, juego detras)
- `ctypes.string_at()` para lectura segura del shared memory (evita access violation con `memmove`)
- Sensor siempre reporta si RTSS esta activo (0 FPS = ningun juego detectado)

**Limitacion:** Requiere RTSS/MSI Afterburner ejecutandose. Sin RTSS, no hay sensor.

#### 9. Element selector panel (`ui/editor.py`) — NUEVO
**Problema:** Elementos con Z-order bajo quedaban ocultos detras de otros y no se podian seleccionar en el canvas.
**Solucion:** `ElementListPanel` — lista de elementos debajo del canvas.
- Muestra todos los elementos ordenados por Z con nombre descriptivo: `[z=1] Sensor: cpu.percent`
- Click en la lista selecciona el elemento en el canvas y en el panel de propiedades
- Sincronizacion bidireccional: seleccionar en canvas → actualiza lista y viceversa
- Se refresca automaticamente al modificar el layout (signal `layout_modified`)

#### 10. Foreground process sensor removal from sys.fps
- `sys.fps` ahora es RTSS exclusivo
- `sys.refresh_rate` monitor Hz removido (era confuso junto a FPS)
- `app.process` y `app.window_title` permanecen como sensores independientes

### Archivos modificados
- `renderer.py`: +`_find_font_file()`, `_REALTIME_SENSORS`, `_realtime_elements`, clock per-frame, `datetime` import
- `config.py`: +`bar_direction` field, `_DEFAULT_LAYOUT_VERSION` → 6
- `ui/editor.py`: arc_bar bounds fix (top-left), bar direction preview, arc_bar angle negation, +`ElementListPanel`, +`select_element()`, +`get_elements()`
- `ui/main_window.py`: save system rewrite (_dirty flag, _mark_dirty, _update_title, closeEvent QMessageBox), +bar_direction combo/widget, ColorButton parent fix, +ElementListPanel integration, import update
- `sensors/system.py`: removed fake FPS counter, removed `sys.refresh_rate`
- `sensors/fps.py`: NUEVO — RTSS shared memory reader
- `sensors/foreground.py`: sin cambios sustanciales
- `sensors/base.py`: +FpsSensor en register_defaults

### Reglas nuevas del bucle
18. PIL `ImageFont.truetype()` NO resuelve font family names — necesita file path. Usar `_find_font_file()` via winreg/fc-match.
19. Qt `drawArc` es CCW, PIL `draw.arc` es CW — negar angulos al convertir.
20. `QColorDialog` parent: nunca usar un widget con stylesheet de color — usar `self.window()`.
21. Shared memory Win32: preferir `ctypes.string_at(addr, size)` sobre `ctypes.memmove(buf, addr, size)` para lectura — evita access violations con punteros 64-bit.
22. Game FPS en Windows sin admin: unica via practica es RTSS shared memory. DwmGetCompositionTimingInfo roto en Win11 24H2+, ETW requiere admin.
23. Auto-save es anti-pattern para editores visuales — usar dirty flag + save explícito.

---

## Sesion 5 — Phase 3: Display Modes (2026-04-04)

### Objetivo
Implementar tres modos de display:
- **Static**: usuario elige un layout fijo (comportamiento actual)
- **Rotative**: ciclar entre layouts seleccionados con intervalo configurable
- **Reactive**: cambiar layout según la aplicación en primer plano

### Arquitectura

```
ModeController (main thread, QTimers)
    ├── rotative: QTimer cada N segundos → set_active(next_layout)
    ├── reactive: QTimer cada 1s → lee app.process → set_active(matched)
    └── emite layout_switched signal → editor sincroniza combo + canvas
```

El render thread ya hace poll de `config.active_layout` cada tick — no requiere cambios.
ModeController se pausa cuando el editor tiene cambios sin guardar (`_dirty`).

### Cambios

#### `config.py` — Modelos de datos + ConfigManager extendido
- 4 dataclasses nuevos: `ReactiveRule`, `RotativeConfig`, `ReactiveConfig`, `ModeConfig`
- `ConfigManager`: `_read_state()` / `_write_state()` reemplazan `_read_active_name()` / `_write_active_name()`
- Nuevo: `mode_config` property, `save_mode_config()` method
- `state.json` ahora persiste tanto `active_layout` como `mode` config

#### `modes.py` — NUEVO — ModeController
- `ModeController(QObject)` con `layout_switched = Signal(str)`
- `_rotate_timer`: avanza al siguiente layout en la lista, filtra layouts eliminados
- `_react_timer`: lee `app.process` de sensor cache, match case-insensitive contra reglas
- `pause() / resume()`: suspende/reanuda auto-switching (usado por editor dirty guard)
- `start() / stop() / reload()`: ciclo de vida

#### `daemon.py` — Integración
- Import y creación de `ModeController` en `TurzxDaemon.__init__`
- `start_render()`: configura sensor source lambda + `mode_controller.start()`
- `stop_render()`: `mode_controller.stop()` antes de detener render thread

#### `ui/main_window.py` — UI de modos
- Import: `ModeConfig`, `ReactiveRule`, `RotativeConfig`, `ReactiveConfig`
- Nuevo group box "Display Mode" en panel izquierdo:
  - 3 radio buttons: Static / Rotative / Reactive
  - Panel rotativo: lista checkable de layouts + spinbox intervalo (5-600s)
  - Panel reactivo: lista de reglas proceso→layout + add/remove + fallback combo
  - Botón "Apply Mode"
- `_mark_dirty()` → `mode_controller.pause()`
- `_save_layout()` / `closeEvent(No)` → `mode_controller.resume()`
- `_on_mode_layout_switched()`: sincroniza combo + recarga canvas on auto-switch
- `_load_mode_ui()`: carga configuración de modos desde config

#### `tray.py` — Modo en tooltip + pausa
- Tooltip muestra modo actual: "TURZX Monitor (Rotative)"
- Nueva acción "Pause Mode" / "Resume Mode" visible en modos no-estáticos
- `_update_mode_tooltip()` conectado a `layout_switched` signal

### Archivos modificados
- `config.py`: +4 dataclasses, ConfigManager extendido con mode persistence
- `modes.py`: NUEVO — ModeController completo
- `daemon.py`: +ModeController wiring
- `ui/main_window.py`: +Display Mode UI, pause/resume integration
- `tray.py`: +mode tooltip, +pause mode action

### Reglas nuevas del bucle
24. ModeController vive en main thread (QTimers) — render thread no necesita cambios porque ya polls `config.active_layout`.
25. El editor NO debe pausar el mode controller al abrirse — los modos corren libre, el editor sincroniza solo cuando no hay cambios sin guardar.
26. `reload()` es accion explicita del usuario (Apply Mode) — DEBE desactivar `_paused` antes de arrancar timers.
27. Rotacion con pool < 2 layouts no tiene sentido — skip silencioso. Con pool >= 2, siempre avanzar a layout diferente del activo.

---

## Sesion 6 — Mode controller bug fixes + CPU temp MAHM (2026-04-05)

### Bugs encontrados y corregidos

#### Bug 1: Rotativo nunca cambiaba de layout
**Causa raiz**: `showEvent` del editor pausaba el ModeController cada vez que la ventana se mostraba. Cuando el usuario clicaba "Apply Mode", `reload()` llamaba `_apply_mode()` que comprobaba `if self._paused: return` y salía sin arrancar timers.

**Fix**:
- `reload()` ahora hace `self._paused = False` antes de arrancar timers (es acción explícita del usuario)
- Eliminado `pause()` de `showEvent` — el editor ya no pausa el mode controller al abrirse
- Eliminado `resume()` de `closeEvent` — coherente con el cambio anterior

#### Bug 2: Rotativo se saltaba turnos
**Causa raiz**: `_on_rotate()` cogía `pool[idx]` y luego comprobaba `if target != active_name`. Si idx coincidía con el layout activo, ese tick entero se perdía sin avanzar.

**Fix**: Si el target coincide con el layout activo, avanza al siguiente inmediatamente. También requiere `len(pool) >= 2` — rotar con un solo layout no tiene sentido.

#### Bug 3: Reactivo inconsistente
**Causa raiz**: Mismo que Bug 1 — el `_paused` flag impedía arrancar el timer reactivo después de aplicar el modo desde el editor.

### Cambios

#### `modes.py`
- `reload()`: añadido `self._paused = False` — acción explícita no debe respetar pausa
- `_on_rotate()`: requiere pool >= 2; skip automático si target == active; siempre emite `layout_switched`

#### `ui/main_window.py`
- `showEvent`: eliminado `mode_controller.pause()` — el editor no interfiere con los modos
- `closeEvent`: eliminado `mode_controller.resume()` — coherente con showEvent

#### `sensors/cpu.py` (sesión anterior, documentado aquí)
- Reemplazado `_wmi_cpu_temp()` (wmic, roto en Win11) por `_mahm_cpu_temp()` — lee MAHMSharedMemory directamente
- Entry layout MAHM v2: 5×char[260] + float data@+1300 + float min@+1304 + float max@+1308

### Reglas nuevas del bucle
28. wmic está deprecado/eliminado en Win11 24H2+ — usar PowerShell CIM o shared memory directamente.
29. MAHM shared memory v2: entry_size=1324, datos reales en offset +1300 (no +780 como sugeriría el struct naive).
30. El editor y el mode controller son sistemas independientes — el editor no debe pausar/reanudar modos. Solo sincroniza UI via signal `layout_switched` cuando no hay edits pendientes.
24. Sensores real-time (clock/date) deben excluirse del cache de overlay y dibujarse per-frame.

---

## Sesion 7 — Layout Transitions (2026-04-05)

### Problema
Al cambiar de layout (rotativo o reactivo), la transición era instantánea y brusca — primero cambiaba el fondo de video y luego se actualizaba el texto, causando un efecto visual extraño.

### Solución — Motor de transiciones PIL

Nuevo módulo `turzx/transitions.py` con transiciones frame-a-frame usando PIL puro (cross-platform):

**Efectos disponibles:**
- `none` — cambio instantáneo (default para static)
- `fade` — crossfade entre frames
- `swipe_left` / `swipe_right` — desplazamiento horizontal
- `swipe_up` / `swipe_down` — desplazamiento vertical

**Arquitectura:**

```
RenderThread._tick()
    ├── Detecta cambio de layout (current_name != _last_layout_name)
    ├── _start_transition(): captura frame actual como old_frame
    │   └── lee transition type + duration desde mode_config
    ├── _compose_frame(): genera new_frame con el layout nuevo
    └── Si hay transición activa:
        ├── progress = elapsed / duration (0.0 → 1.0)
        ├── apply_transition(old_frame, new_frame, progress, type)
        └── Cuando progress >= 1.0: transición completa, limpiar estado
```

El motor opera a nivel de frames PIL completos (overlay + background ya compuestos), así que la transición es atómica — no hay desincronización entre fondo y texto.

### Cambios

#### `transitions.py` — NUEVO
- `apply(old, new, progress, kind)` → `Image.Image`
- 5 funciones de blending: `_fade`, `_swipe_left/right/up/down`
- Dispatch dict para extensibilidad
- `TRANSITIONS` list exportada para UI

#### `config.py`
- `RotativeConfig`: +`transition: str = "fade"`, +`transition_duration: float = 0.5`
- `ReactiveConfig`: +`transition: str = "fade"`, +`transition_duration: float = 0.5`
- `to_dict()` / `from_dict()` incluyen ambos campos

#### `renderer.py`
- `render_frame()` refactorizado: delega a `_compose_frame()` para PIL Image
- `_compose_frame()`: compone un frame completo (bg + overlay + real-time) como PIL Image
- `to_jpeg()` importado desde `images.py` para conversión final

#### `daemon.py` — RenderThread con motor de transición
- Estado de transición: `_transition_old_frame`, `_transition_start`, `_transition_duration`, `_transition_type`
- `_tick()`: detecta cambio de layout → `_start_transition(now)` → blending per-frame
- `_start_transition()`: captura último frame, lee config de transición desde mode_config
- Solo activo en modos rotative/reactive (static no genera cambios de layout)

#### `ui/main_window.py` — UI de transiciones
- Import: `QDoubleSpinBox`, `TRANSITIONS`
- Panel rotativo: +combo "Transition" (none/fade/swipe_*) + spinner "Duration" (0.1-3.0s)
- Panel reactivo: +combo "Transition" + spinner "Duration" (idem)
- `_apply_mode()`: incluye transition + transition_duration en ModeConfig
- `_load_mode_ui()`: restaura valores de transición desde config

### Auditoria Linux

**Transiciones: 100% compatible.** Todo es PIL puro — `Image.blend()`, `Image.new()`, `Image.paste()`. Sin dependencias de plataforma.

**Resumen actualizado de compatibilidad:**

| Componente | Linux | Nota |
|---|---|---|
| transitions.py | ✅ | PIL puro |
| modes.py | ✅ | QTimers, no OS deps |
| renderer.py | ✅ | PIL + cv2 (opcional) |
| cpu temp (MAHM) | ❌ Windows-only | Linux: `psutil.sensors_temperatures()` |
| cpu freq (PDH) | ❌ Windows-only | Linux: `/sys/...cpufreq/scaling_cur_freq` |
| foreground app | ⚠️ Parcial | Windows: ctypes, Linux: xdotool (X11 only) |
| FPS sensor (RTSS) | ❌ Windows-only | Sin equivalente Linux directo |
| USB device | ✅ | libusb sistema |
| tray icon | ⚠️ | GNOME necesita AppIndicator |

### Reglas nuevas del bucle
31. Las transiciones deben operar sobre frames PIL completos (post-compose) — nunca sobre capas individuales, para evitar desincronización fondo/texto.
32. `_start_transition()` captura el frame ANTES del cambio — si no hay frame previo, salta la transición silenciosamente.
33. Transiciones solo aplican en modos no-estáticos — en static, el usuario cambia manualmente y espera resultado inmediato.

---

## Sesion 8 — Real-Render Canvas + Layer Locking (2026-04-05)

### Problema
El canvas del editor dibujaba elementos con primitivas Qt (QFont, QPen, etc.) que no coincidían con el resultado real en la pantalla USB: sensores mostraban valores hardcodeados ("42.0%"), las fuentes no coincidían con PIL, los gradientes eran aproximados. Además, era fácil mover accidentalmente elementos durante la edición.

### Solución — Bitmap renderizado + Proxies transparentes + Bloqueo de capas

**Canvas real-render:**
Reemplazar el dibujo Qt por-elemento con un bitmap de `Renderer.render_image()` — la misma función que genera frames para la pantalla USB. Un `QGraphicsPixmapItem` a z=-9999 muestra el resultado real. Los `ElementItem` se vuelven proxies transparentes (solo dibujan selección).

**Layer locking:**
Checkbox en el panel de elementos para bloquear/desbloquear capas. Elementos bloqueados no se pueden arrastrar (cursor prohibido, rechazo de movimiento).

```
ConfigWindow._canvas_timer (200ms static / 100ms video)
    │
    ├── renderer.render_image(layout, sensor_values) → PIL Image
    ├── _pil_to_qpixmap(pil_img) → QPixmap (BGRA raw, sin JPEG)
    └── scene.update_render_pixmap(pixmap) → _render_bg at z=-9999
        └── ElementItems: transparentes, solo rect de selección
            ├── Deseleccionado: invisible
            ├── Seleccionado: rect cyan discontinuo
            └── Seleccionado+Locked: rect rojo discontinuo
```

### Cambios

#### `config.py`
- `LayoutElement`: +`locked: bool = False` — persiste en JSON, layouts viejos default `False`
- Layout version: 6

#### `editor.py` — Render bitmap + transparent proxy + lock

**`_pil_to_qpixmap(pil_image)`** — Helper PIL→QPixmap:
- Convierte a RGBA, `tobytes("raw", "BGRA")` → `QImage(Format_ARGB32)` → `.copy()` para seguridad de memoria
- Sin roundtrip JPEG — píxel-perfecto

**`EditorScene`:**
- `_render_bg: QGraphicsPixmapItem | None` — bitmap renderizado a z=-9999
- `update_render_pixmap(pixmap)` — crea o actualiza el bitmap
- `load_layout()` limpia `_render_bg`

**`ElementItem.paint()`** — Proxy transparente:
- No dibuja nada excepto rect de selección cuando `isSelected()`
- Color: cyan para normal, rojo para locked. Borde discontinuo + fill semi-transparente

**`ElementItem.itemChange()`** — Rechazo de drag:
- `ItemPositionChange`: si `locked`, retorna `self.pos()` (posición actual = sin movimiento)
- `ItemPositionHasChanged`: sincroniza x,y normalmente para elementos desbloqueados

**`ElementItem.refresh()`** — Sync de flags:
- Locked: `ItemIsSelectable | ItemSendsGeometryChanges`, cursor `ForbiddenCursor`
- Unlocked: + `ItemIsMovable`, cursor `SizeAllCursor`

**`ElementListPanel`** — Checkboxes de bloqueo:
- Items con `ItemIsUserCheckable`, checked = locked
- Prefijo `🔒` en el nombre del elemento cuando está bloqueado
- `_on_item_changed()`: actualiza `el.locked`, refresca flags, emite `layout_modified`

#### `ui/main_window.py` — Timer de canvas

- `_canvas_timer`: QTimer 200ms (static) / 100ms (video)
- `_tick_canvas_render()`: render_image → _pil_to_qpixmap → scene.update_render_pixmap
- Sensor values: del cache de RenderThread o fallback a `sensors.read_all()`
- Re-render inmediato en: property change, background change, layout_modified (drag end)
- `showEvent()`: arranca canvas timer
- `closeEvent()`: para canvas timer
- `_on_layout_modified()`: combina `_mark_dirty()` + `_tick_canvas_render()`
- `_adjust_preview_timer()`: también ajusta canvas timer interval

### Auditoria Linux

**Real-render canvas: 100% compatible.** Usa `Renderer.render_image()` (PIL puro) → QPixmap via QImage. Sin dependencias de plataforma.

**Lock system: 100% compatible.** Solo flags de Qt y atributos de dataclass.

### Reglas nuevas del bucle
34. El canvas del editor debe usar `render_image()` — NUNCA dibujar con Qt primitivas. Un solo bitmap a z=-9999 como fondo, ElementItems como proxies transparentes.
35. `_pil_to_qpixmap()` usa BGRA raw + `.copy()` — nunca JPEG roundtrip para el canvas (pérdida de calidad).
36. Lock rejection en `ItemPositionChange` (antes del movimiento), no en `ItemPositionHasChanged` (ya movido).
37. Canvas timer se para en `closeEvent()` y rearranca en `showEvent()` para no consumir recursos en segundo plano.

---

## Sesion 9 — Eliminar Live Preview + Botón Pause Mode en UI (2026-04-05)

### Problema
1. **Live Preview redundante**: El canvas del editor ya muestra el render real PIL (sesión 8). El widget "Live Preview" debajo del canvas era una duplicación exacta que consumía recursos extra (otro timer + otra llamada a `render_image()` + conversión JPEG).
2. **Pause Mode inaccesible**: "Pause Mode" (pausar auto-switching de layouts en modo rotativo/reactivo) solo estaba disponible en el menú contextual del tray. El usuario tenía que abandonar la ventana principal para acceder a esta funcionalidad.
3. **Confusión "Pause" vs "Pause Mode"**: Dos opciones en el menú tray con nombres similares pero funciones distintas.

### Análisis de las dos funciones "Pause"

| | **Pause** (tray) | **Pause Mode** (tray + UI) |
|---|---|---|
| **Qué hace** | Para TODO: render thread + mode controller | Solo para auto-switching de layouts |
| **Rendering** | Se detiene completamente | Sigue activo (sensores se actualizan) |
| **Pantalla** | Se congela en último frame | Sigue viva con el layout actual |
| **Cuándo usar** | Apagar temporalmente el dispositivo | Editar tranquilamente sin que el modo cambie el layout |
| **API** | `daemon.stop_render()` / `start_render()` | `mode_controller.pause()` / `resume()` |
| **Estado** | `daemon.is_running` | `mode_controller._paused` |

**Conclusión**: Ambas funciones son correctas y distintas. "Pause" = apagar dispositivo, "Pause Mode" = congelar auto-switching. Ambas se mantienen en el tray, y "Pause Mode" se añade también a la UI principal.

### Solución

#### Eliminar Live Preview
- Borrar `self._preview = PreviewWidget()`, `self._timer` (preview timer), `_tick_preview()`, widget QLabel("Live Preview")
- Renombrar `_adjust_preview_timer()` → `_adjust_canvas_timer()` (solo gestiona canvas timer)
- Eliminar import de `PreviewWidget`
- `preview.py` queda huérfano (no se borra del repo para mantener historial limpio, pero no se usa)

#### Añadir botón Pause Mode en UI
- `QPushButton("Pause Mode")` checkable, junto al botón "Apply Mode"
- Visible solo en modo rotative/reactive (igual que en el tray)
- Toggle: `mode_controller.pause()` / `resume()`, sync texto "Pause Mode" ↔ "Resume Mode"
- `_sync_pause_button()` sincroniza estado del botón con `mode_controller._paused`
- Se llama en: toggle click, apply mode (reload resetea paused), load mode UI

### Cambios

#### `ui/main_window.py`

**Eliminado:**
- Import `from .preview import PreviewWidget`
- `self._preview = PreviewWidget()`
- `self._timer` (preview QTimer) y su conexión/start
- QLabel("Live Preview") + `self._preview` en el layout central
- `_tick_preview()` método completo
- Referencias a `self._timer.setInterval()` en `_adjust_preview_timer`

**Renombrado:**
- `_adjust_preview_timer()` → `_adjust_canvas_timer()` (3 ocurrencias)

**Añadido:**
- `self._btn_pause_mode` — QPushButton checkable
- `_toggle_mode_pause()` — toggle pause/resume en mode controller
- `_sync_pause_button()` — sync texto y estado checked del botón
- `_on_mode_radio()` actualizado: muestra/oculta `_btn_pause_mode`
- `_load_mode_ui()` actualizado: sync visibilidad y estado pause
- `_apply_mode()` actualizado: llama `_sync_pause_button()` (reload resetea paused)

**Comentarios actualizados:**
- Docstring del módulo: eliminar referencia a "live preview"
- Sección "Live preview" → "Canvas rendering"
- `_on_background_changed` docstring actualizado

#### `renderer.py`
- Comentario de `render_image()` actualizado: "preview widget" → "editor canvas"

### Auditoria Linux

**Sin impacto.** Solo se eliminó código Qt y se añadió un botón Qt.

### Reglas nuevas del bucle
38. No duplicar renders: un solo timer de canvas es suficiente. Si el canvas muestra el render real, no hay necesidad de un widget preview separado.
39. "Pause" (tray) = detener render thread completo. "Pause Mode" (tray + UI) = pausar solo auto-switching. Son funciones distintas, ambas necesarias.
40. El botón Pause Mode en la UI debe ser checkable y sincronizarse con `mode_controller._paused` — incluyendo cuando Apply Mode hace `reload()` (que resetea paused).