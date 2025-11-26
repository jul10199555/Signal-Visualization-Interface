# main.py — Raspberry Pi Pico (RP2040) / MicroPython
# Protocolo compatible:
#   PC -> "0\n"  | Pico -> "0\n"  | luego imprime "READY\n"

import sys, time
from machine import Pin, PWM

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
# NOTA: asumo que en tu código real tienes definido encoder_pin_a a partir de noencoder_pin_a
encoder_pin_a   = noencoder_pin_a

hall_sensor_0_a = Pin(2, Pin.IN, Pin.PULL_UP)   # HOME 0°
hall_sensor_90  = Pin(4, Pin.IN, Pin.PULL_UP)   # 90°

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

ANGULO_ENTRE_SENSORES = 88.5   # corrige si mides otro valor

FACTOR_APRENDIZAJE   = 0.0     # DESACTIVADO para evitar drift
MARGEN_DEG_PRE_FRENO = 1.0     # margen para pre-freno

MIN_GPP = 0.001
MAX_GPP = 0.2

# Factor de seguridad al bajar sin Hall0
SAFETY_FACTOR_DOWN = 1.5

# ============================================================
#   ESTADO GLOBAL
# ============================================================
pulse_count       = 0
last_state_a      = encoder_pin_a.value()
current_direction = FORWARD

GRADOS_POR_PULSO_FORWARD  = 0.014   # inicial, se recalcula en calibración
GRADOS_POR_PULSO_BACKWARD = 0.014

calibracion_lista = 0       # 0 ⇒ se debe calibrar antes de correr modos

angulo_constante     = 90
velocidad_constante  = 7
angulo_referencial   = 0.0
angulo_referencial_anterior = 0.0

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

def stop_motor():
    enable.duty_u16(0)
    in1.value(0)
    in2.value(0)
    print("Motor detenido")

def count_pulses(pin):
    global pulse_count, last_state_a, angulo_referencial
    state_a = encoder_pin_a.value()
    state_b = encoder_pin_b.value()
    if state_a != last_state_a:
        sentido = -1 if state_a == state_b else 1
        pulse_count += sentido

        # ángulo neto desde el origen (solo para logging)
        if current_direction == FORWARD:
            angulo_referencial += sentido * GRADOS_POR_PULSO_FORWARD
        else:
            angulo_referencial += sentido * GRADOS_POR_PULSO_BACKWARD

        last_state_a = state_a

encoder_pin_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=count_pulses)

def grados_a_pulsos(grados, direccion):
    if grados < 0:
        grados = 0
    if grados > ANGULO_ENTRE_SENSORES:
        grados = ANGULO_ENTRE_SENSORES
    if direccion == FORWARD:
        gpp = GRADOS_POR_PULSO_FORWARD
    else:
        gpp = GRADOS_POR_PULSO_BACKWARD
    if gpp <= 0:
        gpp = 0.014
    pulsos = int(grados / gpp)
    return max(1, pulsos)

def calcular_grados():
    if current_direction == FORWARD:
        return abs(pulse_count * GRADOS_POR_PULSO_FORWARD)
    else:
        return abs(pulse_count * GRADOS_POR_PULSO_BACKWARD)

def corregir_dinamicamente(grados, pulsos):
    """
    Corrección suave de GRADOS_POR_PULSO.
    FACTOR_APRENDIZAJE = 0 ⇒ desactivado (no hace nada).
    """
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
#   HALLS
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

def esperar_liberacion(pin, debounce_ms=20):
    while True:
        if pin.value() == 1:
            time.sleep(debounce_ms / 1000)
            if pin.value() == 1:
                break
        time.sleep(0.005)

def estimar_pulsos_entre_sensores():
    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        return 99999
    return int(ANGULO_ENTRE_SENSORES / gpp)

def buscar_hall(pin_objetivo, direccion, rpm_busqueda, timeout_pulsos):
    """
    Avanza en 'direccion' a baja velocidad hasta detectar 'pin_objetivo' (activo-bajo),
    con límite de 'timeout_pulsos' desde la entrada a la función.
    Retorna True si detectó el Hall, False si se alcanzó el timeout.
    """
    global pulse_count
    base = pulse_count  # FIX: usar diferencia absoluta real, no abs()-base
    control_motor(direccion, rpm_busqueda)
    while True:
        if pin_objetivo.value() == 0:
            stop_motor()
            return True
        if abs(pulse_count - base) >= timeout_pulsos:  # FIX timeout correcto
            stop_motor()
            return False
        time.sleep(0.001)

