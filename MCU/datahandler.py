import sys
import time
try:
    from payload_schema import parse_keyed_payload_line
except ImportError:
    from .payload_schema import parse_keyed_payload_line

# Dummy storage flag for date-time sync response behavior.
# Set to False to emulate "microSD missing" warning (0x0F).
DUMMY_MICROSD_INSERTED = True

# Date-time sync response codes.
DTT_OK_CODE = "0x00"
DTT_WARN_INVALID = "0x0E"
DTT_WARN_MICROSD = "0x0F"

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
        self.micro_sd_inserted = DUMMY_MICROSD_INSERTED
        self.last_set_datetime = None  # (year, month, day, hour, minute, second)
        self._reset_to_initial_mode(reset_datetime=False)

    def _reset_to_initial_mode(self, reset_datetime=False):
        # Reset runtime/session values to idle startup mode.
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

        if reset_datetime:
            self.last_set_datetime = None

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
        ok, err, parsed = parse_keyed_payload_line(raw_line, expand_presets=True)
        if not ok:
            return False, err, {}
        return True, "", parsed

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

    def _is_datetime_sync_command(self, command):
        parts = command.split("_")
        if len(parts) != 6:
            return False
        for p in parts:
            if not p.isdigit():
                return False
        return True

    def _is_leap_year(self, year):
        return (year % 4 == 0) and ((year % 100 != 0) or (year % 400 == 0))

    def _days_in_month(self, year, month):
        if month in (1, 3, 5, 7, 8, 10, 12):
            return 31
        if month in (4, 6, 9, 11):
            return 30
        if month == 2:
            return 29 if self._is_leap_year(year) else 28
        return 0

    def _validate_datetime_sync(self, command):
        if not self._is_datetime_sync_command(command):
            return False, ()
        y, m, d, hh, mm, ss = [int(v) for v in command.split("_")]
        if y < 2000 or y > 2099:
            return False, ()
        if m < 1 or m > 12:
            return False, ()
        max_day = self._days_in_month(y, m)
        if d < 1 or d > max_day:
            return False, ()
        if hh < 0 or hh > 23:
            return False, ()
        if mm < 0 or mm > 59:
            return False, ()
        if ss < 0 or ss > 59:
            return False, ()
        return True, (y, m, d, hh, mm, ss)

    def _handle_datetime_sync(self, command):
        ok, parts = self._validate_datetime_sync(command)
        if not ok:
            sys.stdout.write(DTT_WARN_INVALID + "\n")
            return True

        self.last_set_datetime = parts
        if self.micro_sd_inserted:
            sys.stdout.write(DTT_OK_CODE + "\n")
        else:
            sys.stdout.write(DTT_WARN_MICROSD + "\n")
        return True

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

        if self._is_datetime_sync_command(command):
            self._handle_datetime_sync(command)
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

        if command.startswith("END"):
            self._reset_to_initial_mode(reset_datetime=False)
            return

        if command.startswith("EXIT"):
            sys.exit()

        print("No command received")
