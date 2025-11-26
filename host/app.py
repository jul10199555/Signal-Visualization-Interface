import customtkinter as ctk

from heatmap_display import HeatmapApp
from serial_interface import SerialInterface
import serial.tools.list_ports as list_ports

from payload import Payload

from control_page import ControlPage, ComPortMenu
from multi_display import WaveformApp
from settings import SettingsPage

# 👇 NUEVO: importar la página de Bending (archivo nuevo)
from bending_page import BendingPage

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class Navbar(ctk.CTkFrame):
    '''Lets user navigate between core parts of the UI'''
    def __init__(self, master, switch_frame):
        super().__init__(master)
        self.switch_frame = switch_frame
        self.nav = ctk.CTkSegmentedButton(
            self,
            width=400,
            values=["Settings", "Waveform", "∆R/Ro", "Heatmap", "Calc."],
            corner_radius=12,
            command=self.switch_frame
        )
        self.nav.set("Settings")
        self.nav.pack(side="top")


class FirstExecutionMenu(ctk.CTkFrame):
    '''Allows user to select COM port and board configuration'''
    def __init__(self, master, serial_interface: SerialInterface, on_board_selected, on_bending_selected):

        def select_board(entry):
            '''Sets board to selected board'''
            if entry in ["MUX08", "MUX32", "Bending"]:
                self.board = entry

        def set_port(port):
            '''Sets COM port to selected COM port'''
            self.port = port
            
        def request_connect():
            '''Connects to COM and navega según board seleccionada'''
            try:
                if self.board == '' or self.port == '':
                    return
                serial_interface.connect(self.port)
                # Si el usuario eligió "Bending", saltamos a la pantalla Bending
                if self.board == "Bending":
                    on_bending_selected(self.board)
                else:
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

        # 👇 Agregamos "Bending" al dropdown
        board_dropdown = ctk.CTkComboBox(self, values=["Select a Board", "MUX32", "MUX08", "Bending"], command=select_board)
        board_dropdown.set("MUX32")  # valor por defecto si quieres
        self.board = "MUX32"
        board_dropdown.pack(pady=20)

        # Un único botón; decide a dónde ir en función del valor del combo
        ctk.CTkButton(self, text="Submit", command=request_connect).pack(pady=20)


class App(ctk.CTk):
    '''Main container for interface'''
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
        self.initial_page = FirstExecutionMenu(
            self,
            self.serial_interface,
            self.on_board_selected,
            self.on_bending_selected  # 👈 NUEVO callback
        )
        self.initial_page.grid(row=0, column=0, sticky="nsew")

        # Pages dict to manage different pages
        self.pages = {}

        # Para mantener referencia a la BendingPage cuando se use
        self.bending_page = None

    def on_board_selected(self, board):
        '''Crea la página de control y permite regresar a la inicial'''
        self.initial_page.destroy()

        def go_back():
            # Al regresar desde ControlPage:
            # 1) destruir la página
            # 2) desconectar serial
            # 3) volver a la pantalla inicial
            self.control_page.destroy()
            self.serial_interface.disconnect()
            self.initial_page = FirstExecutionMenu(
                self,
                self.serial_interface,
                self.on_board_selected,
                self.on_bending_selected
            )
            self.initial_page.grid(row=0, column=0, sticky='nsew')

        self.control_page = ControlPage(
            self.page_container,
            self.serial_interface,
            board,
            self.on_config_sent,
            on_back=go_back
        )
        self.control_page.grid(row=0, column=0, sticky='nsew')
        self.show_control_page()

    # NUEVO: flujo cuando eligen “Bending” en la primera pantalla
    def on_bending_selected(self, board):
        # Quitamos la pantalla inicial
        self.initial_page.destroy()

        def go_back_from_bending():
            # Al regresar: destruimos la página, desconectamos serial, y volvemos a la pantalla inicial
            if self.bending_page is not None:
                self.bending_page.destroy()
                self.bending_page = None
            self.serial_interface.disconnect()
            self.initial_page = FirstExecutionMenu(
                self,
                self.serial_interface,
                self.on_board_selected,
                self.on_bending_selected
            )
            self.initial_page.grid(row=0, column=0, sticky="nsew")

        # Creamos y mostramos la BendingPage
        self.bending_page = BendingPage(
            self.page_container,
            self.serial_interface,
            on_back=go_back_from_bending
        )
        self.bending_page.grid(row=0, column=0, sticky="nsew")
        self.bending_page.tkraise()


    def on_config_sent(self, header, channels, filename, window_size, sampling_rate):
        '''Called upon leaving control page. creates main interface UI'''
        # Remove control page
        self.control_page.destroy()

        # Format given file name
        if filename[-4:] != '.csv':
            filename += '.csv'

        # Configure payload parameters
        p = Payload(
            window_size=window_size,
            num_rows_detach=window_size // 100,
            out_file_name=f"output/{filename}",
            keys=header,
            channels=channels
        )

        # Show Navbar
        self.navbar = Navbar(self, self.switch_frame)
        self.navbar.grid(row=0, column=0, sticky="ew", pady=5)

        # Initialize pages
        self.pages["Settings"] = SettingsPage(self.page_container, self.serial_interface, p, sampling_rate/1000,
                                              self.control_page.get_robot())
        self.pages["Waveform"] = WaveformApp(self.page_container, p, False, 1000/sampling_rate)
        r_div = WaveformApp(self.page_container, p, True, 1000/sampling_rate)
        self.pages["∆R/Ro"] = r_div
        self.pages["Heatmap"] = HeatmapApp(self.page_container, p, r_div)

        for page in self.pages.values():
            page.grid(row=0, column=0, sticky="nsew")

        # Display Settings Tab Initially
        self.switch_frame("Settings")

    def switch_frame(self, selected):
        if selected in self.pages:
            self.pages[selected].tkraise()
        else:
            if self.initial_page:
                self.initial_page.tkraise()

    def show_control_page(self):
        self.control_page.tkraise()

    def clear_window(self):
        for widget in self.winfo_children():
            widget.destroy()

    def close(self):
        self.clear_window()
        self.serial_interface.disconnect()
        exit()
