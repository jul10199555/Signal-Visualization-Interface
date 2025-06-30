import sys
import random # REMOVE IN FINAL PRODUCT
from itertools import count #REMOVE IN FINAL PRODUCT

class DataHandler():
    '''
    Handles the exchange of data between the microcontroller and host computer
    '''
    def __init__(self):
        self.angle = 0
        self.cycles = 0
        self.speed = 0
        self.cycles_remaining = 0
        self.interval = 1
        self.paused = True
        self.index = count() # REMOVE IN FINAL PRODUCT
        self.channels = 0

    def run(self):
        '''
        Starts the main loop of the data exchange
        '''
        while True:
            # check for command
            self._process_command()

    def _send_data(self): # REMOVE IN FINAL PRODUCT
        '''
        Sends x and y data values to the host
        '''
        sys.stdout.write(f"0.1,0.1,{random.randint(0,100)}\n")

    def _process_command(self):
        '''
        Processes incoming commands from host
        '''
        command = sys.stdin.readline().strip()
        if command == None:
            pass

        elif command == '0':
            sys.stdout.write("ACK\n")

        elif command == '1':
            sys.stdout.write("ACK\n") # can put stuff before this, e.g. wait for calibration
            config_data = sys.stdin.readline()
            config_data = config_data.split(',')
            for segment in config_data:
                if segment.startswith("CHAN"):
                    self.channels = int(segment[4:])

            channel_header = ""
            if self.channels == 1:
                channel_header = "Resistance (6001)"
                    
            sys.stdout.write(f"5001 <LOAD> (VDC),5021 <DISP> (VDC),{channel_header}")

        elif command == '2':
            self._send_data()

        elif command.startswith("SET"):
            parts = command.split()[1:]
            
            for p in parts:
                
                if "angle=" in p:
                    self.angle = float(p.split('=')[1])
                elif "speed=" in p:
                    self.speed = int(p.split('=')[1])
                elif "cycles=" in p:
                    cycles = int(p.split('=')[1])
                    self.cycles_remaining = cycles


        elif command.startswith("PAUSE"):
            self.paused = True
        
        elif command.startswith("EXIT"):
            sys.exit()

        else:
            print("No command received")

    # def _non_blocking_stdin_readline(self):
    #     '''
    #     Polls stdin for input
    #     '''
    #     res = self.spoll.poll(0)
    #     if res:
    #         return sys.stdin.readline() # Read one character
    #     return None