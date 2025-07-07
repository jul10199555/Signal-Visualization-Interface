import customtkinter as ctk
from serial_interface import SerialInterface
import serial.tools.list_ports as list_ports
import input_validation as iv

class ComPortMenu(ctk.CTkFrame):
    '''A dropdown showing available open COM ports.'''
    def __init__(self, master, setPortCallback):
        super().__init__(master, fg_color='transparent')

        def get_com_ports():
            '''Retrieves available COM ports.'''
            port_info = ["Select a Port"]
            for port in list_ports.comports():
                port_info.append(f"{port.description}")
            return port_info
        
        def update_com_ports():
            '''Called upon clicking refresh. Refreshes available COM port list.'''
            self.port_dropdown.configure(values=get_com_ports())

        def select_port(entry):
            '''Calls port setter callback when a COM port is selected from the dropdown.'''
            for port in list_ports.comports():
                if port.device in entry:
                    setPortCallback(port.device)

        ports = get_com_ports()

        port_frame = ctk.CTkFrame(self, fg_color='transparent')
        port_frame.pack(pady=20)

        self.port_dropdown = ctk.CTkComboBox(port_frame, values=ports, width=200, command=select_port)
        self.port_dropdown.pack(side="left", padx=(0, 10))

        refresh_button = ctk.CTkButton(port_frame, text="Refresh", command=update_com_ports, width=60)
        refresh_button.pack(side="left")

