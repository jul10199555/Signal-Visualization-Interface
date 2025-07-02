# heatmap_ctk_refactored.py
# pip install customtkinter
import customtkinter as ctk
import matplotlib.pyplot as plt
import seaborn as sns
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from payload import Payload
from heatmap import Heatmap, s5x41_switcher

#  ─── CustomTkinter Setup ─────────────────────────────────────────────────────
ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class HeatmapApp(ctk.CTkFrame):
    # THE ro - BASE RESISTANCE, DETERMINES WHETHER IT'S DISPLAYING THE DERIVATIVE OR THE RESISTANCE
    def __init__(self, master, payload: Payload, ro=None):
        super().__init__(master)
        self.payload = payload
        self.ro = ro

        # Matplotlib figure and axis setup
        self.fig, self.ax = plt.subplots(figsize=(10, 2.5), dpi=100)
        self.fig.tight_layout()
        canvas = FigureCanvasTkAgg(self.fig, master=self)
        canvas.get_tk_widget().pack(fill="both", expand=True, padx=6, pady=(0,6))
        self.canvas = canvas

        # Initial plot
        self.draw_heatmap()

    def draw_heatmap(self):
        """Compute heatmap and plot it on a fresh axis."""
        # Clear entire figure to remove old colorbars/axes
        self.fig.clf()
        self.ax = self.fig.add_subplot(111)
        self.fig.tight_layout()

        # Compute matrix
        hm = Heatmap(self.payload, self.ro)
        mat = hm.calc_pts_diagonal(s5x41_switcher)

        # Plot heatmap
        sns.heatmap(
            mat,
            cmap="jet",
            ax=self.ax,
            xticklabels=False,
            yticklabels=False
        )
        self._decorate_axes(mat)
        self.canvas.draw_idle()

    def refresh_heatmap(self):
        self.draw_heatmap()

    def set_payload(self, payload: Payload):
        self.payload = payload

    def _decorate_axes(self, mat):
        """Internal helper to add ticks, labels, and secondary axes."""
        # Bottom x-labels
        evens = list(range(2, mat.shape[1], 2))
        bottom_labels = [f"{i}'" for i in range(1, len(evens)+1)]
        self.ax.set_xticks(evens)
        self.ax.set_xticklabels(bottom_labels, rotation=0, fontsize=8)
        self.ax.set_xlabel("Columns")

        # Left y-labels
        rows = list(range(mat.shape[0]))
        self.ax.set_yticks(rows)
        self.ax.set_yticklabels([str(i) for i in range(1, mat.shape[0]+1)],
                                rotation=0, fontsize=8)
        self.ax.set_ylabel("Rows")

        # Top axis
        ax_top = self.ax.twiny()
        ax_top.set_xlim(self.ax.get_xlim())
        ax_top.set_xticks(evens)
        ax_top.set_xticklabels(range(1, len(evens)+1),
                               rotation=0, fontsize=8)
        ax_top.xaxis.set_ticks_position('top')
        ax_top.xaxis.set_label_position('top')
        ax_top.set_xlabel("Columns")

        # Right axis
        ax_right = self.ax.twinx()
        ax_right.set_ylim(self.ax.get_ylim())
        ax_right.set_yticks(rows)
        ax_right.set_yticklabels([f"{i}'" for i in range(1, mat.shape[0]+1)],
                                 rotation=0, fontsize=8)
        ax_right.yaxis.set_ticks_position('right')
        ax_right.yaxis.set_label_position('right')


if __name__ == "__main__":
    # ── Build your Payload as you already do ───────────────────────────────────
    extra_keys = ["5001 <LOAD> (VDC)", "5021 <DISP> (VDC)"] \
               + [f"{6001 + i} (OHM)" for i in range(40)]
    p = Payload(
        window_size=1_000_000,
        num_rows_detach=1_000,
        out_file_name="output/heatmap.csv",
        channels=21,
        keys=extra_keys
    )

    # Push some dummy data
    import random
    from datetime import datetime, timezone, timedelta
    t0 = datetime.now(timezone.utc)
    for i in range(200):
        load_v = round(0.00030 + 1e-7*i, 9)
        disp_v = round(0.00019 + 1e-7*i, 9)
        resist = [round(11_000 + random.uniform(-500,500),4) for _ in range(40)]
        line = ",".join([f"{load_v}", f"{disp_v}", *map(str,resist)])
        p.push(line, time=t0)
        t0 += timedelta(milliseconds=100)

    # Launch the GUI
    root = ctk.CTk()
    root.geometry("900x350")
    root.title("5×41 Diagonal Heatmap")
    app = HeatmapApp(root, p)
    app.pack(fill="both", expand=True)
    root.mainloop()
