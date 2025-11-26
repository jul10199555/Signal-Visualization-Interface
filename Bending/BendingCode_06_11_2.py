# main.py — Raspberry Pi Pico (RP2040) / MicroPython
# Protocolo compatible con tu SerialInterface:
#   PC -> "0\n"  | Pico -> "0\n"  | luego imprime "READY\n"

import sys, time

#* ---------------------------- NUEVO -----------------------------
from machine import Pin, PWM
import time

# === Pines del motor ===
in1 = Pin(16, Pin.OUT)
in2 = Pin(17, Pin.OUT)
enable = PWM(Pin(18))

# === Pines del encoder y sensores Hall ===
encoder_pin_a = Pin(14, Pin.IN, Pin.PULL_UP)
encoder_pin_b = Pin(15, Pin.IN, Pin.PULL_UP)
hall_sensor_0_a = Pin(2, Pin.IN, Pin.PULL_UP)
hall_sensor_90 = Pin(4, Pin.IN, Pin.PULL_UP)

# === Constantes ===
RPM_BUSQUEDA = 6                  # Velocidad segura (baja) para buscar el Hall
FACTOR_TIMEOUT_BUSQUEDA = 1.5     # 1.5x la distancia odométrica estimada entre sensores
PWM_FREQ = 1000
FORWARD = "forward"
BACKWARD = "backward"
FACTOR_APRENDIZAJE = 0.01
RPM_MAX = 30

# Margen para pre-freno dependiente de la velocidad
MARGEN_DEG_PRE_FRENO_BASE = 1.0      # grados
MARGEN_DEG_PRE_FRENO_K    = 0.35     # grados por RPM (ajusta a prueba)

def margen_deg_prefreno(vel_rpm):
    """Devuelve el margen angular antes del frenado, ajustado a la velocidad."""
    return MARGEN_DEG_PRE_FRENO_BASE + MARGEN_DEG_PRE_FRENO_K * max(vel_rpm, 0)

# === Variables de estado ===
pulse_count = 0
last_state_a = encoder_pin_a.value()
current_direction = FORWARD
sistema_activo = False
calibracion_lista = 0
GRADOS_POR_PULSO_FORWARD = 0.014
GRADOS_POR_PULSO_BACKWARD = 0.014
pulsos_objetivo = 0
factor_inercia = 3 # Valor inicial
offset_angulo_objetivo = 0.0  # Corrección dinámica del ángulo
ANGULO_ENTRE_SENSORES = 88.5  # Ajusta
VELOCIDAD_CALIBRACION = 7 # rpm
VELOCIDAD_MEDICION = 7     # rpm
VELOCIDAD_CICLOS =7       # rpm 
angulo_referencial = 0.0
angulo_referencial_anterior = 0.0
grados_actuales=0
# === Configuración de modos de operación ===
# Modos permitidos: "constante" o "variable"
modo_velocidad = "variable"   # opciones: "constante" o "variable"
modo_angulo = "constante"      # opciones: "constante" o "variable"
# === Configuración de ángulo ===
angulo_constante = 90
angulo_inicial = 0
angulo_final = 90
angulo_escalon = 5
angulo_actual=0
#==== configuracion de velocidad ===#
velocidad_escalon = 1
velocidad_actual = 7
velocidad_inicial = 7

# === Funciones ===
def grados_a_pulsos(grados, direccion):
    if direccion == FORWARD:
        return int(grados / GRADOS_POR_PULSO_FORWARD)
    elif direccion == BACKWARD:
        return int(grados / GRADOS_POR_PULSO_BACKWARD)
    else:
        raise ValueError("Dirección desconocida en grados_a_pulsos")

def inicializar_motor():
    in1.value(0)
    in2.value(0)
    enable.duty_u16(0)
    enable.freq(PWM_FREQ)

def rpm_a_duty(rpm):
    return min(int((rpm / RPM_MAX) * 65535), 65535)

def control_motor(direction, rpm):
    global current_direction
    duty = rpm_a_duty(rpm)
    in1.value(1 if direction == FORWARD else 0)
    in2.value(1 if direction == BACKWARD else 0)
    enable.duty_u16(duty)
    current_direction = direction
'''
def stop_motor():
    
    enable.duty_u16(0)
    in1.value(0)
    in2.value(0)
    print("Motor detenido")'''
def stop_motor():
    # Freno activo breve para suprimir avance por inercia (ajusta según tu driver)
    enable.duty_u16(65535)
    in1.value(1); in2.value(1)   # en muchos drivers esto aplica freno (cortocircuito controlado)
    time.sleep_ms(20)
    # Liberar
    enable.duty_u16(0)
    in1.value(0); in2.value(0)
    print("Motor detenido")

