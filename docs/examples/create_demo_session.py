#!/usr/bin/env python3
"""
create_demo_session.py

Generate synthetic session logs for demoing Temperature Logger without a
DAQ970A. Writes the same line format the app's SessionWriter produces;
import the result via File Operations -> Import Session.

Deliberately does not import from TempLogger.py.
The four format helpers below are duplicated from there;
if the format changes, both files need updating together.

Usage:
    python create_demo_session.py
"""

import hashlib
import random
import sys
from datetime import datetime
from pathlib import Path

try:
    from PyQt5.QtWidgets import (QApplication, QDialog, QVBoxLayout,
        QHBoxLayout, QGridLayout, QGroupBox, QLabel, QSpinBox,
        QDoubleSpinBox, QLineEdit, QPushButton, QCheckBox, QDialogButtonBox,
        QFileDialog, QMessageBox)
except ImportError:
    print("PyQt5 is required. Install: pip install PyQt5")
    sys.exit(1)


# ── Session log format (duplicated from TempLogger.py) ───────────────────────

HASH_SEP = " H="


def _hash(content):
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _q(s):
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _meta_line(meta):
    ch = ",".join(str(i) for i in meta['channels'])
    names = ",".join(_q(n) for n in meta['names'])
    return (f"META T={meta['wall_clock']} E={meta['elapsed']:.6f} "
            f"SR={meta['interval']} CH={ch} N={names} "
            f"S={_q(meta['serial'])} C={_q(meta['customer'])} X=")


def _data_line(elapsed, channels, values):
    ch = ",".join(str(i) for i in channels)
    raw = ",".join(f"{v:.3f}" for v in values)
    return f"D E={elapsed:.6f} CH={ch} RAW={_q(raw)}"


def _event_line(elapsed, label):
    return f"E E={elapsed:.6f} L={label}"


def _emit(f, content, corrupt=False):
    """Write one hashed line. If corrupt, write a wrong hash so the app's
    read_session flags it as a failed integrity check on import."""
    h = "0" * 64 if corrupt else _hash(content)
    f.write(f"{content}{HASH_SEP}{h}\n")


# ── Channel profiles ──────────────────────────────────────────────────────
#
# Each channel gets a "personality" from this list, cycled by index. That
# way channels look like different data rather than copies with slight
# differences, and the filter's different behaviours (rejecting a spike,
# holding a candidate run, freezing on a stuck channel) can all be
# visible on the same plot.
#
# Fields:
#   noise_mult      scales the per-sample gaussian noise
#   drift_mult      scales the random-walk step
#   spike_chance    per-sample probability of an injected spike
#   spike_mag       (min, max) magnitude of injected spikes, in °C
#   character       None | 'ramp' | 'step' | 'stick_high'
   
PROFILES = [
    # 0: ordinary -- occasional small spikes the filter quietly rejects
    dict(noise_mult=1.0, drift_mult=1.0, spike_chance=0.006,
         spike_mag=(30, 60), character=None),
    # 1: noticeably noisier than the rest, no spikes
    dict(noise_mult=2.5, drift_mult=1.0, spike_chance=0.0,
         spike_mag=(0, 0), character=None),
    # 2: slow ramp partway through the session
    dict(noise_mult=1.0, drift_mult=1.0, spike_chance=0.0,
         spike_mag=(0, 0), character='ramp'),
    # 3: step change, filter has to promote a candidate run to accept it
    dict(noise_mult=1.0, drift_mult=1.0, spike_chance=0.0,
         spike_mag=(0, 0), character='step'),
    # 4: frequent LARGE spikes
    dict(noise_mult=1.0, drift_mult=1.0, spike_chance=0.010,
         spike_mag=(80, 200), character=None),
    # 5: steady reference for most of the session, then stuck high
    dict(noise_mult=0.4, drift_mult=0.4, spike_chance=0.0,
         spike_mag=(0, 0), character='stick_high'),
    # 6: steady, quiet, no surprises
    dict(noise_mult=0.3, drift_mult=0.3, spike_chance=0.0,
         spike_mag=(0, 0), character=None),
]

