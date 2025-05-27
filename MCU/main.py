import sys
import time
import random
from itertools import count

angle = 0
pulses = 0
cycles = 0

index = count()

def send_data():
    x = next(index)
    y = random.randint(0, 5)
    sys.stdout.write(f"{x},{y}\n")

def process_command(cmd: str):
    global angle, pulses, cycles
    if cmd.startswith("SET"):
        parts = cmd.split()[1:]
        
        for p in parts:
            
            if "angle=" in p:
                angle = float(p.split('=')[1])
            elif "pulses=" in p:
                pulses = int(p.split('=')[1])
            elif "cycles=" in p:
                cycles = int(p.split('=')[1])

    elif cmd.startswith("STOP"):
        angle = 0
        pulses = 0
        cycles = 0
        index = count()

while True:
    # check for command
    # command = sys.stdin.readline().strip()
    # process_command(command)
    # sys.stdout.write(f'angle: {angle}, pulses: {pulses}, cycles: {cycles}\n')
    send_data()
    time.sleep(1)