def count_pulses(pin):
    global pulse_count, last_state_a, angulo_referencial
    state_a = encoder_pin_a.value()
    state_b = encoder_pin_b.value()

    if state_a != last_state_a:
        # Determinar sentido físico del giro por cuadratura
        sentido = -1 if state_a == state_b else 1

        pulse_count += sentido

        # Actualizar ángulo referencial neto desde el origen
        angulo_referencial += sentido * (
            GRADOS_POR_PULSO_FORWARD if current_direction == FORWARD else GRADOS_POR_PULSO_BACKWARD
        )

        last_state_a = state_a

encoder_pin_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=count_pulses)

def calcular_grados():
    if current_direction == FORWARD:
        return abs(pulse_count * GRADOS_POR_PULSO_FORWARD)
    else:
        return abs(pulse_count * GRADOS_POR_PULSO_BACKWARD)

def corregir_dinamicamente(grados, pulsos):
    global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD
    if pulsos == 0:
        return
    error = angulo_constante - grados
    ajuste = FACTOR_APRENDIZAJE * error / pulsos
    if current_direction == FORWARD:
        GRADOS_POR_PULSO_FORWARD += ajuste
    else:
        GRADOS_POR_PULSO_BACKWARD += ajuste

'''def cambiar_direccion():
    global pulse_count, pulsos_objetivo, offset_angulo_objetivo
    global current_direction
    grados = calcular_grados()
    print(f"\033[1mGrados girados: {grados:.2f}°\033[0m")
    #print(f"Ángulo referencial acumulado: {angulo_referencial:.2f}°")

    corregir_dinamicamente(grados, abs(pulse_count))

    nueva_direccion = BACKWARD if current_direction == FORWARD else FORWARD
    current_direction = nueva_direccion

    actualizar_angulo()
    actualizar_velocidad()
    alternar_direccion_velocidad_variable()
    imprimir_modo_actual()'''
def cambiar_direccion():
    global pulse_count, pulsos_objetivo, offset_angulo_objetivo, current_direction
    grados = calcular_grados()
    print(f"\033[1mGrados girados: {grados:.2f}°\033[0m")

    # Aprendizaje fino de grados por pulso
    corregir_dinamicamente(grados, abs(pulse_count))

    # Alineación fina al objetivo antes de invertir sentido
    alineacion_fina_post_sensor()

    nueva_direccion = BACKWARD if current_direction == FORWARD else FORWARD
    current_direction = nueva_direccion

    actualizar_angulo()
    actualizar_velocidad()
    alternar_direccion_velocidad_variable()
    imprimir_modo_actual()

    # ------- Interlock: no arranques contra un final activo -------
    if nueva_direccion == FORWARD and hall90_activo():
        print("Final 90° activo; esperando liberación antes de arrancar FORWARD...")
        esperar_liberacion(hall_sensor_90)
    elif nueva_direccion == BACKWARD and hall0_activo():
        print("Final 0° activo; esperando liberación antes de arrancar BACKWARD...")
        esperar_liberacion(hall_sensor_0_a)
    # --------------------------------------------------------------

    if nueva_direccion == FORWARD:
        pulsos_objetivo = int(angulo_actual / GRADOS_POR_PULSO_FORWARD)
    else:
        pulsos_objetivo = int(angulo_actual / GRADOS_POR_PULSO_BACKWARD)

    pulse_count = 0
    control_motor(nueva_direccion, velocidad_actual)
    print("Cambio de dirección a:", nueva_direccion)
    
