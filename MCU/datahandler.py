import sys
import time

# try random; fall back to urandom if needed
try:
    import random
    _randint = lambda: random.randint(0, 100)
except ImportError:
    import urandom
    _randint = lambda: (urandom.getrandbits(7) % 101)

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
        self.channels = 0
        self.ready = False

    def wait(self):
        '''Waits until parameters have been configured. CALL AFTER RUN, BEFORE GETTERS'''
        while not self.ready:
            time.sleep(1)

    def get_speed(self) -> int:
        return self.speed
    
    def get_angle(self):
        return self.angle
    
    def get_cycles(self) -> int:
        return self.cycles
    
    def get_variable_speed(self) -> tuple:
        return self.vary_speed
    
    def get_variable_angle(self) -> tuple:
        return self.vary_angle

    def run(self):
        while True:
            self._process_command()

    def _send_data(self):  # REMOVE IN FINAL PRODUCT
        '''
        Sends x and y data values to the host
        '''
        datastr = ""
        iter_n = self.channels if self.channels != 21 else 40
        for _ in range(iter_n):
            datastr += f',{_randint()}'
        sys.stdout.write(f"0.1,0.1{datastr}\n")

    def _process_command(self):
        '''
        Processes incoming commands from host
        '''
        command = sys.stdin.readline().strip()

        if not command:
            return  # nothing to do

        if command == '0':
            sys.stdout.write("ACK\n")

        elif command == '1':
            sys.stdout.write("ACK\n")  # e.g. wait for calibration first if needed
            config_data = sys.stdin.readline().strip().split(',')
            self.channels = int(config_data[-1])

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
                channel_header = ('1-1p (6001), 1-3p (6002), 2-4p (6003), 3-1p (6004), 3-5p (6005), 4-2p (6006), 4-6p (6007), '
                                  '5-3p (6008), 5-7p (6009), 6-4p (6010), 6-8p (6011), 7-5p (6012), 7-9p (6013), 8-6p (6014), 8-10p (6015), '
                                  '9-7p (6016), 9-11p (6017), 10-8p (6018), 10-12p (6019), 11-9p (6020), 11-13p (6021), 12-10p (6022), 12-14p (6023), '
                                  '13-11p (6024), 13-15p (6025), 14-12p (6026), 14-16p (6027), 15-13p (6028), 15-17p (6029), 16-14p (6030), 16-18p (6031), '
                                  '17-15p (6032), 17-19p (6033), 18-16p (6034), 18-20p (6035), 19-17p (6036), 19-21p (6037), 20-18p (6038), '
                                  '21-19p (6039), 21-21p (6040)')
            else:
                channel_header = "Resistance (6001)"
                    
            sys.stdout.write(f"5001 <LOAD> (VDC),5021 <DISP> (VDC),{channel_header}\n")

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
                elif p.startswith('VSPD'):  # VSPD_I#_F#_S#
                    p2 = p.split('_')[1:]
                    self.vary_speed = (int(p2[0][1:]), int(p2[1][1:]), int(p2[2][1:]))
                elif p.startswith('VDEG'):
                    p2 = p.split('_')[1:]
                    self.vary_angle = (int(p2[0][1:]), int(p2[1][1:]), int(p2[2][1:]))
            self.ready = True

        elif command.startswith("PAUSE"):
            self.paused = True
        
        elif command.startswith("EXIT"):
            sys.exit()

        else:
            print("No command received")