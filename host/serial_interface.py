import serial
import threading

class SerialInterface:
    def __init__(self, port='COM4', baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self.ser = None
        self.reading = False

    def connect(self):
        '''
        Connects to microcontroller.
        '''
        
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=1)

        except serial.SerialException as e:
            print(f"Error opening serial port: {e}")
            self.ser = None

    def disconnect(self):
        '''
        Closes microcontroller connection. 
        '''

        self.reading = False
        if self.ser and self.ser.is_open:
            self.ser.close()
    
    def send_command(self, command: str):
        '''
        Sends command (str) to microcontroller.
        '''

        self.ser.write((command + '\n').encode())

    def read_lines(self, callback):
        '''
        Spawns new thread to read from microcontroller and calls
        respective callback function.
        '''
        def _read():
            self.reading = True
            # Must be connected and reading
            while self.ser and self.reading:
                try:
                    line = self.ser.readline().decode().strip()
                    if line:
                        # call the external function
                        callback(line)

                except Exception as e:
                    print(f"Read error: {e}")
                    self.reading = False
                    break   
        # thread so that real-time reading does not block sending commands to device    
        threading.Thread(target=_read, daemon=True).start()
