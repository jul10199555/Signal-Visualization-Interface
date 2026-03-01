# ============================================================
# Firmware: main.py — Raspberry Pi Pico (RP2040) / MicroPython
# Protocol:
#   PC -> "0\n"  | Pico -> "0\n"  | luego imprime "READY\n"
#
# Version:      v2.10.1
# Build date:   2026-02-23
# Build time:   09:35:00 (America/Merida)
#
# Changelog:
# - v2.10.1:
#   * Reverted Soft-start (removed)
#   * Added STOP-abort support during CALIBRACION, HOME, ENDPOS (non-blocking serial polling)
# - v2.10.0:
#   * Added Hall IRQ latching (Hall0 + Hall90) with debounce + emergency stop
#   * Mode 1 prioritizes IRQ flags to invert direction promptly at high RPM
# - v2.9.1:
#   * Removed walrus (:=), atomic pulse_count, timeouts, numeric parsing, no regex
# - v2.9.0:
#   * HX711 integrated (non-blocking + EMA), resistance field added to TX in modes 1..4.
# ============================================================

import sys, time
from machine import Pin, PWM

# ============================================================
#   DEBUG (prints that are NOT protocol tokens)
# ============================================================
DEBUG_PRINTS = True

def dbg(*args):
    if DEBUG_PRINTS:
        try:
            print(*args)
        except Exception:
            pass

# ============================================================
#   HARDWARE
# ============================================================
# Motor
in1 = Pin(16, Pin.OUT)
in2 = Pin(17, Pin.OUT)
enable = PWM(Pin(18))

# Encoder & Hall
noencoder_pin_a = Pin(14, Pin.IN, Pin.PULL_UP)
encoder_pin_b   = Pin(15, Pin.IN, Pin.PULL_UP)
encoder_pin_a   = noencoder_pin_a

hall_sensor_0_a = Pin(2, Pin.IN, Pin.PULL_UP)   # HOME 0° (activo-bajo)
hall_sensor_90  = Pin(4, Pin.IN, Pin.PULL_UP)   # 90°     (activo-bajo)

# LED integrado Pico
led_cal = Pin(25, Pin.OUT)

# NeoPixel WS2812 en GPIO23
try:
    import neopixel
    np_led = neopixel.NeoPixel(Pin(23, Pin.OUT), 1)
except Exception:
    np_led = None

# ============================================================
#   IRQ CONTROL (atomic sections)
# ============================================================
try:
    import machine as _machine
    _HAS_IRQ_CTRL = hasattr(_machine, "disable_irq") and hasattr(_machine, "enable_irq")
except Exception:
    _machine = None
    _HAS_IRQ_CTRL = False

def _irq_disable():
    if _HAS_IRQ_CTRL and _machine is not None:
        try:
            return _machine.disable_irq()
        except Exception:
            return None
    return None

def _irq_restore(state):
    if state is not None and _HAS_IRQ_CTRL and _machine is not None:
        try:
            _machine.enable_irq(state)
        except Exception:
            pass

# ============================================================
#   PROTOCOLO: nonblocking stdin poll
# ============================================================
try:
    import uselect
    _poll = uselect.poll()
    _poll.register(sys.stdin, uselect.POLLIN)
except Exception:
    _poll = None

def _readline_nonblocking():
    if not _poll:
        return None
    ev = _poll.poll(0)
    if not ev:
        return None
    line = sys.stdin.readline()
    return line.strip() if line else None

def _stop_requested_nonblocking():
    """
    Revisa si el host mandó STOP/END mientras estamos en rutinas bloqueantes.
    - Consume la línea si existe.
    - Retorna True si se detecta STOP o END.
    """
    line = _readline_nonblocking()
    if not line:
        return False
    t = line.strip().upper()
    if t in ("STOP", "END"):
        return True
    return False

# ============================================================
#   CONSTANTES
# ============================================================
PWM_FREQ = 1000
FORWARD  = "forward"
BACKWARD = "backward"

RPM_MAX               = 30
VELOCIDAD_CALIBRACION = 6
VELOCIDAD_MEDICION    = 6
VELOCIDAD_CICLOS      = 7

ANGULO_ENTRE_SENSORES = 88.5

FACTOR_APRENDIZAJE   = 0.0
MARGEN_DEG_PRE_FRENO = 1.0

MIN_GPP = 0.001
MAX_GPP = 0.2

SAFETY_FACTOR_DOWN = 1.5

# Timeouts (seguridad anti-cuelgues)
HALL_WAIT_MAX_MS_DEFAULT = 20000
CALIB_STEP_MAX_MS        = 25000

# Modo2 límites
MODE2_MAX_STEPS = 1500

# Hall IRQ debounce (ms)
HALL_IRQ_DEBOUNCE_MS = 25

# ============================================================
#   ESTADO GLOBAL GENERAL
# ============================================================
pulse_count       = 0
last_state_a      = encoder_pin_a.value()
current_direction = FORWARD

GRADOS_POR_PULSO_FORWARD  = 0.014
GRADOS_POR_PULSO_BACKWARD = 0.014

calibracion_lista = 0
global_calibrated = False

angulo_constante     = 90.0
velocidad_constante  = 7
angulo_referencial   = 0.0
angulo_referencial_anterior = 0.0

is_calibrating   = False
cal_blink_state  = False

# ============================================================
#   HALL IRQ LATCH FLAGS
# ============================================================
hall0_irq_latched = False
hall90_irq_latched = False
hall0_irq_ts = 0
hall90_irq_ts = 0

# ============================================================
#   ESTADO ESPECÍFICO MODO 2
# ============================================================
mode2_state             = 0
mode2_rep_count         = 0
mode2_angles            = []
mode2_idx               = 0
mode2_current_angle_est = 0.0
mode2_velocity          = 7
mode2_allow_hall90      = False
mode2_error_flag        = False

