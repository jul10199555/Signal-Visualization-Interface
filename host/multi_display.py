# pip install customtkinter
from typing import Dict

import customtkinter as ctk
import matplotlib.dates as mdates  # add once at the top of the file
import matplotlib.pyplot as plt
import pandas
import seaborn as sns
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

from payload import Payload

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class WaveformApp(ctk.CTkFrame):

    # SAMPLING FREQ IN HZ
    def __init__(self, master, payload: Payload, sampling_freq: int = 10):
        # THE POSITION FOR THE RESISTIVE CHANNELS WILL BE [LENGTH - # CHANNELS : ]
        super().__init__(master)
        self.sampling_freq = sampling_freq

        self.payload = payload

        # CHECK WHAT TIME STAMPS ARE SUPPORTED WITH THE PAYLOAD's WINDOW SIZE & THE SAMPLING FREQ
        base_time_period = {"1ms": 0.001, "5ms": 0.005, "30ms": 0.03, "100ms": 0.1, "500ms": 0.5, "1s": 1, "10s": 10,
                            "30s": 30, "1m": 60, "5m": 300, "10m": 600, "30m": 1800, "1hr": 3600}

        self.time_period = {}
        for period in base_time_period.keys():
            seconds = base_time_period[period]
            if (seconds * sampling_freq >= 1) and (seconds * sampling_freq <= payload.window_size):
                self.time_period[period] = seconds

        # DEFAULT WILL BE THE MEDIAN PT FOR TIME PERIOD -> CURRENT WINDOW DISPLAY FOR THE WAVEFORM
        time_half_len = len(self.time_period) // 2

        self.window_size_label = list(self.time_period.keys())[time_half_len]
        self.window_size_disp = self.time_period[self.window_size_label]

        # MAIN
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 3))
        body.grid_rowconfigure(0, weight=0)
        body.grid_rowconfigure(1, weight=1)

        self.win_sel = ctk.CTkSegmentedButton(
            body,
            values=list(self.time_period.keys()),
            corner_radius=12,
            command=self._time_period_switch
        )
        self.win_sel.set(self.window_size_label)
        self.win_sel.grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.is_deriv = ctk.StringVar(value="off")
        ctk.CTkCheckBox(body, text="View ∆R/R0%", variable=self.is_deriv, onvalue="on", offvalue="off").grid(row=0,column=1,pady=5)

        # WAVEFORM
        self.fig, self.ax = plt.subplots(figsize=(5, 4), dpi=100)
        self.fig.set_tight_layout(True)

        self.canvas = FigureCanvasTkAgg(self.fig, master=body)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, sticky="nsew",
                                padx=(0, 8), pady=0)

        # CHANNEL SELECT
        channel_grp = ctk.CTkScrollableFrame(body, fg_color="transparent")
        channel_grp.grid(row=1, column=1, sticky="nsew")

        ctk.CTkLabel(channel_grp, text="Channel Select").pack(anchor="w", pady=(6, 4))
        self.mass_sel_btn = ctk.CTkButton(channel_grp, text="SELECT/DESELECT ALL", corner_radius=12,
                                          command=self._mass_select)
        self.mass_sel_btn.pack(anchor="w", pady=(6, 4))

        self.channel_box_select: Dict[str, ctk.CTkCheckBox] = {}
        for ch in (payload.get_channels()):
            cb = ctk.CTkCheckBox(channel_grp, text=ch, command=self._update_graph)
            cb.pack(anchor="w", pady=2)
            self.channel_box_select[ch] = cb

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=3)
        body.grid_columnconfigure(1, weight=1)

    # placeholder
    def _noop(self, *_):
        pass

    def _time_period_switch(self, value):
        self.window_size_label = value
        self.window_size_disp = self.time_period[value]

        self._update_graph()

    def _mass_select(self):
        # CHECK WHETHER TO SELECT OR UNSELECT ALL -> if a single channel is unselected then the mode will be select al
        # UNSELECT WILL ONLY HAPPEN WHEN ALL CHANNELS ARE TOGGLED ON
        select_all: bool = False
        for ch_s in self.channel_box_select.values():
            if not ch_s.get():  # NOT SELECTED
                select_all = True
                ch_s.select()

        # SELECT ALL -> UNSELECT ALL IF ALL WERE PREVIOUSLY TOGGLED ON
        if not select_all:
            for ch_s in self.channel_box_select.values():
                ch_s.deselect()

        self._update_graph()

    def _update_graph(self):
        selected_channels = [
            name for name, cb in self.channel_box_select.items() if cb.get()
        ]
        self.ax.clear()

        if not selected_channels:
            self.ax.text(0.5, 0.5, "SELECT AT LEAST ONE CHANNEL",
                         ha="center", va="center", transform=self.ax.transAxes)
        else:
            df = (self.payload.to_dataframe().set_index("Time")[selected_channels])

            his_amount = int(self.window_size_disp * self.sampling_freq)
            df = df.tail(his_amount)

            long_df = (df.reset_index()
                       .melt(id_vars="Time",
                             var_name="Channel",
                             value_name="Value"))
            long_df["Time"] = pandas.to_datetime(long_df["Time"],
                                                 format="%d/%m/%Y %H:%M:%S:%f",
                                                 utc=True)
            if self.is_deriv == "off":
                sns.scatterplot(
                    data=long_df,
                    x="Time",
                    y="Value",
                    hue="Channel",
                    palette=sns.color_palette("husl", len(selected_channels)),
                    s=20,
                    ax=self.ax,
                    legend=True
                )
            else:
                pass

            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            self.fig.autofmt_xdate()

            self.ax.set_xlabel("Time")
            self.ax.set_ylabel("Resistance")
            self.ax.set_title("Active Resistance of the Channels")

        self.canvas.draw_idle()


# if __name__ == "__main__":
#     extra_keys = (
#             ["5001 <LOAD> (VDC)", "5021 <DISP> (VDC)"]
#             + [f"{6001 + i} (OHM)" for i in range(21)]  # 6001 … 6022
#     )

#     p = Payload(
#         window_size=1000000,
#         num_rows_detach=10,
#         out_file_name="output/10k_test.csv",
#         keys=extra_keys,
#         channels=21
#     )

#     WaveformApp(p).mainloop()