class ControlPage(ctk.CTkFrame):
    '''A page which houses all configuration settings for the test.'''

    def __init__(self, master, serial_interface: SerialInterface, board: str, on_config_selected):
        super().__init__(master)
        machine_form_fields = {}
        material_form_fields = {}
        board_fields = {}
        general_fields = {}
        payload = {}
        self.channels = 0
        self.error_flag = False
        self.board = board
        self.machine = ""
        self.material = ""
        self.isFingerBend = False
        self.pico_port = ""
        self.pico_ser = None

        def pack_test_settings(parent):
            '''Packs program cycles entry into UI.'''

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
            '''Packs cyclic vs monotonic test setting dropdown into the UI.'''

            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")

            test_type_dropdown = ctk.CTkComboBox(parent, values=["Test Type", "Cyclic (C)", "Monotonic (F)"])
            test_type_dropdown.pack(anchor="w", padx=20, pady=5)

            material_form_fields["test type"] = {"widget": test_type_dropdown, "validate": lambda val: val in ["Cyclic (C)", "Monotonic (F)"]}

        def pack_displacement_and_load(parent):
            '''Packs displacement and load configuration settings into UI.'''

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
            '''Packs hx711 load settings into UI.'''

            ctk.CTkLabel(parent, text="Load (HX711 Load Cell)", font=("Helvetica", 16, "bold")).pack(anchor="w")
            load_frame = ctk.CTkFrame(parent, fg_color="transparent")
            load_frame.pack(padx=20, pady=5, anchor="w")
            load_readings = ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?")
            load_readings.pack(anchor="w")

            # Load Cell Capacity row (above, on same line)
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

        def pack_strain(parent):
            '''Packs strain configuration settings into UI.'''

            ctk.CTkLabel(parent, text="Prototype Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
            prototype_frame = ctk.CTkFrame(parent, fg_color="transparent")
            prototype_frame.pack(padx=20, pady=5, anchor="w")

            strain_frame = ctk.CTkFrame(prototype_frame)
            strain_frame.pack(anchor="w", pady=5)

            ctk.CTkLabel(strain_frame, text="Maximum Strain (N):").pack(side="left", anchor="w", padx=(0,5))
            strain = ctk.CTkEntry(strain_frame, placeholder_text="e.g., 5")
            strain.pack(side="left")

            machine_form_fields["strain"] = {"widget": strain, "validate": iv.check_float}

        def pack_channel(parent):
            '''Packs channel entry into UI.'''
        
            ctk.CTkLabel(parent, text="Channels", font=("Helvetica", 16, "bold")).pack(anchor="w")
            channel_frame = ctk.CTkFrame(parent, fg_color="transparent")
            channel_frame.pack(padx=20, pady=5, anchor="w")

            ctk.CTkLabel(channel_frame, text="Default Number of Channels:").pack(side="left", anchor="w", padx=(0,5))
            channels = ctk.CTkEntry(channel_frame, placeholder_text=self.channels)
            channels.pack(side="left")

            material_form_fields["channels"] = {"widget": channels, "validate": lambda val: val.isdigit()}
   
        def pack_debond(parent):
            '''Packs debond checkbox into UI.'''
            ctk.CTkLabel(parent, text="Debond", font=("Helvetica", 16, "bold")).pack(anchor="w")
            has_debond = ctk.CTkCheckBox(parent, text="Sensor Has Debond")
            has_debond.pack(padx=20, anchor="w")

            material_form_fields["debond"] = {"widget": has_debond, "validate": None}

        def pack_sensor_config(parent):
            '''Packs sensor dimension entries into UI.'''
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
            '''Packs sensor contact entries into UI.'''
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
            '''Called upon selecting a machine in the machine options dropdown. Dynamically builds UI depending on option picked.'''

            # Clear frame to provide a clean slate to display entries
            for widget in machine_settings_frame.winfo_children():
                widget.destroy()

            machine_form_fields.clear() # clear dict every time option is chosen
            self.isFingerBend = False

            if option != machine_options[0]:
                self.machine = option

            if option == "Shimadzu":
                pack_displacement_and_load(machine_settings_frame)
            elif option == "MTS":
                pack_test_settings(machine_settings_frame)
                pack_displacement_and_load(machine_settings_frame)
            elif option == "Mini-Shimadzu":
                pack_test_settings(machine_settings_frame)
                pack_displacement_and_load(machine_settings_frame)
                pack_hx711_load(machine_settings_frame)
            elif option == "Festo":
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
                self.isFingerBend = True
                speed_var = ctk.StringVar(value="off")
                angle_var = ctk.StringVar(value="off")

                def vary_speed():
                    '''When checked, changes UI to allow user to set initial, final, and step motor speed parameters.'''

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
                    '''When checked, changes UI to allow user to set initial, final, and step motor angle parameters.'''

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

                def set_port(port):
                    '''Sets port for connecting to Raspberry Pi Pico'''
                    self.pico_port = port

                ctk.CTkLabel(machine_settings_frame, text="Select Control MCU", font=("Helvetica", 16, 'bold')).pack(anchor='w')
                com_menu = ComPortMenu(machine_settings_frame, set_port)
                com_menu.pack(pady=5, anchor='w')
                pack_test_settings(machine_settings_frame)
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
                pack_strain(machine_settings_frame)
                motor_disp_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                motor_disp_frame.pack(padx=20, pady=5, anchor="w")
                
                ctk.CTkLabel(motor_disp_frame, text="Motor Displacement (mm/min):").pack(anchor="w", side="left", padx=(0, 5))
                motor_disp = ctk.CTkEntry(motor_disp_frame, placeholder_text="e.g., 60")
                motor_disp.pack(side="left")

                machine_form_fields["motor displacement"] = {"widget": motor_disp, "validate": iv.check_float}

        def material_option_picker(option):
            '''Called upon selecting a material in the material options dropdown. Dynamically builds UI depending on option picked.'''

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
            '''Gets widget value and validates it, based on the validation function of the widget. Highlights border of error causing widget <red>.'''
            widget = meta["widget"]
            validate = meta["validate"]

            # user left channel box blank, indicating they want defaul no. active channels
            if key == "channels" and widget.get() == "":
                payload[key] = self.channels
                return

            if isinstance(widget, ctk.CTkCheckBox):
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
            '''Called upon clicking the submit button. Calls extract on every form dictionary (material, machine, general forms).
            Then, constructs a serial payload to send to the board'''

            self.error_flag = 0
            data = ""
            payload.clear()

            # Error-check fields
            for key, meta in general_fields.items():
                extract(key, meta)

            for key, meta in machine_form_fields.items():
                extract(key, meta)

            for key, meta in material_form_fields.items():
                extract(key, meta)

            for key, meta in board_fields.items():
                extract(key, meta)

            # Construct payload data
            if not self.error_flag:
                try:
                    if board == "MUX32":
                        data = f"MUX32,ENV_{payload['temp units'] if payload['temp checkbox'] else "NT"}"
                        data += f"_{"RH" if payload['rh checkbox'] else "NRH"}_{payload['pressure units'] if payload['pressure checkbox'] else "NP"}"
                        data += f"_{payload['gas units'] if payload['gas checkbox'] else "NG"}"
                        data += f"_{payload['lux units'] + "_" + payload['lux bits'] if payload['light checkbox'] else "NL"}"

                    else:
                        data = "MUX08"

                    data += ","

                    if self.machine == "Shimadzu" or self.machine == "MTS" or "Mini-Shimadzu":
                        data += "SMDZ" if self.machine == "Shimadzu" else ""
                        data += f"MTS,{payload['repetitions']}C" if self.machine == "MTS" else ""
                        data += f"MINI,{payload['repetitions']}C,{"HXLR" if payload['hx711 load readings'] else "NHXLR"},HX{payload['hx711 load cell capacity']+'_'+payload['hx711 load cell units']}"if self.machine == "Mini-Shimadzu" else ""
                        data += f",{"DR" if payload["displacement readings"] else "NDR"},{payload["displacement voltage"]}V_{payload["displacement distance"]+'_'+payload["displacement distance units"]}"
                        data += f",{"LR" if payload['load readings'] else "NLR"},{payload['load cell capacity']}_{payload['load voltage']}V,{payload['load force']+'_'+payload['load force units']}"

                    elif self.machine == "Angular Bending/Deformation Prototype":
                        data += f"BEND,{payload['repetitions']}C"
                        pico_data = f"SET,{payload['repetitions']}C,"
                        if payload.get('motor speed'):
                            pico_data += f"{payload['motor speed']}RPM"
                        else:
                            pico_data+= f"VSPD_I{payload['initial speed']}_F{payload['final speed']}_S{payload['speed step']}"

                        if payload.get('angle'):
                            pico_data += f",{payload['angle']}DEG"
                        else:
                            pico_data += f",VDEG_I{payload['initial angle']}_F{payload['final angle']}_S{payload['angle step']}"


                    elif self.machine == "One-Axis Strain Prototype":
                        data += f"OAX,{payload['repetitions']}C"
                        data += f",{payload['strain']}N,{payload['motor displacement']}mm"

                    if self.material == "CNT-GFW" or self.material == "GS-GFW":
                        data += f",{"CNT" if self.material == "CNT-GFW" else "GS"},{payload["test type"][-2]},L{payload['length']},W{payload['width']},H{payload['height']},{'D' if payload["debond"] else 'ND'},S{payload['sensor number']}"

                    elif self.material == "MWCNT" or self.material == "MXene" or self.material == "Cx-Alpha":
                        data += ",MW" if self.material == "MWCNT" else ""
                        data += ",MX" if self.material == "MXene" else ""
                        data += ",CX" if self.material == "Cx-Alpha" else ""
                        data += f",L{payload['length']},W{payload['width']},H{payload['height']},R{payload['row']}_C{payload['column']},S{payload['sensor number']}"

                    data += f",CHAN{payload['channels']}"
                    print(data)
                    # if finger bend is selected, connect to RP Pico
                    if self.isFingerBend:
                        self.pico_ser = SerialInterface()
                        # attempt to connect to pico
                        if self.pico_ser.connect(self.pico_port, 5):
                            return # no con exito :(
                        self.pico_ser.send_command(pico_data)
                        
                    serial_interface.send_command("1")
                    if serial_interface.ser.readline().decode().strip() != 'ACK': return # mcu is ready to receive data
                    serial_interface.send_command(data) # send config data to MCU
                    raw = serial_interface.ser.readline().decode().strip() # MCU sends back header info to help structure payload
                    on_config_selected(raw.split(','), 40 if payload['channels'] == 21 else int(payload['channels']), payload['filename'], int(payload['max data']), int(payload['sampling rate'])) # callback, destroys control page and takes user to main menu
                except Exception as e:
                    print(e)
                    # print("Error: Machine and Material Selections Incompatible!")

        if board == "MUX32":
            # pack necessary paramters for MUX32 Configuration
            def config_light():
                lux_units.configure(state="normal" if light_checkbox.get() else "disabled")
                lux_bits.configure(state="normal" if light_checkbox.get() else "disabled")

            env_frame = ctk.CTkFrame(self, fg_color="transparent")
            env_frame.pack(pady=5)

            light_frame = ctk.CTkFrame(self, fg_color="transparent")
            light_frame.pack(pady=5)

            temp_units = ctk.CTkComboBox(env_frame, values=["C", "F"], state="disabled")
            temp_checkbox = ctk.CTkCheckBox(env_frame, text="Enable Temperature Measurement", command=lambda: temp_units.configure(state="normal" if temp_checkbox.get() else "disabled"))
            temp_checkbox.pack(side="left", padx=10)
            temp_units.pack(side="left", padx=10)

            rh_checkbox = ctk.CTkCheckBox(env_frame, text="Enable R.H% Measurement")
            rh_checkbox.pack(side="left", padx=10)

            pressure_units = ctk.CTkComboBox(env_frame, values=["hPa", "mBar", "mmHg"], state="disabled")
            pressure_checkbox = ctk.CTkCheckBox(env_frame, text="Enable Atm. Pressure Measurement", command=lambda: pressure_units.configure(state="normal" if pressure_checkbox.get() else "disabled"))
            pressure_checkbox.pack(side="left", padx=10)
            pressure_units.pack(side="left", padx=10)

            gas_units = ctk.CTkComboBox(env_frame, values=["KOhms", "TVoC Scale"], state="disabled")
            gas_checkbox = ctk.CTkCheckBox(env_frame, text="Enable Gas Measurement", command=lambda: gas_units.configure(state="normal" if gas_checkbox.get() else "disabled"))
            gas_checkbox.pack(side="left", padx=10)
            gas_units.pack(side="left", padx=10)

            lux_units = ctk.CTkComboBox(light_frame, values=["ALS", "UVS"], state="disabled")
            lux_bits = ctk.CTkComboBox(light_frame, values=["16", "17", "18", "19", "20"], state="disabled")
            light_checkbox = ctk.CTkCheckBox(light_frame, text="Enable Ambient/UV Light Measurement", command=config_light)
            light_checkbox.pack(side="left", padx=10)
            ctk.CTkLabel(light_frame, text="Lux Mode").pack(side="left", padx=10)
            lux_units.pack(side="left", padx=10)
            ctk.CTkLabel(light_frame, text="Lux Bits").pack(side="left", padx=10)
            lux_bits.pack(side="left", padx=10)

            # Log items in board fields dictionary to validate values
            board_fields["temp checkbox"] = {"widget": temp_checkbox, "validate": None}
            board_fields["temp units"] = {"widget": temp_units, "validate": lambda val: not(val not in ["C", "F"] and temp_checkbox.get())}
            board_fields["rh checkbox"] = {"widget": rh_checkbox, "validate": None}
            board_fields["pressure checkbox"] = {"widget": pressure_checkbox, "validate": None}
            board_fields["pressure units"] = {"widget": pressure_units, "validate": lambda val: not(val not in ["hPa", "mBar", "mmHg"] and pressure_checkbox.get())}
            board_fields["gas checkbox"] = {"widget": gas_checkbox, "validate": None}
            board_fields["gas units"] = {"widget": gas_units, "validate": lambda val: not(val not in ["KOhms", "TVoC Scale"] and gas_checkbox.get())}
            board_fields["light checkbox"] = {"widget": light_checkbox, "validate": None}
            board_fields["lux units"] = {"widget": lux_units, "validate": lambda val: not(val not in ["ALS", "UVS"] and light_checkbox.get())}
            board_fields["lux bits"] = {"widget": lux_bits, "validate": lambda val: not(val not in ["16", "17", "18", "19", "20"] and light_checkbox.get())}

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

        general_fields['machine options'] = {'widget': machine_combo, 'validate': lambda val: val in ["Shimadzu", "MTS", "Mini-Shimadzu", "Festo", "Angular Bending/Deformation Prototype", "One-Axis Strain Prototype"]}

        machine_settings_frame = ctk.CTkFrame(machine_column, width=300, height=100, border_width=1, corner_radius=6)
        machine_settings_frame.pack()

        # === Column 2: Material combo + settings ===
        material_column = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        material_column.pack(side="left", padx=10)

        material_options = ["Choose a Material", "CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]
        material_combo = ctk.CTkComboBox(material_column, values=material_options, command=material_option_picker)
        material_combo.pack(pady=(0, 5))

        general_fields['material options'] = {'widget': material_combo, 'validate': lambda val: val in ["CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]}

        material_settings_frame = ctk.CTkFrame(material_column, width=300, height=100, border_width=1, corner_radius=6)
        material_settings_frame.pack()

        # Sampling rate row
        sampling_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        sampling_frame.pack(pady=20)

        ctk.CTkLabel(sampling_frame, text="Measurement Time Frequency (ms):").pack(side="left", padx=(0, 5))
        sampling_rate = ctk.CTkEntry(sampling_frame, placeholder_text="e.g., 1000")
        sampling_rate.pack(side="left")

        general_fields["sampling rate"] = {'widget': sampling_rate, 'validate': lambda val: val.isdigit()}

        frame = ctk.CTkFrame(param_frame, fg_color='transparent')
        frame.pack(pady=5)

        ctk.CTkLabel(frame, text="Enter Filename to Save Data To:").pack(side='left', padx=5)

        file_entry =  ctk.CTkEntry(frame, placeholder_text='*.csv')
        file_entry.pack(side='left', padx=5)

        ctk.CTkLabel(frame, text='Enter Maximum Visible Points:').pack(side='left', padx=(20, 5))

        max_data_entry = ctk.CTkEntry(frame, placeholder_text='At least 100')
        max_data_entry.pack(side='left', padx=5)

        general_fields['filename'] = {'widget': file_entry, 'validate': lambda val: val != ""}
        general_fields['max data'] = {'widget': max_data_entry, 'validate': lambda val: val.isdigit() and int(val) >= 100}

        # Submit button
        ctk.CTkButton(param_frame, text="Submit", command=submit_values).pack(pady=10)