def go_home(rpm_busqueda=VELOCIDAD_MEDICION):
    """
    Regresa con seguridad al 0° (Hall 0).
    Deja: pulse_count=0, current_direction=BACKWARD parado en 0°.
    """
    global pulse_count, current_direction

    # Si ya está activo el Hall 0, libera un poco hacia FORWARD y regresa
    if hall0_activo():
        small_release = max(5, estimar_pulsos_entre_sensores() // 10)
        base = pulse_count  # FIX: medir desplazamiento real
        control_motor(FORWARD, max(3, rpm_busqueda))
        while abs(pulse_count - base) < small_release:  # FIX
            time.sleep(0.001)
        stop_motor()
        esperar_liberacion(hall_sensor_0_a)

    timeout = int(1.5 * max(estimAR := estimar_pulsos_entre_sensores(), 50))
    found = buscar_hall(hall_sensor_0_a, BACKWARD, max(3, rpm_busqueda), timeout)
    if not found:
        print("WARN: No se encontró Hall 0 dentro del timeout.")
        stop_motor()
        return False

    stop_motor()
    pulse_count = 0
    current_direction = BACKWARD
    print("Home alcanzado (0°).")
    return True

# ============================================================
#   CALIBRACIÓN Y MEDICIÓN DE ÁNGULO ENTRE SENSORES
# ============================================================
def medir_angulo_entre_sensores():
    global pulse_count

    print("→ Midiendo ángulo real entre sensores Hall...")

    # 1. Buscar primero el sensor de 90° hacia adelante
    control_motor(FORWARD, VELOCIDAD_MEDICION)
    while hall_sensor_90.value() == 1:
        time.sleep(0.001)
    stop_motor()
    time.sleep(0.2)
    print("Sensor 90° detectado (inicio de medición)")

    # 2. Medir desde aquí hacia el sensor de 0° en dirección opuesta
    pulse_count = 0
    control_motor(BACKWARD, VELOCIDAD_MEDICION)
    while hall_sensor_0_a.value() == 1:
        time.sleep(0.001)
    stop_motor()
    print("Sensor 0° detectado (fin de medición)")

    # 3. Calcular el ángulo medido
    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    if gpp <= 0:
        gpp = 0.014
    angulo = abs(pulse_count) * gpp
    print(f"Ángulo medido entre sensores (90° → 0°): {angulo:.2f}°")
    return angulo

def calibrar_motor():
    global pulse_count, GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD

    print("Iniciando calibración (ciclos entre Hall 0° y 90°)...")
    pulse_count = 0
    ciclos = 8
    forward_pulses = []
    backward_pulses = []

    direccion = FORWARD
    sensor_actual = hall_sensor_0_a
    sensor_siguiente = hall_sensor_90

    for i in range(ciclos + 1):
        print(f"→ Ciclo {i+1}: moviendo {direccion}")
        pulse_count = 0
        control_motor(direccion, VELOCIDAD_CALIBRACION)

        while sensor_siguiente.value() == 1:
            time.sleep(0.001)

        time.sleep(0.02)
        stop_motor()

        if i > 0:
            pulsos = abs(pulse_count)
            if direccion == FORWARD:
                forward_pulses.append(pulsos)
            else:
                backward_pulses.append(pulsos)
            print(f"Pulsos en ciclo {i+1}: {pulsos}")
        else:
            print(f"(Ignorado) Pulsos en ciclo {i+1}: {abs(pulse_count)}")

        direccion = BACKWARD if direccion == FORWARD else FORWARD
        sensor_actual, sensor_siguiente = sensor_siguiente, sensor_actual
        time.sleep(0.5)

    prom_forward  = sum(forward_pulses) / len(forward_pulses)
    prom_backward = sum(backward_pulses) / len(backward_pulses)

    GRADOS_POR_PULSO_FORWARD  = ANGULO_ENTRE_SENSORES / prom_forward
    GRADOS_POR_PULSO_BACKWARD = ANGULO_ENTRE_SENSORES / prom_backward

    # Clamps de seguridad
    GRADOS_POR_PULSO_FORWARD  = min(max(GRADOS_POR_PULSO_FORWARD,  MIN_GPP), MAX_GPP)
    GRADOS_POR_PULSO_BACKWARD = min(max(GRADOS_POR_PULSO_BACKWARD, MIN_GPP), MAX_GPP)

    print("Calibración completada.")
    print(f"Promedio FORWARD: {prom_forward}, BACKWARD: {prom_backward}")
    print(f"GRADOS_POR_PULSO_FORWARD inicial: {GRADOS_POR_PULSO_FORWARD:.6f}")
    print(f"GRADOS_POR_PULSO_BACKWARD inicial: {GRADOS_POR_PULSO_BACKWARD:.6f}")

    stop_motor()
    pulse_count = 0
    return True

def _calibrar_y_medir_y_home():
    """Secuencia estándar: calibrar -> medir ángulo entre sensores -> volver a 0° y parar."""
    global calibracion_lista, pulse_count, angulo_referencial, angulo_referencial_anterior, current_direction

    calibrar_motor()
    try:
        medir_angulo_entre_sensores()
    except Exception as e:
        print("Aviso: medir_angulo_entre_sensores() falló:", e)

    go_home()
    stop_motor()

    # Estado limpio en 0°
    pulse_count = 0
    angulo_referencial = 0.0
    angulo_referencial_anterior = 0.0
    current_direction = FORWARD
    calibracion_lista = 1
    sys.stdout.write("Motor en Home (0°)\n")

# ============================================================
#   MODO 1: Ángulo fijo, velocidad fija
#   SUBE con encoder, BAJA hasta Hall0 (con rescate por encoder si falla)
# ============================================================
def mode1_action(cfg):
    """
    Lógica:
    - Subida (FORWARD):
        * Usa encoder para llegar al ángulo objetivo.
        * Pre-freno cerca del objetivo.
        * Si llega a Hall90 antes de objetivo, invierte igual por seguridad.
    - Bajada (BACKWARD):
        * Baja hasta que se active Hall0.
        * Si NO se activa Hall0 y se recorren demasiados pulsos:
            - Detiene.
            - Invierte y sube la MISMA cantidad de pulsos medida por el encoder.
            - Se detiene arriba, listo para siguiente ciclo.
    """
    global calibracion_lista, pulse_count, angulo_referencial, angulo_referencial_anterior
    global current_direction, velocidad_constante, angulo_constante

    try:
        v, kv = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")
        a, ka = _get_val_and_key(cfg, ["angle", "angulo"], 90, "angle")

        # Saturar ángulo
        if a < 0:
            a = 0
        if a > ANGULO_ENTRE_SENSORES:
            a = int(ANGULO_ENTRE_SENSORES)

        # Primera entrada al modo → calibrar y dejar en 0°
        if not calibracion_lista:
            angulo_constante    = a
            velocidad_constante = v

            _calibrar_y_medir_y_home()

            current_direction = FORWARD
            pulse_count       = 0
            control_motor(current_direction, velocidad_constante)

            grados_actuales = 0.0
            sys.stdout.write(str(["modo", 1, kv, velocidad_constante, ka, grados_actuales]) + "\n")
            return

        # --- CICLO NORMAL ---
        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
        if gpp <= 0:
            gpp = 0.014

        pulsos_obj = grados_a_pulsos(angulo_constante, FORWARD)
        margen_pulsos    = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
        pulsos_pre_freno = max(0, pulsos_obj - margen_pulsos)
        rpm_pre_freno    = max(3, int(velocidad_constante / 3))

        pulsos_abs = abs(pulse_count)

        # ---------- FORWARD: de 0° hacia angulo_constante ----------
        if current_direction == FORWARD:
            # Límite duro Hall90
            if hall90_activo():
                print("Modo1: Hall 90° detectado. Invirtiendo a BACKWARD.")
                stop_motor()
                grados = calcular_grados()
                corregir_dinamicamente(grados, pulsos_abs)
                # FIX: reiniciar contador al iniciar bajada
                pulse_count = 0
                current_direction = BACKWARD
                control_motor(current_direction, velocidad_constante)

            # Objetivo por encoder alcanzado
            elif pulsos_abs >= pulsos_obj:
                print("Modo1: objetivo encoder alcanzado (UP). Invirtiendo a BACKWARD.")
                stop_motor()
                grados = calcular_grados()
                corregir_dinamicamente(grados, pulsos_abs)
                # FIX: reiniciar contador al iniciar bajada
                pulse_count = 0
                current_direction = BACKWARD
                control_motor(current_direction, velocidad_constante)

            else:
                # Pre-freno cerca del objetivo
                if pulsos_abs >= pulsos_pre_freno:
                    control_motor(FORWARD, rpm_pre_freno)
                else:
                    control_motor(FORWARD, velocidad_constante)

            # Estimación de ángulo (clamp al objetivo)
            grados_actuales = calcular_grados()
            if grados_actuales > angulo_constante:
                grados_actuales = float(angulo_constante)

        # ---------- BACKWARD: de angulo_constante hacia 0° ----------
        else:
            # 1) Caso ideal: Hall0 detectado
            if hall0_activo():
                print("Modo1: Hall 0° detectado. Invirtiendo a FORWARD (reset a 0°).")
                stop_motor()
                pulse_count = 0
                grados_actuales = 0.0
                current_direction = FORWARD
                control_motor(current_direction, velocidad_constante)

            # 2) Caso anómalo: NO hay Hall0 y ya recorrió demasiados pulsos
            else:
                pulsos_span     = grados_a_pulsos(ANGULO_ENTRE_SENSORES, BACKWARD)
                max_pulsos_down = int(SAFETY_FACTOR_DOWN * pulsos_span)

                if pulsos_abs >= max_pulsos_down:
                    print("Modo1: BAJANDO sin Hall0. Activando rescate por encoder.")
                    stop_motor()
                    pulsos_fallo = pulsos_abs  # lo que recorrió bajando sin ver Hall0

                    # Subir la MISMA cantidad de pulsos
                    pulse_count = 0
                    current_direction = FORWARD
                    control_motor(FORWARD, velocidad_constante)
                    while abs(pulse_count) < pulsos_fallo:
                        time.sleep(0.001)
                    stop_motor()

                    # Dejar arriba, listo para siguiente ciclo
                    current_direction = FORWARD
                    pulse_count = 0
                    grados_actuales = float(angulo_constante)  # aproximado

                else:
                    # 3) Caso normal: seguir bajando hacia Hall0
                    control_motor(BACKWARD, velocidad_constante)
                    grados_tmp = angulo_constante - pulsos_abs * gpp
                    if grados_tmp < 0:
                        grados_tmp = 0.0
                    grados_actuales = grados_tmp

        # Reporte al host
        sys.stdout.write(str(["modo", 1, kv, velocidad_constante, ka, grados_actuales]) + "\n")

    except Exception as e:
        stop_motor()
        go_home()
        stop_motor()
        sys.stdout.write("ERROR en modo 1: " + str(e) + "\n")

# ============================================================
#   MODO 2, 3, 4: PLACEHOLDERS (no mueven motor)
# ============================================================
def mode2_action(cfg):
    ia, kia = _get_val_and_key(cfg, ["init_angle", "angulo_inicial"], 0, "init_angle")
    fa, kfa = _get_val_and_key(cfg, ["final_angle", "angulo_final"], 90, "final_angle")
    sa, ksa = _get_val_and_key(cfg, ["step_angle"], 1, "step_angle")
    v,  kv  = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")
    # NO mover motor en esta versión
    sys.stdout.write(str(["modo", 2, kia, ia, kfa, fa, ksa, sa, kv, v]) + "\n")

def mode3_action(cfg):
    a,  ka  = _get_val_and_key(cfg, ["angle", "angulo"], 1, "angle")
    iv, kiv = _get_val_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel")
    fv, kfv = _get_val_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel")
    sv, ksv = _get_val_and_key(cfg, ["step_vel"], 1, "step_vel")
    sys.stdout.write(str(["modo", 3, ka, a, kiv, iv, kfv, fv, ksv, sv]) + "\n")

def mode4_action(cfg):
    ia, kia = _get_val_and_key(cfg, ["init_angle", "angulo_inicial"], 0, "init_angle")
    fa, kfa = _get_val_and_key(cfg, ["final_angle", "angulo_final"], 90, "final_angle")
    sa, ksa = _get_val_and_key(cfg, ["step_angle"], 1, "step_angle")
    iv, kiv = _get_val_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel")
    fv, kfv = _get_val_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel")
    sv, ksv = _get_val_and_key(cfg, ["step_vel"], 1, "step_vel")
    sys.stdout.write(str(["modo", 4, kia, ia, kfa, fa, ksa, sa, kiv, iv, kfv, fv, ksv, sv]) + "\n")

MODE_HANDLERS = {
    1: mode1_action,
    2: mode2_action,
    3: mode3_action,
    4: mode4_action,
}

# ============================================================
#   PROTOCOLO / MAIN LOOP
# ============================================================
try:
    import uselect
    _poll = uselect.poll()
    _poll.register(sys.stdin, uselect.POLLIN)
except:
    _poll = None

def _readline_nonblocking():
    if not _poll:
        return None
    ev = _poll.poll(0)
    if not ev:
        return None
    line = sys.stdin.readline()
    return line.strip() if line else None

try:
    import ujson as _json
except:
    _json = None

def _normalize_to_json_like(s: str) -> str:
    return s.strip().replace("'", '"')

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
        try:
            d[k] = int(v)
        except:
            d[k] = v
    return d

def _parse_config(s: str) -> dict:
    s_norm = _normalize_to_json_like(s)
    if _json:
        try:
            obj = _json.loads(s_norm)
            if isinstance(obj, dict):
                return obj
        except:
            pass
    return _manual_parse_dict(s_norm)

STATE_IDLE, STATE_RUN, STATE_PAUSED = 0, 1, 2
INTERVAL_MS = 150

def _get_val_and_key(cfg: dict, aliases, default_val, default_key):
    for k in aliases:
        if k in cfg:
            try:
                return int(cfg[k]), k
            except:
                try:
                    return int(str(cfg[k]).strip()), k
                except:
                    pass
    return default_val, default_key

def _classify_command(line):
    if not line:
        return None
    t = line.strip().upper()
    if t in ("PAUSE", "PAUSA"):
        return "PAUSE"
    if t == "RUN":
        return "RUN"
    if t == "STOP":
        return "STOP"
    if t == "END":
        return "END"
    if t == "0":
        return "HANDSHAKE"
    return None

def _extract_mode(cfg):
    mode_raw = cfg.get("modo", cfg.get("mode", None))
    if mode_raw is None:
        raise ValueError("falta 'modo' o 'mode'")
    if isinstance(mode_raw, str):
        try:
            import ure as re
        except:
            import re
        m = re.search(r"(\d+)", mode_raw)
        if not m:
            raise ValueError("'mode/modo' debe contener 1..4")
        return int(m.group(1))
    return int(mode_raw)

def main():
    global calibracion_lista
    state = STATE_IDLE
    modo, cfg = None, {}
    printed_ready = False
    handshaken = False
    next_t = time.ticks_ms()

    while True:
        line = _readline_nonblocking()

        # Handshake / END
        if line:
            cmd = _classify_command(line)
            if cmd == "HANDSHAKE":
                sys.stdout.write("0\n")
                handshaken = True
                printed_ready = False
                continue
            elif cmd == "END":
                sys.stdout.write("STOP\n")
                state = STATE_IDLE
                modo, cfg = None, {}
                printed_ready = False
                handshaken = False
                calibracion_lista = 0
                continue

        if not handshaken:
            time.sleep(0.01)
            continue

        if state == STATE_IDLE and not printed_ready:
            sys.stdout.write("READY\n")
            inicializar_motor()
            printed_ready = True

        if state == STATE_IDLE:
            if not line:
                time.sleep(0.01)
                continue

            cmd = _classify_command(line)
            if cmd == "STOP":
                calibracion_lista = 0
                sys.stdout.write("STOP\n")
                printed_ready = False
                continue
            elif cmd == "RUN":
                sys.stdout.write("RUN\n")
                continue
            elif cmd == "PAUSE":
                sys.stdout.write("PAUSE\n")
                state = STATE_PAUSED
                continue

            try:
                cfg = _parse_config(line)
                modo = _extract_mode(cfg)
                if modo not in MODE_HANDLERS:
                    sys.stdout.write("ERROR: 'modo' debe ser 1..4\n")
                    continue

                # NUEVO modo ⇒ forzar recalibración la próxima vez que se llame modeX_action
                calibracion_lista = 0
                state = STATE_RUN
                next_t = time.ticks_ms()
            except Exception as e:
                sys.stdout.write("ERROR: " + str(e) + "\n")
                time.sleep(0.01)
                continue

        elif state == STATE_RUN:
            if line:
                cmd = _classify_command(line)
                if cmd == "PAUSE":
                    sys.stdout.write("PAUSE\n")
                    state = STATE_PAUSED
                    continue
                elif cmd == "RUN":
                    sys.stdout.write("RUN\n")
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif cmd == "STOP":
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

        elif state == STATE_PAUSED:
            if line:
                cmd = _classify_command(line)
                if cmd == "RUN":
                    sys.stdout.write("RUN\n")
                    state = STATE_RUN
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif cmd == "STOP":
                    go_home()
                    stop_motor()
                    calibracion_lista = 0
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE
                    modo, cfg, printed_ready = None, {}, False
                elif cmd == "PAUSE":
                    sys.stdout.write("PAUSE\n")
            time.sleep(0.01)

if __name__ == "__main__":
    main()

#MODO 1 OK