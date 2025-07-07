import time
import urx

ROBOT_IP = "192.168.56.101"

with urx.Robot(ROBOT_IP) as rob:
    rob.set_tcp((0, 0, 0, 0, 0, 0))      # good practice
    rob.set_payload(0.5)                 # adjust to your tool

    up = [0.894, -1.263, 0.911, 0.201, -0.55, 0.215]
    down = [0.887, -0.772, 1.602, -1.009, -0.678, 0.146]

    for _ in range(10):
        rob.movej(up, acc=1, vel=1, wait=False)
        time.sleep(3)
        rob.movej(down, acc=1, vel=1, wait=False)
        time.sleep(3)
