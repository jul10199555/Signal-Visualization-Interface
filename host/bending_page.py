# bending_page.py
import customtkinter as ctk
import threading
import time
import json
import ast

from serial_interface import SerialInterface

# === presetsBending ===
import presetsBending  # nuevo: importamos tus presetsBending .py


class BendingPage(ctk.CTkFrame):
    def __init__(self, master, serial_interface: SerialInterface, on_back):
        super().__init__(master)
        self.serial_interface = serial_interface
        self.on_back = on_back

        # Estado de lectura
        self.reader_thread = None
        self.stop_event = threading.Event()
        self.listening = False

        # ===== Layout base =====
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ---- Título ----
        title = ctk.CTkLabel(self, text="Bending", font=("Helvetica", 22, "bold"))
        title.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 8))

        # ---- Área scrolleable ----
        self.scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.scroll.grid(row=1, column=0, sticky="nsew", padx=20, pady=(0, 10))

        # Contenedor del formulario
        self.form = ctk.CTkFrame(self.scroll, fg_color="transparent")
        self.form.pack(fill="x", pady=8)

        # ====== Selector de Mode ======
        mode_row = ctk.CTkFrame(self.form, fg_color="transparent")
        mode_row.pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(mode_row, text="Mode:", font=("Helvetica", 14, "bold")).pack(
            side="left", padx=(0, 10)
        )

        self.mode_values = ["Mode 1", "Mode 2", "Mode 3", "Mode 4"]
        self.mode_texts = {
            "Mode 1": "Modo 1:\nVelocidad Constante\nÁngulo Constante.",
            "Mode 2": "Modo 2:\nVelocidad Constante\nÁngulo Variable.",
            "Mode 3": "Modo 3:\nVelocidad Variable\nÁngulo Constante.",
            "Mode 4": "Modo 4:\nVelocidad Variable\nÁngulo Variable.",
        }

        self.mode_combo = ctk.CTkComboBox(
            mode_row, values=self.mode_values, command=self._on_mode_change, width=180
        )
        self.mode_combo.set("Mode 1")
        self.mode_combo.pack(side="left")

        # === presetsBending: UI ===
        preset_row = ctk.CTkFrame(self.form, fg_color="transparent")
        preset_row.pack(fill="x", pady=(6, 6))

        ctk.CTkLabel(preset_row, text="Preset:", font=("Helvetica", 14, "bold")).pack(
            side="left", padx=(0, 10)
        )
        self.preset_combo = ctk.CTkComboBox(preset_row, values=[], width=260)
        self.preset_combo.pack(side="left")

        ctk.CTkButton(preset_row, text="Aplicar", width=90, command=self._apply_selected_preset).pack(
            side="left", padx=(8, 0)
        )
        ctk.CTkButton(preset_row, text="Guardar actual…", width=130, command=self._save_current_as_preset).pack(
            side="left", padx=8
        )
        ctk.CTkButton(preset_row, text="Eliminar", width=100, fg_color="#b33", command=self._delete_selected_preset).pack(
            side="left", padx=8
        )

        # Cargar lista de presetsBending
        self._reload_presetsBending()

        # Descripción dinámica
        desc_frame = ctk.CTkFrame(self.form, fg_color="transparent")
        desc_frame.pack(fill="x", pady=(8, 12))
        self.mode_desc = ctk.CTkLabel(
            desc_frame,
            text=self.mode_texts["Mode 1"],
            justify="left",
            anchor="w",
            font=("Helvetica", 13),
        )
        self.mode_desc.pack(fill="x")

        # ====== Sección dinámica: 2 columnas (Ángulo / Velocidad) ======
        self.two_col = ctk.CTkFrame(self.form, fg_color="transparent")
        self.two_col.pack(fill="x", pady=(4, 10))

        self.left_col = ctk.CTkFrame(self.two_col, fg_color="transparent")
        self.right_col = ctk.CTkFrame(self.two_col, fg_color="transparent")

        self.left_col.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.right_col.pack(side="left", fill="x", expand=True, padx=(8, 0))

        ctk.CTkLabel(self.left_col, text="Ángulo (°)", font=("Helvetica", 15, "bold")).pack(
            anchor="w", pady=(0, 6)
        )
        ctk.CTkLabel(self.right_col, text="Velocidad (rpm)", font=("Helvetica", 15, "bold")).pack(
            anchor="w", pady=(0, 6)
        )

        self.inputs = {}
        self.errors = {}

        self._build_mode_specific_fields("Mode 1")

        # — Sección Restricciones —
        self.rules = ctk.CTkFrame(self.form, fg_color="transparent")
        self.rules.pack(fill="x", pady=(8, 12))
        self._render_rules_text()

        # — Sección Lectura (aparece tras Submit válido) —
        self.read_frame = ctk.CTkFrame(self.form, fg_color="transparent")

        # — Botonera —
        submit_row = ctk.CTkFrame(self.form, fg_color="transparent")
        submit_row.pack(fill="x", pady=(6, 8))
        self.status_label = ctk.CTkLabel(submit_row, text="", text_color="#999999")
        self.status_label.pack(side="right", padx=8)

        ctk.CTkButton(submit_row, text="Submit", command=self._on_submit, width=120).pack(side="left", pady=4, padx=(0, 6))
        ctk.CTkButton(submit_row, text="Pause", command=self._on_pause, width=100, fg_color="#888").pack(side="left", pady=4, padx=6)
        ctk.CTkButton(submit_row, text="Stop", command=self._on_stop, width=100, fg_color="#b33").pack(side="left", pady=4, padx=6)

        # ---- Barra inferior ----
        bottom_bar = ctk.CTkFrame(self, fg_color="transparent")
        bottom_bar.grid(row=2, column=0, sticky="ew", padx=20, pady=(0, 18))
        bottom_bar.grid_columnconfigure(0, weight=1)
        back_btn = ctk.CTkButton(bottom_bar, text="⟵ Regresar", command=self._go_back, width=140, fg_color="#444", text_color="white")
        back_btn.pack(side="left")

    # ===================== Helpers de Serial (igual que tu código) =====================
    def _is_serial_ready(self) -> bool:
        try:
            si = self.serial_interface
            if si is None:
                return False
            ser = getattr(si, "ser", None)
            return ser is not None
        except Exception:
            return False

    def _ensure_serial_ready(self) -> bool:
        if self._is_serial_ready():
            return True
        si = self.serial_interface
        if si is None:
            self._set_status("SerialInterface no inyectado.")
            return False
        connect = getattr(si, "connect", None)
        if callable(connect):
            try:
                port = getattr(si, "port", None) or getattr(si, "device", None)
                baud = getattr(si, "baudrate", None) or 115200
                if port:
                    self._set_status(f"Intentando conectar a {port} @ {baud}...")
                    connect(port, baud)
                    if self._is_serial_ready():
                        self._set_status(f"Conectado a {port}.")
                        return True
                    else:
                        self._set_status("No se pudo establecer la conexión (si.ser sigue vacío).")
                        return False
                else:
                    self._set_status("No hay puerto configurado en SerialInterface (si.port).")
                    return False
            except Exception as e:
                self._set_status(f"Fallo al conectar: {e}")
                return False
        self._set_status("Serial no disponible (falta conexión).")
        return False

    # ===================== Modo dinámico =====================
    def _on_mode_change(self, choice: str):
        self.mode_desc.configure(text=self.mode_texts.get(choice, ""))
        self._build_mode_specific_fields(choice)

    def _reset_inputs(self):
        self.inputs.clear()
        self.errors.clear()

    def _add_labeled_entry(self, parent: ctk.CTkFrame, label: str, placeholder: str = "", width: int = 120):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", pady=4)
        ctk.CTkLabel(row, text=label).pack(side="left", padx=(0, 8))
        entry = ctk.CTkEntry(row, width=width, placeholder_text=placeholder)
        entry.pack(side="left")
        err = ctk.CTkLabel(parent, text="", text_color="#ff6666", font=("Helvetica", 11))
        err.pack(anchor="w", pady=(2, 0))
        return entry, err

    def _build_mode_specific_fields(self, mode: str):
        for w in self.left_col.winfo_children()[1:]:
            w.destroy()
        for w in self.right_col.winfo_children()[1:]:
            w.destroy()
        self._reset_inputs()

        # Ángulo
        if mode in ("Mode 1", "Mode 3"):
            ang_cte, err = self._add_labeled_entry(self.left_col, "Ángulo:", "0–90")
            self.inputs["angle_const"] = ang_cte
            self.errors["angle_const"] = err
        else:
            ang_i, err_i = self._add_labeled_entry(self.left_col, "Ángulo Inicial:", "0–90")
            ang_f, err_f = self._add_labeled_entry(self.left_col, "Ángulo Final:", "0–90")
            ang_s, err_s = self._add_labeled_entry(self.left_col, "Step (Ángulo):", "0–45")
            self.inputs["angle_init"] = ang_i
            self.inputs["angle_final"] = ang_f
            self.inputs["angle_step"] = ang_s
            self.errors["angle_init"] = err_i
            self.errors["angle_final"] = err_f
            self.errors["angle_step"] = err_s

        # Velocidad
        if mode in ("Mode 1", "Mode 2"):
            vel_cte, err = self._add_labeled_entry(self.right_col, "Velocidad:", "7–30")
            self.inputs["speed_const"] = vel_cte
            self.errors["speed_const"] = err
        else:
            vi, err_vi = self._add_labeled_entry(self.right_col, "Velocidad Inicial:", "7–30")
            vf, err_vf = self._add_labeled_entry(self.right_col, "Velocidad Final:", "7–30")
            st, err_st = self._add_labeled_entry(self.right_col, "Step (Velocidad):", "7–30")
            self.inputs["speed_init"] = vi
            self.inputs["speed_final"] = vf
            self.inputs["speed_step"] = st
            self.errors["speed_init"] = err_vi
            self.errors["speed_final"] = err_vf
            self.errors["speed_step"] = err_st

    # ======= Texto de reglas =======
    def _render_rules_text(self):
        for w in self.rules.winfo_children():
            w.destroy()
        ctk.CTkLabel(self.rules, text="Restricciones", font=("Helvetica", 14, "bold")).pack(anchor="w", pady=(0, 4))
        rules_txt = (
            "• Ángulo: valores enteros entre 0 y 90.\n"
            "• Ángulo variable: el Ángulo Final no puede ser menor que el Inicial.\n"
            "• Step (Ángulo): entero entre 0 y 45.\n"
            "• Velocidad (constante o inicial/final): enteros entre 7 y 30 rpm.\n"
            "• Step (Velocidad): entero entre 7 y 30 rpm.\n"
            "• En Velocidad variable, la inicial puede ser mayor o menor que la final."
        )
        ctk.CTkLabel(self.rules, text=rules_txt, justify="left", anchor="w").pack(anchor="w")

    # ===================== Validaciones =====================
    def _clear_errors(self):
        for lbl in self.errors.values():
            lbl.configure(text="")

    @staticmethod
    def _parse_int(text: str):
        try:
            return int(text.strip())
        except Exception:
            return None

    def _validate(self, mode: str):
        self._clear_errors()
        ok = True
        data = {"modo": self._mode_number(mode)}

        # Ángulo
        if "angle_const" in self.inputs:
            v = self._parse_int(self.inputs["angle_const"].get())
            if v is None or not (0 <= v <= 90):
                self.errors["angle_const"].configure(text="Ángulo debe ser entero entre 0 y 90.")
                ok = False
            else:
                data["angle"] = v
        else:
            a_i = self._parse_int(self.inputs["angle_init"].get())
            a_f = self._parse_int(self.inputs["angle_final"].get())
            a_s = self._parse_int(self.inputs["angle_step"].get())
            if a_i is None or not (0 <= a_i <= 90):
                self.errors["angle_init"].configure(text="Inicial debe ser 0–90.")
                ok = False
            if a_f is None or not (0 <= a_f <= 90):
                self.errors["angle_final"].configure(text="Final debe ser 0–90.")
                ok = False
            if ok and a_f < a_i:
                self.errors["angle_final"].configure(text="El ángulo final no puede ser menor al inicial.")
                ok = False
            if a_s is None or not (0 <= a_s <= 45):
                self.errors["angle_step"].configure(text="Step (Ángulo) debe ser 0–45.")
                ok = False
            if ok:
                data["angle_init"] = a_i
                data["angle_final"] = a_f
                data["angle_step"] = a_s

        # Velocidad
        if "speed_const" in self.inputs:
            v = self._parse_int(self.inputs["speed_const"].get())
            if v is None or not (7 <= v <= 30):
                self.errors["speed_const"].configure(text="Velocidad debe ser un entero entre 7 y 30.")
                ok = False
            else:
                data["speed"] = v
        else:
            v_i = self._parse_int(self.inputs["speed_init"].get())
            v_f = self._parse_int(self.inputs["speed_final"].get())
            st = self._parse_int(self.inputs["speed_step"].get())
            if v_i is None or not (7 <= v_i <= 30):
                self.errors["speed_init"].configure(text="Inicial debe ser 7–30.")
                ok = False
            if v_f is None or not (7 <= v_f <= 30):
                self.errors["speed_final"].configure(text="Final debe ser 7–30.")
                ok = False
            if st is None or not (7 <= st <= 30):
                self.errors["speed_step"].configure(text="Step (Velocidad) debe ser 7–30.")
                ok = False
            if ok:
                data["speed_init"] = v_i
                data["speed_final"] = v_f
                data["speed_step"] = st

        return ok, data

    # ===================== Serial helpers =====================
    @staticmethod
    def _mode_number(mode_name: str) -> int:
        return {"Mode 1": 1, "Mode 2": 2, "Mode 3": 3, "Mode 4": 4}.get(mode_name, 0)

    def _compose_command_json(self, cfg: dict) -> str:
        m = cfg["modo"]
        if m == 1:
            payload = {"modo": 1, "velocity": cfg["speed"], "angle": cfg["angle"]}
        elif m == 2:
            payload = {
                "modo": 2,
                "velocity": cfg["speed"],
                "init_angle": cfg["angle_init"],
                "final_angle": cfg["angle_final"],
                "step_angle": cfg["angle_step"],
            }
        elif m == 3:
            payload = {
                "modo": 3,
                "angle": cfg["angle"],
                "init_vel": cfg["speed_init"],
                "final_vel": cfg["speed_final"],
                "step_vel": cfg["speed_step"],
            }
        elif m == 4:
            payload = {
                "modo": 4,
                "init_angle": cfg["angle_init"],
                "final_angle": cfg["angle_final"],
                "step_angle": cfg["angle_step"],
                "init_vel": cfg["speed_init"],
                "final_vel": cfg["speed_final"],
                "step_vel": cfg["speed_step"],
            }
        else:
            payload = {"modo": 0}
        return json.dumps(payload, separators=(",", ":"))

    # ----- Parser RX -----
    @staticmethod
    def _parse_modo_velocity_angle(s: str):
        try:
            lst = ast.literal_eval(s)
            if not isinstance(lst, list):
                return None, None, None
            d = {}
            i = 0
            while i + 1 < len(lst):
                k = lst[i]
                v = lst[i + 1]
                if isinstance(k, str):
                    key = k.strip().lower()
                    try:
                        val = int(v)
                    except Exception:
                        val = v
                    d[key] = val
                i += 2
            modo = d.get("modo")
            velocity = d.get("velocity", d.get("velocidad"))
            angle = d.get("angle", d.get("angulo"))
            for name, val in (("modo", modo), ("velocity", velocity), ("angle", angle)):
                if val is None:
                    continue
                if not isinstance(val, int):
                    try:
                        if isinstance(val, str) and val.strip().isdigit():
                            if name == "modo":
                                modo = int(val)
                            elif name == "velocity":
                                velocity = int(val)
                            elif name == "angle":
                                angle = int(val)
                        else:
                            return None, None, None
                    except Exception:
                        return None, None, None
            return modo, velocity, angle
        except Exception:
            return None, None, None

    def _start_reader(self):
        if self.listening:
            return
        self.stop_event.clear()
        self.listening = True

        def _worker():
            try:
                if not self._ensure_serial_ready():
                    self.listening = False
                    return
                ser = getattr(self.serial_interface, "ser", None)
                if not ser:
                    self._set_status("Serial no disponible.")
                    self.listening = False
                    return
                self._set_status("Leyendo datos...")
                while not self.stop_event.is_set():
                    raw = self.serial_interface.ser.readline().decode().strip()
                    if not raw:
                        continue
                    print(f"[RX] {raw}")
                    modo, vel, ang = self._parse_modo_velocity_angle(raw)
                    if (modo is not None) and (vel is not None) and (ang is not None):
                        self._update_readings(modo, ang, vel)
                    time.sleep(0.003)
            except Exception as e:
                self._set_status(f"Error lector: {e}")
            finally:
                self.listening = False

        self.reader_thread = threading.Thread(target=_worker, daemon=True)
        self.reader_thread.start()

    def _set_status(self, text: str):
        self.after(0, lambda: self.status_label.configure(text=text))

    def _update_readings(self, mode_val: int, angle_val: int, speed_val: int):
        def _do():
            if hasattr(self, "mode_value_label"):
                self.mode_value_label.configure(text=str(mode_val))
            if hasattr(self, "angle_value_label"):
                self.angle_value_label.configure(text=str(angle_val))
            if hasattr(self, "speed_value_label"):
                self.speed_value_label.configure(text=str(speed_val))
        self.after(0, _do)

    # ===================== Acciones =====================
    def _on_submit(self):
        mode = self.mode_combo.get()
        ok, cfg = self._validate(mode)
        if not ok:
            return
        cmd_str = self._compose_command_json(cfg)
        self._send_submit_command(cmd_str)
        if not hasattr(self, "read_section_shown") or not self.read_section_shown:
            self._build_read_section()
            self.read_section_shown = True
        self._start_reader()

    def _send_submit_command(self, cmd_str: str):
        try:
            if not self._ensure_serial_ready():
                return
            if hasattr(self.serial_interface, "send_command") and callable(self.serial_interface.send_command):
                self.serial_interface.send_command(cmd_str)
            else:
                ser = self.serial_interface.ser
                ser.write((cmd_str + "\n").encode())
            self._set_status("Comando enviado.")
        except Exception as e:
            self._set_status(f"Error al enviar: {e}")
            return

    def _on_pause(self):
        try:
            if not self._ensure_serial_ready():
                return
            if hasattr(self.serial_interface, "send_command") and callable(self.serial_interface.send_command):
                self.serial_interface.send_command("PAUSE")
            else:
                self.serial_interface.ser.write(b"PAUSE\n")
            self._set_status("PAUSE enviado.")
        except Exception as e:
            self._set_status(f"Error PAUSE: {e}")

    def _on_stop(self):
        try:
            if not self._ensure_serial_ready():
                return
            if hasattr(self.serial_interface, "send_command") and callable(self.serial_interface.send_command):
                self.serial_interface.send_command("STOP")
            else:
                self.serial_interface.ser.write(b"STOP\n")
            self._set_status("STOP enviado.")
        except Exception as e:
            self._set_status(f"Error STOP: {e}")

    def _build_read_section(self):
        self.read_frame.pack(fill="x", pady=(12, 6))
        ctk.CTkLabel(self.read_frame, text="Lectura", font=("Helvetica", 16, "bold")).pack(anchor="w", pady=(0, 8))
        mode_row = ctk.CTkFrame(self.read_frame, fg_color="transparent")
        mode_row.pack(fill="x", pady=(0, 6))
        ctk.CTkLabel(mode_row, text="Modo", font=("Helvetica", 14, "bold")).pack(side="left")
        self.mode_value_label = ctk.CTkLabel(mode_row, text="--", font=("Helvetica", 18))
        self.mode_value_label.pack(side="left", padx=(8, 0))

        grid = ctk.CTkFrame(self.read_frame, fg_color="transparent")
        grid.pack(fill="x")
        left = ctk.CTkFrame(grid, fg_color="transparent")
        right = ctk.CTkFrame(grid, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True, padx=(0, 8))
        right.pack(side="left", fill="x", expand=True, padx=(8, 0))

        ctk.CTkLabel(left, text="Ángulo (°)", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.angle_value_label = ctk.CTkLabel(left, text="--", font=("Helvetica", 22))
        self.angle_value_label.pack(anchor="w", pady=(4, 6))

        ctk.CTkLabel(right, text="Velocidad (rpm)", font=("Helvetica", 14, "bold")).pack(anchor="w")
        self.speed_value_label = ctk.CTkLabel(right, text="--", font=("Helvetica", 22))
        self.speed_value_label.pack(anchor="w", pady=(4, 6))

    def _go_back(self):
        if self.listening:
            self.stop_event.set()
        if callable(self.on_back):
            self.on_back()

    # ===================== presetsBending: lógica =====================
    def _reload_presetsBending(self):
        self._all_presetsBending = presetsBending.load_all()
        names = list(self._all_presetsBending.keys())
        if not names:
            names = [""]
        self.preset_combo.configure(values=names)
        if names:
            self.preset_combo.set(names[0])

    def _apply_selected_preset(self):
        name = self.preset_combo.get().strip()
        if not name or name not in self._all_presetsBending:
            self._set_status("Selecciona un preset válido.")
            return
        cfg = self._all_presetsBending[name]
        self._apply_preset_cfg(cfg)
        self._set_status(f"Preset aplicado: {name}")

    def _apply_preset_cfg(self, cfg: dict):
        """
        Ajusta el modo y rellena los campos visibles con los valores del preset.
        """
        modo = int(cfg.get("modo", 0))

        # Cambiar el combo de modo (redibuja campos)
        name_by_mode = {1: "Mode 1", 2: "Mode 2", 3: "Mode 3", 4: "Mode 4"}.get(modo, "Mode 1")
        if self.mode_combo.get() != name_by_mode:
            self.mode_combo.set(name_by_mode)
            self._on_mode_change(name_by_mode)

        # Ahora, según modo, rellenar
        def set_entry(key: str, value):
            if key in self.inputs and hasattr(self.inputs[key], "delete"):
                self.inputs[key].delete(0, "end")
                self.inputs[key].insert(0, str(value))

        if modo == 1:
            # angle_const, speed_const
            if "angle" in cfg: set_entry("angle_const", cfg["angle"])
            if "speed" in cfg: set_entry("speed_const", cfg["speed"])

        elif modo == 2:
            if "init_angle" in cfg: set_entry("angle_init", cfg["init_angle"])
            if "final_angle" in cfg: set_entry("angle_final", cfg["final_angle"])
            if "step_angle" in cfg: set_entry("angle_step", cfg["step_angle"])
            if "velocity" in cfg:   set_entry("speed_const", cfg["velocity"])

        elif modo == 3:
            if "angle" in cfg:      set_entry("angle_const", cfg["angle"])
            if "init_vel" in cfg:   set_entry("speed_init", cfg["init_vel"])
            if "final_vel" in cfg:  set_entry("speed_final", cfg["final_vel"])
            if "step_vel" in cfg:   set_entry("speed_step", cfg["step_vel"])

        elif modo == 4:
            if "init_angle" in cfg: set_entry("angle_init", cfg["init_angle"])
            if "final_angle" in cfg: set_entry("angle_final", cfg["final_angle"])
            if "step_angle" in cfg: set_entry("angle_step", cfg["step_angle"])
            if "init_vel" in cfg:   set_entry("speed_init", cfg["init_vel"])
            if "final_vel" in cfg:  set_entry("speed_final", cfg["final_vel"])
            if "step_vel" in cfg:   set_entry("speed_step", cfg["step_vel"])

    def _save_current_as_preset(self):
        """
        Valida el formulario actual y pide un nombre para guardar como preset (usuario).
        """
        mode = self.mode_combo.get()
        ok, cfg = self._validate(mode)
        if not ok:
            self._set_status("Corrige los errores antes de guardar el preset.")
            return

        # Convertir cfg de validación -> llaves de firmware (como ya haces en _compose_command_json)
        m = cfg["modo"]
        if m == 1:
            store = {"modo": 1, "angle": cfg["angle"], "speed": cfg["speed"]}
        elif m == 2:
            store = {
                "modo": 2,
                "velocity": cfg["speed"],
                "init_angle": cfg["angle_init"],
                "final_angle": cfg["angle_final"],
                "step_angle": cfg["angle_step"],
            }
        elif m == 3:
            store = {
                "modo": 3,
                "angle": cfg["angle"],
                "init_vel": cfg["speed_init"],
                "final_vel": cfg["speed_final"],
                "step_vel": cfg["speed_step"],
            }
        else:  # m == 4
            store = {
                "modo": 4,
                "init_angle": cfg["angle_init"],
                "final_angle": cfg["angle_final"],
                "step_angle": cfg["angle_step"],
                "init_vel": cfg["speed_init"],
                "final_vel": cfg["speed_final"],
                "step_vel": cfg["speed_step"],
            }

        # UI simple para pedir nombre (sin ventana extra):
        def _commit():
            name = entry.get().strip()
            prompt.destroy()
            try:
                if presetsBending.is_builtin(name):
                    # No permitir sobreescribir los BUILTIN
                    self._set_status("No se puede sobreescribir un preset base. Usa otro nombre.")
                    return
                presetsBending.save_user_preset(name, store)
                self._reload_presetsBending()
                self.preset_combo.set(name)
                self._set_status(f"Preset guardado: {name}")
            except Exception as e:
                self._set_status(f"No se pudo guardar: {e}")

        prompt = ctk.CTkToplevel(self)
        prompt.title("Guardar preset")
        ctk.CTkLabel(prompt, text="Nombre del preset:").pack(padx=16, pady=(16, 6))
        entry = ctk.CTkEntry(prompt, width=280, placeholder_text="Ej. Mi preset M1 @10° 7rpm")
        entry.pack(padx=16, pady=6)
        btns = ctk.CTkFrame(prompt, fg_color="transparent")
        btns.pack(pady=(6, 16))
        ctk.CTkButton(btns, text="Guardar", command=_commit).pack(side="left", padx=8)
        ctk.CTkButton(btns, text="Cancelar", fg_color="#777", command=prompt.destroy).pack(side="left", padx=8)

        # centrar aprox
        prompt.geometry("+200+150")
        entry.focus_set()

    def _delete_selected_preset(self):
        name = self.preset_combo.get().strip()
        if not name:
            self._set_status("Selecciona un preset.")
            return
        if presetsBending.is_builtin(name):
            self._set_status("No se puede eliminar un preset base.")
            return
        ok = presetsBending.delete_user_preset(name)
        if ok:
            self._reload_presetsBending()
            self._set_status(f"Preset eliminado: {name}")
        else:
            self._set_status("Ese preset no existe en el almacenamiento de usuario.")
