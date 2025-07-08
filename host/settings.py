import customtkinter as ctk
from serial_interface import SerialInterface
import threading
import time

class SettingsPage(ctk.CTkFrame):
    def __init__(self, master, serial_interface: SerialInterface, push, sampling_rate, robot=None):
        super().__init__(master)
        self.paused = True
        self.serial_interface = serial_interface
        self.push_callback = push
        self.sampling_rate = sampling_rate
        button_frame = ctk.CTkFrame(self, fg_color="transparent")
        button_frame.pack(pady=10)

        self.start_btn = ctk.CTkButton(button_frame, text="Start/Resume", command=self.start)
        self.start_btn.pack(side='left', padx=10)

        self.pause_btn = ctk.CTkButton(button_frame, text="Pause Test", state="disabled", command=self.pause)
        self.pause_btn.pack(side='left', padx=10)

        self.stop_btn = ctk.CTkButton(button_frame, text="Stop Test", state="disabled", command=self.stop)
        self.stop_btn.pack(side='left', padx=10)

        self.robot = robot

    def start(self):
        if self.paused:
            self.paused = False
            self.read_thread = threading.Thread(target=self.serial_interface.read_lines, args=(self.push_callback,), daemon=True)
            self.read_thread.start()
            self.write_thread = threading.Thread(target=self.request_data, daemon=True)
            self.write_thread.start()
            self.start_btn.configure(state="disabled")
            self.pause_btn.configure(state="normal")

            # ENABLE ROBOT IF APPLICABLE
            if self.robot:
                t = threading.Thread(target=self.robot.run, daemon=True)
                t.start()

    def pause(self):
        if not self.paused:
            self.paused = True
            self.read_thread.join()
            self.write_thread.join()
            self.start_btn.configure(state="normal")
            self.pause_btn.configure(state="disabled")

            if self.robot:
                self.robot.stop()

    def stop(self):
        self.read_thread.join() if self.read_thread else None
        self.write_thread.join() if self.write_thread else None
        self.start_btn.configure(state="disabled")
        self.pause_btn.configure(state="disabled")
        self.serial_interface.disconnect()


    def request_data(self):
        while self.paused == False:
            self.serial_interface.send_command("2")
            time.sleep(self.sampling_rate)
        print("Paused, thread exiting")
        