# Baseline offsets applied per channel on top of the "starting temp" the
# user picked, so six channels don't stack on one another in the plot.
CHANNEL_OFFSETS = [0.0, 2.5, 8.0, 20.0, -0.5, 5.0]


# ── Generator ─────────────────────────────────────────────────────────────────

def generate(path, channels, duration, interval, start_temp, stability,
             spikes, dropout, corrupt, weird_events, stuck, seed,
             filter_range_max=800.0):
    """Write one session log. Returns (rows, events_written, corrupt_lines)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)

    rows = int(duration / interval)
    ch_list = list(range(channels))
    names = [f"Ch {i+1}" for i in ch_list]

    # stability in [0, 1]: 0 = very steady, 1 = very noisy.
    # Scaled so 0.5 (the default) gives visible wiggle on a 20-50 °C plot.
    noise_sigma = 0.02 + stability * 1.5
    drift_step  = 0.001 + stability * 0.05

    dropout_at = int(rows * 0.7) if dropout else None
    weird_at   = int(rows * 0.35) if weird_events else None
    stuck_at   = int(rows * 0.6) if stuck else None
    dropout_ch = 4 % channels

    baselines = [start_temp + CHANNEL_OFFSETS[i % len(CHANNEL_OFFSETS)]
                 for i in range(channels)]

    drift = [0.0] * channels
    events = 0
    corrupt_count = 0

    with open(path, 'w', encoding='utf-8') as f:
        _emit(f, _meta_line({
            'wall_clock': datetime.now().isoformat(timespec='seconds'),
            'elapsed': 0.0, 'interval': interval,
            'channels': ch_list, 'names': names,
            'serial': 'DEMO', 'customer': 'DEMO',
        }))

        for row in range(rows):
            elapsed = row * interval

            # Physically-impossible event sequence: PAUSED twice in a row
            # with no RESUMED between them. Valid per the log format,
            # never produced by the app.
            if weird_events and row == weird_at:
                _emit(f, _event_line(elapsed, 'PAUSED'))
                _emit(f, _event_line(elapsed + 0.001, 'PAUSED'))
                _emit(f, _event_line(elapsed + 0.002, 'RESUMED'))
                events += 3
                continue

            values = []
            for ch in range(channels):
                # Channel drop-out: no reading at all after dropout_at.
                if (dropout_at is not None
                        and row >= dropout_at and ch == dropout_ch):
                    values.append(0.0)
                    continue

                profile = PROFILES[ch % len(PROFILES)]

                # Stuck-high: baseline becomes an out-of-range value, so
                # the filter freezes on the last confirmed anchor.
                if (profile['character'] == 'stick_high'
                        and stuck_at is not None and row >= stuck_at):
                    values.append(filter_range_max + 100.0)
                    continue

                drift[ch] += rng.gauss(0.0, drift_step * profile['drift_mult'])
                v = (baselines[ch] + drift[ch]
                     + rng.gauss(0.0, noise_sigma * profile['noise_mult']))

                # Character events
                if profile['character'] == 'ramp':
                    r0, r1 = rows // 4, rows * 3 // 4
                    if r0 <= row < r1:
                        v += (row - r0) * 0.06
                elif profile['character'] == 'step':
                    if row >= rows * 2 // 5:
                        v += 18.0

                # Per-channel spike injection
                if (spikes and profile['spike_chance'] > 0
                        and row > 10
                        and rng.random() < profile['spike_chance']):
                    lo, hi = profile['spike_mag']
                    v += rng.choice([-1, 1]) * rng.uniform(lo, hi)

                values.append(v)

            is_corrupt = corrupt and row > 0 and row % 137 == 0
            _emit(f, _data_line(elapsed, ch_list, values), corrupt=is_corrupt)
            if is_corrupt:
                corrupt_count += 1

    return rows, events, corrupt_count


# ── UI ────────────────────────────────────────────────────────────────────────

class Dialog(QDialog):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Demo Session Creator")
        self.setFixedWidth(440)

        layout = QVBoxLayout(self)

        g = QGroupBox("Session")
        gl = QGridLayout(g)

        gl.addWidget(QLabel("Channels:"), 0, 0)
        self.channels = QSpinBox(); self.channels.setRange(1, 40); self.channels.setValue(6)
        gl.addWidget(self.channels, 0, 1)

        gl.addWidget(QLabel("Duration (s):"), 1, 0)
        self.duration = QDoubleSpinBox(); self.duration.setRange(1, 7200); self.duration.setValue(600)
        gl.addWidget(self.duration, 1, 1)

        gl.addWidget(QLabel("Interval (s):"), 2, 0)
        self.interval = QDoubleSpinBox()
        self.interval.setRange(0.05, 10); self.interval.setDecimals(2); self.interval.setValue(0.5)
        gl.addWidget(self.interval, 2, 1)

        gl.addWidget(QLabel("Starting temp (°C):"), 3, 0)
        self.start_temp = QDoubleSpinBox()
        self.start_temp.setRange(-50, 500); self.start_temp.setValue(22.0)
        gl.addWidget(self.start_temp, 3, 1)

        gl.addWidget(QLabel("Stability:"), 4, 0)
        self.stability = QDoubleSpinBox()
        self.stability.setRange(0.0, 1.0); self.stability.setSingleStep(0.1)
        self.stability.setValue(0.5)
        self.stability.setToolTip("0 = flat reference lines, 1 = very noisy")
        gl.addWidget(self.stability, 4, 1)

        gl.addWidget(QLabel("Seed:"), 5, 0)
        self.seed = QSpinBox(); self.seed.setRange(0, 2**31 - 1); self.seed.setValue(42)
        gl.addWidget(self.seed, 5, 1)

        layout.addWidget(g)

        fg = QGroupBox("Inject")
        fl = QVBoxLayout(fg)
        self.spikes  = QCheckBox("Periodic spikes");         self.spikes.setChecked(True)
        self.dropout = QCheckBox("One channel drops out near the end")
        self.stuck   = QCheckBox("One channel gets stuck out-of-range (held-value warning)")
        self.corrupt = QCheckBox("Corrupt hash on a few lines")
        self.weird   = QCheckBox("Impossible event sequence (PAUSED / PAUSED)")
        for w in (self.spikes, self.dropout, self.stuck, self.corrupt, self.weird):
            fl.addWidget(w)
        layout.addWidget(fg)

        path_row = QHBoxLayout()
        path_row.addWidget(QLabel("Output:"))
        default = Path(__file__).resolve().parent / "sessions" / "demo_session.log"
        self.path = QLineEdit(str(default))
        path_row.addWidget(self.path, 1)
        browse = QPushButton("…"); browse.setFixedWidth(30)
        browse.clicked.connect(self._browse)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        btns = QDialogButtonBox()
        gen = btns.addButton("Generate", QDialogButtonBox.AcceptRole)
        btns.addButton(QDialogButtonBox.Close)
        gen.clicked.connect(self._generate)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _browse(self):
        p, _ = QFileDialog.getSaveFileName(
            self, "Save as", str(Path(self.path.text()).parent),
            "Session Logs (*.log)")
        if p:
            self.path.setText(p)

    def _generate(self):
        p = self.path.text().strip()
        if not p:
            QMessageBox.warning(self, "No path", "Please choose an output path.")
            return
        try:
            rows, events, corrupted = generate(
                p, self.channels.value(), self.duration.value(),
                self.interval.value(), self.start_temp.value(),
                self.stability.value(), self.spikes.isChecked(),
                self.dropout.isChecked(), self.corrupt.isChecked(),
                self.weird.isChecked(), self.stuck.isChecked(),
                self.seed.value())
        except OSError as e:
            QMessageBox.warning(self, "Write failed", str(e))
            return

        msg = f"Wrote {p}\n{rows} rows × {self.channels.value()} channels"
        if events:    msg += f"\n{events} odd events injected"
        if corrupted: msg += f"\n{corrupted} lines with corrupted hashes"
        msg += "\n\nImport via File Operations → Import Session."
        QMessageBox.information(self, "Done", msg)


def main():
    app = QApplication(sys.argv)
    d = Dialog()
    d.show()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())
