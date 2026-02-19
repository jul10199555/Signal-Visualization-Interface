import serial
import time
from datetime import datetime, timedelta

# Debug flags for serial monitor logs.
# Set to True while debugging payload exchange.
DEBUG_SERIAL_TX = False
DEBUG_SERIAL_RX = False


class SerialInterface:
    STATUS_DISCONNECTED = "Disconnected"
    STATUS_CONNECTING = "Connecting"
    STATUS_READY = "Ready"
    STATUS_STREAMING = "Streaming"
    STATUS_ERROR = "Error"

    def __init__(self, baudrate=115200, debug_tx=DEBUG_SERIAL_TX, debug_rx=DEBUG_SERIAL_RX, status_callback=None):
        self.port = None
        self.baudrate = baudrate
        self.ser = None
        self.debug_tx = bool(debug_tx)
        self.debug_rx = bool(debug_rx)

        self.status = self.STATUS_DISCONNECTED
        self.status_reason = "Not connected."
        self.last_error = ""
        self.status_callback = status_callback

    def _log_tx(self, message: str):
        if self.debug_tx:
            print(f"[SERIAL TX] {message}")

    def _log_rx(self, message: str):
        if self.debug_rx:
            print(f"[SERIAL RX] {message}")

    def _set_status(self, state: str, reason: str = ""):
        self.status = state
        self.status_reason = reason
        if self.status_callback:
            try:
                self.status_callback(state, reason)
            except Exception:
                pass

    def get_last_error(self) -> str:
        return self.last_error

    def sync_mcu_datetime(self, offset_seconds=2, ack_timeout=0.8):
        """
        Sends MCU date-time sync command in the format:
        YYYY_MM_DD_HH_MM_SS
        Returns (ok: bool, payload: str, ack_code: str).
        """
        if not (self.ser and self.ser.is_open):
            self.last_error = "Cannot sync date-time: serial link is not connected."
            self._set_status(self.STATUS_ERROR, self.last_error)
            return False, "", ""

        try:
            ts = datetime.now() + timedelta(seconds=float(offset_seconds))
            payload = ts.strftime("%Y_%m_%d_%H_%M_%S")

            # Clear stale bytes before sending one-shot sync command.
            try:
                self.ser.reset_input_buffer()
            except Exception:
                pass

            if not self.send_command(payload):
                return False, "", ""

            ack_code = ""
            prev_timeout = self.ser.timeout
            try:
                self.ser.timeout = ack_timeout
                raw = self.ser.readline()
                ack_code = raw.decode(errors="ignore").strip() if raw else ""
                if ack_code:
                    self._log_rx(ack_code)
            except Exception:
                pass
            finally:
                try:
                    self.ser.timeout = prev_timeout
                except Exception:
                    pass

            return True, payload, ack_code
        except Exception as e:
            self.last_error = f"Date-time sync failed: {type(e).__name__}: {e}"
            self._set_status(self.STATUS_ERROR, self.last_error)
            return False, "", ""

    def connect(self, port=None, timeout=1, retries=1, retry_delay=0.5):
        current_port = self.port
        target_port = port if port else self.port

        if not target_port:
            self.last_error = "No serial port selected."
            self._set_status(self.STATUS_ERROR, self.last_error)
            return 1

        # If already connected and switching ports, close old link first.
        if self.ser and self.ser.is_open and current_port and current_port != target_port:
            self.disconnect()

        self.port = target_port

        # If already connected on same port, keep current session.
        if self.ser and self.ser.is_open:
            self._set_status(self.STATUS_READY, f"Connected on {self.port}")
            return 0

        last_err = ""
        for attempt in range(1, max(1, int(retries)) + 1):
            try:
                self._set_status(self.STATUS_CONNECTING, f"Opening {self.port} (attempt {attempt}/{retries})")
                ser = serial.Serial(self.port, self.baudrate, timeout=timeout)
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
                        self.last_error = ""
                        self._set_status(self.STATUS_READY, f"Connected on {self.port}")
                        return 0

                last_err = f"Handshake timeout after {timeout}s on {self.port}."
                ser.close()
            except Exception as e:
                last_err = f"Port open failed on {self.port}: {type(e).__name__}: {e}"

            if attempt < retries:
                time.sleep(max(0.0, float(retry_delay)))

        self.last_error = last_err or "Connection failed."
        self._set_status(self.STATUS_ERROR, self.last_error)
        return 1

    def ensure_connection(self, timeout=1, retries=3, retry_delay=0.5) -> bool:
        if self.ser and self.ser.is_open:
            return True
        if not self.port:
            self.last_error = "Cannot reconnect: no known serial port."
            self._set_status(self.STATUS_ERROR, self.last_error)
            return False
        return self.connect(port=self.port, timeout=timeout, retries=retries, retry_delay=retry_delay) == 0

    def disconnect(self):
        """Closes microcontroller connection."""
        if self.ser and self.ser.is_open:
            try:
                self._log_tx("END")
                self.ser.write(b"END\n")
            except Exception:
                pass
            try:
                self.ser.close()
            except Exception:
                pass
        self.ser = None
        self._set_status(self.STATUS_DISCONNECTED, "Disconnected by user.")

    def send_command(self, command: str, auto_recover=False, reconnect_retries=2, reconnect_timeout=1, retry_delay=0.5):
        """Sends command (str) to microcontroller."""
        if not (self.ser and self.ser.is_open):
            if auto_recover:
                if not self.ensure_connection(timeout=reconnect_timeout, retries=reconnect_retries, retry_delay=retry_delay):
                    return False
            else:
                self.last_error = "Cannot send command: serial link is not connected."
                self._set_status(self.STATUS_ERROR, self.last_error)
                return False

        try:
            self._log_tx(command)
            self.ser.write((command + "\n").encode())
            if command in ("r", "2"):
                self._set_status(self.STATUS_STREAMING, "Streaming live data.")
            return True
        except Exception as e:
            err = f"Serial write failed: {type(e).__name__}: {e}"
            self.last_error = err
            if auto_recover and self.ensure_connection(timeout=reconnect_timeout, retries=reconnect_retries, retry_delay=retry_delay):
                try:
                    self._log_tx(command)
                    self.ser.write((command + "\n").encode())
                    if command in ("r", "2"):
                        self._set_status(self.STATUS_STREAMING, "Streaming live data.")
                    return True
                except Exception as e2:
                    self.last_error = f"Retry write failed: {type(e2).__name__}: {e2}"
                    self._set_status(self.STATUS_ERROR, self.last_error)
                    return False

            self._set_status(self.STATUS_ERROR, self.last_error)
            return False

    def read_line(self, timeout=None, auto_recover=False, reconnect_retries=2, reconnect_timeout=1, retry_delay=0.5):
        if not (self.ser and self.ser.is_open):
            if auto_recover:
                if not self.ensure_connection(timeout=reconnect_timeout, retries=reconnect_retries, retry_delay=retry_delay):
                    return None
            else:
                self.last_error = "Cannot read: serial link is not connected."
                self._set_status(self.STATUS_ERROR, self.last_error)
                return None

        prev_timeout = self.ser.timeout
        use_timeout = prev_timeout if timeout is None else timeout
        try:
            self.ser.timeout = use_timeout
            raw = self.ser.readline()
            line = raw.decode(errors="ignore").strip() if raw else ""
            if line:
                self._log_rx(line)
                return line

            self.last_error = f"Read timeout after {use_timeout}s on {self.port}."
            self._set_status(self.STATUS_ERROR, self.last_error)
            return None
        except Exception as e:
            self.last_error = f"Serial read failed: {type(e).__name__}: {e}"
            if auto_recover and self.ensure_connection(timeout=reconnect_timeout, retries=reconnect_retries, retry_delay=retry_delay):
                return self.read_line(timeout=timeout, auto_recover=False)
            self._set_status(self.STATUS_ERROR, self.last_error)
            return None
        finally:
            try:
                self.ser.timeout = prev_timeout
            except Exception:
                pass

    def mark_ready(self, reason="Connection idle."):
        if self.ser and self.ser.is_open:
            self._set_status(self.STATUS_READY, reason)
