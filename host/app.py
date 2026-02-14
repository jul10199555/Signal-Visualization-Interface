import threading
import time

import customtkinter as ctk

from heatmap_display import HeatmapApp
from serial_interface import SerialInterface

from payload import Payload

from control_page import ControlPage, ComPortMenu
from multi_display import WaveformApp
from settings import SettingsPage
from calc_page import MetricsPage

from bending_page import BendingPage

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

# User-adjustable clock offset (seconds) when syncing MCU time from PC time.
MCU_TIME_SYNC_OFFSET_SECONDS = 1


class Navbar(ctk.CTkFrame):
    """Lets user navigate between core parts of the UI."""

    def __init__(self, master, switch_frame):
        super().__init__(master)
        self.switch_frame = switch_frame
        self.nav = ctk.CTkSegmentedButton(
            self,
            width=460,
            values=["Waveform", "DeltaR/Ro", "Heatmap", "Calc.", "Settings"],
            corner_radius=12,
            command=self.switch_frame,
        )
        self.nav.set("Waveform")
        self.nav.pack(side="top")


class BottomBar(ctk.CTkFrame):
    """Always-visible status and run control bar."""

    def __init__(self, master, on_toggle_run, on_stop):
        super().__init__(master)

        self.grid_columnconfigure(0, weight=3)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=3)

        self.stream_label = ctk.CTkLabel(self, text="Stream stopped.", anchor="w")
        self.stream_label.grid(row=0, column=0, sticky="w", padx=12, pady=8)

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.grid(row=0, column=1)
        self.start_btn = ctk.CTkButton(center, text="Start", command=on_toggle_run)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = ctk.CTkButton(center, text="Stop Test", command=on_stop)
        self.stop_btn.pack(side="left", padx=6)

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=2, sticky="e", padx=12)

        self.status_badge = ctk.CTkLabel(
            right,
            text="Disconnected",
            width=120,
            corner_radius=10,
            fg_color="#6B7280",
            text_color="white",
        )
        self.status_badge.pack(side="right")

        self.status_reason = ctk.CTkLabel(right, text="", anchor="e")
        self.status_reason.pack(side="right", padx=(0, 8))

    def set_stream_status(self, text: str, color: str = "white"):
        self.stream_label.configure(text=text, text_color=color)

    def set_run_state(self, state: str):
        if state == "running":
            self.start_btn.configure(text="Pause", state="normal")
        elif state == "paused":
            self.start_btn.configure(text="Resume", state="normal")
        else:
            self.start_btn.configure(text="Start", state="normal")
        self.stop_btn.configure(state="normal")

    def set_connection_state(self, state: str, reason: str = ""):
        color_map = {
            "Disconnected": "#6B7280",
            "Connecting": "#2563EB",
            "Ready": "#059669",
            "Streaming": "#0EA5A4",
            "Error": "#DC2626",
        }
        self.status_badge.configure(text=state, fg_color=color_map.get(state, "#6B7280"))
        self.status_reason.configure(text=reason)


