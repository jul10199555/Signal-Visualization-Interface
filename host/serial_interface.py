import serial
import serial.tools.list_ports
import threading
import time

# Debug flags for serial monitor logs.
# Set to True while debugging payload exchange.
DEBUG_SERIAL_TX = False
DEBUG_SERIAL_RX = False


class SerialInterface:
    def __init__(self, baudrate=115200, debug_tx=DEBUG_SERIAL_TX, debug_rx=DEBUG_SERIAL_RX):
        self.port = None
        self.baudrate = baudrate
        self.ser = None
        self.debug_tx = bool(debug_tx)
        self.debug_rx = bool(debug_rx)

    def _log_tx(self, message: str):
        if self.debug_tx:
            print(f"[SERIAL TX] {message}")

    def _log_rx(self, message: str):
        if self.debug_rx:
            print(f"[SERIAL RX] {message}")

    def connect(self, port, timeout=1):
        ser = serial.Serial(port, self.baudrate, timeout=timeout)
        time.sleep(0.2)
        ser.reset_input_buffer()

        self._log_tx("0")
        ser.write(b"0\n")

        t0 = time.time()
        while time.time() - t0 < timeout:
            resp = ser.readline().decode(errors="ignore").strip()
            if resp:
                self._log_rx(resp)
            if resp == "0":
                self.ser = ser
                self.port = port
                return 0

        ser.close()
        return 1

    def disconnect(self):
        """Closes microcontroller connection."""
        if self.ser and self.ser.is_open:
            self._log_tx("END")
            self.ser.write(b"END\n")
            self.ser.close()

    def send_command(self, command: str):
        """Sends command (str) to microcontroller."""
        self._log_tx(command)
        self.ser.write((command + "\n").encode())

    def read_lines(self, plot):
        """
        Spawns new thread to read from microcontroller and calls
        respective callback function.
        """

        def _read():
            while self.ser:
                try:
                    line = self.ser.readline().decode(errors="ignore").strip()
                    if line:
                        self._log_rx(line)
                        plot(line)
                except Exception as e:
                    print(f"Read error: {e}")
                    break

        threading.Thread(target=_read, daemon=True).start()
