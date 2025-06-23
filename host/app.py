import customtkinter as ctk
from serial_interface import SerialInterface
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import input_validation as iv
from matplotlib.widgets import Slider
import serial.tools.list_ports as list_ports
import os
import pandas as pd
import time
import threading
from payload import Payload
from multi_display import WaveformApp

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

ANGLE_DEFAULT = 0
CYCLES_DEFAULT = 0
PULSES_DEFAULT = 0
RESOLUTION_DEFAULT = 60
X_LIM_DEFAULT = (0, 100)
Y_LIM_DEFAULT = (0, 100)

# GUI Pages
class FirstExecutionMenu(ctk.CTkFrame):
    def __init__(self, master, serial_interface: SerialInterface, on_board_selected):
        def get_com_ports():
            port_info = ["Select a Port"]
            for port in list_ports.comports():
                port_info.append(f"{port.description}")
            return port_info
        
        def update_com_ports():
            port_dropdown.configure(values=get_com_ports())

        def select_port(entry):
            for port in list_ports.comports():
                if port.device in entry:
                    self.port = port.device

        def select_board(entry):
            if entry in ["MUX08", "MUX32"]:
                self.board = entry
            
        def request_connect():
            # try:
            #     # UNCOMMENT WHEN BOARD IS ACTUALLY CONNECTED
            #     # serial_interface.connect(self.port)
            #     on_board_selected(self.board)
            #     # show_main_menu()
            # except Exception as e:
            #     print(e)
            #     return
            on_board_selected(self.board)
        
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        ports = get_com_ports()
        self.port = ""
        self.board = ""

        ctk.CTkLabel(self, text="Select a COM Port", font=("Helvetica", 16, "bold")).pack(pady=40)

        port_frame = ctk.CTkFrame(self)
        port_frame.pack(pady=20)

        port_dropdown = ctk.CTkComboBox(port_frame, values=ports, width=200, command=select_port)
        port_dropdown.pack(side="left", padx=(0, 10))

        refresh_button = ctk.CTkButton(port_frame, text="Refresh Ports", command=update_com_ports)
        refresh_button.pack(side="left")

        board_dropdown = ctk.CTkComboBox(self, values=["Select a Board", "MUX32", "MUX08"], command=select_board)
        board_dropdown.pack(pady=20)

        ctk.CTkButton(self, text="Submit", command=request_connect).pack(pady=20)