class FirstExecutionMenu(ctk.CTkFrame):
    """Allows user to select COM port and board configuration."""

    def __init__(self, master, serial_interface: SerialInterface, on_board_selected, on_bending_selected):
        def select_board(entry):
            if entry in ["MUX08", "MUX32", "Bending"]:
                self.board = entry

        def set_port(port):
            self.port = port

        def request_connect():
            if self.board == "" or self.port == "":
                self.connect_status.configure(text="Select both board and serial port.", text_color="orange")
                return

            err = serial_interface.connect(self.port, timeout=2, retries=3, retry_delay=0.7)
            if err:
                reason = serial_interface.get_last_error() or "Connection failed."
                self.connect_status.configure(text=reason, text_color="red")
                return

            self.connect_status.configure(text=f"Connected on {self.port}", text_color="green")
            if self.board == "Bending":
                on_bending_selected(self.board)
            else:
                on_board_selected(self.board)

            # One-shot date-time sync after handshake and page transition.
            def _sync_time_once():
                ok_sync, payload, ack_code = serial_interface.sync_mcu_datetime(MCU_TIME_SYNC_OFFSET_SECONDS)
                if ok_sync:
                    if serial_interface.debug_tx:
                        print(f"[TIME SYNC] Sent: {payload}")
                    if serial_interface.debug_rx and ack_code:
                        print(f"[TIME SYNC] ACK: {ack_code}")
                else:
                    print(serial_interface.get_last_error() or "MCU date-time sync failed.")

            master.after(120, _sync_time_once)

        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        self.port = ""
        self.board = ""

        ctk.CTkLabel(self, text="Select a COM Port", font=("Helvetica", 16, "bold")).pack(pady=40)

        port_menu = ComPortMenu(self, set_port)
        port_menu.pack(pady=20)

        board_dropdown = ctk.CTkComboBox(
            self,
            values=["Select a Board", "MUX32", "MUX08", "Bending"],
            command=select_board,
        )
        board_dropdown.set("MUX32")
        self.board = "MUX32"
        board_dropdown.pack(pady=20)

        ctk.CTkButton(self, text="Submit", command=request_connect).pack(pady=10)
        self.connect_status = ctk.CTkLabel(self, text="")
        self.connect_status.pack(pady=(6, 0))


