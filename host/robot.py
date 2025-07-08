import threading
import time
from typing import Sequence

import urx


class Robot:

    # THE ROBOT ARM CONNECT TO THE IP ADDRESS OF THE ROBOT -> COMPUTER HAS TO BE CONNECTED TO THE ROBOT VIA ETHERNET
    # THE ROBOT WILL MOVE FROM THE UP TO THE DOWN POSITION INDEFINITELY WHILE WAITING FOR THE ALLOCATED PERIOD
    # POSITION IS BASED ON THE JOINT POSITIONS OF THE ROBOT (J0,J1,J2,J3,J4,J5)
    # ACCELERATION AND VELOCITY IS FROM 0.00 - 1.00, WHERE 1.00 IS THE MAXIMUM
    # PERIOD_TIME IS THE TOTAL TIME THAT THE ROBOT WILL GO FROM UP -> DOWN THEN BACK UP,
    # THE PERIOD FOR ONE ITERATION IN SECONDS
    def __init__(self, ip_address: str, up_jpos: Sequence[float], down_jpos: Sequence[float], period_time: float,
                 velocity: float = 1, acceleration: float = 1):
        if len(up_jpos) != 6:
            raise RuntimeError(f"UP JOINT POSITION IS INCORRECT (6 JFloat POSITIONS): {up_jpos}")
        if len(down_jpos) != 6:
            raise RuntimeError(f"DOWN JOINT POSITION IS INCORRECT (6 JFloat POSITIONS): {down_jpos}")

        if velocity > 1:
            raise RuntimeError(f"VELOCITY EXCEEDS MAX RANGE OF 1.00: {velocity}")
        if acceleration > 1:
            raise RuntimeError(f"ACCELERATION EXCEEDS MAX RANGE OF 1.00: {acceleration}")

        try:
            self.robot = urx.Robot(ip_address)
        except Exception as exc:
            raise RuntimeError(f"ISSUE CONNECTING AND INITIALIZING THE ROBOT, IP ADDRESS: {ip_address}, {exc}")

        self.up_jpos = up_jpos
        self.down_jpos = down_jpos
        self.period_time = period_time
        self.velocity = velocity
        self.acceleration = acceleration

        self.stop_flag = False

    # RETURN THE CURRENT JOINT POSITIONS
    def get_pos(self) -> Sequence[float]:
        return self.robot.getj()

    def run(self):
        self.stop_flag = False

        while True:
            self.robot.movej(self.up_jpos, acc=self.acceleration, vel=self.velocity, wait=False)
            if self.stop_flag:
                break
            time.sleep(self.period_time / 2)

            self.robot.movej(self.down_jpos, acc=self.acceleration, vel=self.velocity, wait=False)
            if self.stop_flag:
                break
            time.sleep(self.period_time / 2)

        self.robot.movej(self.up_jpos, acc=self.acceleration, vel=self.velocity, wait=False)  # RESET ROBOT TO UP POS
        self.robot.close()

    def stop(self):
        self.stop_flag = True


if __name__ == "__main__":
    robot = Robot(
        "192.168.56.101",
        [1.314, -1.407, 1.772, -1.985, -1.634, -0.262],
        [1.384, -1.044, 1.889, -2.492, -1.617, -0.137],
        period_time=3
    )

    t = threading.Thread(target=robot.run, daemon=True)
    t.start()

    time.sleep(20)
    robot.stop()

    t.join()
