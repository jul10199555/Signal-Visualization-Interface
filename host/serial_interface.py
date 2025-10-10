import serial
import serial.tools.list_ports
import threading
import time

class SerialInterface:
    def __init__(self, baudrate=115200):
        self.port = None
        self.baudrate = baudrate
        self.ser = None

    def connect(self, port, timeout=1):
        ser = serial.Serial(port, self.baudrate, timeout=timeout)
        time.sleep(0.2)            # dar tiempo a enumerar/CDC
        ser.reset_input_buffer()    # limpiar basura inicial como "READY"
        ser.write(b"0\n")           # handshake
        # Lee líneas hasta encontrar exactamente "0" (por si algo se coló)
        t0 = time.time()
        while time.time() - t0 < timeout:
            resp = ser.readline().decode(errors="ignore").strip()
            if resp == "0":
                self.ser = ser
                self.port = port
                return 0
        ser.close()
        return 1

    def disconnect(self):
        '''
        Closes microcontroller connection. 
        '''
        if self.ser and self.ser.is_open:
            self.ser.write(b"END\n")
            self.ser.close()
    
    def send_command(self, command: str):
        '''
        Sends command (str) to microcontroller.
        '''

        self.ser.write((command + '\n').encode())

    def read_lines(self, plot):
        '''
        Spawns new thread to read from microcontroller and calls
        respective callback function.
        '''
        def _read():
            # Must be connected and reading
            while self.ser:
                try:
                    line = self.ser.readline().decode().strip()
                    if line:
                        # call the external function
                        print(line)
                        plot(line)

                except Exception as e:
                    print(f"Read error: {e}")
                    break   
        # thread so that real-time reading does not block sending commands to device    
        threading.Thread(target=_read, daemon=True).start()