class App(ctk.CTk):
    """Main container for interface."""

    def __init__(self):
        super().__init__()
        self.title("Signal Visualization Interface")
        self.geometry("1000x800")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.close)

        self.connection_state = SerialInterface.STATUS_DISCONNECTED
        self.connection_reason = "Not connected."

        self.serial_interface = SerialInterface(status_callback=self._on_serial_status)

        self.navbar = None
        self.bottom_bar = None

        self.page_container = ctk.CTkFrame(self)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)

        self.initial_page = FirstExecutionMenu(
            self,
            self.serial_interface,
            self.on_board_selected,
            self.on_bending_selected,
        )
        self.initial_page.grid(row=0, column=0, sticky="nsew")

        self.pages = {}
        self.bending_page = None
        self.control_page = None

        self._stream_stop_event = threading.Event()
        self._stream_thread = None
        self._stream_running = False
        self._stream_state = "stopped"
        self._stream_payload = None
        self._stream_sampling_rate = 1.0
        self._stream_robot = None

    def _on_serial_status(self, state: str, reason: str):
        try:
            self.after(0, lambda: self._apply_serial_status(state, reason))
        except Exception:
            self._apply_serial_status(state, reason)

    def _apply_serial_status(self, state: str, reason: str):
        self.connection_state = state
        self.connection_reason = reason
        if self.bottom_bar:
            self.bottom_bar.set_connection_state(state, reason)

    def _set_stream_legend(self, text: str, color: str = "white"):
        def _apply():
            bar = self.bottom_bar
            if bar and bar.winfo_exists():
                bar.set_stream_status(text, color)

        try:
            self.after(0, _apply)
        except Exception:
            _apply()

    def _reset_test_variables(self):
        self._stream_stop_event = threading.Event()
        self._stream_thread = None
        self._stream_running = False
        self._stream_state = "stopped"
        self._stream_payload = None
        self._stream_sampling_rate = 1.0
        self._stream_robot = None

    def _destroy_runtime_ui(self):
        if self.bottom_bar and self.bottom_bar.winfo_exists():
            self.bottom_bar.destroy()
        self.bottom_bar = None

        if self.navbar and self.navbar.winfo_exists():
            self.navbar.destroy()
        self.navbar = None

        for page in list(self.pages.values()):
            try:
                if page and page.winfo_exists():
                    page.destroy()
            except Exception:
                pass
        self.pages = {}

        if self.control_page and self.control_page.winfo_exists():
            self.control_page.destroy()
        self.control_page = None

        if self.bending_page and self.bending_page.winfo_exists():
            self.bending_page.destroy()
        self.bending_page = None

    def _return_to_initial_state(self):
        self.serial_interface.disconnect()
        self.serial_interface.port = None

        self._destroy_runtime_ui()
        self._reset_test_variables()

        if self.initial_page and self.initial_page.winfo_exists():
            self.initial_page.destroy()

        self.initial_page = FirstExecutionMenu(
            self,
            self.serial_interface,
            self.on_board_selected,
            self.on_bending_selected,
        )
        self.initial_page.grid(row=0, column=0, sticky="nsew")

    def end_test(self):
        try:
            self.stop_streaming(disconnect=False)
        except Exception:
            pass
        self._return_to_initial_state()

    def toggle_streaming(self):
        if self._stream_state == "running":
            self.pause_streaming()
        else:
            self.start_streaming()

    def start_streaming(self):
        if self._stream_state == "running":
            return
        if not self._stream_payload:
            self._set_stream_legend("No active payload configured.", "orange")
            return

        if not self.serial_interface.ensure_connection(timeout=2, retries=3, retry_delay=0.7):
            reason = self.serial_interface.get_last_error() or "Unable to connect."
            self._set_stream_legend(reason, "red")
            return

        was_paused = self._stream_state == "paused"
        self._stream_running = True
        self._stream_state = "running"
        self._stream_stop_event.clear()
        if self.bottom_bar:
            self.bottom_bar.set_run_state("running")

        self._stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._stream_thread.start()
        self._set_stream_legend("Streaming resumed." if was_paused else "Streaming started.", "green")

        if self._stream_robot:
            t = threading.Thread(target=self._stream_robot.run, daemon=True)
            t.start()

    def pause_streaming(self):
        if self._stream_state != "running":
            return

        self._stream_running = False
        self._stream_stop_event.set()

        if self._stream_thread and self._stream_thread.is_alive():
            self._stream_thread.join(timeout=2)

        self.serial_interface.mark_ready("Paused.")
        if self._stream_robot:
            self._stream_robot.stop()

        self._stream_state = "paused"
        if self.bottom_bar:
            self.bottom_bar.set_run_state("paused")
        self._set_stream_legend("Acquisition paused.", "orange")

    def stop_streaming(self, disconnect=True):
        if self._stream_state == "stopped":
            self._set_stream_legend("Stream stopped.", "white")
            return

        if self._stream_state == "running":
            self._stream_running = False
            self._stream_stop_event.set()

            if self._stream_thread and self._stream_thread.is_alive():
                self._stream_thread.join(timeout=2)

        self._stream_running = False
        self._stream_state = "stopped"
        if self.bottom_bar:
            self.bottom_bar.set_run_state("stopped")

        try:
            self._stream_payload.to_csv()
        except Exception as e:
            self._set_stream_legend(f"CSV export error: {e}", "orange")

        if disconnect:
            self.serial_interface.disconnect()
        else:
            self.serial_interface.mark_ready("Connection idle.")

        if self._stream_robot:
            self._stream_robot.stop()

        self._set_stream_legend("Stream stopped.", "white")

    def _stream_loop(self):
        read_timeout = max(1.0, self._stream_sampling_rate * 1.5)

        while not self._stream_stop_event.is_set():
            if not self.serial_interface.send_command(
                "r",
                auto_recover=True,
                reconnect_retries=3,
                reconnect_timeout=2,
                retry_delay=0.5,
            ):
                reason = self.serial_interface.get_last_error() or "Send failed."
                self._set_stream_legend(reason, "red")
                time.sleep(0.5)
                continue

            line = self.serial_interface.read_line(
                timeout=read_timeout,
                auto_recover=True,
                reconnect_retries=3,
                reconnect_timeout=2,
                retry_delay=0.5,
            )
            if line is None:
                reason = self.serial_interface.get_last_error() or "Read timeout."
                self._set_stream_legend(reason, "red")
                time.sleep(0.2)
                continue

            try:
                self._stream_payload.push(line)
                self._set_stream_legend("Receiving samples.", "green")
            except Exception as e:
                self._set_stream_legend(f"Payload parse error: {e}", "orange")

            time.sleep(max(0.001, self._stream_sampling_rate))

    def on_board_selected(self, board):
        """Creates the control page and allows returning to initial menu."""
        self.initial_page.destroy()
        self.initial_page = None

        def go_back():
            self.control_page.destroy()
            self.control_page = None
            self.serial_interface.disconnect()
            self.initial_page = FirstExecutionMenu(
                self,
                self.serial_interface,
                self.on_board_selected,
                self.on_bending_selected,
            )
            self.initial_page.grid(row=0, column=0, sticky="nsew")

        self.control_page = ControlPage(
            self.page_container,
            self.serial_interface,
            board,
            self.on_config_sent,
            on_back=go_back,
        )
        self.control_page.grid(row=0, column=0, sticky="nsew")
        self.show_control_page()

    def on_bending_selected(self, board):
        self.initial_page.destroy()
        self.initial_page = None

        def go_back_from_bending():
            if self.bending_page is not None:
                self.bending_page.destroy()
                self.bending_page = None
            self.serial_interface.disconnect()
            self.initial_page = FirstExecutionMenu(
                self,
                self.serial_interface,
                self.on_board_selected,
                self.on_bending_selected,
            )
            self.initial_page.grid(row=0, column=0, sticky="nsew")

        self.bending_page = BendingPage(self.page_container, self.serial_interface, on_back=go_back_from_bending)
        self.bending_page.grid(row=0, column=0, sticky="nsew")
        self.bending_page.tkraise()

    def on_config_sent(self, header, channels, filename, window_size, sampling_rate):
        """Called upon leaving control page. Creates main interface UI."""
        robot_ref = self.control_page.get_robot() if self.control_page else None
        self.control_page.destroy()
        self.control_page = None

        if filename[-4:] != ".csv":
            filename += ".csv"

        p = Payload(
            window_size=window_size,
            num_rows_detach=max(1, window_size // 100),
            out_file_name=f"output/{filename}",
            keys=header,
            channels=channels,
        )

        self._stream_payload = p
        self._stream_sampling_rate = sampling_rate / 1000
        self._stream_robot = robot_ref
        self._stream_running = False
        self._stream_state = "stopped"
        self._stream_stop_event.clear()

        self.navbar = Navbar(self, self.switch_frame)
        self.navbar.grid(row=0, column=0, sticky="ew", pady=(5, 2))

        self.bottom_bar = BottomBar(self, self.toggle_streaming, self.end_test)
        self.bottom_bar.grid(row=2, column=0, sticky="ew", pady=(2, 5))
        self.bottom_bar.set_connection_state(self.connection_state, self.connection_reason)
        self.bottom_bar.set_run_state("stopped")
        self.bottom_bar.set_stream_status("Stream stopped.", "white")

        self.pages["Waveform"] = WaveformApp(self.page_container, p, False, 1000 / sampling_rate)
        r_div = WaveformApp(self.page_container, p, True, 1000 / sampling_rate)
        self.pages["DeltaR/Ro"] = r_div
        self.pages["Heatmap"] = HeatmapApp(self.page_container, p, r_div)
        self.pages["Calc."] = MetricsPage(self.page_container, p)
        self.pages["Settings"] = SettingsPage(
            self.page_container,
            self.serial_interface,
            p,
            sampling_rate / 1000,
            self._stream_robot,
        )

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        self.switch_frame("Waveform")

    def switch_frame(self, selected):
        if selected in self.pages:
            self.pages[selected].tkraise()
        elif self.initial_page and self.initial_page.winfo_exists():
            self.initial_page.tkraise()

    def show_control_page(self):
        self.control_page.tkraise()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def close(self):
        try:
            self.stop_streaming(disconnect=False)
        except Exception:
            pass
        self.serial_interface.disconnect()
        self.clear_window()
        exit()
