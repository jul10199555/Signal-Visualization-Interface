import customtkinter as ctk

from robot import Robot
from serial_interface import SerialInterface
import serial.tools.list_ports as list_ports
import input_validation as iv
import presets  # <-- usar el módulo completo
import pprint
import os
import importlib


class ComPortMenu(ctk.CTkFrame):
    '''A dropdown showing available open COM ports.'''
    def __init__(self, master, setPortCallback):
        super().__init__(master, fg_color='transparent')

        def get_com_ports():
            port_info = ["Select a Port"]
            for port in list_ports.comports():
                port_info.append(f"{port.description}")
            return port_info
        
        def update_com_ports():
            self.port_dropdown.configure(values=get_com_ports())

        def select_port(entry):
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
    def __init__(self, master, serial_interface: SerialInterface, board: str, on_config_selected, on_back):
        super().__init__(master)

        # --- Recargar presets de disco cada vez que se entra a esta página ---
        try:
            importlib.reload(presets)
        except Exception:
            pass

        # === CONTENEDOR PRINCIPAL CON SCROLL ===
        scrollable = ctk.CTkScrollableFrame(self, fg_color="transparent")
        scrollable.pack(fill="both", expand=True, padx=10, pady=10)

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
        self.need_pico = False
        self.pico_port = ""
        self.pico_ser = None
        self.robot = None

        # ============ Helpers para leer/escribir presets ============
        def _widget_value(widget):
            if isinstance(widget, ctk.CTkCheckBox):
                return bool(widget.get())
            return widget.get()

        def _read_fields(fields_dict):
            out = {}
            for key, meta in fields_dict.items():
                try:
                    out[key] = _widget_value(meta["widget"])
                except Exception:
                    pass
            return out

        def _presets_path():
            # Guardar SIEMPRE junto al archivo actual
            return os.path.join(os.path.dirname(__file__), "presets.py")

        def _save_preset_to_file(new_presets):
            try:
                content = "PRESETS = " + pprint.pformat(new_presets, width=100, sort_dicts=False) + "\n"
                with open(_presets_path(), "w", encoding="utf-8") as f:
                    f.write(content)
                # Actualizar el módulo en memoria para esta sesión
                presets.PRESETS = new_presets
                try:
                    importlib.reload(presets)  # por si hay otros lugares que lo lean
                except Exception:
                    pass
                return True, None
            except Exception as e:
                return False, str(e)

        def save_current_preset():
            name = preset_name_entry.get().strip()
            if not name:
                save_status.configure(text="Pon un nombre para el preset.", text_color="orange")
                return

            # Construir preset según estructura
            preset = {
                "machine": self.machine if self.machine else general_fields['machine options']['widget'].get(),
                "material": self.material if self.material else general_fields['material options']['widget'].get(),
                "general": _read_fields(general_fields),
                "machine_fields": _read_fields(machine_form_fields),
                "material_fields": _read_fields(material_form_fields),
                "board_fields": _read_fields(board_fields) if self.board == "MUX32" else {}
            }

            # Limpiar valores "Choose..." si quedaron
            if preset["machine"] in ["Chooze a Machine", "Choose a Machine", "Select a Machine"]:
                preset["machine"] = ""
            if preset["material"] in ["Choose a Material", "Select a Material"]:
                preset["material"] = ""

            # Tomar lo actual del módulo y actualizar
            new_presets = dict(presets.PRESETS)
            new_presets[name] = preset

            ok, err = _save_preset_to_file(new_presets)
            if ok:
                save_status.configure(text=f"Preset '{name}' guardado en presets.py", text_color="green")
                # refrescar combo local
                current_values = list(preset_combo.cget("values"))
                if name not in current_values:
                    preset_combo.configure(values=[*current_values, name])
            else:
                save_status.configure(text=f"Error al guardar: {err}", text_color="red")
        # ============================================================

        # ---------- Resto de tu código (igual que antes) ----------
        def pack_test_settings(parent):
            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
            rep_row = ctk.CTkFrame(parent, fg_color="transparent")
            rep_row.pack(anchor="w", padx=20, pady=5)
            ctk.CTkLabel(rep_row, text="Program Cycles Repetitions:").pack(side="left", padx=(0, 5))
            repetitions = ctk.CTkEntry(rep_row, placeholder_text="e.g., 500", width=100)
            repetitions.pack(side="left")
            machine_form_fields["repetitions"] = {"widget": repetitions, "validate": lambda val: val.isdigit()}

        def pack_material_test_settings(parent):
            ctk.CTkLabel(parent, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
            test_type_dropdown = ctk.CTkComboBox(parent, values=["Test Type", "Cyclic (C)", "Monotonic (F)"])
            test_type_dropdown.pack(anchor="w", padx=20, pady=5)
            material_form_fields["test type"] = {"widget": test_type_dropdown, "validate": lambda val: val in ["Cyclic (C)", "Monotonic (F)"]}

        def pack_displacement_and_load(parent):
            ctk.CTkLabel(parent, text="Displacement", font=("Helvetica", 16, "bold")).pack(anchor="w")
            displacement_fields = ctk.CTkFrame(parent, fg_color="transparent")
            displacement_fields.pack(padx=20, pady=5, anchor="w")
            disp_readings_available = ctk.CTkCheckBox(displacement_fields, text="Are Displacement Readings Available?")
            disp_readings_available.pack(anchor="w")
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

            ctk.CTkLabel(parent, text="Load", font=("Helvetica", 16, "bold")).pack(anchor="w")
            load_frame = ctk.CTkFrame(parent, fg_color="transparent")
            load_frame.pack(padx=20, pady=5, anchor="w", fill="x")
            load_readings_available = ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?")
            load_readings_available.pack(anchor="w")
            volt_force_row = ctk.CTkFrame(load_frame, fg_color="transparent")
            volt_force_row.pack(anchor="w", pady=5)
            ctk.CTkLabel(volt_force_row, text="Voltage-Newton Equivalence:").pack(side="left", padx=(0, 5))
            voltage_entry = ctk.CTkEntry(volt_force_row, width=60, placeholder_text="V")
            voltage_entry.pack(side="left", padx=2)
            ctk.CTkLabel(volt_force_row, text="V =").pack(side="left", padx=2)
            force_entry = ctk.CTkEntry(volt_force_row, width=60, placeholder_text="e.g., 500")
            force_entry.pack(side="left", padx=2)
            force_units = ctk.CTkComboBox(volt_force_row, values=["g", "N", "kg", "kN"], width=80)
            force_units.pack(side="left", padx=2)

            machine_form_fields["displacement readings"] = {"widget": disp_readings_available, "validate": None}
            machine_form_fields["displacement voltage"] = {"widget": disp_voltage, "validate": iv.check_float}
            machine_form_fields["displacement distance"] = {"widget": disp_dist, "validate": iv.check_float}
            machine_form_fields["displacement distance units"] = {"widget": disp_dist_units, "validate": lambda val: val in ["N", "mm", "cm", "in"]}
            machine_form_fields["load readings"] = {"widget": load_readings_available, "validate": None}
            machine_form_fields["load voltage"] = {"widget": voltage_entry, "validate": iv.check_float}
            machine_form_fields["load force"] = {"widget": force_entry, "validate": iv.check_float}
            machine_form_fields["load force units"] = {"widget": force_units, "validate": lambda val: val in ['g', 'N', 'kg', 'kN']}

        def pack_hx711_load(parent):
            ctk.CTkLabel(parent, text="Load (HX711 Load Cell)", font=("Helvetica", 16, "bold")).pack(anchor="w")
            load_frame = ctk.CTkFrame(parent, fg_color="transparent")
            load_frame.pack(padx=20, pady=5, anchor="w")
            load_readings = ctk.CTkCheckBox(load_frame, text="Are Load Readings Available?")
            load_readings.pack(anchor="w")
            load_cell_row = ctk.CTkFrame(load_frame, fg_color="transparent")
            load_cell_row.pack(anchor="w", pady=5)
            ctk.CTkLabel(load_cell_row, text="Load Cell Capacity:").pack(side="left", padx=(0, 5))
            load_cell_entry = ctk.CTkEntry(load_cell_row, width=120, placeholder_text="e.g., 500")
            load_cell_entry.pack(side="left")
            force_units = ctk.CTkComboBox(load_cell_row, values=["g", "N", "kg"], width=80)
            force_units.pack(side="left", padx=2)
            machine_form_fields["hx711 load readings"] = {"widget": load_readings, "validate": None}
            machine_form_fields["hx711 load cell capacity"] = {"widget": load_cell_entry, "validate": iv.check_float}
            machine_form_fields["hx711 load cell units"] = {"widget": force_units, "validate": lambda val: val in ['mg', 'g', 'N', 'kg', 'kN']}

        def pack_strain(parent):
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
            machine_form_fields.clear()
            self.need_pico = False
            if option != machine_options[0]:
                self.machine = option

            if option == "Shimadzu":
                pack_test_settings(machine_settings_frame)
                pack_displacement_and_load(machine_settings_frame)
            elif option == "MTS":
                pack_test_settings(machine_settings_frame)
                pack_displacement_and_load(machine_settings_frame)
            elif option == "Mini-Shimadzu":
                pack_test_settings(machine_settings_frame)
                pack_displacement_and_load(machine_settings_frame)
                pack_hx711_load(machine_settings_frame)
            elif option == "Festo":
                ctk.CTkLabel(machine_settings_frame, text="Test Settings", font=("Helvetica", 16, "bold")).pack(anchor="w")
                ip_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                ip_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(ip_frame, text="Robot IP Address:").pack(side="left", padx=(0, 5))
                ip_entry = ctk.CTkEntry(ip_frame, placeholder_text="e.g., 192.168.56.101")
                ip_entry.pack(side="left")
                ip_entry.insert(0, "192.168.56.101")
                up_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                up_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(up_frame, text="Up Joint Pos:").pack(side="left", padx=(0, 5))
                up_entry = ctk.CTkEntry(up_frame, placeholder_text="j0,j1,j2,j3,j4,j5")
                up_entry.pack(side="left")
                up_entry.insert(0, "1.314,-1.407,1.772,-1.985,-1.634,-0.262")
                down_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                down_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(down_frame, text="Down Joint Pos:").pack(side="left", padx=(0, 5))
                down_entry = ctk.CTkEntry(down_frame, placeholder_text="j0,j1,j2,j3,j4,j5")
                down_entry.pack(side="left")
                down_entry.insert(0, "1.384,-1.044,1.889,-2.492,-1.617,-0.137")
                period_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                period_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(period_frame, text="Period Time (s):").pack(side="left", padx=(0, 5))
                period_entry = ctk.CTkEntry(period_frame, width=80, placeholder_text="e.g., 3.0")
                period_entry.pack(side="left")
                period_entry.insert(0, "3.0")
                va_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                va_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(va_frame, text="Velocity (0–1):").pack(side="left", padx=(0, 5))
                vel_entry = ctk.CTkEntry(va_frame, width=60, placeholder_text="1.0")
                vel_entry.pack(side="left", padx=(0, 15))
                vel_entry.insert(0, "1.0")
                ctk.CTkLabel(va_frame, text="Acceleration (0–1):").pack(side="left", padx=(0, 5))
                acc_entry = ctk.CTkEntry(va_frame, width=60, placeholder_text="1.0")
                acc_entry.pack(side="left")
                acc_entry.insert(0, "1.0")
                btn_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                btn_frame.pack(padx=20, pady=15, anchor="w")

                def on_connect():
                    ip = ip_entry.get().strip()
                    up = [float(x) for x in up_entry.get().split(",")]
                    down = [float(x) for x in down_entry.get().split(",")]
                    period = float(period_entry.get())
                    vel = float(vel_entry.get())
                    acc = float(acc_entry.get())
                    robot = Robot(ip, up, down, period, velocity=vel, acceleration=acc)
                    self.robot = robot
                    ctk.CTkLabel(btn_frame, text="✓ Connected", text_color="green").pack(side="left", padx=(10, 0))

                ctk.CTkButton(btn_frame, text="Connect", command=on_connect).pack(side="left")

            elif option == "Angular Bending/Deformation Prototype":
                self.need_pico = True
                speed_var = ctk.StringVar(value="off")
                angle_var = ctk.StringVar(value="off")

                def vary_speed():
                    for widget in motor_speed_frame.winfo_children():
                        widget.destroy()
                    if speed_var.get() == "off":
                        ctk.CTkLabel(motor_speed_frame, text="Motor Speed (RPM):").pack(anchor="w", side="left", padx=(0, 5))
                        motor_speed = ctk.CTkEntry(motor_speed_frame, placeholder_text="e.g., 60")
                        motor_speed.pack(side="left")
                        machine_form_fields.pop('initial speed', None)
                        machine_form_fields.pop('final speed', None)
                        machine_form_fields.pop('speed step', None)
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
                        machine_form_fields.pop('motor speed', None)
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
                        machine_form_fields.pop('initial angle', None)
                        machine_form_fields.pop('final angle', None)
                        machine_form_fields.pop('angle step', None)
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
                        machine_form_fields.pop('angle', None)
                        machine_form_fields['initial angle'] = {'widget': initial_angle, 'validate': iv.check_float}
                        machine_form_fields['final angle'] = {'widget': final_angle, 'validate': iv.check_float}
                        machine_form_fields['angle step'] = {'widget': step, 'validate': iv.check_float}

                def set_port(port):
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

            elif option == "One-Axis Strain Prototype":
                self.need_pico = True
                pack_test_settings(machine_settings_frame)
                pack_strain(machine_settings_frame)
                pack_hx711_load(machine_settings_frame)
                motor_disp_frame = ctk.CTkFrame(machine_settings_frame, fg_color="transparent")
                motor_disp_frame.pack(padx=20, pady=5, anchor="w")
                ctk.CTkLabel(motor_disp_frame, text="Motor Displacement (mm/min):").pack(anchor="w", side="left", padx=(0, 5))
                motor_disp = ctk.CTkEntry(motor_disp_frame, placeholder_text="e.g., 60")
                motor_disp.pack(side="left")

                def set_port(port):
                    self.pico_port = port

                ctk.CTkLabel(machine_settings_frame, text="Select Control MCU", font=("Helvetica", 16, 'bold')).pack(anchor='w')
                com_menu = ComPortMenu(machine_settings_frame, set_port)
                com_menu.pack(pady=5, anchor='w')
                machine_form_fields["motor displacement"] = {"widget": motor_disp, "validate": iv.check_float}

        def material_option_picker(option):
            for widget in material_settings_frame.winfo_children():
                widget.destroy()
            material_form_fields.clear()
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
            if key == "channels" and widget.get() == "":
                payload[key] = self.channels
                return
            if isinstance(widget, ctk.CTkCheckBox):
                payload[key] = widget.get()
            elif isinstance(widget, (ctk.CTkEntry, ctk.CTkComboBox)):
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
            for key, meta in general_fields.items():
                extract(key, meta)
            for key, meta in machine_form_fields.items():
                extract(key, meta)
            for key, meta in material_form_fields.items():
                extract(key, meta)
            for key, meta in board_fields.items():
                extract(key, meta)

            dist_units = ['N', 'mm', 'cm', 'in']
            force_units = ['mg', 'g', 'N', 'kg', 'kN']

            if not self.error_flag:
                try:
                    if board == "MUX32":
                        data = f"MUX32,{payload['temp units'] if payload['temp checkbox'] else 'N'}"
                        data += f"_{'H' if payload['rh checkbox'] else 'N'}"
                        data += f"_{payload['pressure units'] if payload['pressure checkbox'] else 'N'}"
                        data += f"_{payload['gas units'] if payload['gas checkbox'] else 'N'}"
                        data += f",{payload['lux units'] + '_' + payload['lux bits'] if payload['light checkbox'] else 'N'}"
                    else:
                        data = "MUX08"

                    data += ","

                    if self.machine in ["Shimadzu", "MTS", "Mini-Shimadzu"]:
                        data += "S" if self.machine == "Shimadzu" else ""
                        data += "T" if self.machine == "MTS" else ""
                        data += "M" if self.machine == "Mini-Shimadzu" else ""
                        data += f",{payload['repetitions']}"

                        if not payload['displacement readings']:
                            payload['displacement voltage'] = payload['displacement distance'] = '0'
                            payload['displacement distance units'] = 'N'
                        if not payload['load readings']:
                            payload['load force'] = payload['load voltage'] = '0'
                            payload['load force units'] = 'N'

                        data += f",{ 'D' if payload['displacement readings'] else 'N' }_{payload['displacement voltage']}_{payload['displacement distance'] + '_' + str(dist_units.index(payload['displacement distance units']))}"
                        data += f",{ 'L' if payload['load readings'] else 'N' }_{payload['load force']}_{payload['load voltage'] + '_' + str(force_units.index(payload['load force units']))}"

                    elif self.machine == "Angular Bending/Deformation Prototype":
                        data += f"F,{payload['repetitions']}"
                        pico_data = f"SET,{payload['repetitions']}C,"
                        if payload.get('motor speed'):
                            data += f",S_0.0_{payload['motor speed']}_0.0"
                            pico_data += f"{payload['motor speed']}RPM"
                        else:
                            data += f"V_{payload['initial speed']}_{payload['final speed']}_{payload['speed step']}"
                            pico_data += f"VSPD_I{payload['initial speed']}_F{payload['final speed']}_S{payload['speed step']}"
                        if payload.get('angle'):
                            data += f",A_0.0_{payload['angle']}_0.0"
                            pico_data += f",{payload['angle']}DEG"
                        else:
                            data += f",V_{payload['initial angle']}_{payload['final angle']}_{payload['angle step']}"
                            pico_data += f",VDEG_I{payload['initial angle']}_F{payload['final angle']}_S{payload['angle step']}"

                    elif self.machine == "One-Axis Strain Prototype":
                        data += f"O,{payload['repetitions']}C"
                        pico_data = f"SET,{payload['repetitions']}C"
                        pico_data += f",{payload['strain']}N,{payload['motor displacement']}mm"
                        
                    if self.machine in ['Mini-Shimadzu', "One-Axis Strain Prototype"]:
                        if not payload['hx711 load readings']:
                            payload['hx711 load cell capacity'] = '0'
                            payload['hx711 load cell units'] = 'N'
                        data += f",{ 'H' if payload['hx711 load readings'] else 'N' }_{payload['hx711 load cell capacity'] + '_' + str(force_units.index(payload['hx711 load cell units']))}"
                    else:
                        data += ",N_0_0"

                    if self.material in ["CNT-GFW", "GS-GFW"]:
                        data += f",{ 'C' if self.material == 'CNT-GFW' else 'G' }"
                        data += f",{payload['test type'][-2]}"
                        data += f",{payload['length']}_{payload['width']}_{payload['height']}"
                        data += f",{ 'D' if payload['debond'] else 'N' }"
                        data += f",{payload['sensor number']}"
                    elif self.material in ["MWCNT", "MXene", "Cx-Alpha"]:
                        data += ",M" if self.material == "MWCNT" else ""
                        data += ",X" if self.material == "MXene" else ""
                        data += ",C" if self.material == "Cx-Alpha" else ""
                        data += f",{payload['length']}_{payload['width']}_{payload['height']}"
                        data += f",{payload['column']}_{payload['row']},{payload['sensor number']}"

                    data += f",{payload['channels']}"
                    print(data)

                    if self.need_pico:
                        pico_data += f",{payload['channels']}"
                        self.pico_ser = SerialInterface()
                        if self.pico_ser.connect(self.pico_port, 5):
                            return
                        self.pico_ser.send_command(pico_data)
                        
                    serial_interface.send_command("1")
                    if serial_interface.ser.readline().decode().strip() != '0':
                        return
                    serial_interface.send_command(data)
                    raw = serial_interface.ser.readline().decode().strip()

                    on_config_selected(
                        raw.split(','),
                        40 if payload['channels'] == 21 else int(payload['channels']),
                        payload['filename'],
                        int(payload['max data']),
                        int(payload['sampling rate'])
                    )
                except Exception as e:
                    print(e)

        def _clear_frame(frame):
            for w in frame.winfo_children():
                w.destroy()

        def _set_widget_value(widget, value):
            if isinstance(widget, ctk.CTkEntry):
                widget.delete(0, "end")
                widget.insert(0, str(value))
            elif isinstance(widget, ctk.CTkComboBox):
                widget.set(str(value))
            elif isinstance(widget, ctk.CTkCheckBox):
                if value:
                    widget.select()
                else:
                    widget.deselect()

        def _apply_to_fields(values_dict, fields_dict):
            for key, val in values_dict.items():
                meta = fields_dict.get(key)
                if not meta:
                    continue
                _set_widget_value(meta["widget"], val)

        def reset_values():
            try:
                sampling_rate.delete(0, "end")
                file_entry.delete(0, "end")
                max_data_entry.delete(0, "end")
            except Exception:
                pass
            try:
                machine_combo.set(machine_options[0])
                self.machine = ""
                _clear_frame(machine_settings_frame)
                machine_form_fields.clear()
            except Exception:
                pass
            try:
                material_combo.set(material_options[0])
                self.material = ""
                _clear_frame(material_settings_frame)
                material_form_fields.clear()
            except Exception:
                pass
            self.channels = 0
            if self.board == "MUX32":
                for key in ["temp checkbox", "rh checkbox", "pressure checkbox", "gas checkbox", "light checkbox"]:
                    if key in board_fields:
                        try:
                            board_fields[key]["widget"].deselect()
                            board_fields[key]["widget"].invoke()
                        except Exception:
                            pass
                for key in ["temp units", "pressure units", "gas units", "lux units", "lux bits"]:
                    if key in board_fields:
                        widget = board_fields[key]["widget"]
                        try:
                            vals = widget.cget("values")
                            if vals:
                                widget.configure(state="normal")
                                widget.set(vals[0])
                                widget.configure(state="disabled")
                        except Exception:
                            pass

        # === UI de presets ===
        presets_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
        presets_frame.pack(pady=(10, 10), fill="x")

        ctk.CTkLabel(presets_frame, text="Preset de Configuración", font=("Helvetica", 16, "bold")).pack(anchor="w")

        presets_row = ctk.CTkFrame(presets_frame, fg_color="transparent")
        presets_row.pack(anchor="w", pady=5)

        preset_names = ["Selecciona...", *presets.PRESETS.keys()]  # <-- del módulo recargado
        preset_combo = ctk.CTkComboBox(presets_row, values=preset_names, width=220)
        preset_combo.set(preset_names[0])
        preset_combo.pack(side="left", padx=(0, 10))

        def apply_preset():
            name = preset_combo.get()
            if name not in presets.PRESETS:
                return
            preset = presets.PRESETS[name]
            if "machine" in preset:
                machine_combo.set(preset["machine"])
                machine_option_picker(preset["machine"])
            if "material" in preset:
                material_combo.set(preset["material"])
                material_option_picker(preset["material"])
            if "general" in preset:
                _apply_to_fields(preset["general"], general_fields)
            if self.board == "MUX32" and "board_fields" in preset:
                for k in ["temp checkbox", "rh checkbox", "pressure checkbox", "gas checkbox", "light checkbox"]:
                    if k in preset["board_fields"] and k in board_fields:
                        _set_widget_value(board_fields[k]["widget"], preset["board_fields"][k])
                for k, v in preset["board_fields"].items():
                    if k in ["temp checkbox", "rh checkbox", "pressure checkbox", "gas checkbox", "light checkbox"]:
                        continue
                    if k in board_fields:
                        try:
                            board_fields[k]["widget"].configure(state="normal")
                        except Exception:
                            pass
                        _set_widget_value(board_fields[k]["widget"], v)
            if "machine_fields" in preset:
                _apply_to_fields(preset["machine_fields"], machine_form_fields)
            if "material_fields" in preset:
                _apply_to_fields(preset["material_fields"], material_form_fields)

        ctk.CTkButton(presets_row, text="Aplicar preset", command=apply_preset).pack(side="left", padx=(0, 8))
        ctk.CTkButton(presets_row, text="Reset", command=reset_values).pack(side="left", padx=6)

        save_row = ctk.CTkFrame(presets_frame, fg_color="transparent")
        save_row.pack(anchor="w", pady=(8, 0), fill="x")

        preset_name_entry = ctk.CTkEntry(save_row, placeholder_text="Nombre del preset...", width=220)
        preset_name_entry.pack(side="left", padx=(0, 8))

        ctk.CTkButton(save_row, text="Guardar preset", command=save_current_preset).pack(side="left")

        save_status = ctk.CTkLabel(presets_frame, text="", text_color="green")
        save_status.pack(anchor="w", pady=(6, 0))

        # === Board (MUX32) ===
        if board == "MUX32":
            def config_light():
                lux_units.configure(state="normal" if light_checkbox.get() else "disabled")
                lux_bits.configure(state="normal" if light_checkbox.get() else "disabled")

            tehu_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
            tehu_frame.pack(pady=5)
            praq_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
            praq_frame.pack(pady=5)
            light_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
            light_frame.pack(pady=5)

            temp_units = ctk.CTkComboBox(tehu_frame, values=["C", "F"], state="disabled")
            temp_checkbox = ctk.CTkCheckBox(tehu_frame, text="Enable Temperature Measurement", command=lambda: temp_units.configure(state="normal" if temp_checkbox.get() else "disabled"))
            temp_checkbox.pack(side="left", padx=10)
            temp_units.pack(side="left", padx=10)

            rh_checkbox = ctk.CTkCheckBox(tehu_frame, text="Enable R.H% Measurement")
            rh_checkbox.pack(side="left", padx=10)

            pressure_units = ctk.CTkComboBox(praq_frame, values=["hPa", "mBar", "mmHg"], state="disabled")
            pressure_checkbox = ctk.CTkCheckBox(praq_frame, text="Enable Atm. Pressure Measurement", command=lambda: pressure_units.configure(state="normal" if pressure_checkbox.get() else "disabled"))
            pressure_checkbox.pack(side="left", padx=10)
            pressure_units.pack(side="left", padx=10)

            gas_units = ctk.CTkComboBox(praq_frame, values=["KOhms", "TVoC"], state="disabled")
            gas_checkbox = ctk.CTkCheckBox(praq_frame, text="Enable Gas Measurement", command=lambda: gas_units.configure(state="normal" if gas_checkbox.get() else "disabled"))
            gas_checkbox.pack(side="left", padx=10)
            gas_units.pack(side="left", padx=10)

            lux_units = ctk.CTkComboBox(light_frame, values=["ALS", "UVS"], state="disabled")
            lux_bits = ctk.CTkComboBox(light_frame, values=["13", "16", "17", "18", "19", "20"], state="disabled")
            light_checkbox = ctk.CTkCheckBox(light_frame, text="Enable Ambient/UV Light Measurement", command=config_light)
            light_checkbox.pack(side="left", padx=10)
            ctk.CTkLabel(light_frame, text="Lux Mode").pack(side="left", padx=10)
            lux_units.pack(side="left", padx=10)
            ctk.CTkLabel(light_frame, text="Lux Bits").pack(side="left", padx=10)
            lux_bits.pack(side="left", padx=10)

            board_fields["temp checkbox"] = {"widget": temp_checkbox, "validate": None}
            board_fields["temp units"] = {"widget": temp_units, "validate": lambda val: not(val not in ["C", "F"] and temp_checkbox.get())}
            board_fields["rh checkbox"] = {"widget": rh_checkbox, "validate": None}
            board_fields["pressure checkbox"] = {"widget": pressure_checkbox, "validate": None}
            board_fields["pressure units"] = {"widget": pressure_units, "validate": lambda val: not(val not in ["hPa", "mBar", "mmHg"] and pressure_checkbox.get())}
            board_fields["gas checkbox"] = {"widget": gas_checkbox, "validate": None}
            board_fields["gas units"] = {"widget": gas_units, "validate": lambda val: not(val not in ["KOhms", "TVoC"] and gas_checkbox.get())}
            board_fields["light checkbox"] = {"widget": light_checkbox, "validate": None}
            board_fields["lux units"] = {"widget": lux_units, "validate": lambda val: not(val not in ["ALS", "UVS"] and light_checkbox.get())}
            board_fields["lux bits"] = {"widget": lux_bits, "validate": lambda val: not(val not in ["13", "16", "17", "18", "19", "20"] and light_checkbox.get())}

        # === Main param frame ===
        param_frame = ctk.CTkFrame(scrollable, fg_color="transparent")
        param_frame.pack(pady=40)

        top_row_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        top_row_frame.pack()

        # Column 1
        machine_column = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        machine_column.pack(side="left", padx=10)

        machine_options = ["Chooze a Machine", "Shimadzu", "MTS", "Mini-Shimadzu", "Festo", "Angular Bending/Deformation Prototype", "One-Axis Strain Prototype"]
        machine_combo = ctk.CTkComboBox(machine_column, values=machine_options, command=machine_option_picker)
        machine_combo.pack(pady=(0, 5))

        general_fields['machine options'] = {'widget': machine_combo, 'validate': lambda val: val in ["Shimadzu", "MTS", "Mini-Shimadzu", "Festo", "Angular Bending/Deformation Prototype", "One-Axis Strain Prototype"]}

        machine_settings_frame = ctk.CTkFrame(machine_column, width=300, height=100, border_width=1, corner_radius=6)
        machine_settings_frame.pack()

        # Column 2
        material_column = ctk.CTkFrame(top_row_frame, fg_color="transparent")
        material_column.pack(side="left", padx=10)

        material_options = ["Choose a Material", "CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]
        material_combo = ctk.CTkComboBox(material_column, values=material_options, command=material_option_picker)
        material_combo.pack(pady=(0, 5))

        general_fields['material options'] = {'widget': material_combo, 'validate': lambda val: val in ["CNT-GFW", "GS-GFW", "MWCNT", "MXene", "Cx-Alpha"]}

        material_settings_frame = ctk.CTkFrame(material_column, width=300, height=100, border_width=1, corner_radius=6)
        material_settings_frame.pack()

        # Sampling
        sampling_frame = ctk.CTkFrame(param_frame, fg_color="transparent")
        sampling_frame.pack(pady=20)
        ctk.CTkLabel(sampling_frame, text="Measurement Time Frequency (ms):").pack(side="left", padx=(0, 5))
        sampling_rate = ctk.CTkEntry(sampling_frame, placeholder_text="e.g., 1000")
        sampling_rate.pack(side="left")
        general_fields["sampling rate"] = {'widget': sampling_rate, 'validate': lambda val: val.isdigit()}

        # Filename / Max Points
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

        # Submit
        ctk.CTkButton(param_frame, text="Submit", command=submit_values).pack(pady=10)

        # Back
        back_button = ctk.CTkButton(
            scrollable,
            text="⟵ Regresar",
            command=on_back,
            fg_color="#444",
            text_color="white"
        )
        back_button.pack(pady=20)

    def get_robot(self):
        return self.robot
