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
MARGEN_DEG_PRE_FRENO = 1.0

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
ANGULO_ENTRE_SENSORES = 88.5  # Ajusta este valor según medición o pruebas
VELOCIDAD_CALIBRACION = 6  # rpm
VELOCIDAD_MEDICION = 6     # rpm
VELOCIDAD_CICLOS =7       # rpm o lo que quieras
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

def cambiar_direccion():
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
    ciclos = 4
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
    control_motor(current_direction, velocidad_constante)
    calibracion_lista = 1
    print("Motor encendido")
    print("Inicio en dirección:", current_direction)

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
    pulsos_correccion = int(abs(angulo_faltante) / ((GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD)/2))
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

# === Inicio del sistema ===
inicializar_motor()

# Inicializar ángulo actual dependiendo del modo
if modo_angulo == "constante":
    angulo_actual = angulo_constante
else:
    angulo_actual = angulo_inicial
direccion_aumentando_angulo = True  # bandera para subir o bajar ángulo
# === Configuración de velocidad ===
velocidad_constante = VELOCIDAD_CICLOS
velocidad_inicial = 6
velocidad_final = 30
velocidad_escalon = 1
velocidad_actual = velocidad_constante
direccion_aumentando_velocidad = True
# --- Determinar modo actual automáticamente ---
if modo_angulo == "constante" and modo_velocidad == "variable":
    modo_actual = "angulo_constante_velocidad_variable"
elif modo_angulo == "constante" and modo_velocidad == "constante":
    modo_actual = "angulo_constante_velocidad_constante"
elif modo_angulo == "variable" and modo_velocidad == "constante":
    modo_actual = "angulo_variable_velocidad_constante"
else:
    modo_actual = "modo_no_definido"
    print("Modo no definido. Verifica las variables modo_angulo y modo_velocidad.")

# Calcular número total de pasos de velocidad (opcional usar luego para lógica avanzada)
num_variaciones = int(abs(velocidad_final - velocidad_inicial) / velocidad_escalon)
print(f"Número total de variaciones de velocidad: {num_variaciones}")

# === Inicio del movimiento ===
calibrar_motor()
ANGULO_ENTRE_SENSORES = medir_angulo_entre_sensores()  # ← se actualiza tras calibración
# --- Seguridad después de calibración ---
stop_motor()  # Asegurar que motor esté detenido
pulse_count = 0
grados_actuales = 0
angulo_referencial = 0.0
current_direction = FORWARD
velocidad_actual = 0

print("Motor en Home (0°). Presiona Enter para iniciar modo constante...")
input()  # Espera confirmación manual antes de arrancar
# === Inicialización automática según el modo seleccionado ===
if modo_angulo == "constante":
    angulo_actual = angulo_constante
else:
    angulo_actual = angulo_inicial
    direccion_aumentando_angulo = True  # Solo se usa en modo variable
if modo_velocidad == "constante":
    velocidad_actual = velocidad_constante
else:
    velocidad_actual = velocidad_inicial
    direccion_aumentando_velocidad = True  # Solo se usa en modo variable