def realizar_ajuste_fino_si_es_necesario(grados_girados, sensor):
    global factor_inercia, offset_angulo_objetivo

    diferencia = angulo_constante + offset_angulo_objetivo - grados_girados
    if diferencia < 0.3:
        return  # Muy cerca: no se requiere ajuste fino

    if modo_velocidad == "variable":
        if sensor == "90":
            # En sensor 90° siempre se puede ajustar en modo variable
            pulsos_max = 200
            pulsos_min = 30
            pulsos_ajuste = int((velocidad_actual - velocidad_inicial) * (pulsos_min - pulsos_max) / (velocidad_final - velocidad_inicial) + pulsos_max)
        elif sensor == "0":
            # Solo permitir si la velocidad inicial es mayor que la final (inversión de comportamiento)
            if velocidad_inicial > velocidad_final:
                pulsos_max = 200
                pulsos_min = 30
                pulsos_ajuste = int((velocidad_actual - velocidad_final) * (pulsos_min - pulsos_max) / (velocidad_inicial - velocidad_final) + pulsos_max)
            else:
                return  # No se permite ajuste fino en sensor 0° si no se cumple la condición
        else:
            return
    else:
        pulsos_ajuste = 120  # Valor fijo en modo constante

    print(f"Alineación fina: avanzando {pulsos_ajuste} pulsos adicionales a {velocidad_actual} RPM (factor_inercia: {factor_inercia:.3f})")

    pulsos_iniciales = pulse_count
    control_motor(current_direction, velocidad_actual)
    while abs(pulse_count - pulsos_iniciales) < pulsos_ajuste:
        time.sleep(0.001)
    stop_motor()
    print("Alineación fina completada")

    # Ajuste de offset y factor de inercia
    nuevos_grados = calcular_grados()
    error = angulo_constante - nuevos_grados
    if abs(error) < 20:
        offset_angulo_objetivo += 0.3 * error
        offset_angulo_objetivo = max(0, min(offset_angulo_objetivo, 15))
        print(f"Offset de ángulo ajustado: {offset_angulo_objetivo:.2f}°")

        ajuste = 0.1 * error / velocidad_actual
        factor_inercia += ajuste
        factor_inercia = max(0.5, min(factor_inercia, 10))
        print(f"Nuevo factor_inercia: {factor_inercia:.3f}")
        
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
    grados_por_pulso = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    angulo = abs(pulse_count) * grados_por_pulso
    print(f"Ángulo medido entre sensores (90° → 0°): {angulo:.2f}°")
    return angulo

def calibrar_motor():
    global pulse_count, GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD
    global current_direction, calibracion_lista, pulsos_objetivo

    print("Iniciando calibración...")
    pulse_count = 0
    ciclos = 8
    forward_pulses = []
    backward_pulses = []

    direccion = FORWARD
    direccion_inicial = direccion
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

    prom_forward = sum(forward_pulses) / len(forward_pulses)
    prom_backward = sum(backward_pulses) / len(backward_pulses)

    GRADOS_POR_PULSO_FORWARD = ANGULO_ENTRE_SENSORES / prom_forward
    GRADOS_POR_PULSO_BACKWARD = ANGULO_ENTRE_SENSORES / prom_backward

    print("Calibración completada.")
    print(f"Promedio FORWARD: {prom_forward}, BACKWARD: {prom_backward}")
    print(f"GRADOS_POR_PULSO_FORWARD inicial: {GRADOS_POR_PULSO_FORWARD:.6f}")
    print(f"GRADOS_POR_PULSO_BACKWARD inicial: {GRADOS_POR_PULSO_BACKWARD:.6f}")

    nueva_direccion = BACKWARD if direccion_inicial == FORWARD else FORWARD
    current_direction = nueva_direccion

    # Calcular pulsos objetivo inicial
    angulo = angulo_constante
    if current_direction == FORWARD:
        pulsos_objetivo = int(angulo / GRADOS_POR_PULSO_FORWARD)
    else:
        pulsos_objetivo = int(angulo / GRADOS_POR_PULSO_BACKWARD)

    pulse_count = 0
    control_motor(current_direction, 7)
    calibracion_lista = 1
    print("Motor encendido")
    print("Inicio en dirección:", current_direction)
    
    return True

def actualizar_angulo():
    global angulo_actual, direccion_aumentando_angulo

    if modo_angulo == "constante":
        angulo_actual = angulo_constante
    else:  # variable
        if direccion_aumentando_angulo:
            angulo_actual += angulo_escalon
            if angulo_actual >= angulo_final:
                angulo_actual = angulo_final
                direccion_aumentando_angulo = False
        else:
            angulo_actual -= angulo_escalon
            if angulo_actual <= angulo_inicial:
                angulo_actual = angulo_inicial
                direccion_aumentando_angulo = True
                
def alineacion_fina_post_sensor():
    global factor_inercia, offset_angulo_objetivo

    direccion = current_direction
    rpm = VELOCIDAD_CICLOS if modo_velocidad == "constante" else velocidad_actual

    angulo_faltante = angulo_constante + offset_angulo_objetivo - calcular_grados()
    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
    pulsos_correccion = int(abs(angulo_faltante) / (gpp or 0.014))
    print(f"Alineación fina: avanzando {pulsos_correccion} pulsos adicionales a {rpm} RPM (factor_inercia: {factor_inercia:.3f})")

    pulsos_iniciales = pulse_count
    control_motor(direccion, rpm)

    while abs(pulse_count - pulsos_iniciales) < pulsos_correccion:
        time.sleep(0.001)

    stop_motor()
    print("Alineación fina completada")

    grados = calcular_grados()
    error = angulo_constante - grados

    if abs(error) < 20:
        offset_angulo_objetivo += 0.3 * error
        offset_angulo_objetivo = max(0, min(offset_angulo_objetivo, 15))
        print(f"Offset de ángulo ajustado: {offset_angulo_objetivo:.2f}°")

        ajuste = 0.1 * error / rpm
        factor_inercia += ajuste
        factor_inercia = max(0.5, min(factor_inercia, 10))
        print(f"Nuevo factor_inercia: {factor_inercia:.3f}")