class ControlPage(ctk.CTkFrame):
    def __init__(self, master, serial_interface: SerialInterface, board: str): # make sure to add MUX settings
        super().__init__(master)
        # self.grid(row=0, column=0, sticky="nsew")
        machine_form_fields = {}
        material_form_fields = {}
        payload = {}
        self.channels = 0
        self.error_flag = False
        self.board = board
        self.machine = ""
        self.material = ""

        def pack_test_settings(parent):
            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")

            # Create a horizontal row for the label and entry
            rep_row = ctk.CTkFrame(parent, fg_color="transparent")
            rep_row.pack(anchor="w", padx=20, pady=5)

            ctk.CTkLabel(rep_row, text="Program Cycles Repetitions:").pack(side="left", padx=(0, 5))
            repetitions = ctk.CTkEntry(rep_row, placeholder_text="e.g., 500", width=100)
            repetitions.pack(side="left")

            # add dict item
            machine_form_fields["repetitions"] = {"widget": repetitions, "validate": lambda val: val.isdigit()}

        def pack_material_test_settings(parent):
            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")

            test_type_dropdown = ctk.CTkComboBox(parent, values=["Test Type", "Cyclic (C)", "Monotonic (F)"])
            test_type_dropdown.pack(anchor="w", padx=20, pady=5)

            material_form_fields["test type"] = {"widget": test_type_dropdown, "validate": lambda val: val in ["Cyclic (C)", "Monotonic (F)"]}

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
            load_cell_cap = ctk.CTkEntry(load_cell_row, width=120, placeholder_text="e.g., 500")
            load_cell_cap.pack(side="left")

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

            machine_form_fields["displacement readings"] = {"widget": disp_readings_available, "validate": None}
            machine_form_fields["displacement voltage"] = {"widget": disp_voltage, "validate": iv.check_float}
            machine_form_fields["displacement distance"] = {"widget": disp_dist, "validate": iv.check_float}
            machine_form_fields["displacement distance units"] = {"widget": disp_dist_units, "validate": lambda val: val in ["mm", "cm", "in"]}

            machine_form_fields["load readings"] = {"widget": load_readings_available, "validate": None}
            machine_form_fields["load cell capacity"] = {"widget": load_cell_cap, "validate": iv.check_float}
            machine_form_fields["load voltage"] = {"widget": voltage_entry, "validate": iv.check_float}
            machine_form_fields["load force"] = {"widget": force_entry, "validate": iv.check_float}
            machine_form_fields["load force units"] = {"widget": force_units, "validate": lambda val: val in ["kN", "N", "kg", "g"]}

        def pack_hx711_load(parent):
            ctk.CTkLabel(parent, text="Load (HX711 Load Cell)", font=("Helvetica", 16, "bold")).pack(anchor="w")
            load_frame = ctk.CTkFrame(parent, fg_color="transparent")
            load_frame.pack(padx=20, pady=5, anchor="w")
            load_readings = ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?")
            load_readings.pack(anchor="w")

            # 🔹 Load Cell Capacity row (above, on same line)
            load_cell_row = ctk.CTkFrame(load_frame, fg_color="transparent")
            load_cell_row.pack(anchor="w", pady=5)

            ctk.CTkLabel(load_cell_row, text="Load Cell Capacity (N):").pack(side="left", padx=(0, 5))
            load_cell_entry = ctk.CTkEntry(load_cell_row, width=120, placeholder_text="e.g., 500")
            load_cell_entry.pack(side="left")
            force_units = ctk.CTkComboBox(load_cell_row, values=["N", "kg", "g"], width=80)
            force_units.pack(side="left", padx=2)

            machine_form_fields["hx711 load readings"] = {"widget": load_readings, "validate": None}
            machine_form_fields["hx711 load cell capacity"] = {"widget": load_cell_entry, "validate": iv.check_float}
            machine_form_fields["hx711 load cell units"] = {"widget": force_units, "validate": lambda val: val in ["N", "kg", "g"]}

        def pack_prototype(parent):
            ctk.CTkLabel(parent, text="Prototype Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
            prototype_frame = ctk.CTkFrame(parent, fg_color="transparent")
            prototype_frame.pack(padx=20, pady=5, anchor="w")

            # cycles_frame = ctk.CTkFrame(prototype_frame)
            # cycles_frame.pack(anchor="w", pady=5)

            # ctk.CTkLabel(cycles_frame, text="Repetition Cycles:").pack(side="left", anchor="w", padx=(0,5))
            # cycles = ctk.CTkEntry(cycles_frame, placeholder_text="e.g., 500")
            # cycles.pack(side="left")

            strain_frame = ctk.CTkFrame(prototype_frame)
            strain_frame.pack(anchor="w", pady=5)

            ctk.CTkLabel(strain_frame, text="Maximum Strain (N):").pack(side="left", anchor="w", padx=(0,5))
            strain = ctk.CTkEntry(strain_frame, placeholder_text="e.g., 5")
            strain.pack(side="left")

            machine_form_fields["strain"] = {"widget": strain, "validate": iv.check_float}

        def pack_channel(parent):
            ctk.CTkLabel(parent, text="Channels", font=("Helvetica", 16, "bold")).pack(anchor="w")
            channel_frame = ctk.CTkFrame(parent, fg_color="transparent")
            channel_frame.pack(padx=20, pady=5, anchor="w")

            ctk.CTkLabel(channel_frame, text="Default Number of Channels:").pack(side="left", anchor="w", padx=(0,5))
            channels = ctk.CTkEntry(channel_frame, placeholder_text=self.channels)
            channels.pack(side="left")

            material_form_fields["channels"] = {"widget": channels, "validate": lambda val: val.isdigit()}
   
        def pack_debond(parent):
            ctk.CTkLabel(parent, text="Debond", font=("Helvetica", 16, "bold")).pack(anchor="w")
            has_debond = ctk.CTkCheckBox(parent, text="Sensor Has Debond")
            has_debond.pack(padx=20, anchor="w")

            material_form_fields["debond"] = {"widget": has_debond, "validate": None}

        def pack_sensor_config(parent):
            ctk.CTkLabel(parent, text="Sensor Configuration", font=("Helvetica", 16, "bold")).pack(anchor="w")

            length_frame = ctk.CTkFrame(parent, fg_color="transparent")
            length_frame.pack(padx=20,pady=5, anchor="w")

            width_frame = ctk.CTkFrame(parent, fg_color="transparent")
            width_frame.pack(padx=20, pady=5, anchor="w")

            height_frame = ctk.CTkFrame(parent, fg_color="transparent")
            height_frame.pack(padx=20, pady=5, anchor="w")

            sensor_num_frame = ctk.CTkFrame(parent, fg_color="transparent")
            sensor_num_frame.pack(padx=20, pady=5, anchor="w")

            ctk.CTkLabel(length_frame, text="Sensor Length (mm):").pack(side="left", anchor="w", padx=(0, 5))
            length = ctk.CTkEntry(length_frame, placeholder_text="e.g., 5")
            length.pack(side="left")

            ctk.CTkLabel(width_frame, text="Sensor Width (mm):").pack(side="left", anchor="w", padx=(0, 5))
            width = ctk.CTkEntry(width_frame, placeholder_text="e.g., 5")
            width.pack(side="left")

            ctk.CTkLabel(height_frame, text="Sensor Height (mm):").pack(side="left", anchor="w", padx=(0, 5))
            height = ctk.CTkEntry(height_frame, placeholder_text="e.g., 5")
            height.pack(side="left")

            ctk.CTkLabel(sensor_num_frame, text="Sensor Number:").pack(side="left", anchor="w", padx=(0, 5))
            sensor_num = ctk.CTkEntry(sensor_num_frame, placeholder_text="e.g., 1")
            sensor_num.pack(side="left")

            material_form_fields["length"] = {"widget": length, "validate": iv.check_float}
            material_form_fields["width"] = {"widget": width, "validate": iv.check_float}
            material_form_fields["height"] = {"widget": height, "validate": iv.check_float}
            material_form_fields["sensor number"] = {"widget": sensor_num, "validate": lambda val: val.isdigit()}

        def pack_contact(parent):
            ctk.CTkLabel(parent, text="Contact Configuration", font=("Helvetica", 16, "bold")).pack(anchor="w")

            row_contact_frame = ctk.CTkFrame(parent, fg_color="transparent")
            row_contact_frame.pack(padx=20,pady=5, anchor="w")

            col_contact_frame = ctk.CTkFrame(parent, fg_color="transparent")
            col_contact_frame.pack(padx=20, pady=5, anchor="w")

            ctk.CTkLabel(row_contact_frame, text=f"Sensor Row Where Contact was Set (1-{int(self.channels/2)}):").pack(side="left", anchor="w", padx=(0, 5))
            row = ctk.CTkEntry(row_contact_frame, placeholder_text="e.g., 5")
            row.pack(side="left")

            ctk.CTkLabel(col_contact_frame, text=f"Sensor Column Where Contact was Set (1-{int(self.channels/2)}):").pack(side="left", anchor="w", padx=(0, 5))
            col = ctk.CTkEntry(col_contact_frame, placeholder_text="e.g., 5")
            col.pack(side="left")

            material_form_fields["row"] = {"widget": row, "validate": lambda val: val.isdigit()}
            material_form_fields["column"] = {"widget": col, "validate": lambda val: val.isdigit()}
        
        def machine_option_picker(option):
            for widget in machine_settings_frame.winfo_children():
                widget.destroy()

            machine_form_fields.clear() # clear dict every time option is chosen

            if option != machine_options[0]:
                self.machine = option

            if option == "Shimadzu": # shimadzu
                pack_load_and_displacement(machine_settings_frame)
            elif option == "MTS": # MTS
                pack_test_settings(machine_settings_frame)
                pack_load_and_displacement(machine_settings_frame)
            elif option == "Mini-Shimadzu": # Mini-Shimadzu
                pack_test_settings(machine_settings_frame)
                pack_load_and_displacement(machine_settings_frame)
                pack_hx711_load(machine_settings_frame)
            elif option == "Festo": # Festo
                pack_test_settings(machine_settings_frame)
                initial_coord_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                initial_coord_frame.pack(padx=20, pady=5, anchor="w")

                ctk.CTkLabel(initial_coord_frame, text="Non-Contact/Initial Coordinates (x,y,z):").pack(side="left", anchor="w", padx=(0,5))
                initial_coord = ctk.CTkEntry(initial_coord_frame, placeholder_text="e.g., 5,1,12")
                initial_coord.pack(side="left")

                final_coord_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                final_coord_frame.pack(padx=20, pady=5, anchor="w")

                ctk.CTkLabel(final_coord_frame, text="Contact/Final Coordinates (x,y,z):").pack(side="left", anchor="w", padx=(0,5))
                final_coord = ctk.CTkEntry(final_coord_frame, placeholder_text="e.g., 0,5,2")
                final_coord.pack(side="left")

                machine_form_fields["initial coordinates"] = initial_coord
                machine_form_fields["final coordinates"] = final_coord
            elif option == "Angular Bending/Deformation Prototype": # Angular Bending
                speed_var = ctk.StringVar(value="off")
                angle_var = ctk.StringVar(value="off")
                def vary_speed():
                    for widget in motor_speed_frame.winfo_children():
                        widget.destroy()
                    if speed_var.get() == "off":
                        ctk.CTkLabel(motor_speed_frame, text="Motor Speed (RPM):").pack(anchor="w", side="left", padx=(0, 5))
                        motor_speed = ctk.CTkEntry(motor_speed_frame, placeholder_text="e.g., 60")
                        motor_speed.pack(side="left")
                        
                        machine_form_fields.pop('initial speed')
                        machine_form_fields.pop('final speed')
                        machine_form_fields.pop('speed step')

                        machine_form_fields['motor speed'] = {'widget': motor_speed, 'validate': iv.check_float}
                    else:
                        ctk.CTkLabel(motor_speed_frame, text="Motor Speed (RPM) (initial, final, steps):").pack(anchor="w", side="left", padx=(0,5))
                        initial_speed = ctk.CTkEntry(motor_speed_frame, width=80)
                        initial_speed.pack(side="left", padx=5)
                        ctk.CTkLabel(motor_speed_frame, text=", ").pack(side="left", padx=5)
                        final_speed = ctk.CTkEntry(motor_speed_frame, width=80)
                        final_speed.pack(side="left", padx=5)
                        ctk.CTkLabel(motor_speed_frame, text=", ").pack(side="left", padx=5)
                        step = ctk.CTkEntry(motor_speed_frame, width=80)
                        step.pack(side="left", padx=5)

                        machine_form_fields.pop('motor speed')
                        machine_form_fields['initial speed'] = {'widget': initial_speed, 'validate': iv.check_float}
                        machine_form_fields['final speed'] = {'widget': final_speed, 'validate': iv.check_float}
                        machine_form_fields['speed step'] = {'widget': step, 'validate': iv.check_float}

                def vary_angle():
                    for widget in angle_frame.winfo_children():
                        widget.destroy()
                    if angle_var.get() == "off":
                        ctk.CTkLabel(angle_frame, text="Device Angle (°):").pack(anchor="w", side="left", padx=(0, 5))
                        angle = ctk.CTkEntry(angle_frame, placeholder_text="e.g., 60")
                        angle.pack(side="left")
                        
                        machine_form_fields.pop('initial angle')
                        machine_form_fields.pop('final angle')
                        machine_form_fields.pop('angle step')

                        machine_form_fields['angle'] = {'widget': angle, 'validate': iv.check_float}
                    else:
                        ctk.CTkLabel(angle_frame, text="Device Angle (°) (initial, final, step):").pack(anchor="w", side="left", padx=(0,5))
                        initial_angle = ctk.CTkEntry(angle_frame, width=80)
                        initial_angle.pack(side="left", padx=5)
                        ctk.CTkLabel(angle_frame, text=", ").pack(side="left", padx=5)
                        final_angle = ctk.CTkEntry(angle_frame, width=80)
                        final_angle.pack(side="left", padx=5)
                        ctk.CTkLabel(angle_frame, text=", ").pack(side="left", padx=5)
                        step = ctk.CTkEntry(angle_frame, width=80)
                        step.pack(side="left", padx=5)

                        machine_form_fields.pop('angle')
                        machine_form_fields['initial angle'] = {'widget': initial_angle, 'validate': iv.check_float}
                        machine_form_fields['final angle'] = {'widget': final_angle, 'validate': iv.check_float}
                        machine_form_fields['angle step'] = {'widget': step, 'validate': iv.check_float}

                pack_test_settings(machine_settings_frame)
                #pack_prototype(machine_settings_frame)
                ctk.CTkCheckBox(machine_settings_frame, text="Variable Speed", variable=speed_var, onvalue="on", offvalue="off", command=vary_speed).pack(anchor="w", padx=20)
                motor_speed_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                motor_speed_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(motor_speed_frame, text="Motor Speed (RPM):").pack(anchor="w", side="left", padx=(0, 5))
                motor_speed = ctk.CTkEntry(motor_speed_frame, placeholder_text="e.g., 60")
                motor_speed.pack(side="left")

                ctk.CTkCheckBox(machine_settings_frame, text="Variable Angle", variable=angle_var, onvalue="on", offvalue="off", command=vary_angle).pack(anchor="w", padx=20)
                angle_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                angle_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(angle_frame, text="Device Angle (°):").pack(anchor="w", side="left", padx=(0, 5))
                angle = ctk.CTkEntry(angle_frame, placeholder_text="e.g., 60")
                angle.pack(side="left")

                machine_form_fields["motor speed"] = {"widget": motor_speed, "validate": iv.check_float}
                machine_form_fields["angle"] = {"widget": angle, "validate": iv.check_float}

            elif option == "One-Axis Strain Prototype": # Single-Axis Strain
                pack_test_settings(machine_settings_frame)
                pack_prototype(machine_settings_frame)
                motor_disp_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                motor_disp_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(motor_disp_frame, text="Motor Displacement (mm/min):").pack(anchor="w", side="left", padx=(0, 5))
                motor_disp = ctk.CTkEntry(motor_disp_frame, placeholder_text="e.g., 60")
                motor_disp.pack(side="left")

                machine_form_fields["motor displacement"] = {"widget": motor_disp, "validate": iv.check_float}

        def material_option_picker(option):
            for widget in material_settings_frame.winfo_children():
                widget.destroy()

            material_form_fields.clear() # clear dict every time option is chosen

            if option != material_options[0]:
                self.material = option

            if option == material_options[1] or option == material_options[2]:
                self.channels = 21
                pack_material_test_settings(material_settings_frame)
                pack_channel(material_settings_frame)
                pack_debond(material_settings_frame)
                pack_sensor_config(material_settings_frame)
            elif option == material_options[3]:
                self.channels = 10
                pack_channel(material_settings_frame)
                pack_contact(material_settings_frame)
                pack_sensor_config(material_settings_frame)
            elif option == material_options[4] or option == material_options[5]:
                self.channels = 8
                pack_channel(material_settings_frame)
                pack_contact(material_settings_frame)
                pack_sensor_config(material_settings_frame)

        def extract(key, meta):

            widget = meta["widget"]
            validate = meta["validate"]

            # user left channel box blank, indicating they want defaul no. active channels
            if key == "channels" and widget.get() == "":
                payload[key] = self.channels
                return

            if isinstance(widget, ctk.CTkCheckBox):
                payload[key] = widget.get()

            elif isinstance(widget, ctk.CTkComboBox):
                payload[key] = widget.get()

            elif isinstance(widget, ctk.CTkEntry) or isinstance(widget, ctk.CTkComboBox):
                value = widget.get()

                if validate(value):
                    payload[key] = value
                    widget.configure(border_color="gray50")
                else:
                    self.error_flag = 1
                    widget.configure(border_color="red")

        def submit_values():
            self.error_flag = 0
            data = ""
            payload.clear()
            for key, meta in machine_form_fields.items():
                extract(key, meta)

            for key, meta in material_form_fields.items():
                extract(key, meta)

            if not self.error_flag:
                try:
                    if self.machine == "Shimadzu":
                        data = f"SMDZ,{"DR" if payload["displacement readings"] else "NDR"},{payload["displacement voltage"]}_{payload["displacement distance"]+payload["displacement distance units"]}"
                        data += f",{"LR" if payload['load readings'] else "NLR"},{payload['load cell capacity']}N_{payload['load voltage']},{payload['load force']+payload['load force units']}"

                    elif self.machine == "MTS":
                        data = f"MTS,{payload["repetitions"]}C"
                        data += f",{"DR" if payload["displacement readings"] else "NDR"},{payload["displacement voltage"]}V_{payload["displacement distance"]+payload["displacement distance units"]}"
                        data += f",{"LR" if payload['load readings'] else "NLR"},{payload['load cell capacity']}N_{payload['load voltage']}V,{payload['load force']+payload['load force units']}"

                    elif self.machine == "Mini-Shimadzu":
                        data = f"MINI,{payload["repetitions"]}C"
                        data += f",{"DR" if payload["displacement readings"] else "NDR"},{payload["displacement voltage"]}V_{payload["displacement distance"]+payload["displacement distance units"]}"
                        data += f",{"LR" if payload['load readings'] else "NLR"},{payload['load cell capacity']}N_{payload['load voltage']}V,{payload['load force']+payload['load force units']}"
                        data += f",{"HXLR" if payload['hx711 load readings'] else "NHXLR"},HX{payload['hx711 load cell capacity']+payload['hx711 load cell units']}"

                    elif self.machine == "Angular Bending/Deformation Prototype":
                        data = f"BEND,{payload['repetitions']}C"
                        if payload.get('motor speed'):
                            data += f",{payload['motor speed']}RPM"
                        else:
                            data += f",VSPD_I{payload['initial speed']}_F{payload['final speed']}_S{payload['speed step']}"
                        if payload.get('angle'):
                            data += f",{payload['angle']}DEG"
                        else:
                            data += f",VDEG_I{payload['initial angle']}_F{payload['final angle']}_S{payload['angle step']}"


                    elif self.machine == "One-Axis Strain Prototype":
                        data = f"OAX,{payload['repetitions']}C"
                        data += f",{payload['strain']}N,{payload['motor displacement']}mm"

                    if self.material == "CNT-GFW":
                        data += f",CNT,{payload["test type"][-2]},{'D' if payload["debond"] else 'ND'},S{payload['sensor number']}"
                    elif self.material == "GS-GFW":
                        data += f",GS,{payload["test type"][-2]},{'D' if payload["debond"] else 'ND'},S{payload['sensor number']}"
                    elif self.material == "MWCNT":
                        data += f",MW,L{payload['length']},W{payload['width']},H{payload['height']},R{payload['row']},C{payload['column']},S{payload['sensor number']}"
                    elif self.material == "MXene":
                        data += f",MX,L{payload['length']},W{payload['width']},H{payload['height']},R{payload['row']},C{payload['column']},S{payload['sensor number']}"
                    elif self.material == "Cx-Alpha":
                        data += f",CX,L{payload['length']},W{payload['width']},H{payload['height']},R{payload['row']},C{payload['column']},S{payload['sensor number']}"
                    print(data)
                except Exception as e:
                    print(e)
                    print("Error: Machine and Material Selections Incompatible!")
            
        
        ctk.CTkLabel(self, text="Parameter Configuration", font=ctk.CTkFont(size=20)).pack(pady=20)

        # Main param frame
        param_frame = ctk.CTkFrame(self, fg_color="transparent")
        param_frame.pack(pady=40)

        # Frame to hold dropdown + settings frames in two vertical columns
        top_row_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        top_row_frame.pack()

        # === Column 1: Machine combo + settings ===
        machine_column = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        machine_column.pack(side="left", padx=10)

        machine_options = ["Chooze a Machine", "Shimadzu", "MTS", "Mini-Shimadzu", "Festo", "Angular Bending/Deformation Prototype", "One-Axis Strain Prototype"]
        machine_combo = ctk.CTkComboBox(machine_column, values=machine_options, command=machine_option_picker)
        machine_combo.pack(pady=(0, 5))

        machine_settings_frame = ctk.CTkFrame(machine_column, width=300, height=100, border_width=1, corner_radius=6)
        machine_settings_frame.pack()

        # === Column 2: Material combo + settings ===
        material_column = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        material_column.pack(side="left", padx=10)

        material_options = ["Choose a Material", "CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]
        material_combo = ctk.CTkComboBox(material_column, values=material_options, command=material_option_picker)
        material_combo.pack(pady=(0, 5))

        material_settings_frame = ctk.CTkFrame(material_column, width=300, height=100, border_width=1, corner_radius=6)
        material_settings_frame.pack()

        # Sampling rate row
        sampling_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        sampling_frame.pack(pady=20)

        ctk.CTkLabel(sampling_frame, text="Measurement Time Frequency (ms):").pack(side="left", padx=(0, 5))
        sampling_rate = ctk.CTkEntry(sampling_frame, placeholder_text="e.g., 1000")
        sampling_rate.pack(side="left")

        machine_form_fields["sampling rate"] = {'widget': sampling_rate, 'validate': lambda val: val.isdigit()}

        # Submit button
        ctk.CTkButton(param_frame, text="Submit", command=submit_values).pack(pady=20)

class SingleChannelPage(ctk.CTkFrame):
    def __init__(self, master, go_back, serial_interface: SerialInterface):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        self.serial_interface = serial_interface
        self.running = False # If true, do not spawn a new thread to read values. If false, clear to spawn thread
        self.paused = True
        self.sampling_rate = 1

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
        #self.slider.slidermax = self.x_vals[-1]
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

class Navbar(ctk.CTkFrame):
    def __init__(self, master, switch_frame):
        super().__init__(master)
        self.switch_frame = switch_frame
        self.nav = ctk.CTkSegmentedButton(
            self,
            width=400,
            values=["Settings", "Waveform", "Heatmap", "Calc."],
            corner_radius=12,
            command=self.switch_frame  # TODO: IMPLEMENT COMMAND FOR HEADER NAVIGATION
        )
        self.nav.set("Settings")
        self.nav.pack(side="top")

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Signal Visualization Interface")
        self.geometry("1000x800")
        self.grid_rowconfigure(1, weight=1)  # Row 1 will hold pages
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.serial_interface = SerialInterface()

        # Placeholders for navbar and pages
        self.navbar = None
        self.page_container = ctk.CTkFrame(self)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)


        # Initial page
        self.initial_page = FirstExecutionMenu(self, self.serial_interface, self.on_board_selected)
        self.initial_page.grid(row=0, column=0, sticky="nsew")

        # Pages dict to manage different pages
        self.pages = {}


    def on_board_selected(self, board):
        # Remove initial page
        self.initial_page.destroy()

        extra_keys = (
            ["5001 <LOAD> (VDC)", "5021 <DISP> (VDC)"]
            + [f"{6001 + i} (OHM)" for i in range(21)]  # 6001 … 6022
        )

        p = Payload(
            window_size=1000000,
            num_rows_detach=10,
            out_file_name="output/10k_test.csv",
            keys=extra_keys,
            channels=21
        )

        # Show Navbar
        self.navbar = Navbar(self, self.switch_frame)
        self.navbar.grid(row=0, column=0, sticky="ew", pady=5)

        # Initialize pages
        self.pages["Settings"] = ControlPage(self.page_container, self.serial_interface, board)
        self.pages["Waveform"] = WaveformApp(self.page_container, p)
        # self.pages["Heatmap"] = HeatmapPage(self.page_container)  # Replace with real class
        # self.pages["Calc."] = CalculationPage(self.page_container)  # Replace with real class

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.switch_frame("Settings")

    def switch_frame(self, selected):
        page = self.pages.get(selected)
        if page:
            page.tkraise()


    def show_execution_page(self):
        self.initial_page.tkraise()

    def show_single_channel(self):
        threading.Thread(target=self.auto_connect_serial, daemon=True).start()
        self.single_page.tkraise()

    def show_control_page(self):
        self.control_page.tkraise()

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

