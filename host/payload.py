"""
payload.py  –  Rolling-window buffer for mixed-type sensor payloads
Texas A&M University X UADY
"""

from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Deque, Any, List

import pandas

"""
Collect variable-length CSV payload lines into fixed-length deques,
then export the current window to a CSV file
"""


class Payload:

    # WINDOW SIZE IS THE AMOUNT OF DEPTH/SCANS OF DATA - Y VALUE
    def __init__(self, window_size: int, num_rows_detach: int, out_file_name: str, channels: int = None,
                 keys: list[str] = None):

        if (keys is not None) and (channels is not None):
            self.channels = channels
            self.keys = ["Scan", "Time"] + keys
        else:  # DEFAULT LAYOUT
            self.channels = 21
            self.keys = ["Scan", "Time", "temp", "rel_humid", "atm_pres", "tvoc", "lux", "dig0", "dig1", "dig2",
                         "dig3", "sh_disp", "sh_load", "sig_max", "HX711_force"]
            for ch in range(self.channels):
                self.keys.append(f"R{ch}")

        if num_rows_detach > window_size:
            raise RuntimeError(f"NUMBER OF ROWS TO DETACH EXCEEDS WINDOW SIZE: window_size={window_size}, "
                               f"num_rows_detach={num_rows_detach} ")

        self.curr_seq = 0
        self.data: Dict[str, Deque[Any]] = {}
        self.window_size = window_size
        self.num_rows_detach = num_rows_detach
        self.out_file_name = out_file_name

        for key in self.keys:
            self.data[key] = deque(maxlen=window_size)

    """
    Split `raw_payload` on commas and append each value to its deque.
    'raw_payload' has to be in the same order as the init keys and no headers expected, SCAN # and Time will be auto
    """
    def push(self, raw_payload: str, scan: int = None, time: datetime = None) -> None:

        buffer = raw_payload.split(",")

        expected_size = len(self.keys) - 2
        if expected_size != len(buffer):
            raise RuntimeError(f"INPUTTED BUFFER IS INVALID FOR PAYLOAD: buffer_size={len(buffer)},"
                               f" expected_key_size={expected_size}")

        if scan is None:
            self.data["Scan"].append(self.curr_seq)
            self.curr_seq += 1
        else:
            self.data["Scan"].append(scan)
        if time is None:
            ts = datetime.now(timezone.utc)
            self.data["Time"].append(ts)
        else:
            self.data["Time"].append(time)

        i = 0
        for key in self.keys[2:]:
            self.data[key].append(float(buffer[i]))
            i += 1

        # TOTAL DATA (ALL WINDOWS) IS FULL -> UNLOAD SOME WINDOWS TO THE DISK (CSV)
        while len(self.data["Scan"]) >= self.window_size:
            self.detach_rows(self.num_rows_detach, self.out_file_name)

    # DUMP THE CURRENT WINDOW OF THE PAYLOAD INTO A CSV FILE
    def to_csv(self, file_name: str) -> None:
        if not self.data:
            raise RuntimeError("DATA UNDEF: NOTHING TO WRITE")

        path = Path(file_name)
        (self.to_dataframe()).to_csv(path, mode="a", index=False, header=not path.exists())

    # Convert the data to a pandas' dataframe
    def to_dataframe(self, only_channels: bool = False) -> pandas.DataFrame:
        df = pandas.DataFrame({k: list(v) for k, v in self.data.items()})
        if only_channels:
            df = df[self.get_channels()]

        df["Time"] = pandas.to_datetime(df["Time"], utc=True).dt.strftime("%d/%m/%Y %H:%M:%S:%f").str[:-3]
        df = df.astype({"Scan": "int64"})
        return df

    def get_channels(self) -> list[str]:
        return self.keys[-self.channels:]

    def get_most_recent_data(self) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        for k, dq in self.data.items():
            if dq:
                result[k] = dq[-1]
            else:
                result[k] = 0
        return result

    # detach num_rows (oldest) rows  from the data and push it to the csv file
    # todo: add a limit for the csv files where it will push to another csv file when the file size is too large
    def detach_rows(self, num_rows: int, file_name: str) -> None:

        row_size = len(self.data["Scan"])
        if row_size < num_rows:
            raise RuntimeError(f"NOT ENOUGH DATA TO DETACH ROWS: DESIRED={num_rows}, ACTUAL={row_size}")

        rows: List[Dict[str, Any]] = []

        for _ in range(num_rows):
            row: Dict[str, Any] = {}

            for (col, dq) in self.data.items():
                value = dq.popleft()
                row[col] = value

            rows.append(row)

        df = pandas.DataFrame(rows, columns=list(self.data.keys()))

        path = Path(file_name)

        df.to_csv(path, mode="a", index=False, header=not path.exists())