def actualizar_velocidad():
    global velocidad_actual, direccion_aumentando_velocidad

    if modo_velocidad != "variable":
        velocidad_actual = velocidad_constante
        return

    if direccion_aumentando_velocidad:
        velocidad_actual += velocidad_escalon
        if velocidad_actual >= velocidad_final:
            velocidad_actual = velocidad_final
            direccion_aumentando_velocidad = False  # ← aquí el cambio importante
    else:
        velocidad_actual -= velocidad_escalon
        if velocidad_actual <= velocidad_inicial:
            velocidad_actual = velocidad_inicial
            direccion_aumentando_velocidad = True   # ← y aquí también

def alternar_direccion_velocidad_variable():
    global direccion_aumentando_velocidad

    if modo_velocidad == "variable":
        direccion_aumentando_velocidad = not direccion_aumentando_velocidad
        
def imprimir_modo_actual():
    print(f"\n--- MODO ACTUAL ---")
    print(f"Ángulo: {modo_angulo.upper()}")

    if modo_velocidad == "constante":
        print(f"Velocidad: CONSTANTE")
        print(f"→ Velocidad RPM: {velocidad_actual:.2f}")
    else:
        # Determinar si está aumentando o disminuyendo en función de dirección y objetivos
        if current_direction == FORWARD:
            comportamiento = "aumentando" if velocidad_final > velocidad_inicial else "disminuyendo"
        else:
            comportamiento = "disminuyendo" if velocidad_final > velocidad_inicial else "aumentando"

        print(f"Velocidad: VARIABLE ({comportamiento})")
        print(f"Velocidad actual: {velocidad_actual:.0f} RPM, paso de {velocidad_escalon} RPM, objetivo entre {velocidad_inicial} y {velocidad_final}")
# ====== Utilidades de seguridad y finales de carrera ======
def _hall_activo_debounced(pin, muestras=5, dt_ms=4):
    """Activo-bajo con PULL_UP. Requiere nivel bajo estable durante 'muestras'."""
    for _ in range(muestras):
        if pin.value() == 1:
            return False
        time.sleep(dt_ms / 1000)
    return True

def hall0_activo():
    return _hall_activo_debounced(hall_sensor_0_a)

def hall90_activo():
    return _hall_activo_debounced(hall_sensor_90)
# === Lectura genérica de Hall (activo-bajo) ===
def leer_hall(pin, con_antirebote=True, muestras=5, dt_ms=4):
    """
    Devuelve True si el sensor Hall está ACTIVO (nivel bajo con PULL_UP).
    - con_antirebote=True usa la misma lógica de _hall_activo_debounced().
    - Si lo pones en False, hace una lectura instantánea (sin filtro).
    """
    if con_antirebote:
        return _hall_activo_debounced(pin, muestras=muestras, dt_ms=dt_ms)
    # Lectura directa (sin antirrebote): activo-bajo
    return pin.value() == 0

def esperar_liberacion(pin, debounce_ms=20):
    """Espera a que el Hall pase a inactivo (alto) de forma estable."""
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
    base = abs(pulse_count)
    control_motor(direccion, rpm_busqueda)
    while True:
        if pin_objetivo.value() == 0:   # hall activo-bajo
            stop_motor()
            return True
        if abs(pulse_count) - base >= timeout_pulsos:
            stop_motor()
            return False
        time.sleep(0.001)

def go_home(rpm_busqueda=VELOCIDAD_MEDICION):
    """
    Regresa con seguridad al 0° (Hall 0). 
    - Si ya estás sobre el Hall 0, se libera primero y luego se ingresa de nuevo.
    - Usa buscar_hall() con timeout basado en la odometría estimada.
    Deja: pulse_count=0, current_direction=BACKWARD parado en 0°.
    """
    global pulse_count, current_direction

    # 1) Si ya está activo el Hall 0, libera un poco hacia FORWARD y regresa
    if hall0_activo():
        print("Hall 0° ya activo. No se requiere movimiento.")

     # --- 2) Buscar Hall 0 en BACKWARD (1 segundo) ---
    velocidad_busqueda = max(7, rpm_busqueda)
    print("Buscando Hall 0 (BACKWARD, 1s)...")
    start_time = time.time()
    control_motor(BACKWARD, rpm_busqueda)
    found = False
    last_dir = BACKWARD  # Registrar dirección actual
    while time.time() - start_time < 1.0:
        if leer_hall(hall_sensor_0_a):
            found = True
            break
        time.sleep(0.001)
    stop_motor()

    # --- 3) Si no se encontró, intentar hacia FORWARD (2 segundos) ---
    if not found:
        print("WARN: No se encontró Hall 0 yendo hacia atrás. Intentando hacia adelante (2s)...")
        start_time = time.time()
        control_motor(FORWARD, rpm_busqueda)
        last_dir = FORWARD
        while time.time() - start_time < 2.0:
            if leer_hall(hall_sensor_0_a):
                found = True
                break
            time.sleep(0.001)
        stop_motor()

    # --- 4) Verificar resultado final ---
    if not found:
        print("WARN: No se encontró Hall 0 en ninguna dirección dentro del tiempo límite.")
        stop_motor()
        return False

    # --- 5) Asegurar HOME ---
    pulse_count = 0
    current_direction = last_dir  # Guarda la dirección donde realmente se encontró el Hall
    print("Home alcanzado (0°).")
    return True


