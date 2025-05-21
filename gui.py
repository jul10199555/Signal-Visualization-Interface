import customtkinter as ctk

ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Finger Bending Interface")
        self.geometry("600x400")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.start_page = StartPage(self)
        self.control_page = ControlPage(self)
        self.analyze_page = AnalyzePage(self)

        self.show_frame(self.start_page)

    def show_frame(self, frame):
        frame.tkraise()


class StartPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure((0, 1, 2, 3), weight=1)
        self.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self, text="Welcome", font=("Helvetica", 24)).grid(row=0, column=0, pady=10)

        ctk.CTkButton(self, text="Control", command=lambda: master.show_frame(master.control_page)).grid(row=1, column=0, pady=10)

        ctk.CTkButton(self, text="Analyze", command=lambda: master.show_frame(master.analyze_page)).grid(row=2, column=0, pady=10)


class ControlPage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure((0, 1, 2, 3, 4, 5, 6), weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Back Button (Top Left)
        back_btn = ctk.CTkButton(self, text="← Back", width=60, command=lambda: master.show_frame(master.start_page))
        back_btn.grid(row=0, column=0, padx=10, pady=10, sticky="nw")

        ctk.CTkLabel(self, text="Control Panel", font=("Helvetica", 20)).grid(row=1, column=0, pady=10)

        self.angle_entry = ctk.CTkEntry(self, placeholder_text="Device Angle (degrees)")
        self.angle_entry.grid(row=2, column=0, padx=20, pady=5, sticky="ew")

        self.cycles_entry = ctk.CTkEntry(self, placeholder_text="Device Cycles")
        self.cycles_entry.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        self.speed_entry = ctk.CTkEntry(self, placeholder_text="Device Speed (Hz)")
        self.speed_entry.grid(row=4, column=0, padx=20, pady=5, sticky="ew")

        # New Enter Button at the bottom
        enter_btn = ctk.CTkButton(self, text="Enter", command=self.submit_values)
        enter_btn.grid(row=6, column=0, pady=20)

    def submit_values(self):
        # Placeholder for user-defined function
        angle = self.angle_entry.get()
        cycles = self.cycles_entry.get()
        speed = self.speed_entry.get()
        print(f"Angle: {angle}, Cycles: {cycles}, Speed: {speed}")


class AnalyzePage(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)
        self.grid(row=0, column=0, sticky="nsew")
        self.grid_rowconfigure((0, 1, 2), weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Back Button (Top Left)
        back_btn = ctk.CTkButton(self, text="← Back", width=60, command=lambda: master.show_frame(master.start_page))
        back_btn.grid(row=0, column=0, padx=10, pady=10, sticky="nw")

        ctk.CTkLabel(self, text="Analyze Page", font=("Helvetica", 20)).grid(row=1, column=0, pady=10)

        ctk.CTkLabel(self, text="Graphical data output will be shown here.").grid(row=2, column=0)


if __name__ == "__main__":
    app = App()
    app.mainloop()