# ============================================================
#   ATOMIC HELPERS FOR pulse_count
# ============================================================
def pulse_reset_atomic():
    global pulse_count
    s = _irq_disable()
    try:
        pulse_count = 0
    finally:
        _irq_restore(s)

def pulse_get_atomic():
    s = _irq_disable()
    try:
        return pulse_count
    finally:
        _irq_restore(s)

def pulse_set_atomic(val):
    global pulse_count
    s = _irq_disable()
    try:
        pulse_count = val
    finally:
        _irq_restore(s)

# ============================================================
#   LEDs: helpers
# ============================================================
def _np_write(r, g, b):
    if np_led is None:
        return
    np_led[0] = (int(r) & 0xFF, int(g) & 0xFF, int(b) & 0xFF)
    np_led.write()

def _led_all_off():
    led_cal.value(0)
    _np_write(0, 0, 0)

def _led_set_idle_not_calibrated():
    led_cal.value(0)
    _np_write(120, 40, 0)

def _led_set_calibrated():
    led_cal.value(1)
    _np_write(0, 120, 0)

def _led_calibrating_toggle():
    global cal_blink_state
    cal_blink_state = not cal_blink_state
    if cal_blink_state:
        led_cal.value(1)
        _np_write(80, 80, 80)
    else:
        led_cal.value(0)
        _np_write(0, 0, 0)

# ============================================================
#   MOTOR / ENCODER
# ============================================================
def inicializar_motor():
    in1.value(0)
    in2.value(0)
    enable.freq(PWM_FREQ)
    enable.duty_u16(0)

def rpm_a_duty(rpm):
    if rpm <= 0:
        return 0
    if rpm > RPM_MAX:
        rpm = RPM_MAX
    return int((rpm / RPM_MAX) * 65535)

def control_motor(direction, rpm):
    global current_direction
    duty = rpm_a_duty(rpm)
    enable.duty_u16(duty)
    if direction == FORWARD:
        in1.value(1)
        in2.value(0)
    else:
        in1.value(0)
        in2.value(1)
    current_direction = direction

def _motor_emergency_stop_isr_safe():
    try:
        enable.duty_u16(0)
        in1.value(0)
        in2.value(0)
    except Exception:
        pass

def stop_motor():
    enable.duty_u16(0)
    in1.value(0)
    in2.value(0)
    dbg("Motor detenido")

def count_pulses(pin):
    global pulse_count, last_state_a, angulo_referencial
    state_a = encoder_pin_a.value()
    state_b = encoder_pin_b.value()
    if state_a != last_state_a:
        sentido = -1 if state_a == state_b else 1
        pulse_count += sentido

        if current_direction == FORWARD:
            angulo_referencial += sentido * GRADOS_POR_PULSO_FORWARD
        else:
            angulo_referencial += sentido * GRADOS_POR_PULSO_BACKWARD

        last_state_a = state_a

encoder_pin_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=count_pulses)

def grados_a_pulsos(grados, direccion):
    try:
        grados = float(grados)
    except Exception:
        grados = 0.0

    if grados < 0:
        grados = 0.0
    if grados > ANGULO_ENTRE_SENSORES:
        grados = float(ANGULO_ENTRE_SENSORES)

    gpp = GRADOS_POR_PULSO_FORWARD if direccion == FORWARD else GRADOS_POR_PULSO_BACKWARD
    if gpp <= 0:
        gpp = 0.014
    pulsos = int(grados / gpp)
    return max(1, pulsos)

def calcular_grados():
    pc = pulse_get_atomic()
    if current_direction == FORWARD:
        return abs(pc * GRADOS_POR_PULSO_FORWARD)
    else:
        return abs(pc * GRADOS_POR_PULSO_BACKWARD)

def corregir_dinamicamente(grados, pulsos):
    global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD
    if FACTOR_APRENDIZAJE <= 0.0:
        return
    if pulsos == 0:
        return
    error = angulo_constante - grados
    ajuste = FACTOR_APRENDIZAJE * error / pulsos
    if current_direction == FORWARD:
        GRADOS_POR_PULSO_FORWARD += ajuste
        GRADOS_POR_PULSO_FORWARD = min(max(GRADOS_POR_PULSO_FORWARD, MIN_GPP), MAX_GPP)
    else:
        GRADOS_POR_PULSO_BACKWARD += ajuste
        GRADOS_POR_PULSO_BACKWARD = min(max(GRADOS_POR_PULSO_BACKWARD, MIN_GPP), MAX_GPP)

# ============================================================
#   HALLS: polling debounce (legacy)
# ============================================================
def _hall_activo_debounced(pin, muestras=5, dt_ms=3):
    for _ in range(muestras):
        if pin.value() == 1:
            return False
        time.sleep(dt_ms / 1000)
    return True

def hall0_activo():
    return _hall_activo_debounced(hall_sensor_0_a)

def hall90_activo():
    return _hall_activo_debounced(hall_sensor_90)

# ============================================================
#   HALL IRQ HANDLERS
# ============================================================
def _hall0_irq_handler(pin):
    global hall0_irq_latched, hall0_irq_ts
    now = time.ticks_ms()
    if time.ticks_diff(now, hall0_irq_ts) < HALL_IRQ_DEBOUNCE_MS:
        return
    hall0_irq_ts = now
    hall0_irq_latched = True
    if current_direction == BACKWARD:
        _motor_emergency_stop_isr_safe()

def _hall90_irq_handler(pin):
    global hall90_irq_latched, hall90_irq_ts
    now = time.ticks_ms()
    if time.ticks_diff(now, hall90_irq_ts) < HALL_IRQ_DEBOUNCE_MS:
        return
    hall90_irq_ts = now
    hall90_irq_latched = True
    if current_direction == FORWARD:
        _motor_emergency_stop_isr_safe()

