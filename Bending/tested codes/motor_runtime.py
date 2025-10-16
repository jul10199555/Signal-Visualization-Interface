# motor_runtime.py — MicroPython (RP2040)
# Encapsula pines, PWM, encoder y lógica por modos.
from machine import Pin, PWM
import time

FORWARD  = "forward"
BACKWARD = "backward"

class MotorRuntime:
    def __init__(self):
        # --- Pines del motor ---
        self.in1 = Pin(16, Pin.OUT)
        self.in2 = Pin(17, Pin.OUT)
        self.enable = PWM(Pin(18))
        self.PWM_FREQ = 1000

        # --- Pines del encoder/Hall ---
        self.encoder_a = Pin(14, Pin.IN, Pin.PULL_UP)
        self.encoder_b = Pin(15, Pin.IN, Pin.PULL_UP)
        self.hall_0    = Pin(2,  Pin.IN, Pin.PULL_UP)   # activo-bajo
        self.hall_90   = Pin(4,  Pin.IN, Pin.PULL_UP)   # activo-bajo

        # --- Constantes/estado básicos ---
        self.RPM_MAX = 30
        self.MARGEN_DEG_PRE_FRENO = 1.0
        self.ANGULO_ENTRE_SENSORES = 88.5
        self.GRADOS_POR_PULSO_FORWARD  = 0.014
        self.GRADOS_POR_PULSO_BACKWARD = 0.014

        self.current_direction = FORWARD
        self.pulse_count = 0
        self.last_state_a = self.encoder_a.value()

        # Variables de modo/objetivos
        self.modo = 1
        self.velocidad_actual = 0
        self.velocidad_constante = 7
        self.velocidad_inicial = 7
        self.velocidad_final = 30
        self.velocidad_escalon = 1
        self.direccion_aumentando_velocidad = True

        self.angulo_constante = 90
        self.angulo_inicial = 0
        self.angulo_final = 90
        self.angulo_escalon = 1
        self.angulo_actual = self.angulo_constante
        self.direccion_aumentando_angulo = True

        self.pulsos_objetivo = 0

        # Keys de telemetría (se ajustan según alias recibidos)
        self.key_velocity = "velocity"
        self.key_angle    = "angle"

        self._inicializar_motor()
        self.encoder_a.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=self._count_pulses)

    # ------------------ HW helpers ------------------
    def _inicializar_motor(self):
        self.in1.value(0); self.in2.value(0)
        self.enable.duty_u16(0)
        self.enable.freq(self.PWM_FREQ)

    def _rpm_a_duty(self, rpm):
        if rpm <= 0: return 0
        if rpm >= self.RPM_MAX: return 65535
        return int((rpm / self.RPM_MAX) * 65535)

    def _control_motor(self, direction, rpm):
        duty = self._rpm_a_duty(rpm)
        self.in1.value(1 if direction == FORWARD else 0)
        self.in2.value(1 if direction == BACKWARD else 0)
        self.enable.duty_u16(duty)
        self.current_direction = direction

    def _stop_motor(self):
        self.enable.duty_u16(0)
        self.in1.value(0); self.in2.value(0)

    def deinit(self):
        self._stop_motor()

    # ------------------ Odometría ------------------
    def _count_pulses(self, _pin):
        state_a = self.encoder_a.value()
        state_b = self.encoder_b.value()
        if state_a != self.last_state_a:
            sentido = -1 if state_a == state_b else 1
            self.pulse_count += sentido
            self.last_state_a = state_a

    def calcular_grados(self):
        gpp_f = self.GRADOS_POR_PULSO_FORWARD
        gpp_b = self.GRADOS_POR_PULSO_BACKWARD
        gpp = (gpp_f + gpp_b) / 2 if (gpp_f > 0 and gpp_b > 0) else 0.014
        return abs(self.pulse_count) * gpp

    def grados_a_pulsos(self, grados, direccion):
        gpp = self.GRADOS_POR_PULSO_FORWARD if direccion == FORWARD else self.GRADOS_POR_PULSO_BACKWARD
        gpp = gpp if gpp > 0 else 0.014
        return max(0, int(grados / gpp))

    # ------------------ Hall / seguridad ------------------
    def _hall_activo_debounced(self, pin, muestras=5, dt_ms=4):
        for _ in range(muestras):
            if pin.value() == 1:
                return False
            time.sleep_ms(dt_ms)
        return True

    def hall0_activo(self):  return self._hall_activo_debounced(self.hall_0)
    def hall90_activo(self): return self._hall_activo_debounced(self.hall_90)

    # ------------------ Configuración / Modo ------------------
    def _val_key(self, cfg, aliases, default_val, default_key):
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

    def update_mode(self, modo, cfg):
        """Configura parámetros internos según M1..M4 con alias ES/EN y defaults."""
        self.modo = int(modo)

        vel_val, vel_key = self._val_key(cfg, ["velocity","velocidad"], 7, "velocity")
        ang_val, ang_key = self._val_key(cfg, ["angle","angulo"],     1, "angle")
        self.key_velocity = vel_key
        self.key_angle    = ang_key

        if self.modo == 1:
            self.velocidad_constante = vel_val
            self.velocidad_actual    = self.velocidad_constante
            self.angulo_constante    = ang_val
            self.angulo_actual       = self.angulo_constante
            self._reset_for_new_leg()

        elif self.modo == 2:
            ia, _  = self._val_key(cfg, ["init_angle","angulo_inicial"], 0,  "init_angle")
            fa, _  = self._val_key(cfg, ["final_angle","angulo_final"], 90, "final_angle")
            sa, _  = self._val_key(cfg, ["step_angle"],                  1,  "step_angle")
            v,  _  = self._val_key(cfg, ["velocity","velocidad"],        7,  "velocity")
            self.angulo_inicial, self.angulo_final, self.angulo_escalon = ia, fa, max(1, sa)
            self.angulo_constante = max(0, min(self.angulo_final, self.angulo_inicial + self.angulo_escalon))
            self.angulo_actual = self.angulo_constante
            self.velocidad_constante = v
            self.velocidad_inicial   = v
            self.velocidad_final     = v
            self.velocidad_escalon   = 1
            self.velocidad_actual    = self.velocidad_constante
            self._reset_for_new_leg()

        elif self.modo == 3:
            a,  _  = self._val_key(cfg, ["angle","angulo"],                1,  "angle")
            iv, _  = self._val_key(cfg, ["init_vel","velocidad_inicial"],  7,  "init_vel")
            fv, _  = self._val_key(cfg, ["final_vel","velocidad_final"],   30, "final_vel")
            sv, _  = self._val_key(cfg, ["step_vel"],                      1,  "step_vel")
            self.angulo_constante = a
            self.angulo_actual = self.angulo_constante
            self.velocidad_inicial = iv
            self.velocidad_final   = fv
            self.velocidad_escalon = max(1, sv)
            self.velocidad_actual  = self.velocidad_inicial
            self.direccion_aumentando_velocidad = True
            self._reset_for_new_leg()

        elif self.modo == 4:
            ia, _  = self._val_key(cfg, ["init_angle","angulo_inicial"], 0,  "init_angle")
            fa, _  = self._val_key(cfg, ["final_angle","angulo_final"], 90, "final_angle")
            sa, _  = self._val_key(cfg, ["step_angle"],                  1,  "step_angle")
            iv, _  = self._val_key(cfg, ["init_vel","velocidad_inicial"], 7,  "init_vel")
            fv, _  = self._val_key(cfg, ["final_vel","velocidad_final"],  30, "final_vel")
            sv, _  = self._val_key(cfg, ["step_vel"],                     1,  "step_vel")
            self.angulo_inicial, self.angulo_final, self.angulo_escalon = ia, fa, max(1, sa)
            self.angulo_actual = self.angulo_inicial
            self.direccion_aumentando_angulo = True
            self.velocidad_inicial, self.velocidad_final = iv, fv
            self.velocidad_escalon = max(1, sv)
            self.velocidad_actual  = self.velocidad_inicial
            self.direccion_aumentando_velocidad = True
            self._reset_for_new_leg()
        else:
            # fallback a M1
            self.velocidad_constante = vel_val
            self.angulo_constante    = ang_val
            self.velocidad_actual    = self.velocidad_constante
            self.angulo_actual       = self.angulo_constante
            self._reset_for_new_leg()

    def _reset_for_new_leg(self):
        self.pulse_count = 0
        self.current_direction = FORWARD
        self._recompute_pulsos_objetivo()
        self._control_motor(self.current_direction, self.velocidad_actual)

    def _recompute_pulsos_objetivo(self):
        objetivo = max(0, self.angulo_actual)
        self.pulsos_objetivo = self.grados_a_pulsos(objetivo, self.current_direction)

    def _prefreno_threshold(self):
        gpp = (self.GRADOS_POR_PULSO_FORWARD + self.GRADOS_POR_PULSO_BACKWARD) / 2 or 0.014
        margen_pulsos = max(1, int(self.MARGEN_DEG_PRE_FRENO / gpp))
        return max(0, self.pulsos_objetivo - margen_pulsos)

    def _cambiar_direccion(self):
        self._stop_motor()
        self.current_direction = BACKWARD if self.current_direction == FORWARD else FORWARD
        self.pulse_count = 0
        self._recompute_pulsos_objetivo()
        if self.modo in (3, 4):
            self.direccion_aumentando_velocidad = not self.direccion_aumentando_velocidad
        self._control_motor(self.current_direction, self.velocidad_actual)

    def _update_velocidad_variable(self):
        if self.modo not in (3,4):
            return
        obj = max(1, self.pulsos_objetivo)
        fr = min(1.0, max(0.0, abs(self.pulse_count) / obj))
        if self.current_direction == FORWARD:
            self.velocidad_actual = self.velocidad_inicial + fr * (self.velocidad_final - self.velocidad_inicial)
        else:
            self.velocidad_actual = self.velocidad_final - fr * (self.velocidad_final - self.velocidad_inicial)

    def tick(self):
        """Paso de control. Devuelve telemetría con las keys esperadas."""
        _ = self.calcular_grados()  # usamos el cálculo como side info

        # 1) Perfíl de velocidad
        if self.modo in (3,4):
            self._update_velocidad_variable()
        elif self.modo in (1,2):
            self.velocidad_actual = self.velocidad_constante

        # 2) Interlocks por Hall
        if self.current_direction == FORWARD and self.hall90_activo():
            self._cambiar_direccion()
        elif self.current_direction == BACKWARD and self.hall0_activo():
            self._cambiar_direccion()

        # 3) Odometría/objetivo
        if abs(self.pulse_count) >= self.pulsos_objetivo:
            self._cambiar_direccion()

        # 4) Pre-freno
        if abs(self.pulse_count) >= self._prefreno_threshold():
            rpm_cmd = max(2, int(self.velocidad_actual / 3))
        else:
            rpm_cmd = int(self.velocidad_actual)

        self._control_motor(self.current_direction, rpm_cmd)

        # 5) Telemetría
        return {
            self.key_angle:    float(self.calcular_grados()),
            self.key_velocity: float(rpm_cmd)
        }
