import sys
import time
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
        x = next(self.index)
        y = random.randint(0, 100)
        sys.stdout.write(f"{x},{y}\n")

    def _process_command(self):
        '''
        Processes incoming commands from host
        '''
        command = sys.stdin.readline()
        if command == None:
            pass

        elif command.startswith("0"):
            sys.stdout.write("ACK\n")

        elif command.startswith("START"):
            self.paused = False

        elif command.startswith("REQUEST"):
            if self.paused == False:
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