try:
    hall_sensor_0_a.irq(trigger=Pin.IRQ_FALLING, handler=_hall0_irq_handler)
    hall_sensor_90.irq(trigger=Pin.IRQ_FALLING, handler=_hall90_irq_handler)
except Exception as e:
    dbg("WARN: No se pudieron habilitar IRQs en Halls:", e)

def hall_irq_take_flags():
    global hall0_irq_latched, hall90_irq_latched
    s = _irq_disable()
    try:
        h0 = bool(hall0_irq_latched)
        h9 = bool(hall90_irq_latched)
        hall0_irq_latched = False
        hall90_irq_latched = False
        return h0, h9
    finally:
        _irq_restore(s)

# ============================================================
#   HALL helpers (otros)
# ============================================================
def esperar_liberacion(pin, debounce_ms=20, timeout_ms=HALL_WAIT_MAX_MS_DEFAULT):
    t0 = time.ticks_ms()
    while True:
        if _stop_requested_nonblocking():
            return False
        if pin.value() == 1:
            time.sleep(debounce_ms / 1000)
            if pin.value() == 1:
                return True
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            return False
        time.sleep(0.005)

def estimar_pulsos_entre_sensores():
    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        return 99999
    return int(ANGULO_ENTRE_SENSORES / gpp)

def buscar_hall(pin_objetivo, direccion, rpm_busqueda, timeout_pulsos, timeout_ms=HALL_WAIT_MAX_MS_DEFAULT):
    base = pulse_get_atomic()
    t0 = time.ticks_ms()
    control_motor(direccion, rpm_busqueda)
    while True:
        if _stop_requested_nonblocking():
            stop_motor()
            return False
        if pin_objetivo.value() == 0:
            stop_motor()
            return True
        if abs(pulse_get_atomic() - base) >= timeout_pulsos:
            stop_motor()
            return False
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            stop_motor()
            return False
        time.sleep(0.001)

