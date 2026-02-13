import sys
import time

# try random; fall back to urandom if needed
try:
    import random

    def _randint(lo=0, hi=100):
        return random.randint(lo, hi)
except ImportError:
    import urandom

    def _randint(lo=0, hi=100):
        span = hi - lo + 1
        return lo + (urandom.getrandbits(16) % span)


CFG_PRESETS = {
    "CFG1": "MUX_32,ENV_C_H_hPa_KOhms,LUX_ALS_16,MACHINE_S,TCYC_500,DISP_1.0_10_1,LOAD_100_1.0_2,MATYPE_C,TSTYPE_C,MATDIM_5_5_1,DBND_Y,SENSNUM_1,TCH_21,SMPFQ_1000",
    "CFG2": "MUX_32,ENV_C_H_N_N,LUX_ALS_16,MACHINE_S,TCYC_500,DISP_1.0_10_1,LOAD_100_1.0_2,MATYPE_C,TSTYPE_C,MATDIM_5_5_1,DBND_Y,SENSNUM_1,TCH_10,SMPFQ_1000",
}

SUPPORTED_KEYS = {
    "ENV", "LUX", "MACHINE", "TCYC", "DISP", "LOAD", "HX", "MATYPE", "TSTYPE",
    "MATDIM", "DBND", "SENSNUM", "TCH", "SMPFQ", "GRID", "SPD", "ANG", "STR",
}

LEGACY_KEYS = {"TEST", "DELAM", "SAMPLE", "MACH", "SIZE", "MAT", "TSTTYPE", "CH", "SAMPFQ"}

CHANNEL_HEADERS_8 = [
    "1001 <R1> (OHM)", "1002 <R2> (OHM)", "1003 <R3> (OHM)", "1004 <R4> (OHM)",
    "1006 <C1> (OHM)", "1007 <C2> (OHM)", "1008 <C3> (OHM)", "1009 <C4> (OHM)",
]

CHANNEL_HEADERS_10 = [
    "1001 <R1> (OHM)", "1002 <R2> (OHM)", "1003 <R3> (OHM)", "1004 <R4> (OHM)", "1005 <R5> (OHM)",
    "1006 <C1> (OHM)", "1007 <C2> (OHM)", "1008 <C3> (OHM)", "1009 <C4> (OHM)", "1010 <C5> (OHM)",
]

CHANNEL_HEADERS_21 = [
    "1-1p (6001)", "1-3p (6002)", "2-4p (6003)", "3-1p (6004)", "3-5p (6005)", "4-2p (6006)", "4-6p (6007)",
    "5-3p (6008)", "5-7p (6009)", "6-4p (6010)", "6-8p (6011)", "7-5p (6012)", "7-9p (6013)", "8-6p (6014)", "8-10p (6015)",
    "9-7p (6016)", "9-11p (6017)", "10-8p (6018)", "10-12p (6019)", "11-9p (6020)", "11-13p (6021)", "12-10p (6022)", "12-14p (6023)",
    "13-11p (6024)", "13-15p (6025)", "14-12p (6026)", "14-16p (6027)", "15-13p (6028)", "15-17p (6029)", "16-14p (6030)", "16-18p (6031)",
    "17-15p (6032)", "17-19p (6033)", "18-16p (6034)", "18-20p (6035)", "19-17p (6036)", "19-21p (6037)", "20-18p (6038)",
    "21-19p (6039)", "21-21p (6040)",
]


