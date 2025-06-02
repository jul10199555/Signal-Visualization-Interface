import customtkinter as ctk
from serial_interface import SerialInterface
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

ANGLE_DEFAULT = 0
CYCLES_DEFAULT = 0
PULSES_DEFAULT = 0
RESOLUTION_DEFAULT = 60
X_LIM_DEFAULT = (0, 100)
Y_LIM_DEFAULT = (0, 100)

# GUI Pages
class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Signal Visualization Interface")
        self.geometry("900x700")

        # Configure grid
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.serial_interface = SerialInterface()

        # Control Panel (top)
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=0, column=0, sticky="ew", padx=20, pady=(20, 10))
        control_frame.grid_columnconfigure((0,1,2,3,4,5), weight=1)

        ctk.CTkLabel(control_frame, text="Device Angle:", anchor="w").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.angle_entry = ctk.CTkEntry(control_frame, placeholder_text="°")
        self.angle_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Device Cycles:", anchor="w").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.cycles_entry = ctk.CTkEntry(control_frame, placeholder_text="#")
        self.cycles_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Device Pulses:", anchor="w").grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.pulses_entry = ctk.CTkEntry(control_frame, placeholder_text="#")
        self.pulses_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="X Limit:", anchor="w").grid(row=0, column=2, padx=5, pady=5, sticky="ew")
        self.xlim_entry = ctk.CTkEntry(control_frame, placeholder_text="(a,b)")
        self.xlim_entry.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Y Limit:", anchor="w").grid(row=0, column=4, padx=5, pady=5, sticky="ew")
        self.ylim_entry = ctk.CTkEntry(control_frame, placeholder_text="(a,b)")
        self.ylim_entry.grid(row=0, column=5, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(control_frame, text="Data Rate:", anchor="w").grid(row=1, column=2, padx=5, pady=5, sticky="ew")
        self.resolution_entry = ctk.CTkEntry(control_frame, placeholder_text="Hz")
        self.resolution_entry.grid(row=1, column=3, padx=5, pady=5, sticky="ew")

        # Enter Graph Data
        self.resolution_btn = ctk.CTkButton(control_frame, text="Configure Graph", command=self.submit_graph_data)
        self.resolution_btn.grid(row=3, column=5, padx=5, pady=5, sticky="ew")
        
        # Enter Control Values
        self.enter_btn = ctk.CTkButton(control_frame, text="Configure Device", command=self.submit_values)
        self.enter_btn.grid(row=3, column=0, padx=5, pady=5, sticky="ew")

        # Stop Device
        self.stop_btn = ctk.CTkButton(control_frame, text="Stop", command=self.stop)
        self.stop_btn.grid(row=3, column=1, padx=5, pady=5, sticky="ew")

        # Serial Monitor (bottom)
        monitor_frame = ctk.CTkFrame(self)
        monitor_frame.grid(row=1, column=0, sticky="nsew", padx=20, pady=(10, 20))
        monitor_frame.grid_rowconfigure(1, weight=1)
        monitor_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(monitor_frame, text="Live Serial Data", font=ctk.CTkFont(size=16)).grid(row=0, column=0, pady=(10, 5))

        # Configure Plot
        self.fig, self.ax = plt.subplots()
        (self.line,) = self.ax.plot([], [], "bo", lw=2)

        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)
        self.ax.set_xlabel("Strain, ε (%)")
        self.ax.set_ylabel("Rel. Resistance Change, ΔR/Ro (%)")
        self.ax.set_title("Piezoresistive Response")

        self.canvas = FigureCanvasTkAgg(self.fig, master=monitor_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, pady=10)
        self.x_vals, self.y_vals = [], []

        self.start_btn = ctk.CTkButton(monitor_frame, text="Start Monitor", command=self.start_serial)
        self.start_btn.grid(row=2, column=0, pady=10)

        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=1000, cache_frame_data=False)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def submit_values(self):
        '''
        Sends angle, cycle, and pulse data to microcontroller.
        '''
        angle = self.angle_entry.get()
        cycles = self.cycles_entry.get()
        pulses = self.pulses_entry.get()

        angle = angle if angle else ANGLE_DEFAULT
        cycles = cycles if cycles else CYCLES_DEFAULT
        pulses = pulses if pulses else PULSES_DEFAULT

        cmd = f"SET angle={angle} cycles={cycles} pulses={pulses}"
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.send_command(cmd)

    def submit_graph_data(self):
        '''
        Sends resolution data to microcontroller and reconfigures graph
        '''
        resolution = self.resolution_entry.get()
        xlim = self.xlim_entry.get()
        ylim = self.ylim_entry.get()

        resolution = int(resolution) if resolution else RESOLUTION_DEFAULT
        xlim = tuple(map(int, xlim.split(','))) if xlim else X_LIM_DEFAULT
        ylim = tuple(map(int, ylim.split(','))) if ylim else Y_LIM_DEFAULT

        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)

        cmd = f"SET resolution={resolution}"
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.send_command(cmd)

        #self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=60/resolution * 1000, cache_frame_data=False)
        if self.ani:
            self.ani.event_source.stop()
        
        new_interval = 60 / resolution * 1000
        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=new_interval, cache_frame_data=False)
        self.canvas.draw()

    def stop(self):
        '''
        Stops the hardware device.
        '''
        if self.serial_interface.reading:
            if self.serial_interface.ser and self.serial_interface.ser.is_open:
                self.serial_interface.send_command("STOP")

    def start_serial(self):
        '''
        Initializes the reading of real-time data from the micro-controller
        '''
        if not self.serial_interface.reading:
            self.serial_interface.connect()
            self.serial_interface.read_lines(self.get_vals)

    # def display_line(self, line):
    #     self.textbox.configure(state="normal")
    #     self.textbox.insert("end", line + "\n")
    #     self.textbox.see("end")
    #     self.textbox.configure(state="disabled")

    def get_vals(self, data: list):
        '''
        A callback function. Extracts x and y data values from received microcontroller data.
        '''
        try:
            x, y = data.split(',')
            self.x_vals.append(int(x))
            self.y_vals.append(int(y))
        except Exception as e:
            print(f"Error parsing data: {e}")


    def update_plot(self, _):
        '''
        Updates graphing data in the GUI.
        '''
        self.line.set_data(self.x_vals, self.y_vals)
        return self.line,

    def close(self):
        '''
        Called on the event of closing the GUI.
        '''
        self.serial_interface.send_command("EXIT")
        exit()
