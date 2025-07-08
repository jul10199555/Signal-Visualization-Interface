import sys
import random # REMOVE IN FINAL PRODUCT
from itertools import count #REMOVE IN FINAL PRODUCT
import time

class DataHandler():
    '''
    Handles the exchange of data between the microcontroller and host computer
    '''
    def __init__(self):
        self.speed = 0
        self.angle = 0
        self.cycles = 0
        self.vary_speed = (0,0,0)
        self.vary_angle = (0,0,0)
        self.interval = 1
        self.paused = True
        self.index = count() # REMOVE IN FINAL PRODUCT
        self.channels = 0
        self.ready = False

    def wait(self):
        '''Waits until parameters have been configured. CALL AFTER CALLING RUN, AND BEFORE CALLING GETTERS'''
        while not self.ready:
            time.sleep(1)

    def get_speed(self) -> int:
        '''Returns motor speed. CALL WAIT FIRST'''
        return self.speed
    
    def get_angle(self):
        '''Returns motor angle. CALL WAIT FIRST'''
        return self.angle
    
    def get_cycles(self) -> int:
        '''Returns motor angle. CALL WAIT FIRST'''
        return self.cycles
    
    def get_variable_speed(self) -> tuple:
        '''Returns tuple of variable speed paramters. CALL WAIT FIRST'''
        return self.vary_speed
    
    def get_variable_angle(self) -> tuple:
        '''Returns tuple of variable angle parameters. CALL WAIT FIRST'''
        return self.vary_angle

    def run(self):
        '''
        Starts the main loop of the data exchange. CALL BEFORE WAIT
        '''
        while True:
            # check for command
            self._process_command()

    def _send_data(self): # REMOVE IN FINAL PRODUCT
        '''
        Sends x and y data values to the host
        '''
        datastr = ""
        iter = self.channels if self.channels != 21 else 40
        for i in range(iter):
            datastr += f',{random.randint(0,100)}'
        sys.stdout.write(f"0.1,0.1{datastr}\n")

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
            elif self.channels == 8:
                channel_header = ('1001 <R1> (OHM), 1002 <R2> (OHM), 1003 <R3> (OHM), 1004 <R4> (OHM),'
                                    '1006 <C1> (OHM), 1007 <C2> (OHM), 1008 <C3> (OHM), 1009 <C4> (OHM)')
            elif self.channels == 10:
                channel_header = ('1001 <R1> (OHM), 1002 <R2> (OHM), 1003 <R3> (OHM),'
                                    '1004 <R4> (OHM), 1005 <R5> (OHM),'
                                    '1006 <C1> (OHM), 1007 <C2> (OHM), 1008 <C3> (OHM),'
                                    '1009 <C4> (OHM), 1010 <C5> (OHM)')
            elif self.channels == 21:
                channel_header = ('1-1p (6001), 1-3p (6002), 2-4p (6003),' 
                                '3-1p (6004), 3-5p (6005), 4-2p (6006), 4-6p (6007), '
                                '5-3p (6008), 5-7p (6009), 6-4p (6010), 6-8p (6011),'
                                '7-5p (6012), 7-9p (6013), 8-6p (6014), 8-10p (6015), '
                                '9-7p (6016), 9-11p (6017), 10-8p (6018), 10-12p (6019), '
                                '11-9p (6020), 11-13p (6021), 12-10p (6022), 12-14p (6023), '
                                '13-11p (6024), 13-15p (6025), 14-12p (6026), 14-16p (6027),' 
                                '15-13p (6028), 15-17p (6029), 16-14p (6030), 16-18p (6031),' 
                                '17-15p (6032), 17-19p (6033), 18-16p (6034), 18-20p (6035),' 
                                '19-17p (6036), 19-21p (6037), 20-18p (6038), '
                                '21-19p (6039), 21-21p (6040)')
            else:
                channel_header = "Resistance (6001)"
                    
            sys.stdout.write(f"5001 <LOAD> (VDC),5021 <DISP> (VDC),{channel_header}")

        elif command == '2':
            self._send_data()

        elif command.startswith("SET"):
            parts = command.split()[1:]
            
            for p in parts:
                
                if p.endswith('C'):
                    self.cycles = int(p[:-1])
                elif p.endswith('RPM'):
                    self.speed = int(p[:-3])
                elif p.endswith('DEG'):
                    self.angle = int(p[:-3])
                elif p.startswith('VSPD'): # VSPD_I#_F#_S#
                    p = p.split('_')[1:] # ['I#', 'F#', 'S#']
                    self.vary_speed = (int(p[0][1:]), int(p[1][1:]), int(p[2][1:])) # (initial, final, step)
                elif p.startswith('VDEG'):
                    p = p.split('_')[1:]
                    self.vary_angle = (int(p[0][1:]), int(p[1][1:]), int(p[2][1:]))
            self.ready = True

        elif command.startswith("PAUSE"):
            self.paused = True
        
        elif command.startswith("EXIT"):
            sys.exit()

        else:
            print("No command received")
