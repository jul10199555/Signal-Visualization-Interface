import customtkinter as ctk
from serial_interface import SerialInterface
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import json

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# GUI Pages
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Signal Visualization Interface")
        self.geometry("800x600")

        # Configure grid
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.serial_interface = SerialInterface()

        # Control Panel (top)
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        control_frame.grid_columnconfigure((0,1,2,3), weight=1)

        ctk.CTkLabel(control_frame, text="Device Angle:", anchor="w").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.angle_entry = ctk.CTkEntry(control_frame, placeholder_text="°")
        self.angle_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Device Cycles:", anchor="w").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        self.cycles_entry = ctk.CTkEntry(control_frame, placeholder_text="#")
        self.cycles_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Device Pulses:", anchor="w").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.pulses_entry = ctk.CTkEntry(control_frame, placeholder_text="#")
        self.pulses_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        self.enter_btn = ctk.CTkButton(control_frame, text="Enter", command=self.submit_values)
        self.enter_btn.grid(row=1, column=2, padx=5, pady=5, sticky="ew")

        self.stop_btn = ctk.CTkButton(control_frame, text="Stop", command=self.stop)
        self.stop_btn.grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        # Serial Monitor (bottom)
        monitor_frame = ctk.CTkFrame(self)
        monitor_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 20))
        monitor_frame.grid_rowconfigure(1, weight=1)
        monitor_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(monitor_frame, text="Live Serial Data", font=ctk.CTkFont(size=16)).grid(row=0, column=0, pady=(10, 5))

        # self.textbox = ctk.CTkTextbox(monitor_frame, width=760, height=350)
        # self.textbox.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        # self.textbox.configure(state="disabled")

        # Configure Plot
        self.fig, self.ax = plt.subplots()
        (self.line,) = self.ax.plot([], [], lw=2)
        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)
        self.canvas = FigureCanvasTkAgg(self.fig, master=monitor_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, pady=10)
        self.x_vals, self.y_vals = [], []

        self.start_btn = ctk.CTkButton(monitor_frame, text="Start Monitor", command=self.start_serial)
        self.start_btn.grid(row=2, column=0, pady=10)

        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=1000, cache_frame_data=False)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def submit_values(self):
        angle = self.angle_entry.get()
        cycles = self.cycles_entry.get()
        pulses = self.pulses_entry.get()
        cmd = f"SET angle={angle} cycles={cycles} pulses={pulses}"
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.ser.write((cmd + "\n").encode())

    def stop(self):
        if self.serial_interface.reading:
            angle = 0
            cycles = 0
            speed = 0
            
            cmd = f"SET angle={angle} cycles={cycles} pulses={speed}"
            if self.serial_interface.ser and self.serial_interface.ser.is_open:
                self.serial_interface.ser.write((cmd + "\n").encode())

    def start_serial(self):
        if not self.serial_interface.reading:
            self.serial_interface.connect()
            self.serial_interface.read_lines(self.get_vals)

    # def display_line(self, line):
    #     self.textbox.configure(state="normal")
    #     self.textbox.insert("end", line + "\n")
    #     self.textbox.see("end")
    #     self.textbox.configure(state="disabled")

    def get_vals(self, data):
        try:
            x, y = data.split(',')
            self.x_vals.append(int(x))
            self.y_vals.append(int(y))
        except Exception as e:
            print(f"Error parsing data: {e}")


    def update_plot(self, _):
        self.ax.clear()
        self.ax.plot(self.x_vals, self.y_vals)
        return self.line,

    def close(self):
        exit()