class DataHandler:
    """
    Dummy MCU stream:
    - Parses keyed payload config from host.
    - Builds header from configured options.
    - Streams scan,time + configured telemetry + resistance channels.
    """

    def __init__(self):
        self.speed = 0
        self.angle = 0
        self.cycles = 0
        self.vary_speed = (0, 0, 0)
        self.vary_angle = (0, 0, 0)
        self.interval = 1
        self.paused = True
        self.channels = 0
        self.ready = False

        self.board = "MUX_08"
        self.config_map = {}
        self.telemetry_fields = []  # [{"kind": "...", "unit": "...", "header": "...", "meta": "..."}]
        self.channel_headers = []
        self.scan_counter = 0

    def wait(self):
        while not self.ready:
            time.sleep(1)

    def get_speed(self) -> int:
        return self.speed

    def get_angle(self):
        return self.angle

    def get_cycles(self) -> int:
        return self.cycles

    def get_variable_speed(self) -> tuple:
        return self.vary_speed

    def get_variable_angle(self) -> tuple:
        return self.vary_angle

    def run(self):
        while True:
            self._process_command()

    def _normalize_machine(self, raw):
        val = str(raw).strip().upper()
        return {"1": "S", "2": "T", "3": "M", "4": "F", "5": "O"}.get(val, val)

    def _normalize_matype(self, raw):
        val = str(raw).strip().upper()
        return {"1": "C", "2": "G", "3": "M", "4": "X", "5": "A"}.get(val, val)

    def _decode_temp(self, raw):
        val = str(raw).strip().upper()
        return {"1": "C", "2": "F", "0": "N", "C": "C", "F": "F", "N": "N"}.get(val, "N")

    def _decode_hum(self, raw):
        val = str(raw).strip().upper()
        return {"1": "H", "0": "N", "H": "H", "N": "N"}.get(val, "N")

    def _decode_pres(self, raw):
        val = str(raw).strip()
        up = val.upper()
        return {
            "1": "hPa", "2": "mBar", "3": "mmHg", "0": "N",
            "HPA": "hPa", "MBAR": "mBar", "MMHG": "mmHg", "N": "N",
        }.get(up, "N")

    def _decode_gas(self, raw):
        val = str(raw).strip()
        up = val.upper()
        return {"1": "KOhms", "2": "TVoC", "0": "N", "KOHMS": "KOhms", "TVOC": "TVoC", "N": "N"}.get(up, "N")

    def _decode_lux_type(self, raw):
        val = str(raw).strip().upper()
        return {"1": "ALS", "2": "UVS", "0": "N", "ALS": "ALS", "UVS": "UVS", "N": "N"}.get(val, "N")

    def _decode_disp_unit(self, raw):
        val = str(raw).strip().lower()
        return {"1": "mm", "2": "cm", "3": "in", "mm": "mm", "cm": "cm", "in": "in"}.get(val, "mm")

    def _decode_force_unit(self, raw):
        val = str(raw).strip().lower()
        return {"1": "g", "2": "N", "3": "kg", "4": "kN", "g": "g", "n": "N", "kg": "kg", "kn": "kN"}.get(val, "N")

    def _parse_config(self, raw_line):
        expanded = CFG_PRESETS.get(raw_line.strip(), raw_line.strip())
        tokens = [t.strip() for t in expanded.split(",") if t.strip()]
        if not tokens:
            return False, "empty payload", {}
        if tokens[0] not in ("MUX_32", "MUX_08"):
            return False, "token0 must be MUX_32 or MUX_08", {}

        token_map = {}
        for tok in tokens[1:]:
            if "_" not in tok:
                return False, "malformed token", {}
            key = tok.split("_", 1)[0]
            if key in LEGACY_KEYS:
                return False, "legacy key rejected", {}
            if key not in SUPPORTED_KEYS:
                return False, "unknown key", {}
            if key in token_map:
                return False, "duplicated key", {}
            token_map[key] = tok.split("_", 1)[1]

        if tokens[0] == "MUX_08" and ("ENV" in token_map or "LUX" in token_map):
            return False, "ENV/LUX require MUX_32", {}

        required = {"MACHINE", "TCYC", "MATDIM", "SENSNUM", "TCH"}
        for k in required:
            if k not in token_map:
                return False, "missing required key", {}

        machine_code = self._normalize_machine(token_map["MACHINE"])
        if machine_code not in ("S", "T", "M", "F", "O"):
            return False, "invalid machine value", {}

        if machine_code in ("S", "T", "M"):
            req, rej = {"MATYPE", "TSTYPE"}, {"SPD", "ANG", "STR"}
        elif machine_code == "F":
            req, rej = {"MATYPE", "TSTYPE", "SPD", "ANG"}, {"DISP", "LOAD", "STR"}
        else:
            req, rej = {"STR", "MATYPE", "TSTYPE"}, {"DISP", "LOAD", "SPD", "ANG", "GRID"}

        for k in req:
            if k not in token_map:
                return False, "missing machine-specific key", {}
        for k in rej:
            if k in token_map:
                return False, "disallowed key for machine", {}

        if "GRID" in token_map:
            matype = self._normalize_matype(token_map["MATYPE"])
            if matype not in ("M", "X", "A"):
                return False, "GRID not valid for MATYPE", {}

        if "SMPFQ" in token_map:
            try:
                smpfq = int(token_map["SMPFQ"])
            except Exception:
                return False, "invalid SMPFQ", {}
            if smpfq < 100 or smpfq > 600000:
                return False, "SMPFQ out of range", {}

        try:
            channels = int(token_map["TCH"])
        except Exception:
            return False, "invalid TCH", {}
        if channels <= 0:
            return False, "TCH must be > 0", {}

        return True, "", {
            "board": tokens[0],
            "machine": machine_code,
            "channels": channels,
            "token_map": token_map,
        }

    def _build_channel_headers(self, channels):
        if channels == 8:
            return list(CHANNEL_HEADERS_8)
        if channels == 10:
            return list(CHANNEL_HEADERS_10)
        if channels == 21:
            return list(CHANNEL_HEADERS_21)
        return ["Resistance ({})".format(6000 + i) for i in range(1, channels + 1)]

    def _build_telemetry_fields(self):
        fields = []
        cfg = self.config_map

        if "LOAD" in cfg:
            parts = cfg["LOAD"].split("_")
            unit = self._decode_force_unit(parts[2] if len(parts) > 2 else "2")
            fields.append({"kind": "LOAD", "unit": unit, "header": "5001 <LOAD> ({})".format(unit)})

        if "DISP" in cfg:
            parts = cfg["DISP"].split("_")
            unit = self._decode_disp_unit(parts[2] if len(parts) > 2 else "1")
            fields.append({"kind": "DISP", "unit": unit, "header": "5021 <DISP> ({})".format(unit)})

        if "HX" in cfg:
            parts = cfg["HX"].split("_")
            unit = self._decode_force_unit(parts[1] if len(parts) > 1 else "2")
            fields.append({"kind": "HX", "unit": unit, "header": "5031 <HX> ({})".format(unit)})

        if "ENV" in cfg:
            parts = cfg["ENV"].split("_")
            if len(parts) == 4:
                temp_u = self._decode_temp(parts[0])
                hum_u = self._decode_hum(parts[1])
                pres_u = self._decode_pres(parts[2])
                gas_u = self._decode_gas(parts[3])
                if temp_u != "N":
                    fields.append({"kind": "TEMP", "unit": temp_u, "header": "5101 <TEMP> ({})".format(temp_u)})
                if hum_u != "N":
                    fields.append({"kind": "HUM", "unit": "%", "header": "5102 <RH> (%)"})
                if pres_u != "N":
                    fields.append({"kind": "PRES", "unit": pres_u, "header": "5103 <PRES> ({})".format(pres_u)})
                if gas_u != "N":
                    fields.append({"kind": "GAS", "unit": gas_u, "header": "5104 <GAS> ({})".format(gas_u)})

        if "LUX" in cfg:
            parts = cfg["LUX"].split("_")
            if len(parts) >= 2:
                lux_type = self._decode_lux_type(parts[0])
                bits = parts[1]
                if lux_type != "N":
                    fields.append(
                        {
                            "kind": "LUX",
                            "unit": "lx",
                            "meta": "{}_{}".format(lux_type, bits),
                            "header": "5105 <LUX_{}> (bits={})".format(lux_type, bits),
                        }
                    )

        return fields

    def _format_timestamp(self):
        t = time.localtime()
        return "{:04d}-{:02d}-{:02d}_{:02d}:{:02d}:{:02d}".format(t[0], t[1], t[2], t[3], t[4], t[5])

    def _dummy_value(self, field):
        kind = field["kind"]
        unit = field.get("unit", "")
        if kind == "LOAD":
            return "{:.2f}".format(5.0 + (_randint(0, 200) / 10.0))
        if kind == "DISP":
            return "{:.2f}".format(_randint(0, 300) / 10.0)
        if kind == "HX":
            return "{:.2f}".format(_randint(0, 1000) / 10.0)
        if kind == "TEMP":
            c = 20.0 + (_randint(0, 150) / 10.0)
            if unit == "F":
                return "{:.2f}".format((c * 9.0 / 5.0) + 32.0)
            return "{:.2f}".format(c)
        if kind == "HUM":
            return "{:.2f}".format(30.0 + (_randint(0, 600) / 10.0))
        if kind == "PRES":
            if unit in ("hPa", "mBar"):
                return "{:.2f}".format(990.0 + (_randint(0, 300) / 10.0))
            if unit == "mmHg":
                return "{:.2f}".format(740.0 + (_randint(0, 400) / 10.0))
            return "{:.2f}".format(0.0)
        if kind == "GAS":
            if unit == "TVoC":
                return "{:.2f}".format(_randint(0, 600))
            return "{:.2f}".format(10.0 + (_randint(0, 1000) / 10.0))
        if kind == "LUX":
            return "{:.2f}".format(_randint(0, 2000))
        return "{:.2f}".format(_randint(0, 100))

    def _send_data(self):
        iter_n = self.channels if self.channels != 21 else 40
        telemetry_vals = [self._dummy_value(field) for field in self.telemetry_fields]
        channel_vals = [str(390000 + (i * 7) + _randint(0, 1200)) for i in range(iter_n)]
        vals = telemetry_vals + channel_vals
        line = "{},{},{}".format(self.scan_counter, self._format_timestamp(), ",".join(vals))
        self.scan_counter += 1
        sys.stdout.write(line + "\n")

    def _process_command(self):
        command = sys.stdin.readline().strip()
        if not command:
            return

        if command == "0":
            sys.stdout.write("0\n")
            return

        if command == "1":
            sys.stdout.write("0\n")
            ok, err, parsed = self._parse_config(sys.stdin.readline().strip())
            if not ok:
                sys.stdout.write("ERR\n")
                return

            self.board = parsed["board"]
            self.channels = parsed["channels"]
            self.config_map = parsed["token_map"]
            self.telemetry_fields = self._build_telemetry_fields()
            self.channel_headers = self._build_channel_headers(self.channels)
            self.scan_counter = 0

            header = [f["header"] for f in self.telemetry_fields] + self.channel_headers
            sys.stdout.write(",".join(header) + "\n")
            return

        if command == "2" or command == "r":
            self._send_data()
            return

        if command.startswith("SET"):
            parts = command.split()[1:]
            for p in parts:
                if p.endswith("C"):
                    self.cycles = int(p[:-1])
                elif p.endswith("RPM"):
                    self.speed = int(p[:-3])
                elif p.endswith("DEG"):
                    self.angle = int(p[:-3])
                elif p.startswith("VSPD"):
                    p2 = p.split("_")[1:]
                    self.vary_speed = (int(p2[0][1:]), int(p2[1][1:]), int(p2[2][1:]))
                elif p.startswith("VDEG"):
                    p2 = p.split("_")[1:]
                    self.vary_angle = (int(p2[0][1:]), int(p2[1][1:]), int(p2[2][1:]))
            self.ready = True
            return

        if command.startswith("PAUSE"):
            self.paused = True
            return

        if command.startswith("EXIT") or command.startswith("END"):
            sys.exit()

        print("No command received")
