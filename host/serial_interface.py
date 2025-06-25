import serial
import serial.tools.list_ports
import threading
import time

class SerialInterface:
    def __init__(self, baudrate=115200):
        self.port = None
        self.baudrate = baudrate
        self.ser = None

    def connect(self, port):
        '''
        Connects to microcontroller.
        '''
        # loop through all open ports. Send 0, if ACK is heard back, connect to that COM Port

        ser = serial.Serial(port, self.baudrate, timeout=1)
        ser.write("0\n".encode())
        resp = ser.readline().decode().strip()
        time.sleep(0.5)
        if resp == "ACK":
            self.ser = ser
            self.port = port
            return

        
        

    def disconnect(self):
        '''
        Closes microcontroller connection. 
        '''
        if self.ser and self.ser.is_open:
            self.ser.write(b"EXIT\n")
            self.ser.close()
    
    def send_command(self, command: str):
        '''
        Sends command (str) to microcontroller.
        '''

        self.ser.write((command + '\n').encode())

    def read_lines(self, plot, config_payload):
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
                        if line.startswith("Scan"):
                            config_payload(line)
                        # call the external function
                        else:
                            plot(line)

                except Exception as e:
                    print(f"Read error: {e}")
                    break   
        # thread so that real-time reading does not block sending commands to device    
        threading.Thread(target=_read, daemon=True).start()