def go_to_angle(angle, rpm=None):
    """
    Lleva SIEMPRE primero a 0° (Home) y luego al ángulo solicitado.
    - angle se recorta a [0, ANGULO_ENTRE_SENSORES].
    - Usa pre-freno por pulsos cerca del objetivo.
    - Respeta el final de carrera de 90°.
    """
    global current_direction, pulse_count, GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD

    # Normalizar parámetros
    if rpm is None:
        rpm = VELOCIDAD_CICLOS
    angle = max(0.0, min(float(angle), ANGULO_ENTRE_SENSORES))

    # A) Ir a HOME primero
    if not go_home(rpm_busqueda=VELOCIDAD_MEDICION):
        print("ERROR: No se pudo ir a HOME; abortando go_to_angle.")
        return False

    # B) Si el ángulo pedido es 0°, ya terminamos
    if angle <= 0.0:
        print("Ángulo destino = 0°. Ya en HOME.")
        return True

    # C) Avanzar hacia el ángulo destino (FORWARD → 90°)
    current_direction = FORWARD
    pulse_count = 0

    # Objetivo y márgenes
    pulsos_obj = grados_a_pulsos(angle, FORWARD)
    gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2 or 0.014
    margen_pulsos = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
    pulsos_pre_freno = max(0, pulsos_obj - margen_pulsos)
    rpm_pre_freno = max(3, int(rpm / 3))

    print(f"Desplazando a {angle:.2f}° → objetivo {pulsos_obj} pulsos (gpp≈{gpp:.4f}).")
    control_motor(FORWARD, rpm)

    try:
        while True:
            # Si nos acercamos al límite de 90°, respeta Hall 90
            if hall90_activo():
                stop_motor()
                print("Hall 90° detectado antes de alcanzar el objetivo; detenido por seguridad.")
                return False

            # ¿Llegó?
            if abs(pulse_count) >= pulsos_obj:
                stop_motor()
                print(f"Ángulo {angle:.2f}° alcanzado. Pulsos={abs(pulse_count)}.")
                return True

            # Pre-freno
            if abs(pulse_count) >= pulsos_pre_freno:
                control_motor(FORWARD, rpm_pre_freno)
            else:
                control_motor(FORWARD, rpm)

            time.sleep(0.001)

    except KeyboardInterrupt:
        print("go_to_angle interrumpido por usuario.")
        stop_motor()
        return False

#* ---------------------------- END NUEVO -----------------------------

# --- Entrada no bloqueante ---
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

# --- Parser (ujson si disponible; fallback dict simple) ---
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

# --- Estados ---
STATE_IDLE, STATE_RUN, STATE_PAUSED, STATE_CALIBRATING = 0, 1, 2, 3
INTERVAL_MS = 150

# --- Utilidad clave/valor con alias ---
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

pulse_count = 0
angulo_referencial = 0.0
current_direction = FORWARD

velocidad_constante = 7
angulo_constante = 90
        
# --- Acciones por modo ---

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
    # Estado limpio
    pulse_count = 0
    angulo_referencial = 0.0
    angulo_referencial_anterior = 0.0
    current_direction = FORWARD
    calibracion_lista = 1
    sys.stdout.write("Motor en Home (0°)\n")
    
