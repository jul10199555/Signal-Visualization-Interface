from datetime import datetime
from pathlib import Path
import tkinter.filedialog as filedialog

import customtkinter as ctk
import pandas

from payload import Payload


class MetricsPage(ctk.CTkFrame):
    """Computes and displays per-channel metrics from the live payload."""

    def __init__(self, master, payload: Payload):
        super().__init__(master)
        self.payload = payload
        self.metrics_df = None

        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", padx=8, pady=8)

        ctk.CTkLabel(ctrl, text="Rolling RMS Window:").pack(side="left", padx=(6, 4))
        self.rms_window_entry = ctk.CTkEntry(ctrl, width=70)
        self.rms_window_entry.insert(0, "20")
        self.rms_window_entry.pack(side="left", padx=(0, 10))

        ctk.CTkLabel(ctrl, text="Outlier Z-Threshold:").pack(side="left", padx=(6, 4))
        self.z_entry = ctk.CTkEntry(ctrl, width=70)
        self.z_entry.insert(0, "3.0")
        self.z_entry.pack(side="left", padx=(0, 10))

        self.auto_var = ctk.StringVar(value="on")
        ctk.CTkCheckBox(
            ctrl,
            text="Auto Refresh",
            variable=self.auto_var,
            onvalue="on",
            offvalue="off",
        ).pack(side="left", padx=(6, 10))

        ctk.CTkButton(ctrl, text="Refresh", command=self.refresh_metrics).pack(side="left", padx=6)
        ctk.CTkButton(ctrl, text="Export CSV", command=self.export_metrics).pack(side="left", padx=6)

        self.summary_label = ctk.CTkLabel(self, text="No metrics calculated yet.")
        self.summary_label.pack(anchor="w", padx=10)

        self.status_label = ctk.CTkLabel(self, text="")
        self.status_label.pack(anchor="w", padx=10, pady=(0, 6))

        self.table = ctk.CTkTextbox(self)
        self.table.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.refresh_metrics()
        self.after(1000, self.auto_refresh)

    def _parse_config_values(self):
        try:
            window = int(self.rms_window_entry.get())
        except Exception:
            window = 20
        if window <= 0:
            window = 1

        try:
            z_thresh = float(self.z_entry.get())
        except Exception:
            z_thresh = 3.0
        if z_thresh <= 0:
            z_thresh = 3.0

        return window, z_thresh

    def _compute_metrics(self):
        df = self.payload.to_dataframe(only_channels=True)
        if df.empty:
            return pandas.DataFrame()

        window, z_thresh = self._parse_config_values()
        rows = []

        for ch in self.payload.get_channels():
            if ch not in df.columns:
                continue

            s = pandas.to_numeric(df[ch], errors="coerce").dropna()
            if s.empty:
                continue

            min_v = float(s.min())
            max_v = float(s.max())
            mean_v = float(s.mean())
            drift_v = float(s.iloc[-1] - s.iloc[0]) if len(s) > 1 else 0.0
            p2p_v = max_v - min_v

            rolling_rms = s.pow(2).rolling(window=window, min_periods=1).mean().pow(0.5)
            rms_last = float(rolling_rms.iloc[-1])

            std_v = float(s.std(ddof=0))
            if std_v > 0:
                z = (s - mean_v) / std_v
                outlier_mask = z.abs() > z_thresh
            else:
                outlier_mask = pandas.Series([False] * len(s), index=s.index)

            outlier_count = int(outlier_mask.sum())

            rows.append(
                {
                    "Channel": ch,
                    "Samples": int(len(s)),
                    "Min": min_v,
                    "Max": max_v,
                    "Mean": mean_v,
                    "Drift": drift_v,
                    "PeakToPeak": p2p_v,
                    "RollingRMS": rms_last,
                    "OutlierCount": outlier_count,
                    "OutlierFlag": "Y" if outlier_count > 0 else "N",
                }
            )

        if not rows:
            return pandas.DataFrame()

        out_df = pandas.DataFrame(rows)
        return out_df

    def refresh_metrics(self):
        try:
            metrics = self._compute_metrics()
            self.metrics_df = metrics

            self.table.delete("1.0", "end")
            if metrics.empty:
                self.table.insert("end", "No samples available yet.")
                self.summary_label.configure(text="No metrics available.")
                self.status_label.configure(text="Waiting for streamed data.", text_color="orange")
                return

            show_df = metrics.copy()
            for col in ["Min", "Max", "Mean", "Drift", "PeakToPeak", "RollingRMS"]:
                show_df[col] = show_df[col].map(lambda v: f"{v:.4f}")

            self.table.insert("end", show_df.to_string(index=False))
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self.summary_label.configure(
                text=f"Channels: {len(show_df)} | Updated: {now}"
            )
            self.status_label.configure(text="Metrics updated.", text_color="green")
        except Exception as e:
            self.status_label.configure(text=f"Metrics error: {e}", text_color="red")

    def auto_refresh(self):
        if self.auto_var.get() == "on":
            self.refresh_metrics()
        self.after(1000, self.auto_refresh)

    def export_metrics(self):
        if self.metrics_df is None or self.metrics_df.empty:
            self.refresh_metrics()

        if self.metrics_df is None or self.metrics_df.empty:
            self.status_label.configure(text="Nothing to export yet.", text_color="orange")
            return

        default_name = f"metrics_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        out_dir = Path("output")
        out_dir.mkdir(parents=True, exist_ok=True)

        path = filedialog.asksaveasfilename(
            title="Export Metrics CSV",
            defaultextension=".csv",
            initialdir=str(out_dir.resolve()),
            initialfile=default_name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )

        if not path:
            return

        self.metrics_df.to_csv(path, index=False)
        self.status_label.configure(text=f"Metrics exported: {path}", text_color="green")
