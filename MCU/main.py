import sys
import time
import random
from itertools import count
import uselect

angle = 0
speed = 0
cycles = 0
interval = 1
running = False

index = count()

spoll = uselect.poll()
spoll.register(sys.stdin, uselect.POLLIN)

def send_data():
    '''
    Sends x and y data values to the host
    '''
    x = next(index)
    y = random.randint(0, 100)
    sys.stdout.write(f"{x},{y}\n")

def process_command():
    '''
    Processes incoming commands from host
    '''
    global running, angle, speed, cycles, interval
    command = non_blocking_stdin_readline()
    if command == None:
        pass

    elif command.startswith("START"):
        running = True

    elif command.startswith("SET"):
        parts = command.split()[1:]
        
        for p in parts:
            
            if "angle=" in p:
                angle = float(p.split('=')[1])
            elif "speed=" in p:
                speed = int(p.split('=')[1])
            elif "cycles=" in p:
                cycles = int(p.split('=')[1])
            elif "resolution=" in p:
                interval = 1 / int(p.split('=')[1])


    elif command.startswith("STOP"):
        angle = 0
        speed = 0
        cycles = 0
        running = False
    
    elif command.startswith("EXIT"):
        sys.exit()

    else:
        print("No command received")

def non_blocking_stdin_readline():
    '''
    Polls stdin for input
    '''
    res = spoll.poll(0)
    if res:
        return sys.stdin.readline() # Read one character
    return None

while True:
    # check for command
    process_command()
    if running:
        send_data()
    time.sleep(interval)