def mode1_action(cfg):
    try:
        global calibracion_lista, pulse_count, angulo_referencial, angulo_referencial_anterior
        global current_direction, velocidad_constante, angulo_constante, pulsos_objetivo
        global direccion_aumentando_velocidad, direccion_aumentando_angulo
        global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD, velocidad_actual, modo_velocidad, modo_angulo

        # Leer parámetros con alias y valores por defecto
        v,  kv = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")
        a,  ka = _get_val_and_key(cfg, ["angle", "angulo"],       1, "angle")
        
        # Siempre calibrar al entrar al modo (y medir ángulo entre sensores)
        _calibrar_y_medir_y_home()
        
        # --- Seguridad después de calibración ---
        stop_motor()                 # Asegurar que motor esté detenido
        pulse_count = 0
        angulo_referencial = 0.0
        angulo_referencial_anterior = 0.0
        current_direction = FORWARD
        sys.stdout.write("Motor en Home (0°)\n")

        # Actualizar consignas globales
        modo_velocidad = "constante"
        modo_angulo = "constante"
        velocidad_actual = v
        velocidad_constante = v
        angulo_constante = a
        direccion_aumentando_velocidad = False
        direccion_aumentando_angulo = False
        
        # Pre-frenos dependientes de velocidad
        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2 or 0.014
        margen_deg = margen_deg_prefreno(velocidad_constante)
        margen_pulsos = max(1, int(margen_deg / gpp))
        pulsos_pre_freno  = max(0, grados_a_pulsos(angulo_constante, current_direction) - margen_pulsos)
        pulsos_pre_freno2 = max(0, grados_a_pulsos(angulo_constante, current_direction) - int(0.3 * margen_pulsos))
        rpm_pre_freno  = max(2, int(velocidad_constante / 4))
        rpm_pre_freno2 = max(1, int(velocidad_constante / 6))
        
        # ---- MODO 1: Ángulo constante, velocidad constante ----
        # Primero objetivo, luego márgenes:
        ''' pulsos_objetivo = grados_a_pulsos(angulo_constante, current_direction)

        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
        margen_pulsos = max(1, int(MARGEN_DEG_PRE_FRENO / (gpp or 0.014)))
        pulsos_pre_freno = max(0, pulsos_objetivo - margen_pulsos)
        rpm_pre_freno = max(3, int(velocidad_constante / 3))'''

        # Estados de sensores y odometría
        if current_direction == FORWARD:
            if abs(pulse_count) >= pulsos_objetivo:
                stop_motor()
                alineacion_fina_post_sensor()
                cambiar_direccion()
                pulse_count = 0
            elif hall90_activo():
                stop_motor()
                print("Sensor 90° detectado. Alineación fina y cambio de dirección.")
                realizar_ajuste_fino_si_es_necesario(calcular_grados(), "90")
                alineacion_fina_post_sensor()
                cambiar_direccion()
                pulse_count = 0
            else:
                if abs(pulse_count) >= pulsos_pre_freno2:
                    control_motor(current_direction, rpm_pre_freno2)
                elif abs(pulse_count) >= pulsos_pre_freno:
                    control_motor(current_direction, rpm_pre_freno)
                else:
                    control_motor(current_direction, velocidad_constante)
        else: #BACKWARD
            if abs(pulse_count) >= pulsos_objetivo:
                stop_motor()
                alineacion_fina_post_sensor()
                cambiar_direccion()
                pulse_count = 0
            elif hall0_activo():
                stop_motor()
                print("Sensor 0° detectado. Alineación fina y cambio de dirección.")
                realizar_ajuste_fino_si_es_necesario(calcular_grados(), "0")
                alineacion_fina_post_sensor()
                pulse_count = 0
                cambiar_direccion()
            else:
                if abs(pulse_count) >= pulsos_pre_freno2:
                    control_motor(current_direction, rpm_pre_freno2)
                elif abs(pulse_count) >= pulsos_pre_freno:
                    control_motor(current_direction, rpm_pre_freno)
                else:
                    control_motor(current_direction, velocidad_constante)

        grados_actuales = calcular_grados()
        sys.stdout.write(str(["modo", 1, kv, velocidad_constante, ka, grados_actuales]) + "\n")
    except Exception as e:
        stop_motor()
        go_home()
        stop_motor()
        sys.stdout.write("ERROR en modo 1: " + str(e) + "\n")

