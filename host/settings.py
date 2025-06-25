import customtkinter as ctk
import serial_interface as ser
import threading

class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, serial_interface: ser):
        super().__init__(master)
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=10)

        start_btn = ctk.CTkButton(button_frame, text="Start/Resume")
        start_btn.pack(side='left', padx=10)

        pause_btn = ctk.CTkButton(button_frame, text="Pause Test")
        pause_btn.pack(side='left', padx=10)

        stop_btn = ctk.CTkButton(button_frame, text="Stop Test")
        stop_btn.pack(side='left', padx=10)

    def start(self):
        threading.Thread(target=ser.SerialInterface.read_lines, daemon=True)

