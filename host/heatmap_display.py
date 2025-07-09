# heatmap_ctk_refactored.py
# pip install customtkinter
import threading
import time

import customtkinter as ctk
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

import program_configrations

from multi_display import WaveformApp
from payload import Payload
from heatmap import Heatmap

#  ─── CustomTkinter Setup ─────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class HeatmapApp(ctk.CTkFrame):
    def __init__(self, master, payload: Payload, waveform: WaveformApp = None):
        super().__init__(master)
        self.payload = payload
        self.waveform = waveform

        # Controls frame with Refresh button
        ctrl = ctk.CTkFrame(self)
        ctrl.pack(fill="x", pady=6, padx=6)
        self.refresh_btn = ctk.CTkButton(ctrl, text="Refresh Heatmap", command=self.draw_heatmap)
        self.refresh_btn.pack(side="right")

        # Matplotlib figure and axis setup
        self.fig, self.ax = plt.subplots(figsize=(10, 2.5), dpi=100)
        self.fig.tight_layout()
        canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=(0, 6))
        self.canvas = canvas
        self.draw_heatmap()

        threading.Thread(target=self.auto_update, daemon=True).start()

    def draw_heatmap(self):
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()

        # Check payload for recent data
        try:
            recent_data = self.payload.get_most_recent_data()
        except (IndexError, AttributeError):
            recent_data = None

        if not recent_data:
            # No samples yet; prompt user
            self.ax.text(
                0.5, 0.5,
                "No data available.",
                ha="center",
                va="center",
                transform=self.ax.transAxes
            )
            self.canvas.draw_idle()
            return

        # Compute matrix and plot
        hm = Heatmap(self.payload, self.waveform.get_ro())
        mat = hm.calc_pts_diagonal(program_configrations.S5X41_SWITCHER)

        sns.heatmap(
            mat,
            cmap="jet",
            ax=self.ax,
            xticklabels=False,
            yticklabels=False
        )
        self._decorate_axes(mat)
        self.canvas.draw_idle()

    def set_payload(self, payload: Payload):
        self.payload = payload

    def _decorate_axes(self, mat):
        """Add ticks, labels, and secondary axes for clarity."""
        evens = list(range(2, mat.shape[1], 2))
        bottom_labels = [f"{i}'" for i in range(1, len(evens) + 1)]
        self.ax.set_xticks(evens)
        self.ax.set_xticklabels(bottom_labels, rotation=0, fontsize=8)
        self.ax.set_xlabel("Columns")

        rows = list(range(mat.shape[0]))
        self.ax.set_yticks(rows)
        self.ax.set_yticklabels([str(i) for i in range(1, mat.shape[0] + 1)],
                                rotation=0, fontsize=8)
        self.ax.set_ylabel("Rows")

        ax_top = self.ax.twiny()
        ax_top.set_xlim(self.ax.get_xlim())
        ax_top.set_xticks(evens)
        ax_top.set_xticklabels(range(1, len(evens) + 1), rotation=0, fontsize=8)
        ax_top.xaxis.set_ticks_position('top')
        ax_top.xaxis.set_label_position('top')
        ax_top.set_xlabel("Columns")

        ax_right = self.ax.twinx()
        ax_right.set_ylim(self.ax.get_ylim())
        ax_right.set_yticks(rows)
        ax_right.set_yticklabels([f"{i}'" for i in range(1, mat.shape[0] + 1)], rotation=0, fontsize=8)
        ax_right.yaxis.set_ticks_position('right')
        ax_right.yaxis.set_label_position('right')

    def auto_update(self):
        while True:
            self.draw_heatmap()
            time.sleep(1)