def mode2_action(cfg):
    global calibracion_lista, pulse_count, angulo_referencial, angulo_referencial_anterior
    global current_direction, velocidad_constante, angulo_constante, pulsos_objetivo
    global direccion_aumentando_velocidad, direccion_aumentando_angulo
    global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD, angulo_inicial, angulo_final, angulo_escalon, angulo_actual

    ia, kia = _get_val_and_key(cfg, ["init_angle", "angulo_inicial"], 0, "init_angle")
    fa, kfa = _get_val_and_key(cfg, ["final_angle", "angulo_final"], 90, "final_angle")
    sa, ksa = _get_val_and_key(cfg, ["step_angle"], 1, "step_angle")
    v,  kv  = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")

    # Siempre calibrar al entrar al modo (y medir ángulo entre sensores)
    _calibrar_y_medir_y_home()
    # --- Seguridad después de calibración ---
    stop_motor()                 # Asegurar que motor esté detenido
    pulse_count = 0
    angulo_referencial = 0.0
    angulo_referencial_anterior = 0.0
    current_direction = FORWARD
    sys.stdout.write("Motor en Home (0°)\n")
    
    angulo_inicial = ia
    angulo_final = fa
    angulo_escalon = sa
    velocidad_constante = v
    direccion_aumentando_velocidad = False
    direccion_aumentando_angulo = True
    
    try:
        if calibracion_lista and abs(pulse_count) >= pulsos_objetivo:
            stop_motor()
            alineacion_fina_post_sensor()
            cambiar_direccion()
        if modo_angulo == "variable":
            if direccion_aumentando_angulo:
                angulo_actual += angulo_escalon
                if angulo_actual >= angulo_final:
                    angulo_actual = angulo_final
                    direccion_aumentando_angulo = False
                    current_direction = BACKWARD
            else:
                angulo_actual -= angulo_escalon
                if angulo_actual <= angulo_inicial:
                    angulo_actual = angulo_inicial
                    direccion_aumentando_angulo = True
                    current_direction = FORWARD
            pulsos_objetivo = grados_a_pulsos(angulo_actual, current_direction)
            print(f"Ángulo actual: {angulo_actual}°, Velocidad constante: {velocidad_constante} RPM")

        # Control simple a velocidad constante (puedes agregar el doble pre-freno aquí también si lo deseas)
        control_motor(current_direction, velocidad_constante)

        # Alineaciones si toca fin de carrera
        if current_direction == FORWARD and hall90_activo():
            stop_motor()
            realizar_ajuste_fino_si_es_necesario(calcular_grados(), "90")
            alineacion_fina_post_sensor()
            cambiar_direccion()
        elif current_direction == BACKWARD and hall0_activo():
            stop_motor()
            realizar_ajuste_fino_si_es_necesario(calcular_grados(), "0")
            alineacion_fina_post_sensor()
            cambiar_direccion()

        sys.stdout.write(str(["modo", 2, kv, v, "angle", angulo_actual]) + "\n")
    except Exception as e:
        stop_motor()
        sys.stdout.write("ERROR en modo 2: " + str(e) + "\n")




def mode3_action(cfg):
    global calibracion_lista, pulse_count, angulo_referencial, angulo_referencial_anterior
    global current_direction, velocidad_constante, angulo_constante, pulsos_objetivo
    global direccion_aumentando_velocidad, direccion_aumentando_angulo
    global GRADOS_POR_PULSO_FORWARD, GRADOS_POR_PULSO_BACKWARD, velocidad_actual, modo_velocidad, modo_angulo, velocidad_escalon, velocidad_final, velocidad_inicial
    a,  ka  = _get_val_and_key(cfg, ["angle", "angulo"], 1, "angle")
    iv, kiv = _get_val_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel")
    fv, kfv = _get_val_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel")
    sv, ksv = _get_val_and_key(cfg, ["step_vel"], 1, "step_vel")

    # Siempre calibrar al entrar al modo (y medir ángulo entre sensores)
    if not calibracion_lista:
        _calibrar_y_medir_y_home()
    #--- Seguridad después de calibración ---
    stop_motor()    # Asegurar que motor esté detenido
    pulse_count = 0
    angulo_referencial = 0.0
    angulo_referencial_anterior = 0.0
    current_direction = FORWARD
    sys.stdout.write("Motor en Home (0°)\n")
    
    velocidad_inicial = iv
    velocidad_final = fv
    velocidad_escalon = sv
    angulo_final = a
    angulo_inicial = 0
    direccion_aumentando_velocidad = True
    direccion_aumentando_angulo = False
    
    try:
        delta_base_deg = abs(angulo_final - angulo_inicial)
        try:
            piso_back = MARGEN_DEG_SUELO_BACKWARD if current_direction == BACKWARD else 0.0
        except NameError:
            piso_back = 0.0
        delta_tramo_deg = max(0.0, delta_base_deg - piso_back)
        pulsos_objetivo = max(1, grados_a_pulsos(delta_tramo_deg, current_direction))

        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2 or 0.014
        try:
            margen_base = MARGEN_DEG_PRE_FRENO_BASE
        except NameError:
            margen_base = 1.0
        margen_deg_dir = (margen_base + 0.3) if current_direction == BACKWARD else margen_base
        margen_pulsos  = max(1, int(margen_deg_dir / gpp))
        pulsos_pre_freno = max(0, pulsos_objetivo - margen_pulsos)
        rpm_pre_freno = max(2, int(velocidad_final / 3))

        if abs(pulse_count) >= pulsos_objetivo:
            stop_motor()
            alineacion_fina_post_sensor()
            cambiar_direccion()
            pulse_count = 0
        elif (hall90_activo() if current_direction == FORWARD else hall0_activo()):
            stop_motor()
            if current_direction == FORWARD:
                print("Sensor 90° detectado.")
                realizar_ajuste_fino_si_es_necesario(calcular_grados(), "90")
            else:
                print("Sensor 0° detectado.")
                realizar_ajuste_fino_si_es_necesario(calcular_grados(), "0")
            alineacion_fina_post_sensor()
            cambiar_direccion()
            pulse_count = 0
        else:
            fraccion = 0.0 if pulsos_objetivo <= 0 else min(1.0, max(0.0, abs(pulse_count) / pulsos_objetivo))
            if current_direction == FORWARD:
                velocidad_actual = velocidad_inicial + fraccion * (velocidad_final - velocidad_inicial)
            else:
                velocidad_actual = velocidad_final - fraccion * (velocidad_final - velocidad_inicial)
            if abs(pulse_count) >= pulsos_pre_freno:
                control_motor(current_direction, min(velocidad_actual, rpm_pre_freno))
            else:
                control_motor(current_direction, velocidad_actual)

        sys.stdout.write(str(["modo", 3, ka, a, "velocidad", velocidad_actual]) + "\n")
    except Exception as e:
        stop_motor()
        sys.stdout.write("ERROR en modo 3: " + str(e) + "\n")
        

