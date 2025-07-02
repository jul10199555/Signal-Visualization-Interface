import customtkinter as ctk

from host.heatmap_display import HeatmapApp
from serial_interface import SerialInterface
import serial.tools.list_ports as list_ports

from payload import Payload

from control_page import ControlPage, ComPortMenu
from multi_display import WaveformApp
from settings import SettingsPage

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")

ANGLE_DEFAULT = 0
CYCLES_DEFAULT = 0
PULSES_DEFAULT = 0
RESOLUTION_DEFAULT = 60
X_LIM_DEFAULT = (0, 100)
Y_LIM_DEFAULT = (0, 100)

class Navbar(ctk.CTkFrame):
    def __init__(self, master, switch_frame):
        super().__init__(master)
        self.switch_frame = switch_frame
        self.nav = ctk.CTkSegmentedButton(
            self,
            width=400,
            values=["Settings", "Waveform", "∆R/Ro", "Heatmap", "Calc."],
            corner_radius=12,
            command=self.switch_frame  # TODO: IMPLEMENT COMMAND FOR HEADER NAVIGATION
        )
        self.nav.set("Settings")
        self.nav.pack(side="top")

# GUI Pages
class FirstExecutionMenu(ctk.CTkFrame):
    def __init__(self, master, serial_interface: SerialInterface, on_board_selected):

        def select_board(entry):
            if entry in ["MUX08", "MUX32"]:
                self.board = entry

        def set_port(port):
            self.port = port
            
        def request_connect():
            try:
                # UNCOMMENT WHEN BOARD IS ACTUALLY CONNECTED
                if self.board == '': return
                serial_interface.connect(self.port)
                on_board_selected(self.board)
            except Exception as e:
                print(e)
                return
        
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")

        self.port = ""
        self.board = ""

        ctk.CTkLabel(self, text="Select a COM Port", font=("Helvetica", 16, "bold")).pack(pady=40)

        port_menu = ComPortMenu(self, set_port)
        port_menu.pack(pady=20)

        board_dropdown = ctk.CTkComboBox(self, values=["Select a Board", "MUX32", "MUX08"], command=select_board)
        board_dropdown.pack(pady=20)

        ctk.CTkButton(self, text="Submit", command=request_connect).pack(pady=20)

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
        self.initial_page.destroy()
        self.control_page = ControlPage(self.page_container, self.serial_interface, board, self.on_config_sent)
        self.control_page.grid(row=0, column=0, sticky='nsew')
        self.show_control_page()

    def on_config_sent(self, header, channels, sampling_rate):
        # Remove initial page
        self.control_page.destroy()

        p = Payload(
            window_size=1000000,
            num_rows_detach=1000,
            out_file_name="output/1k_out.csv",
            keys=header,
            channels=channels
        )

        # Show Navbar
        self.navbar = Navbar(self, self.switch_frame)
        self.navbar.grid(row=0, column=0, sticky="ew", pady=5)

        # Initialize pages
        self.pages["Settings"] = SettingsPage(self.page_container, self.serial_interface, p.push, sampling_rate/1000)
        self.pages["Waveform"] = WaveformApp(self.page_container, p, False, 1000/sampling_rate)
        r_div = WaveformApp(self.page_container, p, True, 1000/sampling_rate)
        self.pages["∆R/Ro"] = r_div
        self.pages["Heatmap"] = HeatmapApp(self.page_container, p, r_div.get_ro())  # Replace with real class
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
