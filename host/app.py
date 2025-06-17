import customtkinter as ctk
from serial_interface import SerialInterface
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import input_validation as iv
from matplotlib.widgets import Slider
import os
import pandas as pd
import time
import threading

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

ANGLE_DEFAULT = 0
CYCLES_DEFAULT = 0
PULSES_DEFAULT = 0
RESOLUTION_DEFAULT = 60
X_LIM_DEFAULT = (0, 100)
Y_LIM_DEFAULT = (0, 100)

# GUI Pages
class MainMenuPage(ctk.CTkFrame):
    def __init__(self, master, show_single_channel, show_multi_channel):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        formfields = {}

        ctk.CTkLabel(self, text="Main Menu", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=40)

        icon_frame = ctk.CTkFrame(self)
        icon_frame.pack(pady=20)

        single_btn = ctk.CTkButton(icon_frame, text="Single Channel", width=200, height=100, command=show_single_channel)
        single_btn.grid(row=0, column=0, padx=20)

        multi_btn = ctk.CTkButton(icon_frame, text="Control Page", width=200, height=100, command=show_multi_channel)
        multi_btn.grid(row=0, column=1, padx=20)

class ControlPage(ctk.CTkFrame):
    def __init__(self, master, go_back, serial_interface: SerialInterface): # make sure to add MUX settings
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        def pack_test_settings(parent):
            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")

            # Create a horizontal row for the label and entry
            rep_row = ctk.CTkFrame(parent, fg_color="transparent")
            rep_row.pack(anchor="w", padx=20, pady=5)

            ctk.CTkLabel(rep_row, text="Program Cycles Repetitions:").pack(side="left", padx=(0, 5))
            repetitions = ctk.CTkEntry(rep_row, placeholder_text="e.g., 500", width=100)
            repetitions.pack(side="left")


        def pack_load_and_displacement(parent):
                
            # Displacement header
                ctk.CTkLabel(parent, text="Displacement", font=("Helvetica", 16, "bold")).pack(anchor="w")

                # Indented frame for displacement fields
                displacement_fields = ctk.CTkFrame(parent, fg_color="transparent")
                displacement_fields.pack(padx=20, pady=5, anchor="w")

                disp_readings_available = ctk.CTkCheckBox(displacement_fields, text="Are Displacement Readings Available?")
                disp_readings_available.pack(anchor="w")

                # Voltage-distance row frame
                volt_dist_row = ctk.CTkFrame(displacement_fields, fg_color="transparent")
                volt_dist_row.pack(pady=5, anchor="w")

                ctk.CTkLabel(volt_dist_row, text="Voltage-Distance Equivalence:").pack(side="left", padx=(0, 5))
                disp_voltage = ctk.CTkEntry(volt_dist_row, width=60, placeholder_text="V")
                disp_voltage.pack(side="left", padx=2)
                ctk.CTkLabel(volt_dist_row, text="V =").pack(side="left", padx=2)
                disp_dist = ctk.CTkEntry(volt_dist_row, width=60)
                disp_dist.pack(side="left", padx=2)
                disp_dist_units = ctk.CTkComboBox(volt_dist_row, values=["mm", "cm", "in"], width=80)
                disp_dist_units.pack(side="left", padx=2)

                # Load Header
                ctk.CTkLabel(parent, text="Load", font=("Helvetica", 16, "bold")).pack(anchor="w")


                # Indented frame for Load fields
                load_frame = ctk.CTkFrame(parent, fg_color="transparent")
                load_frame.pack(padx=20, pady=5, anchor="w", fill="x")

                load_readings_available = ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?")
                load_readings_available.pack(anchor="w")
                # 🔹 Load Cell Capacity row (above, on same line)
                load_cell_row = ctk.CTkFrame(load_frame, fg_color="transparent")
                load_cell_row.pack(anchor="w", pady=5)

                ctk.CTkLabel(load_cell_row, text="Load Cell Capacity (N):").pack(side="left", padx=(0, 5))
                load_cell_entry = ctk.CTkEntry(load_cell_row, width=120, placeholder_text="e.g., 500")
                load_cell_entry.pack(side="left")

                # 🔹 Voltage-Newton Equivalence row
                volt_force_row = ctk.CTkFrame(load_frame, fg_color="transparent")
                volt_force_row.pack(anchor="w", pady=5)

                ctk.CTkLabel(volt_force_row, text="Voltage-Newton Equivalence:").pack(side="left", padx=(0, 5))
                voltage_entry = ctk.CTkEntry(volt_force_row, width=60, placeholder_text="V")
                voltage_entry.pack(side="left", padx=2)
                ctk.CTkLabel(volt_force_row, text="V =").pack(side="left", padx=2)
                force_entry = ctk.CTkEntry(volt_force_row, width=60, placeholder_text="e.g., 500")
                force_entry.pack(side="left", padx=2)
                force_units = ctk.CTkComboBox(volt_force_row, values=["kN", "N", "kg", "g"], width=80)
                force_units.pack(side="left", padx=2)

        def pack_hx711_load(parent):
            ctk.CTkLabel(parent, text="Load (HX711 Load Cell)", font=("Helvetica", 16, "bold")).pack(anchor="w")
            load_frame = ctk.CTkFrame(parent, fg_color="transparent")
            load_frame.pack(padx=20, pady=5, anchor="w")
            ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?").pack(anchor="w")

            # 🔹 Load Cell Capacity row (above, on same line)
            load_cell_row = ctk.CTkFrame(load_frame, fg_color="transparent")
            load_cell_row.pack(anchor="w", pady=5)

            ctk.CTkLabel(load_cell_row, text="Load Cell Capacity (N):").pack(side="left", padx=(0, 5))
            load_cell_entry = ctk.CTkEntry(load_cell_row, width=120, placeholder_text="e.g., 500")
            load_cell_entry.pack(side="left")
            force_units = ctk.CTkComboBox(load_cell_row, values=["N", "kg", "g"], width=80)
            force_units.pack(side="left", padx=2)

        def pack_prototype(parent):
            ctk.CTkLabel(parent, text="Prototype Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
            prototype_frame = ctk.CTkFrame(parent, fg_color="transparent")
            prototype_frame.pack(padx=20, pady=5, anchor="w")

            cycles_frame = ctk.CTkFrame(prototype_frame)
            cycles_frame.pack(anchor="w", pady=5)

            ctk.CTkLabel(cycles_frame, text="Repetition Cycles:").pack(side="left", anchor="w", padx=(0,5))
            cycles = ctk.CTkEntry(cycles_frame, placeholder_text="e.g., 500")
            cycles.pack(side="left")

            strain_frame = ctk.CTkFrame(prototype_frame)
            strain_frame.pack(anchor="w", pady=5)

            ctk.CTkLabel(strain_frame, text="Maximum Strain (N):").pack(side="left", anchor="w", padx=(0,5))
            strain = ctk.CTkEntry(strain_frame, placeholder_text="e.g., 5")
            strain.pack(side="left")

        def option_picker(option):
            for widget in machine_settings.winfo_children():
                widget.destroy()
            if option == machine_options[0]: # shimadzu
                pack_load_and_displacement(machine_settings)
            elif option == machine_options[1]:
                pack_test_settings(machine_settings)
                pack_load_and_displacement(machine_settings)
            elif option == machine_options[2]:
                pack_test_settings(machine_settings)
                pack_load_and_displacement(machine_settings)
                pack_hx711_load(machine_settings)
            elif option == machine_options[3]:
                pack_test_settings(machine_settings)
                initial_coord_frame = ctk.CTkFrame(machine_settings, fg_color="transparent")
                initial_coord_frame.pack(padx=20, pady=5, anchor="w")

                ctk.CTkLabel(initial_coord_frame, text="Non-Contact/Initial Coordinates (x,y,z):").pack(side="left", anchor="w", padx=(0,5))
                initial_coord = ctk.CTkEntry(initial_coord_frame, placeholder_text="e.g., 5,1,12")
                initial_coord.pack(side="left")

                final_coord_frame = ctk.CTkFrame(machine_settings, fg_color="transparent")
                final_coord_frame.pack(padx=20, pady=5, anchor="w")

                ctk.CTkLabel(final_coord_frame, text="Contact/Final Coordinates (x,y,z):").pack(side="left", anchor="w", padx=(0,5))
                final_coord = ctk.CTkEntry(final_coord_frame, placeholder_text="e.g., 0,5,2")
                final_coord.pack(side="left")
            elif option == machine_options[4]:
                pack_prototype(machine_settings)
                motor_speed_frame = ctk.CTkFrame(machine_settings, fg_color="transparent")
                motor_speed_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(motor_speed_frame, text="Motor Speed (RPM):").pack(anchor="w", side="left", padx=(0, 5))
                motor_speed = ctk.CTkEntry(motor_speed_frame, placeholder_text="e.g., 60")
                motor_speed.pack(side="left")

                angle_frame = ctk.CTkFrame(machine_settings, fg_color="transparent")
                angle_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(angle_frame, text="Device Angle (°):").pack(anchor="w", side="left", padx=(0, 5))
                angle = ctk.CTkEntry(angle_frame, placeholder_text="e.g., 60")
                angle.pack(side="left")
            elif option == machine_options[5]:
                pack_prototype(machine_settings)
                motor_disp_frame = ctk.CTkFrame(machine_settings, fg_color="transparent")
                motor_disp_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(motor_disp_frame, text="Motor Displacement (mm/min):").pack(anchor="w", side="left", padx=(0, 5))
                motor_disp = ctk.CTkEntry(motor_disp_frame, placeholder_text="e.g., 60")
                motor_disp.pack(side="left")

            
            

        ctk.CTkLabel(self, text="Parameter Configuration", font=ctk.CTkFont(size=20)).pack(pady=20)
        ctk.CTkButton(self, text="Back to Main Menu", command=go_back).pack(pady=10)

        # Set Frame to hold options
        param_frame = ctk.CTkFrame(self, fg_color="transparent")
        param_frame.pack(pady=40)

        # Set options for Options Dropdown Menu
        machine_options = ["Shimadzu", "MTS", "Mini-Shimadzu", "Festo", "Angular Bending/Deformation Prototype", "One-Axis Strain Prototype"]
        ctk.CTkComboBox(param_frame, values=machine_options, command=option_picker).grid(row=0, column=0)

        machine_settings = ctk.CTkFrame(param_frame)
        machine_settings.grid(row=1)

        material_options = ["CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]
        ctk.CTkComboBox(param_frame, values=material_options).grid(row=0, column=1)


class SingleChannelPage(ctk.CTkFrame):
    def __init__(self, master, go_back, serial_interface: SerialInterface):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        self.serial_interface = serial_interface
        self.running = False # If true, do not spawn a new thread to read values. If false, clear to spawn thread
        self.paused = True
        self.sampling_rate = 1

        ctk.CTkButton(self, text="Back to Main Menu", command=go_back).grid(row=0, column=0, padx=20, pady=10, sticky="w")

        # Reusing your existing implementation under here
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Top control frame
        control_frame = ctk.CTkFrame(self)
        control_frame.grid(row=1, column=0, sticky="ew", padx=20, pady=(0, 10))
        control_frame.grid_columnconfigure(0, weight=1)
        control_frame.grid_columnconfigure(1, weight=1)

        # Device config frame
        device_config_frame = ctk.CTkFrame(control_frame)
        device_config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="nsew")
        device_config_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(device_config_frame, text="Device Angle:").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.angle_entry = ctk.CTkEntry(device_config_frame, placeholder_text="°")
        self.angle_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(device_config_frame, text="Device Cycles:").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.cycles_entry = ctk.CTkEntry(device_config_frame, placeholder_text="#")
        self.cycles_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(device_config_frame, text="Device Speed:").grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.speed_entry = ctk.CTkEntry(device_config_frame, placeholder_text="RPM")
        self.speed_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.enter_btn = ctk.CTkButton(device_config_frame, text="Configure Device", command=self.submit_values)
        self.enter_btn.grid(row=3, column=0, columnspan=2, padx=5, pady=10)

        # Graph config frame
        graph_config_frame = ctk.CTkFrame(control_frame)
        graph_config_frame.grid(row=0, column=1, padx=10, pady=10, sticky="nsew")
        graph_config_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(graph_config_frame, text="X Limit:").grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        self.xlim_entry = ctk.CTkEntry(graph_config_frame, placeholder_text="(a,b)")
        self.xlim_entry.grid(row=0, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(graph_config_frame, text="Y Limit:").grid(row=1, column=0, padx=5, pady=5, sticky="ew")
        self.ylim_entry = ctk.CTkEntry(graph_config_frame, placeholder_text="(a,b)")
        self.ylim_entry.grid(row=1, column=1, padx=5, pady=5, sticky="ew")

        ctk.CTkLabel(graph_config_frame, text="Data Rate:").grid(row=2, column=0, padx=5, pady=5, sticky="ew")
        self.resolution_entry = ctk.CTkEntry(graph_config_frame, placeholder_text="Hz")
        self.resolution_entry.grid(row=2, column=1, padx=5, pady=5, sticky="ew")

        self.resolution_btn = ctk.CTkButton(graph_config_frame, text="Configure Graph", command=self.submit_graph_data)
        self.resolution_btn.grid(row=3, column=0, columnspan=2, padx=5, pady=10)

        # Monitor frame
        monitor_frame = ctk.CTkFrame(self)
        monitor_frame.grid(row=2, column=0, sticky="nsew", padx=20, pady=(10, 20))
        monitor_frame.grid_rowconfigure(1, weight=1)
        monitor_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(monitor_frame, text="Live Serial Data", font=ctk.CTkFont(size=16)).grid(row=0, column=0, pady=(10, 5))

        self.fig, self.ax = plt.subplots()
        (self.line,) = self.ax.plot([], [], "b-", lw=2)

        self.ax.set_xlim(0, 100)
        self.ax.set_ylim(0, 100)
        self.ax.set_xlabel("Time Elapsed (s)")
        self.ax.set_ylabel("Resistance (Ω)")
        self.ax.set_title("Resistance vs Time")


        self.canvas = FigureCanvasTkAgg(self.fig, master=monitor_frame)
        self.canvas_widget = self.canvas.get_tk_widget()
        self.canvas_widget.grid(row=1, column=0, pady=10)
        self.x_vals, self.y_vals = [], []

        button_row_frame = ctk.CTkFrame(monitor_frame, fg_color="transparent")
        button_row_frame.grid(row=2, column=0, pady=10)

        self.start_btn = ctk.CTkButton(button_row_frame, text="Start/Resume", command=self.start_serial)
        self.start_btn.grid(row=0, column=0, padx=10)

        self.stop_btn = ctk.CTkButton(button_row_frame, text="Pause", command=self.pause)
        self.stop_btn.grid(row=0, column=1, padx=10)

        self.restart_btn = ctk.CTkButton(button_row_frame, text="Stop", command=self.stop)
        self.restart_btn.grid(row=0, column=2, padx=10)

        self.download_btn = ctk.CTkButton(button_row_frame, text="Download Data", command=self.download_data)
        self.download_btn.grid(row=0, column=3, padx=5, pady=5, sticky="ew")

        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=1000, cache_frame_data=False)
        

    def submit_values(self):
        '''
        Sends angle, cycle, and pulse data to microcontroller.
        '''
        angle = self.angle_entry.get()
        cycles = self.cycles_entry.get()
        speed = self.speed_entry.get()

        # Check if entries are valid. Empty entries are assigned default values
        angle = iv.check_float(angle, ANGLE_DEFAULT)
        cycles = iv.check_int(cycles, CYCLES_DEFAULT)
        speed = iv.check_float(speed, PULSES_DEFAULT)

        # highlight entry boxes red if entries are invalid. If not, assign default border color
        if angle == None:
            self.angle_entry.configure(border_color="red")
            return
        else:
            self.angle_entry.configure(border_color="gray50")
        if cycles == None:
            self.cycles_entry.configure(border_color="red")
            return
        else:
            self.cycles_entry.configure(border_color="gray50")
        if speed == None:
            self.speed_entry.configure(border_color="red")
            return
        else:
            self.speed_entry.configure(border_color="gray50")

        cmd = f"SET angle={angle} cycles={cycles} speed={speed}"
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.send_command(cmd)


    def submit_graph_data(self):
        '''
        Sends resolution data to microcontroller and reconfigures graph
        '''
        resolution = self.resolution_entry.get()
        xlim = self.xlim_entry.get()
        ylim = self.ylim_entry.get()

        self.sampling_rate = int(resolution)
        # Check if entries are valid. Empty entries are assigned default values
        resolution = iv.check_int(resolution, RESOLUTION_DEFAULT)
        xlim = iv.check_lim(xlim, X_LIM_DEFAULT)
        ylim = iv.check_lim(ylim, Y_LIM_DEFAULT)

        # highlight entry boxes red if entries are invalid. If not, assign default border color
        if resolution == None:
            self.resolution_entry.configure(border_color="red")
            return
        else:
            self.resolution_entry.configure(border_color="gray50")
        if xlim == None:
            self.xlim_entry.configure(border_color="red")
            return
        else:
            self.xlim_entry.configure(border_color="gray50")
        if ylim == None:
            self.ylim_entry.configure(border_color="red")
            return
        else:
            self.ylim_entry.configure(border_color="gray50")

        self.ax.set_xlim(xlim)
        self.ax.set_ylim(ylim)

        if self.ani:
            self.ani.event_source.stop()
        
        new_interval = 1000/int(resolution)
        self.ani = animation.FuncAnimation(self.fig, self.update_plot, interval=new_interval, cache_frame_data=False)
        self.slider.slidermax = self.x_vals[-1]
        self.canvas.draw()

    def download_data(self):
        file_path = ctk.filedialog.asksaveasfilename(
            title="Select a location",
            filetypes=(("CSV Files", "*.csv"), ("All Files", "*.*")),
            initialdir=os.path.expanduser("~")
        )
        
        if file_path[-4:] != '.csv':
            file_path += '.csv'
        
        data = {'strain': self.x_vals, 'pz_response': self.y_vals}
        df = pd.DataFrame(data)

        df.to_csv(file_path, index=False)

    def pause(self):
        '''
        Pauses data acquisition
        '''
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.send_command("PAUSE")
            self.paused = True


    def stop(self):
        '''
        Stops the hardware device.
        '''
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            self.serial_interface.send_command("EXIT")

    def start_serial(self):
        '''
        Initializes the reading of real-time data from the micro-controller
        '''
        if self.serial_interface.ser and self.serial_interface.ser.is_open:
            # so that thread isn't spawned again when user resumes graph
            if self.running == False:
                self.running = True
                threading.Thread(target=self.serial_interface.read_lines, args=(self.get_vals,), daemon=True).start()
            # thread exits when data acquisition paused. Can only be reopened if acquisition
            # is resumed 
            if self.paused:
                print("Initializing data acquisition")
                self.serial_interface.send_command("START")
                self.paused = False
                threading.Thread(target=self.request_data, daemon=True).start()

    def request_data(self):
        while self.paused == False:
            self.serial_interface.send_command("REQUEST")
            time.sleep(1 / self.sampling_rate)
        print("Paused, thread exiting")

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

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Signal Visualization Interface")
        self.geometry("1000x800")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.serial_interface = SerialInterface()

        self.main_menu = MainMenuPage(self, self.show_single_channel, self.show_control_page)
        self.single_page = SingleChannelPage(self, self.show_main_menu, self.serial_interface)
        self.control_page = ControlPage(self, self.show_main_menu, self.serial_interface)

        self.show_main_menu()

    def show_main_menu(self):
        self.main_menu.tkraise()

    def show_single_channel(self):
        threading.Thread(target=self.auto_connect_serial, daemon=True).start()
        self.single_page.tkraise()

    def show_control_page(self):
        self.control_page.tkraise()

    def go_back(self):
        self.clear_window()
        self.serial_interface.disconnect()
        self.show_main_menu()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def close(self):
        '''
        Called on the event of closing the GUI.
        '''
        self.clear_window()
        self.serial_interface.disconnect()
        exit()

    def auto_connect_serial(self):
        '''
        Waits for COM4 to be available, then connects and starts reading.
        '''
        while True:
            try:
                self.serial_interface.connect()
                if self.serial_interface.ser and self.serial_interface.ser.is_open:
                    print("Connected to COM4.")
                    break
            except:
                print("Waiting for COM4...")
            time.sleep(1)  # Wait before retrying

