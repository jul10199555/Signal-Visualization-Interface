"""
Universal Robot Control Panel — PyQt 5.15 / Python 3.9
A standalone GUI for CB‑series & e‑series Universal Robots powered by the
`urx` Python library.

Features
─────────
• Connect / disconnect over TCP (port 30002)
• Live‑stream joint angles
• Capture an “up” and “down” pose from the current joints
• Loop those two poses for *N* repetitions
• User‑selectable **dwell** (pause) time between poses
• Live analytics tab: TCP pose
• Velocity & acceleration dials expressed as % of the controller limits

Author:Zachary Bauman · 2025‑06‑03
"""

from __future__ import annotations

import sys
import threading
from typing import List, Optional

import urx
from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QObject, QThread, pyqtSignal
from PyQt5.QtGui import QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDial,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QTabWidget,
)

AXES = ("J1", "J2", "J3", "J4", "J5", "J6")  # UR always has 6 joints
DIAL_MIN, DIAL_MAX = 1, 100  # % of controller limits


# PROGRAM-RUNNER THREAD THAT EXECUTES THE UP/DOWN LOOP IN A BACKGROUND THREAD
class WorkerRoboTap(QObject):
    finished = pyqtSignal(str)  # message → UI when done
    progress = pyqtSignal(int, int)  # signal for current number of completed rep.
    error = pyqtSignal(str)  # signal to ui when error

    def __init__(self, robot: urx.Robot, up, down, vel, acc, reps, dwell):
        super().__init__()
        self.robot = robot
        self.up = up
        self.down = down
        self.vel = vel
        self.acc = acc
        self.reps = reps
        self.dwell = dwell
        self._stop_flag = threading.Event()

    def run(self):
        try:
            for i in range(self.reps):
                if self._stop_flag.is_set():

                    self.finished.emit("Aborted by user")
                    return

                self.robot.movej(self.up, acc=self.acc, vel=self.vel, wait=False)
                if self._stop_flag.wait(self.dwell):
                    self.finished.emit("Aborted by user")
                    return

                self.robot.movej(self.down, acc=self.acc, vel=self.vel, wait=False)
                if self._stop_flag.wait(self.dwell):
                    self.finished.emit("Aborted by user")
                    return
                self.progress.emit(i + 1, self.reps)
            self.finished.emit(f"Program completed ({self.reps}x)")

        except Exception as exc:
            self.error.emit(str(exc))

    # HALTS THE RUN TASKS THEN STOPS THE CURRENT MOVEMENT TASK
    def stop(self):
        self._stop_flag.set()
        try:
            self.robot.stopj()
            self.robot.movej(self.up, acc=self.acc, vel=self.vel, wait=False)  # THEN RETURN TO THE UP POSITION
        except Exception:
            pass