def mode4_action(cfg):
    ia, kia = _get_val_and_key(cfg, ["init_angle", "angulo_inicial"], 0, "init_angle")
    fa, kfa = _get_val_and_key(cfg, ["final_angle", "angulo_final"], 90, "final_angle")
    sa, ksa = _get_val_and_key(cfg, ["step_angle"], 1, "step_angle")
    iv, kiv = _get_val_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel")
    fv, kfv = _get_val_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel")
    sv, ksv = _get_val_and_key(cfg, ["step_vel"], 1, "step_vel")
    sys.stdout.write(str(["modo", 4, kia, ia, kfa, fa, ksa, sa, kiv, iv, kfv, fv, ksv, sv]) + "\n")

MODE_HANDLERS = {1: mode1_action, 2: mode2_action, 3: mode3_action, 4: mode4_action}

# --- Comandos ---
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
    # aceptar "modo" o "mode"; números como 1 o strings "Mode 1"
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

        # Handshake y END siempre
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
                continue

        if not handshaken:
            time.sleep(0.01)
            continue

        if state == STATE_IDLE and not printed_ready:
            sys.stdout.write("READY\n")
            inicializar_motor()
            # sys.stdout.write("CALIBRATING\n"); 
            # if calibrar_motor():
            #     sys.stdout.write("CALIBRATED\n")
            printed_ready = True

        if state == STATE_IDLE:
            if not line:
                time.sleep(0.01); continue

            cmd = _classify_command(line)
            if cmd == "STOP":
                calibracion_lista = 0
                sys.stdout.write("STOP\n"); printed_ready = False; continue
            elif cmd == "RUN":
                sys.stdout.write("RUN\n"); continue
            elif cmd == "PAUSE":
                sys.stdout.write("PAUSE\n"); state = STATE_PAUSED; continue

            try:
                cfg = _parse_config(line)
                modo = _extract_mode(cfg)
                if modo not in MODE_HANDLERS:
                    sys.stdout.write("ERROR: 'modo' debe ser 1..4\n"); continue
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
                    go_home()
                    stop_motor()
                    sys.stdout.write("PAUSE\n"); state = STATE_PAUSED; continue
                elif cmd == "RUN":
                    sys.stdout.write("RUN\n")
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif cmd == "STOP":
                    go_home()
                    stop_motor()
                    calibracion_lista = 0
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE; modo, cfg, printed_ready = None, {}, False; continue

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
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE
                    modo, cfg, printed_ready = None, {}, False
                elif cmd == "PAUSE":
                    go_home()
                    stop_motor()
                    sys.stdout.write("PAUSE\n")
            time.sleep(0.01)
            
        # elif state == STATE_CALIBRATING:
        #     if line:
        #         cmd = _classify_command(line)
        #         if cmd == "STOP":
        #             sys.stdout.write("STOP\n")
        #             state = STATE_IDLE
        #             modo, cfg, printed_ready = None, {}, False
        #         elif cmd == "PAUSE":
        #             sys.stdout.write("PAUSE\n")
        #         else:
        #             sys.stdout.write("CALIBRATING\n")
                    
        #     time.sleep(0.01)

if __name__ == "__main__":
    main()