current_direction = FORWARD  # Dirección inicial común para todos los modos
# === Bucle principal ===
try:
    while True:
        grados_actuales = calcular_grados()
        gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
        margen_pulsos = int(MARGEN_DEG_PRE_FRENO / gpp)
        pulsos_pre_freno = max(0, pulsos_objetivo - margen_pulsos)

        # MODO 1: Ángulo constante, velocidad constante
        if modo_actual == "angulo_constante_velocidad_constante":
            pulsos_objetivo = grados_a_pulsos(angulo_constante, current_direction)
            # --- Pre-freno por pulsos: umbral y RPM reducida ---
            gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2
            margen_pulsos = max(1, int(MARGEN_DEG_PRE_FRENO / gpp))
            pulsos_pre_freno = max(0, pulsos_objetivo - margen_pulsos)
            rpm_pre_freno = max(3, int(velocidad_constante / 3))
            # (Opcional) monitoreo
            #print(f"Estado sensor 90°: {'Detectado' if hall_sensor_90.value() == 0 else 'No detectado'}")
            #print(f"Estado sensor 0°: {'Detectado' if hall_sensor_0_a.value() == 0 else 'No detectado'}")

            # ---- Prioridad: finales de carrera (interlocks duros) ----
            if current_direction == FORWARD:
                if abs(pulse_count) >= pulsos_objetivo:
                     stop_motor()
                     cambiar_direccion()
                     pulse_count = 0
                elif hall90_activo():
                     stop_motor()
                     print("Sensor 90° detectado. Cambio automático de dirección.")
                     # (Opcional) alineación fina SOLO después del Hall:
                     # alineacion_fina_post_sensor()
                     # Nota: NO esperar liberación aquí con el motor parado
                     cambiar_direccion()
                     pulse_count = 0
                else:
                     # Pre-freno cuando nos acercamos al objetivo
                     if abs(pulse_count) >= pulsos_pre_freno:
                         control_motor(current_direction, rpm_pre_freno)
                     else:
                         control_motor(current_direction, velocidad_constante)
            elif current_direction == BACKWARD:
                if abs(pulse_count) >= pulsos_objetivo:
                     stop_motor()
                     cambiar_direccion()
                     pulse_count = 0
                elif hall0_activo():
                     stop_motor()
                     print("Sensor 0° detectado. Cambio automático de dirección.")
                     desfase = angulo_referencial - angulo_referencial_anterior
                     #print(f"Desfase del ciclo: {desfase:.2f}°")
                     angulo_referencial_anterior = angulo_referencial
                     # (Opcional) alineación fina SOLO después del Hall:
                     # alineacion_fina_post_sensor()
                     # Nota: NO esperar liberación aquí con el motor parado
                     cambiar_direccion()
                     pulse_count = 0
                else:
                    # Pre-freno cuando nos acercamos al objetivo
                    if abs(pulse_count) >= pulsos_pre_freno:
                        control_motor(current_direction, rpm_pre_freno)
                    else:
                        control_motor(current_direction, velocidad_constante)
        # MODO 2: Ángulo constante, velocidad variable (con inversión por Δángulo de tramo)
        elif modo_actual == "angulo_constante_velocidad_variable":
            # --- 1) Distancia objetivo del tramo (Δ en grados) ---
            delta_base_deg = abs(angulo_final - angulo_inicial)

            # Piso opcional solo en BACKWARD para no acercarse demasiado a 0°
            try:
                piso_back = MARGEN_DEG_SUELO_BACKWARD if current_direction == BACKWARD else 0.0
            except NameError:
                piso_back = 0.0

            # Δ del tramo vigente (no negativa)
            delta_tramo_deg = max(0.0, delta_base_deg - piso_back)

            # --- 2) Objetivo del tramo en pulsos ---
            # Como pulse_count se resetea a 0 tras cambiar_direccion(), el objetivo es Δ (no un ángulo absoluto)
            pulsos_objetivo = max(1, grados_a_pulsos(delta_tramo_deg, current_direction))

            # --- 3) Pre-freno por pulsos (margen dependiente de dirección) ---
            gpp = (GRADOS_POR_PULSO_FORWARD + GRADOS_POR_PULSO_BACKWARD) / 2 or 0.014
            try:
                margen_base = MARGEN_DEG_PRE_FRENO
            except NameError:
                margen_base = 1.0  # fallback si no definiste la constante

            # Un pequeño extra de margen en BACKWARD ayuda a no rozar el Hall de 0°
            margen_deg_dir   = (margen_base + 0.3) if current_direction == BACKWARD else margen_base
            margen_pulsos    = max(1, int(margen_deg_dir / gpp))
            pulsos_pre_freno = max(0, pulsos_objetivo - margen_pulsos)

            # RPM de pre-freno (baja pero con par suficiente)
            rpm_pre_freno = max(2, int(velocidad_final / 3))

            # --- 4) Inversión por odometría + interlocks de seguridad ---
            if abs(pulse_count) >= pulsos_objetivo:
                stop_motor()
                cambiar_direccion()
                pulse_count = 0

            elif (hall90_activo() if current_direction == FORWARD else hall0_activo()):
                stop_motor()
                if current_direction == FORWARD:
                    print("Sensor 90° detectado. Cambio automático de dirección.")
                else:
                    print("Sensor 0° detectado. Cambio automático de dirección.")
                cambiar_direccion()
                pulse_count = 0

            else:
                # --- 5) Perfil de velocidad variable por progreso relativo del tramo ---
                # Progreso relativo 0..1 medido por pulsos del tramo (robusto al reseteo de pulse_count)
                fraccion = 0.0 if pulsos_objetivo <= 0 else min(1.0, max(0.0, abs(pulse_count) / pulsos_objetivo))

                # Interpolación de velocidad: en FORWARD sube, en BACKWARD baja
                if current_direction == FORWARD:
                    velocidad_actual = velocidad_inicial + fraccion * (velocidad_final - velocidad_inicial)
                else:
                    velocidad_actual = velocidad_final - fraccion * (velocidad_final - velocidad_inicial)

                # Pre-freno cerca del objetivo del tramo
                if abs(pulse_count) >= pulsos_pre_freno:
                    control_motor(current_direction, min(velocidad_actual, rpm_pre_freno))
                else:
                    control_motor(current_direction, velocidad_actual)
        # MODO 3: Ángulo variable, velocidad constante
        elif modo_actual == "angulo_variable_velocidad_constante":
            if calibracion_lista and abs(pulse_count) >= pulsos_objetivo:
                stop_motor()
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

            control_motor(current_direction, velocidad_constante)

        time.sleep(0.01)

except KeyboardInterrupt:
    print("Programa detenido por usuario")
    stop_motor()

finally:
    stop_motor()
    in1.value(0)
    in2.value(0)
    enable.duty_u16(0)
    print("Pines desactivados")