def go_home(rpm_busqueda=VELOCIDAD_MEDICION):
    """
    HOME abortable con STOP.
    Retorna True si llegó a Hall0, False si abort/timeout/falla.
    """
    global current_direction

    if _stop_requested_nonblocking():
        stop_motor()
        return False

    if hall0_activo():
        small_release = max(5, estimar_pulsos_entre_sensores() // 10)
        base = pulse_get_atomic()
        control_motor(FORWARD, max(3, rpm_busqueda))
        while abs(pulse_get_atomic() - base) < small_release:
            if _stop_requested_nonblocking():
                stop_motor()
                return False
            time.sleep(0.001)
        stop_motor()

        ok_release = esperar_liberacion(hall_sensor_0_a)
        if not ok_release:
            dbg("WARN: Hall0 no liberó (abort/timeout) durante go_home().")
            # Si fue abort (STOP), salir
            if _stop_requested_nonblocking():
                stop_motor()
                return False

    estim = estimar_pulsos_entre_sensores()
    timeout_pulses = int(1.5 * max(estim, 50))

    found = buscar_hall(hall_sensor_0_a, BACKWARD, max(3, rpm_busqueda), timeout_pulses)
    if not found:
        dbg("WARN: No se encontró Hall 0 dentro del timeout / abort.")
        stop_motor()
        return False

    stop_motor()
    pulse_set_atomic(0)
    current_direction = BACKWARD
    dbg("Home alcanzado (0°).")
    return True

# ============================================================
#   HX711
# ============================================================
HX711_DOUT_PIN = 21
HX711_SCK_PIN  = 20

class HX711:
    def __init__(self, dout_pin: int, sck_pin: int, gain: int = 128):
        self.dout = Pin(dout_pin, Pin.IN, Pin.PULL_UP)
        self.sck  = Pin(sck_pin, Pin.OUT)
        self.sck.value(0)

        if gain not in (128, 64, 32):
            gain = 128
        self.gain = gain

        if gain == 128:
            self._gain_pulses = 1
        elif gain == 64:
            self._gain_pulses = 3
        else:
            self._gain_pulses = 2

    def is_ready(self) -> bool:
        return self.dout.value() == 0

    def _clock_pulse(self):
        self.sck.value(1); time.sleep_us(1)
        self.sck.value(0); time.sleep_us(1)

    def read_raw(self):
        if not self.is_ready():
            return None
        irq_state = _irq_disable()
        try:
            data = 0
            for _ in range(24):
                self.sck.value(1); time.sleep_us(1)
                data = (data << 1) | (1 if self.dout.value() else 0)
                self.sck.value(0); time.sleep_us(1)
            for _ in range(self._gain_pulses):
                self._clock_pulse()
            if data & 0x800000:
                data -= 1 << 24
            return data
        finally:
            _irq_restore(irq_state)

try:
    hx711 = HX711(HX711_DOUT_PIN, HX711_SCK_PIN, gain=32)
except Exception:
    hx711 = None

hx_last_raw = None
hx_filtered = None
HX_ALPHA    = 0.20

def hx_update_nonblocking():
    global hx_last_raw, hx_filtered
    if hx711 is None:
        return None
    raw = hx711.read_raw()
    if raw is None:
        return hx_filtered
    hx_last_raw = raw
    if hx_filtered is None:
        hx_filtered = float(raw)
    else:
        hx_filtered = (1.0 - HX_ALPHA) * float(hx_filtered) + HX_ALPHA * float(raw)
    return hx_filtered

def hx_get_resistance_value():
    return hx_filtered

# ============================================================
#   CALIBRACIÓN Y MEDICIÓN (ABORTABLE con STOP)
# ============================================================
def medir_angulo_entre_sensores(timeout_ms=HALL_WAIT_MAX_MS_DEFAULT):
    dbg("→ Midiendo ángulo real entre sensores Hall...")

    t0 = time.ticks_ms()
    control_motor(FORWARD, VELOCIDAD_MEDICION)
    while hall_sensor_90.value() == 1:
        if _stop_requested_nonblocking():
            stop_motor()
            return None
        if time.ticks_diff(time.ticks_ms(), t0) > timeout_ms:
            stop_motor()
            raise RuntimeError("Timeout esperando Hall90 en medir_angulo_entre_sensores()")
        time.sleep(0.001)
    stop_motor()
    time.sleep(0.2)
    dbg("Sensor 90° detectado (inicio de medición)")

    pulse_reset_atomic()
    t1 = time.ticks_ms()
    control_motor(BACKWARD, VELOCIDAD_MEDICION)
    while hall_sensor_0_a.value() == 1:
        if _stop_requested_nonblocking():
            stop_motor()
            return None
        if time.ticks_diff(time.ticks_ms(), t1) > timeout_ms:
            stop_motor()
            raise RuntimeError("Timeout esperando Hall0 en medir_angulo_entre_sensores()")
        time.sleep(0.001)
    stop_motor()
    dbg("Sensor 0° detectado (fin de medición)")

    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        gpp = 0.014
    angulo = abs(pulse_get_atomic()) * gpp
    dbg("Ángulo medido entre sensores (90° → 0°): %.2f°" % angulo)
    return angulo

def calibrar_motor():
    global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD

    dbg("Calibración: yendo primero a HOME...")
    ok_home = go_home()
    if not ok_home:
        stop_motor()
        return False

    stop_motor()
    time.sleep(0.3)

    dbg("Iniciando calibración (ciclos entre Hall 0° y 90°)...")
    pulse_reset_atomic()
    ciclos = 8
    forward_pulses = []
    backward_pulses = []

    direccion = FORWARD
    sensor_siguiente = hall_sensor_90

    _led_all_off()
    blink_last = time.ticks_ms()

    for i in range(ciclos + 1):
        if _stop_requested_nonblocking():
            stop_motor()
            _led_all_off()
            return False

        dbg("→ Ciclo %d: moviendo %s" % (i + 1, direccion))
        pulse_reset_atomic()
        control_motor(direccion, VELOCIDAD_CALIBRACION)

        t0 = time.ticks_ms()
        while sensor_siguiente.value() == 1:
            if _stop_requested_nonblocking():
                stop_motor()
                _led_all_off()
                return False

            now = time.ticks_ms()
            if time.ticks_diff(now, blink_last) >= 150:
                blink_last = now
                _led_calibrating_toggle()
                sys.stdout.write("CALIBRANDO\n")

            if time.ticks_diff(now, t0) > CALIB_STEP_MAX_MS:
                stop_motor()
                _led_all_off()
                raise RuntimeError("Timeout en calibrar_motor() esperando Hall")

            time.sleep(0.001)

        time.sleep(0.02)
        stop_motor()

        if i > 0:
            pulsos = abs(pulse_get_atomic())
            if direccion == FORWARD:
                forward_pulses.append(pulsos)
            else:
                backward_pulses.append(pulsos)
            dbg("Pulsos en ciclo %d: %d" % (i + 1, pulsos))
        else:
            dbg("(Ignorado) Pulsos en ciclo %d: %d" % (i + 1, abs(pulse_get_atomic())))

        direccion = BACKWARD if direccion == FORWARD else FORWARD
        sensor_siguiente = hall_sensor_0_a if sensor_siguiente is hall_sensor_90 else hall_sensor_90
        time.sleep(0.5)

    _led_all_off()

    if not forward_pulses or not backward_pulses:
        raise RuntimeError("Calibración inválida: faltan pulsos forward/backward")

    prom_forward  = sum(forward_pulses) / len(forward_pulses)
    prom_backward = sum(backward_pulses) / len(backward_pulses)

    GRADOS_POR_PULSO_FORWARD  = ANGULO_ENTRE_SENSORES / prom_forward
    GRADOS_POR_PULSO_BACKWARD = ANGULO_ENTRE_SENSORES / prom_backward

    GRADOS_POR_PULSO_FORWARD  = min(max(GRADOS_POR_PULSO_FORWARD,  MIN_GPP), MAX_GPP)
    GRADOS_POR_PULSO_BACKWARD = min(max(GRADOS_POR_PULSO_BACKWARD, MIN_GPP), MAX_GPP)

    dbg("Calibración completada.")
    dbg("Promedio FORWARD: %s, BACKWARD: %s" % (prom_forward, prom_backward))
    dbg("GRADOS_POR_PULSO_FORWARD inicial: %.6f" % GRADOS_POR_PULSO_FORWARD)
    dbg("GRADOS_POR_PULSO_BACKWARD inicial: %.6f" % GRADOS_POR_PULSO_BACKWARD)

    stop_motor()
    pulse_reset_atomic()
    return True

def _calibrar_y_medir_y_home():
    """
    Calibración abortable con STOP.
    Retorna True si completó, False si abortó.
    """
    global calibracion_lista, angulo_referencial, angulo_referencial_anterior, current_direction
    global global_calibrated, is_calibrating

    dbg("=== Calibración global iniciada ===")
    sys.stdout.write("CALIBRANDO\n")

    global_calibrated = False
    calibracion_lista = 0
    is_calibrating    = True
    _led_all_off()

    ok = calibrar_motor()
    if not ok:
        # abortado o falla
        is_calibrating = False
        _led_set_idle_not_calibrated()
        stop_motor()
        return False

    try:
        ang = medir_angulo_entre_sensores()
        if ang is None:
            # abortado
            is_calibrating = False
            _led_set_idle_not_calibrated()
            stop_motor()
            return False
    except Exception as e:
        dbg("Aviso: medir_angulo_entre_sensores() falló:", e)

    ok_home = go_home()
    stop_motor()
    if not ok_home:
        is_calibrating = False
        _led_set_idle_not_calibrated()
        return False

    # Estado limpio en 0°
    pulse_set_atomic(0)
    angulo_referencial = 0.0
    angulo_referencial_anterior = 0.0
    current_direction = FORWARD

    calibracion_lista = 1
    global_calibrated = True
    is_calibrating    = False

    _led_set_calibrated()

    sys.stdout.write("CALIBRACION LISTA\n")
    sys.stdout.write("Motor en Home (0°) [Calibrado]\n")
    dbg("=== Calibración global terminada ===")
    return True

# ============================================================
#   HELPERS MANUAL (HOME/ENDPOS abortables)
# ============================================================
def manual_home():
    dbg("MANUAL: HOME solicitado")
    ok = go_home()
    stop_motor()
    return ok

def manual_endpos():
    """
    ENDPOS abortable con STOP:
      - Va a HOME
      - Busca Hall90
    Retorna True si llega a Hall90, False si abort/timeout/falla.
    """
    dbg("MANUAL: ENDPOS solicitado")

    ok_home = go_home()
    stop_motor()
    if not ok_home:
        return False

    time.sleep(0.2)

    pulse_reset_atomic()
    estim = estimar_pulsos_entre_sensores()
    timeout = int(1.5 * max(estim, 50))
    dbg("MANUAL ENDPOS: buscando Hall90 con timeout %d pulsos..." % timeout)

    found = buscar_hall(hall_sensor_90, FORWARD, VELOCIDAD_MEDICION, timeout)
    if found:
        dbg("MANUAL ENDPOS: Hall 90° alcanzado.")
        return True
    dbg("WARN MANUAL ENDPOS: No se encontró Hall 90° (timeout/abort).")
    return False

def _manual_move_from_home_to_angle(target_deg, rpm, allow_hall90=False):
    global current_direction

    try:
        target_deg = float(target_deg)
    except Exception:
        target_deg = 0.0

    if target_deg < 0:
        target_deg = 0.0
    if target_deg > ANGULO_ENTRE_SENSORES:
        target_deg = float(ANGULO_ENTRE_SENSORES)

    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        gpp = 0.014

    target_pulses = grados_a_pulsos(target_deg, FORWARD)
    margen_pulsos = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
    pre_freno_start = max(0, target_pulses - margen_pulsos)

    pulse_reset_atomic()
    current_direction = FORWARD
    rpm_high = int(rpm)
    rpm_low  = max(3, rpm_high // 3)

    control_motor(FORWARD, rpm_high)

    t0 = time.ticks_ms()
    while True:
        if _stop_requested_nonblocking():
            stop_motor()
            return False

        h0_irq, h90_irq = hall_irq_take_flags()
        if (h90_irq or hall_sensor_90.value() == 0) and (not allow_hall90):
            dbg("MANUAL: Hall 90° inesperado. Abortando y volviendo a HOME.")
            stop_motor()
            go_home()
            return False

        pulsos = abs(pulse_get_atomic())
        if pulsos >= target_pulses:
            break

        if pulsos >= pre_freno_start:
            control_motor(FORWARD, rpm_low)

        if time.ticks_diff(time.ticks_ms(), t0) > HALL_WAIT_MAX_MS_DEFAULT:
            dbg("WARN: Timeout en _manual_move_from_home_to_angle(). Abortando a HOME.")
            stop_motor()
            go_home()
            return False

        time.sleep(0.001)

    stop_motor()
    dbg("MANUAL: Alcanzado ángulo ~%s°" % target_deg)
    return True

def manual_goto_angle(angle_deg):
    dbg("MANUAL: GOTO solicitado → %s°" % angle_deg)

    ok_home = go_home()
    stop_motor()
    if not ok_home:
        return

    allow_h90 = False
    try:
        allow_h90 = (float(angle_deg) >= ANGULO_ENTRE_SENSORES - 0.5)
    except Exception:
        allow_h90 = False

    _manual_move_from_home_to_angle(angle_deg, VELOCIDAD_MEDICION, allow_hall90=allow_h90)

# ============================================================
#   CONFIG PARSING
# ============================================================
try:
    import ujson as _json
except Exception:
    _json = None

def _normalize_to_json_like(s: str) -> str:
    return s.strip().replace("'", '"')

def _to_number(v):
    if isinstance(v, (int, float)):
        return v
    if v is None:
        return None
    s = str(v).strip()
    if not s:
        return None
    try:
        if ('.' in s) or ('e' in s.lower()):
            return float(s)
        return int(s)
    except Exception:
        try:
            return float(s)
        except Exception:
            return None

def _manual_parse_dict(s: str) -> dict:
    s = s.strip()
    if not (s.startswith("{") and s.endswith("}")):
        raise ValueError("Formato no reconocido (usa dict JSON)")
    inner = s[1:-1].strip()
    if not inner:
        return {}
    parts = [p.strip() for p in inner.split(",")]
    d = {}
    for p in parts:
        if ":" not in p:
            continue
        k, v = p.split(":", 1)
        k = k.strip().strip('"')
        v = v.strip().strip('"')
        num = _to_number(v)
        d[k] = num if num is not None else v
    return d

def _parse_config(s: str) -> dict:
    s_norm = _normalize_to_json_like(s)
    if _json:
        try:
            obj = _json.loads(s_norm)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
    return _manual_parse_dict(s_norm)

STATE_IDLE, STATE_RUN, STATE_PAUSED = 0, 1, 2
INTERVAL_MS = 50

def _get_num_and_key(cfg: dict, aliases, default_val, default_key, cast="auto"):
    for k in aliases:
        if k in cfg:
            val = _to_number(cfg[k])
            if val is None:
                continue
            try:
                if cast == "int":
                    return int(val), k
                if cast == "float":
                    return float(val), k
                return val, k
            except Exception:
                continue
    return default_val, default_key

def _mode_number_from_cfg(cfg):
    mode_raw = cfg.get("modo", cfg.get("mode", None))
    if mode_raw is None:
        raise ValueError("falta 'modo' o 'mode'")
    if isinstance(mode_raw, int):
        return int(mode_raw)
    if isinstance(mode_raw, float):
        return int(mode_raw)
    s = str(mode_raw).strip()
    digits = ""
    for ch in s:
        if "0" <= ch <= "9":
            digits += ch
    if not digits:
        raise ValueError("'mode/modo' debe contener 1..4")
    return int(digits)

# ============================================================
#   MODO 1 (con IRQ halls, SIN soft-start)
# ============================================================
def mode1_action(cfg):
    global current_direction
    global velocidad_constante, angulo_constante

    try:
        v, kv = _get_num_and_key(cfg, ["velocity", "velocidad", "speed"], 7, "velocity", cast="int")
        a, ka = _get_num_and_key(cfg, ["angle", "angulo"], 90.0, "angle", cast="float")

        if a < 0:
            a = 0.0
        if a > ANGULO_ENTRE_SENSORES:
            a = float(ANGULO_ENTRE_SENSORES)

        angulo_constante    = float(a)
        velocidad_constante = int(v)

        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
        if gpp <= 0:
            gpp = 0.014

        pulsos_obj = grados_a_pulsos(angulo_constante, FORWARD)
        margen_pulsos    = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
        pulsos_pre_freno = max(0, pulsos_obj - margen_pulsos)
        rpm_pre_freno    = max(3, int(velocidad_constante / 3))

        pulsos_abs = abs(pulse_get_atomic())
        hall0_irq, hall90_irq = hall_irq_take_flags()

        if current_direction == FORWARD:
            if hall90_irq or hall90_activo():
                dbg("Modo1: Hall 90° detectado. Invirtiendo a BACKWARD.")
                stop_motor()
                grados = calcular_grados()
                corregir_dinamicamente(grados, pulsos_abs)
                pulse_reset_atomic()
                current_direction = BACKWARD
                control_motor(current_direction, velocidad_constante)

            elif pulsos_abs >= pulsos_obj:
                dbg("Modo1: objetivo encoder alcanzado (UP). Invirtiendo a BACKWARD.")
                stop_motor()
                grados = calcular_grados()
                corregir_dinamicamente(grados, pulsos_abs)
                pulse_reset_atomic()
                current_direction = BACKWARD
                control_motor(current_direction, velocidad_constante)

            else:
                if pulsos_abs >= pulsos_pre_freno:
                    control_motor(FORWARD, rpm_pre_freno)
                else:
                    control_motor(FORWARD, velocidad_constante)

            grados_actuales = calcular_grados()
            if grados_actuales > angulo_constante:
                grados_actuales = float(angulo_constante)

        else:
            if hall0_irq or hall0_activo():
                dbg("Modo1: Hall 0° detectado. Invirtiendo a FORWARD (reset a 0°).")
                stop_motor()
                pulse_reset_atomic()
                grados_actuales = 0.0
                current_direction = FORWARD
                control_motor(current_direction, velocidad_constante)

            else:
                pulsos_span     = grados_a_pulsos(ANGULO_ENTRE_SENSORES, BACKWARD)
                max_pulsos_down = int(SAFETY_FACTOR_DOWN * pulsos_span)

                if pulsos_abs >= max_pulsos_down:
                    dbg("Modo1: BAJANDO sin Hall0. Activando rescate por encoder.")
                    stop_motor()
                    pulsos_fallo = pulsos_abs

                    pulse_reset_atomic()
                    current_direction = FORWARD
                    control_motor(FORWARD, velocidad_constante)
                    while abs(pulse_get_atomic()) < pulsos_fallo:
                        time.sleep(0.001)
                    stop_motor()

                    current_direction = FORWARD
                    pulse_reset_atomic()
                    grados_actuales = float(angulo_constante)

                else:
                    control_motor(BACKWARD, velocidad_constante)
                    grados_tmp = float(angulo_constante) - float(pulsos_abs) * float(gpp)
                    if grados_tmp < 0:
                        grados_tmp = 0.0
                    grados_actuales = grados_tmp

        hx_update_nonblocking()
        res_val = hx_get_resistance_value()

        sys.stdout.write(str([
            "modo", 1, kv, velocidad_constante, ka, grados_actuales,
            "resistance", res_val
        ]) + "\n")

    except Exception as e:
        stop_motor()
        go_home()
        stop_motor()
        sys.stdout.write("ERROR en modo 1: " + str(e) + "\n")

# ============================================================
#   MODO 2, 3, 4 (sin cambios)
# ============================================================
def _mode2_move_relative(delta_deg, direction):
    global mode2_error_flag
    try:
        delta_deg = float(delta_deg)
    except Exception:
        delta_deg = 0.0
    if delta_deg <= 0:
        return True

    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        gpp = 0.014

    target_pulses = grados_a_pulsos(delta_deg, direction)
    margen_pulsos = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
    pre_freno_start = max(0, target_pulses - margen_pulsos)

    rpm_high = mode2_velocity
    rpm_low  = max(3, rpm_high // 3)

    pulse_reset_atomic()
    control_motor(direction, rpm_high)

    t0 = time.ticks_ms()
    while True:
        hall0_irq, hall90_irq = hall_irq_take_flags()

        if direction == FORWARD and (not mode2_allow_hall90) and (hall90_irq or hall_sensor_90.value() == 0):
            dbg("Modo2: Hall 90° inesperado durante movimiento.")
            mode2_error_flag = True
            stop_motor()
            return False

        if direction == BACKWARD and (hall0_irq or hall_sensor_0_a.value() == 0):
            dbg("Modo2: Hall 0° inesperado durante movimiento.")
            mode2_error_flag = True
            stop_motor()
            return False

        pulsos = abs(pulse_get_atomic())
        if pulsos >= target_pulses:
            break

        if pulsos >= pre_freno_start:
            control_motor(direction, rpm_low)

        if time.ticks_diff(time.ticks_ms(), t0) > HALL_WAIT_MAX_MS_DEFAULT:
            dbg("WARN: Timeout en _mode2_move_relative(). Abortando.")
            stop_motor()
            mode2_error_flag = True
            return False

        time.sleep(0.001)

    stop_motor()
    return True

def _mode2_move_to_angle(target_deg):
    global mode2_current_angle_est
    try:
        target_deg = float(target_deg)
    except Exception:
        target_deg = mode2_current_angle_est

    delta = target_deg - mode2_current_angle_est
    if abs(delta) < 0.2:
        mode2_current_angle_est = target_deg
        return True

    direction = FORWARD if delta > 0 else BACKWARD
    ok = _mode2_move_relative(abs(delta), direction)
    if ok:
        mode2_current_angle_est = target_deg
    return ok

def mode2_action(cfg):
    global mode2_state, mode2_rep_count, mode2_angles, mode2_idx
    global mode2_current_angle_est, mode2_velocity, mode2_allow_hall90
    global mode2_error_flag

    ia, kia = _get_num_and_key(cfg, ["init_angle", "angulo_inicial"], 0.0, "init_angle", cast="float")
    fa, kfa = _get_num_and_key(cfg, ["final_angle", "angulo_final"], 90.0, "final_angle", cast="float")
    sa, ksa = _get_num_and_key(cfg, ["step_angle"], 1.0, "step_angle", cast="float")
    v,  kv  = _get_num_and_key(cfg, ["velocity", "velocidad", "speed"], 7, "velocity", cast="int")

    ia = float(ia); fa = float(fa); sa = float(sa)

    if ia < 0: ia = 0.0
    if ia > ANGULO_ENTRE_SENSORES: ia = float(ANGULO_ENTRE_SENSORES)
    if fa < ia: fa = ia
    if fa > ANGULO_ENTRE_SENSORES: fa = float(ANGULO_ENTRE_SENSORES)
    if sa < 0: sa = -sa
    if sa == 0: sa = 1.0

    mode2_allow_hall90 = (fa >= (ANGULO_ENTRE_SENSORES - 0.5))
    mode2_velocity = int(v)

    angles = [ia]
    if fa > ia:
        steps = 0
        a = ia + sa
        while a < fa and steps < MODE2_MAX_STEPS:
            angles.append(a)
            a += sa
            steps += 1
        if angles[-1] != fa:
            angles.append(fa)
    mode2_angles = angles

    if not mode2_angles:
        mode2_current_angle_est = 0.0
    else:
        ok = True
        if mode2_state == 0:
            ok = _mode2_move_to_angle(mode2_angles[0])
            if ok:
                mode2_idx = 0
                mode2_state = 1
        elif mode2_state == 1:
            if mode2_idx >= len(mode2_angles) - 1:
                mode2_state = 2
            else:
                ok = _mode2_move_to_angle(mode2_angles[mode2_idx + 1])
                if ok:
                    mode2_idx += 1
        elif mode2_state == 2:
            if mode2_idx <= 0:
                mode2_rep_count += 1
                if mode2_rep_count >= 5:
                    dbg("Modo2: 5 ciclos completados, regresando a HOME.")
                    go_home()
                    stop_motor()
                    mode2_current_angle_est = 0.0
                    mode2_idx = 0
                    mode2_rep_count = 0
                    mode2_state = 0
                else:
                    mode2_state = 1
            else:
                ok = _mode2_move_to_angle(mode2_angles[mode2_idx - 1])
                if ok:
                    mode2_idx -= 1

        if not ok:
            dbg("ERROR: Modo2 anómalo, regresando a HOME.")
            go_home()
            stop_motor()
            mode2_current_angle_est = 0.0
            mode2_idx = 0
            mode2_rep_count = 0
            mode2_state = 0
            mode2_error_flag = False

    hx_update_nonblocking()
    res_val = hx_get_resistance_value()

    sys.stdout.write(str([
        "modo", 2,
        kia, ia,
        kfa, fa,
        ksa, sa,
        kv, v,
        "angle", mode2_current_angle_est,
        "rep", mode2_rep_count,
        "idx", mode2_idx,
        "resistance", res_val
    ]) + "\n")

def mode3_action(cfg):
    a,  ka  = _get_num_and_key(cfg, ["angle", "angulo"], 1.0, "angle", cast="float")
    iv, kiv = _get_num_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel", cast="int")
    fv, kfv = _get_num_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel", cast="int")
    sv, ksv = _get_num_and_key(cfg, ["step_vel"], 1, "step_vel", cast="int")

    hx_update_nonblocking()
    res_val = hx_get_resistance_value()

    sys.stdout.write(str([
        "modo", 3, ka, a, kiv, iv, kfv, fv, ksv, sv,
        "resistance", res_val
    ]) + "\n")

def mode4_action(cfg):
    ia, kia = _get_num_and_key(cfg, ["init_angle", "angulo_inicial"], 0.0, "init_angle", cast="float")
    fa, kfa = _get_num_and_key(cfg, ["final_angle", "angulo_final"], 90.0, "final_angle", cast="float")
    sa, ksa = _get_num_and_key(cfg, ["step_angle"], 1.0, "step_angle", cast="float")
    iv, kiv = _get_num_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel", cast="int")
    fv, kfv = _get_num_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel", cast="int")
    sv, ksv = _get_num_and_key(cfg, ["step_vel"], 1, "step_vel", cast="int")

    hx_update_nonblocking()
    res_val = hx_get_resistance_value()

    sys.stdout.write(str([
        "modo", 4, kia, ia, kfa, fa, ksa, sa, kiv, iv, kfv, fv, ksv, sv,
        "resistance", res_val
    ]) + "\n")

MODE_HANDLERS = {1: mode1_action, 2: mode2_action, 3: mode3_action, 4: mode4_action}

# ============================================================
#   MAIN LOOP
# ============================================================
def main():
    global calibracion_lista, global_calibrated
    global mode2_state, mode2_rep_count, mode2_idx, mode2_current_angle_est, mode2_error_flag

    state = STATE_IDLE
    modo, cfg = None, {}
    printed_ready = False
    handshaken = False
    next_t = time.ticks_ms()

    global_calibrated = False
    calibracion_lista = 0
    _led_set_idle_not_calibrated()

    while True:
        hx_update_nonblocking()

        line = _readline_nonblocking()

        # ==== Handshake y comandos globales / manuales (SIEMPRE) ====
        if line:
            t_upper = line.strip().upper()

            if t_upper == "0":
                sys.stdout.write("0\n")
                handshaken = True
                printed_ready = False
                continue

            if t_upper == "END":
                sys.stdout.write("STOP\n")
                state = STATE_IDLE
                modo, cfg = None, {}
                printed_ready = False
                handshaken = False
                calibracion_lista = 0
                global_calibrated = False
                _led_set_idle_not_calibrated()
                stop_motor()
                continue

            # STOP global (si no estamos en rutinas bloqueantes)
            if t_upper == "STOP" and state != STATE_RUN:
                calibracion_lista = 0
                sys.stdout.write("STOP\n")
                printed_ready = False
                stop_motor()
                continue

            # ----- CALIBRACION, HOME, ENDPOS, GOTO -----
            if t_upper == "CALIBRACION":
                state = STATE_IDLE
                modo, cfg = None, {}
                stop_motor()
                ok = _calibrar_y_medir_y_home()
                if not ok:
                    # abortado por STOP/END
                    calibracion_lista = 0
                    global_calibrated = False
                    _led_set_idle_not_calibrated()
                    sys.stdout.write("STOP\n")
                continue

            if t_upper == "HOME":
                state = STATE_IDLE
                modo, cfg = None, {}
                stop_motor()
                ok = manual_home()
                if not ok:
                    sys.stdout.write("STOP\n")
                continue

            if t_upper == "ENDPOS":
                state = STATE_IDLE
                modo, cfg = None, {}
                stop_motor()
                ok = manual_endpos()
                if not ok:
                    sys.stdout.write("STOP\n")
                continue

            if t_upper.startswith("GOTO"):
                angle = None
                try:
                    parts = line.replace(":", " ").split()
                    if len(parts) >= 2:
                        angle = float(parts[1])
                except Exception:
                    angle = None

                state = STATE_IDLE
                modo, cfg = None, {}
                stop_motor()
                if angle is not None:
                    manual_goto_angle(angle)
                else:
                    sys.stdout.write("ERROR: formato GOTO inválido. Usa 'GOTO 20' o 'GOTO:20'\n")
                continue

        if not handshaken:
            time.sleep(0.01)
            continue

        # READY inicial
        if state == STATE_IDLE and not printed_ready:
            sys.stdout.write("READY\n")
            inicializar_motor()
            printed_ready = True
        # Envío continuo de resistencia en IDLE
        if state == STATE_IDLE:
            now = time.ticks_ms()
            if time.ticks_diff(now, next_t) >= 0:
                hx_update_nonblocking()
                res_val = hx_get_resistance_value()
                sys.stdout.write(str(["resistance", res_val]) + "\n")
                next_t = time.ticks_add(now, INTERVAL_MS)

        # ================== STATE_IDLE ==================
        if state == STATE_IDLE:
            if not line:
                time.sleep(0.01)
                continue

            t_upper = line.strip().upper()

            if t_upper == "RUN":
                sys.stdout.write("RUN\n")
                continue
            elif t_upper in ("PAUSE", "PAUSA"):
                sys.stdout.write("PAUSE\n")
                state = STATE_PAUSED
                continue

            # Aquí esperamos config JSON para modos
            try:
                cfg = _parse_config(line)
                modo = _mode_number_from_cfg(cfg)
                if modo not in MODE_HANDLERS:
                    sys.stdout.write("ERROR: 'modo' debe ser 1..4\n")
                    continue

                if modo == 2:
                    mode2_state             = 0
                    mode2_rep_count         = 0
                    mode2_idx               = 0
                    mode2_current_angle_est = 0.0
                    mode2_error_flag        = False

                state = STATE_RUN
                next_t = time.ticks_ms()
            except Exception as e:
                sys.stdout.write("ERROR: " + str(e) + "\n")
                time.sleep(0.01)
                continue

        # ================== STATE_RUN ==================
        elif state == STATE_RUN:
            if line:
                t_upper = line.strip().upper()
                if t_upper in ("PAUSE", "PAUSA"):
                    sys.stdout.write("PAUSE\n")
                    state = STATE_PAUSED
                    continue
                elif t_upper == "RUN":
                    sys.stdout.write("RUN\n")
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif t_upper == "STOP":
                    go_home()
                    stop_motor()
                    calibracion_lista = 0
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE
                    modo, cfg, printed_ready = None, {}, False
                    continue

            if modo:
                now = time.ticks_ms()
                if time.ticks_diff(now, next_t) >= 0:
                    MODE_HANDLERS[modo](cfg)
                    next_t = time.ticks_add(now, INTERVAL_MS)
            time.sleep(0)

        # ================== STATE_PAUSED ==================
        elif state == STATE_PAUSED:
            if line:
                t_upper = line.strip().upper()
                if t_upper == "RUN":
                    sys.stdout.write("RUN\n")
                    state = STATE_RUN
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif t_upper == "STOP":
                    go_home()
                    stop_motor()
                    calibracion_lista = 0
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE
                    modo, cfg, printed_ready = None, {}, False
                elif t_upper in ("PAUSE", "PAUSA"):
                    sys.stdout.write("PAUSE\n")
            time.sleep(0.01)

if __name__ == "__main__":
    main()