class URGUI(QMainWindow):
    poll_ms = 100  # joint & analytics poll interval (ms)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("UR Control Panel")
        self.resize(1100, 640)

        # runtime state
        self.robot: Optional[urx.Robot] = None  # urx handle (None⇒ offline)
        self.curr_pos: List[float] = [0.0] * 6  # live joint angles (rad)
        self.up_pos: List[float] = [0.0] * 6  # user‑captured pose A
        self.down_pos: List[float] = [0.0] * 6  # user‑captured pose B
        self._vel = 0.2  # rad/s (updated by dial)
        self._acc = 0.4  # rad/s² (updated by dial)

        self._build_header()
        self._build_tabs()
        self._apply_stylesheet()

        # polling timer
        self._timer = QTimer(self, timeout=self._update_live_data)
        self._timer.start(self.poll_ms)
        self._reflect_connected(False)

        # thread
        self._prog_worker: Optional[QThread] = None
        self._prog_thread: Optional[WorkerRoboTap] = None

    def _build_header(self) -> None:
        head = QFrame()
        hbox = QHBoxLayout(head)
        hbox.setContentsMargins(12, 8, 12, 6)
        hbox.setSpacing(12)

        self.ip_cmb = QComboBox(editable=True)
        self.ip_cmb.addItems(["192.168.56.101", "127.0.0.1"])  # defaults
        hbox.addWidget(QLabel("ROBOT IP:"))
        hbox.addWidget(self.ip_cmb, 1)

        self.conn_btn = QPushButton("Connect")
        self.conn_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogYesButton))
        self.conn_btn.clicked.connect(self._toggle_connection)
        hbox.addWidget(self.conn_btn)

        hbox.addStretch(10)
        self.status_label = QLabel("➜Disconnected")
        hbox.addWidget(self.status_label)
        self.setMenuWidget(head)

    def _build_tabs(self) -> None:
        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.ctrl_tab = QWidget()
        self._build_control_tab(self.ctrl_tab)
        self.tabs.addTab(self.ctrl_tab, "Control")

        self.analytics_tab = QWidget()
        self._build_analytics_tab(self.analytics_tab)
        self.tabs.addTab(self.analytics_tab, "Analytics")

    def _build_control_tab(self, root: QWidget) -> None:
        root_lyt = QVBoxLayout(root)
        root_lyt.setSpacing(14)
        root_lyt.setContentsMargins(14, 8, 14, 14)

        pose_grp = QGroupBox("Current Joints (rad)")
        self.pose_tbl = QTableWidget(1, len(AXES))
        self.pose_tbl.setHorizontalHeaderLabels(AXES)
        self.pose_tbl.verticalHeader().hide()
        self.pose_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self.pose_tbl.horizontalHeader().setStretchLastSection(True)
        self.pose_tbl.setFixedHeight(60)
        pose_lyt = QVBoxLayout(pose_grp)
        pose_lyt.addWidget(self.pose_tbl)
        root_lyt.addWidget(pose_grp)

        prog_grp = QGroupBox("Program Poses (target joints)")
        prog_lyt = QGridLayout(prog_grp)
        prog_lyt.setHorizontalSpacing(16)

        for row, (title, prefix) in enumerate((("Up Pose", "up_"), ("Down Pose", "down_"))):
            prog_lyt.addWidget(QLabel(title), row, 0, Qt.AlignRight)
            for col, ax in enumerate(AXES):
                spin = QDoubleSpinBox()
                spin.setDecimals(3)
                spin.setRange(-6.283, 6.283)  # –360° … +360°
                spin.setObjectName(f"{prefix}{ax.lower()}")
                setattr(self, spin.objectName(), spin)
                prog_lyt.addWidget(spin, row, col + 1)

        # repetitions & dwell
        prog_lyt.addWidget(QLabel("Repetitions"), 2, 0, Qt.AlignRight)
        self.reps_spn = QSpinBox(minimum=1, maximum=65535, value=5)
        prog_lyt.addWidget(self.reps_spn, 2, 1)

        prog_lyt.addWidget(QLabel("Dwell(s)"), 2, 2, Qt.AlignRight)
        self.dwell_spn = QDoubleSpinBox(minimum=0.0, maximum=10.0, decimals=2, value=1.0, singleStep=0.1)
        prog_lyt.addWidget(self.dwell_spn, 2, 3)

        # capture buttons
        cap_row = QHBoxLayout();
        cap_row.setSpacing(24)
        self.cap_up_btn = QPushButton("Capture ↑ Current")
        self.cap_down_btn = QPushButton("Capture ↓ Current")
        self.cap_up_btn.clicked.connect(lambda: self._capture(self.up_pos, "up_"))
        self.cap_down_btn.clicked.connect(lambda: self._capture(self.down_pos, "down_"))
        cap_row.addWidget(self.cap_up_btn)
        cap_row.addWidget(self.cap_down_btn)
        prog_lyt.addLayout(cap_row, 3, 0, 1, len(AXES) + 1)
        root_lyt.addWidget(prog_grp)

        param_grp = QGroupBox("Motion Parameters")
        param_lyt = QHBoxLayout(param_grp)
        param_lyt.setSpacing(32)

        self._vel_dial = self._build_dial("Velocity %", 20, self._dial_changed)
        self._acc_dial = self._build_dial("Accel %", 40, self._dial_changed)
        param_lyt.addLayout(self._vel_dial)
        param_lyt.addLayout(self._acc_dial)

        go_col = QVBoxLayout()
        self.start_btn = QPushButton("Start")
        self.stop_btn = QPushButton("Stop")
        self.start_btn.clicked.connect(self._start_program)
        self.stop_btn.clicked.connect(self._stop_program)
        for b in (self.start_btn, self.stop_btn):
            b.setMinimumHeight(46)
        go_col.addWidget(self.start_btn)
        go_col.addWidget(self.stop_btn)
        go_col.addStretch()
        param_lyt.addLayout(go_col)

        root_lyt.addWidget(param_grp)

    def _build_analytics_tab(self, root: QWidget) -> None:
        lyt = QVBoxLayout(root)
        lyt.setContentsMargins(14, 8, 14, 14)
        lyt.setSpacing(12)

        tcp_grp = QGroupBox("TCP Pose (m)")
        tcp_form = QGridLayout(tcp_grp)
        self.tcp_labels = []
        for i, comp in enumerate(("X", "Y", "Z", "RX", "RY", "RZ")):
            tcp_form.addWidget(QLabel(f"{comp}:"), i, 0, Qt.AlignRight)
            lab = QLabel("0.000")
            tcp_form.addWidget(lab, i, 1)
            self.tcp_labels.append(lab)
        lyt.addWidget(tcp_grp)
        lyt.addStretch()

    def _build_dial(self, label: str, initial: int, on_change) -> QVBoxLayout:
        box = QVBoxLayout();
        box.setSpacing(4)
        lab = QLabel(f"{label}: {initial}%");
        lab.setAlignment(Qt.AlignCenter)
        dial = QDial();
        dial.setRange(DIAL_MIN, DIAL_MAX);
        dial.setValue(initial)
        dial.setNotchesVisible(True)
        dial.valueChanged.connect(lambda v, l=lab: (l.setText(f"{label}: {v}%"), on_change()))
        box.addWidget(lab)
        box.addWidget(dial)
        setattr(self, f"_{label.split()[0].lower()}_dial_widget", dial)
        return box

    def _apply_stylesheet(self) -> None:
        blue = "#1976d2"
        self.setStyleSheet(f"""
            QMainWindow {{ background:#f5f5f7; }}
            QGroupBox {{
                font-weight:600; border:1px solid #aab; border-radius:6px;
                margin-top:8px; padding-top:14px;
            }}
            QGroupBox::title {{ left:8px; top:-6px; background:#f5f5f7; padding:0 4px; }}
            QPushButton {{ background:{blue}; color:white; border-radius:4px; padding:6px 20px; font-weight:600; }}
            QPushButton:disabled {{ background:#888; }}
            QPushButton:hover:!disabled {{ background:#105a9d; }}
            QTableWidget {{ background:white; font:700 13px 'Consolas'; }}
        """)

    @pyqtSlot()
    def _toggle_connection(self) -> None:
        if self.robot:  # currently online → disconnect
            self.robot.close()
            self.robot = None
            self._reflect_connected(False)
            return

        ip = self.ip_cmb.currentText().strip()
        if not ip:
            QMessageBox.warning(self, "Missing IP", "Enter a robot IP address.")
            return
        try:
            self.robot = urx.Robot(ip)
            self._dial_changed()  # init vel/acc from dials
            self._reflect_connected(True, f"Connected ({ip})")
        except Exception as exc:  # pragma: no‑cover
            QMessageBox.critical(self, "Connection Error", str(exc))
            self._reflect_connected(False)

    def _reflect_connected(self, ok: bool, msg: str | None = None) -> None:
        widgets = [
            self.cap_up_btn, self.cap_down_btn, self.reps_spn, self.dwell_spn,
            self.start_btn, self.stop_btn,
            *(getattr(self, f"up_{ax.lower()}") for ax in AXES),
            *(getattr(self, f"down_{ax.lower()}") for ax in AXES),
            self._vel_dial.itemAt(1).widget(),  # the actual dial widgets
            self._acc_dial.itemAt(1).widget(),
        ]
        for w in widgets:
            w.setEnabled(ok)
        self.conn_btn.setText("Disconnect" if ok else "Connect")
        self.conn_btn.setIcon(self.style().standardIcon(QStyle.SP_DialogNoButton if ok else QStyle.SP_DialogYesButton))
        self.status_label.setText(msg or "➜ Disconnected")
        self.statusBar().showMessage(msg or "Disconnected")

    def _update_live_data(self) -> None:
        if not self.robot:
            return
        try:
            # joints → control tab
            self.curr_pos = self.robot.getj()
            for col, val in enumerate(self.curr_pos):
                item = QTableWidgetItem(f"{val: .3f}")
                item.setTextAlignment(Qt.AlignCenter)
                self.pose_tbl.setItem(0, col, item)

            tcp = self.robot.getl()  # [x,y,z,rx,ry,rz]
            for lab, val in zip(self.tcp_labels, tcp):
                lab.setText(f"{val: .4f}")

        except Exception:
            self.statusBar().showMessage("Live update failed", 2000)

    def _capture(self, target: List[float], prefix: str) -> None:
        if not self.robot:
            return
        target[:] = self.curr_pos
        for ax, val in zip(AXES, target):
            getattr(self, f"{prefix}{ax.lower()}").setValue(val)
        self.statusBar().showMessage(f"{prefix.rstrip('_').capitalize()} pose captured", 1500)

    def _dial_changed(self):
        self._vel = self._vel_dial.itemAt(1).widget().value() / 100.0  # 0.0 … 1.0
        self._acc = self._acc_dial.itemAt(1).widget().value() / 100.0

    def _start_program(self) -> None:
        if not self.robot:
            return

        up = [getattr(self, f"up_{ax.lower()}").value() for ax in AXES]
        down = [getattr(self, f"down_{ax.lower()}").value() for ax in AXES]

        self._prog_worker = WorkerRoboTap(self.robot, up, down, self._vel, self._acc,
                                          self.reps_spn.value(), self.dwell_spn.value())
        self._prog_thread = QThread()
        self._prog_worker.moveToThread(self._prog_thread)
        self._prog_thread.started.connect(self._prog_worker.run)
        self._prog_worker.progress.connect(self._update_progress)
        self._prog_worker.finished.connect(self._program_finished)
        self._prog_worker.error.connect(self._program_error)
        self._prog_worker.finished.connect(self._prog_thread.quit)
        self._prog_worker.error.connect(self._prog_thread.quit)
        self._prog_thread.finished.connect(self._cleanup_program_thread)

        self.start_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.statusBar().showMessage("Program running…")
        self._prog_thread.start()

    def _stop_program(self):
        if self._prog_worker:
            self._prog_worker.stop()
            self.statusBar().showMessage("Stopping…")

    def _update_progress(self, current: int, total: int):
        self.statusBar().showMessage(f"Loop {current}/{total} in progress…")

    def _program_finished(self, msg: str):
        self.statusBar().showMessage(msg)

    def _program_error(self, err: str):
        QMessageBox.critical(self, "Program Error", err)
        self.statusBar().showMessage("Error — see dialog")

    def _cleanup_program_thread(self):
        self.start_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self._prog_thread = None
        self._prog_worker = None

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon.fromTheme("applications-engineering"))
    app.setFont(QFont("Segoe UI", 10))
    gui = URGUI()
    gui.show()
    sys.exit(app.exec_())
