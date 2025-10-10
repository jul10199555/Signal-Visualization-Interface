# main.py — Raspberry Pi Pico (RP2040) / MicroPython
# USB CDC — sin flush, sin ast
# Reglas clave:
#   - Los nombres de salida coinciden con los nombres de entrada (si se dieron).
#   - Si un parámetro no se envía, se usa default y se imprime con nombre canónico en inglés.

import sys, time

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
        # intenta int; si no, deja string (evita fallar)
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
STATE_IDLE, STATE_RUN, STATE_PAUSED = 0, 1, 2
INTERVAL_MS = 150

# --- Utilidad: obtener valor y nombre a imprimir según entrada/alias ---
def _get_val_and_key(cfg: dict, aliases, default_val, default_key):
    """
    Busca en cfg las claves en 'aliases' (lista de alias en orden de prioridad).
    Si encuentra una, devuelve (valor_int, alias_encontrado).
    Si no, devuelve (default_val, default_key).
    """
    for k in aliases:
        if k in cfg:
            try:
                return int(cfg[k]), k
            except:
                # si viene como string numérico
                try:
                    return int(str(cfg[k]).strip()), k
                except:
                    pass
    return default_val, default_key

# --- Acciones por modo (los nombres de salida respetan el key de entrada) ---
# Modo 1: velocity, angle (defaults 7, 1)
def mode1_action(cfg):
    v, kv = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")
    a, ka = _get_val_and_key(cfg, ["angle", "angulo"], 1, "angle")
    sys.stdout.write(str(["modo", 1, kv, v, ka, a]) + "\n")

# Modo 2: init_angle, final_angle, step_angle, velocity (defaults 0,90,1,7)
def mode2_action(cfg):
    ia, kia = _get_val_and_key(cfg, ["init_angle", "angulo_inicial"], 0, "init_angle")
    fa, kfa = _get_val_and_key(cfg, ["final_angle", "angulo_final"], 90, "final_angle")
    sa, ksa = _get_val_and_key(cfg, ["step_angle"], 1, "step_angle")
    v,  kv  = _get_val_and_key(cfg, ["velocity", "velocidad"], 7, "velocity")
    sys.stdout.write(str(["modo", 2, kia, ia, kfa, fa, ksa, sa, kv, v]) + "\n")

# Modo 3: angle, init_vel, final_vel, step_vel (defaults 1,7,30,1)
def mode3_action(cfg):
    a,  ka  = _get_val_and_key(cfg, ["angle", "angulo"], 1, "angle")
    iv, kiv = _get_val_and_key(cfg, ["init_vel", "velocidad_inicial"], 7, "init_vel")
    fv, kfv = _get_val_and_key(cfg, ["final_vel", "velocidad_final"], 30, "final_vel")
    sv, ksv = _get_val_and_key(cfg, ["step_vel"], 1, "step_vel")
    sys.stdout.write(str(["modo", 3, ka, a, kiv, iv, kfv, fv, ksv, sv]) + "\n")

# Modo 4: init_angle, final_angle, step_angle, init_vel, final_vel, step_vel
#         (defaults 0,90,1,7,30,1)
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
    return None

# --- Máquina principal ---
def main():
    state = STATE_IDLE
    modo, cfg = None, {}
    printed_ready = False
    next_t = time.ticks_ms()

    while True:
        if state == STATE_IDLE and not printed_ready:
            sys.stdout.write("READY\n")
            printed_ready = True

        if state == STATE_IDLE:
            line = _readline_nonblocking()
            if not line:
                time.sleep(0.01)
                continue

            cmd = _classify_command(line)
            if cmd == "STOP":
                sys.stdout.write("STOP\n"); printed_ready = False; continue
            elif cmd == "RUN":
                sys.stdout.write("RUN\n"); continue
            elif cmd == "PAUSE":
                sys.stdout.write("PAUSE\n"); state = STATE_PAUSED; continue

            # Config (dict JSON)
            try:
                cfg = _parse_config(line)
                if "modo" not in cfg:
                    sys.stdout.write("ERROR: falta 'modo'\n"); continue
                modo = int(cfg["modo"])
                if modo not in MODE_HANDLERS:
                    sys.stdout.write("ERROR: 'modo' debe ser 1..4\n"); continue
                state = STATE_RUN
                printed_ready = True
                next_t = time.ticks_ms()
            except Exception as e:
                sys.stdout.write("ERROR: " + str(e) + "\n")
                time.sleep(0.01)
                continue

        elif state == STATE_RUN:
            # Comandos en RUN
            line = _readline_nonblocking()
            if line:
                cmd = _classify_command(line)
                if cmd == "PAUSE":
                    sys.stdout.write("PAUSE\n"); state = STATE_PAUSED; continue
                elif cmd == "RUN":
                    sys.stdout.write("RUN\n")
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif cmd == "STOP":
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE; modo, cfg, printed_ready = None, {}, False; continue

            # Emitir payload según modo
            if modo:
                now = time.ticks_ms()
                if time.ticks_diff(now, next_t) >= 0:
                    MODE_HANDLERS[modo](cfg)
                    next_t = time.ticks_add(now, INTERVAL_MS)
            time.sleep(0.003)

        elif state == STATE_PAUSED:
            # Comandos en PAUSED
            line = _readline_nonblocking()
            if line:
                cmd = _classify_command(line)
                if cmd == "RUN":
                    sys.stdout.write("RUN\n")
                    state = STATE_RUN
                    next_t = time.ticks_add(time.ticks_ms(), INTERVAL_MS)
                elif cmd == "STOP":
                    sys.stdout.write("STOP\n")
                    state = STATE_IDLE
                    modo, cfg, printed_ready = None, {}, False
                elif cmd == "PAUSE":
                    sys.stdout.write("PAUSE\n")
            time.sleep(0.01)

if __name__ == "__main__":
    main()
