import serial
import serial.tools.list_ports
import threading
import time

class SerialInterface:
    def __init__(self, baudrate=115200):
        self.port = None
        self.baudrate = baudrate
        self.ser = None

    def connect(self):
        '''
        Connects to microcontroller.
        '''
        ports = list(serial.tools.list_ports.comports())

        # loop through all open ports. Send SYN, if ACK is heard back, connect to that COM Port
        for port_info in ports:
            try:
                test_port = port_info.device
                ser = serial.Serial(test_port, self.baudrate, timeout=1)
                ser.write("SYN\n".encode())
                resp = ser.readline().decode().strip()
                time.sleep(0.5)
                if resp == "ACK":
                    self.ser = ser
                    self.port = test_port
                    return
                ser.close()
            except:
                continue

        
        

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

    def read_lines(self, callback):
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
                        callback(line)

                except Exception as e:
                    print(f"Read error: {e}")
                    break   
        # thread so that real-time reading does not block sending commands to device    
        threading.Thread(target=_read, daemon=True).start()
