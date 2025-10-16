# presets.py
from __future__ import annotations
from pathlib import Path
import json
from typing import Dict, Any

# Presets "de fábrica" (editables por ti en este .py)
# Claves esperadas por tu firmware / compose_command_json
BUILTIN_PRESETS: Dict[str, Dict[str, Any]] = {
    # ----- MODO 1 (ángulo y velocidad constantes) -----
    "Demo M1 7rpm @ 10°": {"modo": 1, "angle": 10, "speed": 7},
    "Lento M1 7rpm @ 1°": {"modo": 1, "angle": 1,  "speed": 7},

    # ----- MODO 2 (ángulo variable, velocidad constante) -----
    "Barrido A 0→90 step 5 @ 10rpm": {
        "modo": 2, "velocity": 10, "init_angle": 0, "final_angle": 90, "step_angle": 5
    },

    # ----- MODO 3 (ángulo constante, velocidad variable) -----
    "Escalera V 7→30 step 3 @ 5°": {
        "modo": 3, "angle": 5, "init_vel": 7, "final_vel": 30, "step_vel": 3
    },

    # ----- MODO 4 (ángulo y velocidad variables) -----
    "Sweep AV A:0→45 s:5 / V:7→20 s:2": {
        "modo": 4,
        "init_angle": 0, "final_angle": 45, "step_angle": 5,
        "init_vel": 7,  "final_vel": 20, "step_vel": 2
    },
}

# Archivo donde se guardan/eliminan presets del usuario
USER_JSON = Path(__file__).with_name("presets_user.json")


def _read_user() -> Dict[str, Dict[str, Any]]:
    if USER_JSON.exists():
        try:
            return json.loads(USER_JSON.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _write_user(d: Dict[str, Dict[str, Any]]) -> None:
    USER_JSON.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def load_all() -> Dict[str, Dict[str, Any]]:
    """
    Retorna un dict con TODOS los presets:
    { nombre: cfg_dict }
    - Los de BUILTIN_PRESETS (este .py)
    - Los del JSON de usuario
    """
    data = dict(BUILTIN_PRESETS)
    data.update(_read_user())
    return data


def save_user_preset(name: str, cfg: Dict[str, Any]) -> None:
    """
    Guarda/actualiza un preset de usuario en el JSON.
    """
    name = name.strip()
    if not name:
        raise ValueError("Nombre vacío no permitido.")
    user = _read_user()
    user[name] = cfg
    _write_user(user)


def delete_user_preset(name: str) -> bool:
    """
    Elimina un preset del JSON de usuario. Devuelve True si existía.
    (No elimina presets BUILTIN)
    """
    user = _read_user()
    if name in user:
        del user[name]
        _write_user(user)
        return True
    return False


def is_builtin(name: str) -> bool:
    return name in BUILTIN_PRESETS
