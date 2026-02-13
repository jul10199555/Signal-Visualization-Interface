import customtkinter as ctk

from payload import Payload
from serial_interface import SerialInterface


class SettingsPage(ctk.CTkFrame):
    """Settings/info page. Runtime controls are in the bottom bar."""

    def __init__(self, master, serial_interface: SerialInterface, payload: Payload, sampling_rate, robot=None):
        super().__init__(master)

        card = ctk.CTkFrame(self)
        card.pack(fill="both", expand=True, padx=14, pady=14)

        ctk.CTkLabel(card, text="Settings", font=("Helvetica", 18, "bold")).pack(anchor="w", padx=10, pady=(10, 6))

        ctk.CTkLabel(card, text=f"Sampling period: {sampling_rate:.4f} s").pack(anchor="w", padx=10, pady=4)
        ctk.CTkLabel(card, text=f"Channels: {len(payload.get_channels())}").pack(anchor="w", padx=10, pady=4)
        ctk.CTkLabel(card, text=f"Output file: {payload.out_file_name}").pack(anchor="w", padx=10, pady=4)

        if robot is not None:
            ctk.CTkLabel(card, text="Robot controller: configured").pack(anchor="w", padx=10, pady=4)
        else:
            ctk.CTkLabel(card, text="Robot controller: not used").pack(anchor="w", padx=10, pady=4)
