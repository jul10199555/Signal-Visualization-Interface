# pip install customtkinter
from typing import Dict

import customtkinter as ctk
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas
import seaborn as sns
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import threading
import time

from payload import Payload

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("blue")


class WaveformApp(ctk.CTkFrame):

    # SAMPLING FREQ IN HZ
    def __init__(self, master, payload: Payload, is_relative, sampling_freq: int = 10):
        # THE POSITION FOR THE RESISTIVE CHANNELS WILL BE [LENGTH - # CHANNELS : ]
        super().__init__(master)
        self.sampling_freq = sampling_freq
        self.is_relative = is_relative

        self.payload = payload

        self.ro = None

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

        # WAVEFORM
        self.fig, self.ax = plt.subplots(figsize=(5, 4), dpi=100)
        self.fig.set_tight_layout(True)
        
        def check_and_enter_ro():
            if ro_entry.get() and ro_entry.get().isdigit() and ro_entry.get() != '0':
                self.ro = int(ro_entry.get())
                ro_entry.configure(border_color='gray50')
            else:
                ro_entry.configure(border_color='red')

        if self.is_relative:        
            ro_frame = ctk.CTkFrame(body, fg_color='transparent')
            ro_frame.grid(row=0,column=1,pady=5)

            ctk.CTkLabel(ro_frame, text="Enter Base Resistance:").grid(row=0, column=0, padx=5)

            ro_entry = ctk.CTkEntry(ro_frame)
            ro_entry.grid(row=0, column=1, padx=5)


            ctk.CTkButton(ro_frame, text="SET", command=check_and_enter_ro).grid(row=0, column=2, padx=5)

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

        threading.Thread(target=self.auto_update, daemon=True).start()

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
        elif (self.is_relative and self.ro == None):
            self.ax.text(0.5, 0.5, "ENTER A BASE RESISTANCE",
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
            
            if not self.is_relative:
                sns.lineplot(
                    data=long_df,
                    x="Time",
                    y="Value",
                    hue="Channel",
                    palette=sns.color_palette("husl", len(selected_channels)),
                    ax=self.ax,
                    legend=True
                )
                self.ax.set_ylabel("Resistance (Ohms)")

            else:
                delta_df = long_df.copy()
                delta_df['DeltaR_Ro'] = (delta_df['Value'] - self.ro) / self.ro
                sns.lineplot(
                    data=delta_df,
                    x="Time",
                    y="DeltaR_Ro",
                    hue="Channel",
                    palette=sns.color_palette("husl", len(selected_channels)),
                    ax=self.ax,
                    legend=True
                )
                self.ax.set_ylabel("∆R/Ro")

            self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S'))
            self.ax.xaxis.set_major_locator(mdates.AutoDateLocator())
            self.fig.autofmt_xdate()

            self.ax.set_xlabel("Time")
            self.ax.set_title("Active Resistance of the Channels")

        self.canvas.draw_idle()

    def auto_update(self):
        while True:
            self._update_graph()
            time.sleep(1)

