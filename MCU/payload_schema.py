"""
Shared keyed-payload schema and validation rules.

This file is intentionally MicroPython-safe so it can be reused by:
- Host GUI validation before sending config.
- Dummy MCU parser when receiving config.
"""

CFG_PRESETS = {
    "CFG1": "MUX_32,ENV_C_H_hPa_KOhms,LUX_ALS_16,MACHINE_S,TCYC_500,DISP_1.0_10_1,LOAD_100_1.0_2,MATYPE_C,TSTYPE_C,MATDIM_5_5_1,DBND_Y,SENSNUM_1,TCH_21,SMPFQ_1000",
    "CFG2": "MUX_32,ENV_C_H_N_N,LUX_ALS_16,MACHINE_S,TCYC_500,DISP_1.0_10_1,LOAD_100_1.0_2,MATYPE_C,TSTYPE_C,MATDIM_5_5_1,DBND_Y,SENSNUM_1,TCH_10,SMPFQ_1000",
}

SUPPORTED_KEYS = {
    "ENV", "LUX", "MACHINE", "TCYC", "DISP", "LOAD", "HX", "MATYPE", "TSTYPE",
    "MATDIM", "DBND", "SENSNUM", "TCH", "SMPFQ", "GRID", "SPD", "ANG", "STR",
}

LEGACY_KEYS = {"TEST", "DELAM", "SAMPLE", "MACH", "SIZE", "MAT", "TSTTYPE", "CH", "SAMPFQ"}

REQUIRED_ALWAYS = {"MACHINE", "TCYC", "MATDIM", "SENSNUM", "TCH"}

MACHINE_RULES = {
    "S": {"require": {"MATYPE", "TSTYPE"}, "reject": {"SPD", "ANG", "STR"}},
    "T": {"require": {"MATYPE", "TSTYPE"}, "reject": {"SPD", "ANG", "STR"}},
    "M": {"require": {"MATYPE", "TSTYPE"}, "reject": {"SPD", "ANG", "STR"}},
    "F": {"require": {"MATYPE", "TSTYPE", "SPD", "ANG"}, "reject": {"DISP", "LOAD", "STR"}},
    "O": {"require": {"STR", "MATYPE", "TSTYPE"}, "reject": {"DISP", "LOAD", "SPD", "ANG", "GRID"}},
}


def normalize_machine_code(raw):
    val = str(raw).strip().upper()
    return {"1": "S", "2": "T", "3": "M", "4": "F", "5": "O"}.get(val, val)


def normalize_matype_code(raw):
    val = str(raw).strip().upper()
    return {"1": "C", "2": "G", "3": "M", "4": "X", "5": "A"}.get(val, val)


def token_value(tokens, key, default=""):
    prefix = key + "_"
    for tok in tokens[1:]:
        if tok.startswith(prefix):
            return tok[len(prefix):]
    return default


def _normalize_tokens(tokens):
    return [str(t).strip() for t in tokens if str(t).strip()]


def _split_payload_line(raw_line, expand_presets=True):
    raw = str(raw_line).strip()
    if expand_presets:
        raw = CFG_PRESETS.get(raw, raw)
    return _normalize_tokens(raw.split(","))


def validate_keyed_tokens(tokens):
    tokens = _normalize_tokens(tokens)
    if not tokens:
        return False, "Empty payload."
    if tokens[0] not in ("MUX_32", "MUX_08"):
        return False, "Token 0 must be MUX_32 or MUX_08."

    token_map = {}
    for tok in tokens[1:]:
        if "_" not in tok:
            return False, "Malformed token: {}".format(tok)
        key, value = tok.split("_", 1)
        if key in LEGACY_KEYS:
            return False, "Legacy key is not allowed: {}".format(key)
        if key not in SUPPORTED_KEYS:
            return False, "Unknown key: {}".format(key)
        if key in token_map:
            return False, "Duplicated key: {}".format(key)
        token_map[key] = value

    if tokens[0] == "MUX_08" and ("ENV" in token_map or "LUX" in token_map):
        return False, "ENV/LUX are only valid for MUX_32."

    missing = sorted([k for k in REQUIRED_ALWAYS if k not in token_map])
    if missing:
        return False, "Missing required keys: {}".format(", ".join(missing))

    machine_code = normalize_machine_code(token_map["MACHINE"])
    if machine_code not in MACHINE_RULES:
        return False, "Invalid MACHINE value."

    rule = MACHINE_RULES[machine_code]
    missing_machine = sorted([k for k in rule["require"] if k not in token_map])
    if missing_machine:
        return False, "Missing MACHINE-specific keys: {}".format(", ".join(missing_machine))

    rejected = sorted([k for k in rule["reject"] if k in token_map])
    if rejected:
        return False, "Keys not allowed for MACHINE_{}: {}".format(machine_code, ", ".join(rejected))

    if "GRID" in token_map:
        if "MATYPE" not in token_map:
            return False, "GRID requires MATYPE."
        matype = normalize_matype_code(token_map["MATYPE"])
        if matype not in ("M", "X", "A"):
            return False, "GRID is only valid when MATYPE is M, X, or A."

    if "SMPFQ" in token_map:
        try:
            smpfq = int(token_map["SMPFQ"])
        except Exception:
            return False, "SMPFQ must be an integer."
        if smpfq < 100 or smpfq > 600000:
            return False, "SMPFQ must be in range 100..600000."

    try:
        tch = int(token_map["TCH"])
    except Exception:
        return False, "TCH must be an integer."
    if tch <= 0:
        return False, "TCH must be > 0."

    if "LUX" in token_map:
        parts = token_map["LUX"].split("_")
        if len(parts) >= 2:
            ltype = str(parts[0]).strip().upper()
            if ltype not in ("ALS", "UVS", "N", "1", "2", "0"):
                return False, "Invalid LUX type."
            if ltype not in ("N", "0"):
                try:
                    bits = int(parts[1])
                except Exception:
                    return False, "LUX bits must be an integer."
                if bits < 13 or bits > 20:
                    return False, "LUX bits must be in range 13..20."
        else:
            return False, "Malformed LUX token."

    if "ENV" in token_map:
        parts = token_map["ENV"].split("_")
        if len(parts) != 4:
            return False, "Malformed ENV token."

    return True, ""


def parse_keyed_payload_line(raw_line, expand_presets=True):
    tokens = _split_payload_line(raw_line, expand_presets=expand_presets)
    ok, err = validate_keyed_tokens(tokens)
    if not ok:
        return False, err, {}

    token_map = {}
    for tok in tokens[1:]:
        key, value = tok.split("_", 1)
        token_map[key] = value

    machine = normalize_machine_code(token_map["MACHINE"])
    channels = int(token_map["TCH"])
    return True, "", {
        "tokens": tokens,
        "board": tokens[0],
        "machine": machine,
        "channels": channels,
        "token_map": token_map,
    }
