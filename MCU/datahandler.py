import sys
import time
import random # REMOVE IN FINAL PRODUCT
from itertools import count #REMOVE IN FINAL PRODUCT
import uselect

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
        self.running = False
        self.index = count() # REMOVE IN FINAL PRODUCT


        self.spoll = uselect.poll()
        self.spoll.register(sys.stdin, uselect.POLLIN)

    def run(self):
        '''
        Starts the main loop of the data exchange
        '''
        while True:
            # check for command
            self._process_command()
            if self.running:
                self._send_data()
            time.sleep(self.interval)

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
        command = self._non_blocking_stdin_readline()
        if command == None:
            pass

        elif command.startswith("START"):
            self.running = True

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
                elif "resolution=" in p:
                    self.interval = 1 / int(p.split('=')[1])


        elif command.startswith("STOP"):
            self.angle = 0
            self.speed = 0
            self.cycles = 0
            self.running = False

        elif command.startswith("RESTART")    :
            self.cycles_remaining = self.cycles
        
        elif command.startswith("EXIT"):
            sys.exit()

        else:
            print("No command received")

    def _non_blocking_stdin_readline(self):
        '''
        Polls stdin for input
        '''
        res = self.spoll.poll(0)
        if res:
            return sys.stdin.readline() # Read one character
        return None