#!/usr/bin/env python3
# temperature_logger.py

"""
Temperature Logger - Keysight DAQ970A Data Acquisition
    Reads temperature channels from a Keysight DAQ970A, defaults to 40 channels
"""

# =============================================================================
# BOOTSTRAP — dependency check and install
#
# This section runs first, before any real imports, so that a fresh machine
# missing numpy/pyqtgraph/pyvisa/PyQt5 gets them installed and the script
# restarts. On a machine that already has them, every check below is a
# no-op and execution falls straight through to the imports at the end of
# this block — the installer code is never entered.
# =============================================================================

import subprocess
import sys
import os
import time

# ── Dependency checker with auto-restart ─────────────────────────────────────

def restart_script():
    """Restart the current script.

    Called after a successful dependency install to reload the newly
    installed packages. On POSIX, replaces the current process with a
    fresh interpreter via os.execv. On Windows, spawns a child process
    inheriting the parent's console and exits the parent.
    """
    try:
        script_path = os.path.abspath(sys.argv[0])
        python_exe = sys.executable
        cmd = [python_exe, script_path] + sys.argv[1:]
        env = os.environ.copy()
        env['TEMP_LOGGER_RESTARTED'] = '1'

        if sys.platform == 'win32':
            subprocess.Popen(cmd, env=env)
        else:
            os.execve(python_exe, cmd, env)

        sys.exit(0)
    except Exception as e:
        print(f"Could not restart automatically: {e}")
        print("Please restart the script manually.")
        sys.exit(1)

def install_dependencies():
    """Install any missing required packages. Returns True if all were installed.

    Runs `pip install` for each package that fails to import. Does not
    check the whole list first — pip is fast enough on already-installed
    packages, and checking is what we're trying to avoid on the happy path.
    """

    required_packages = {
        'numpy': 'numpy',
        'pyqtgraph': 'pyqtgraph',
        'pyvisa': 'pyvisa',
        'PyQt5': 'PyQt5',
        'pyvisa-py': 'pyvisa_py',
    }

    print("=" * 60)
    print("Temperature Logger - Dependency Install")
    print("=" * 60)

    for package_name, import_name in required_packages.items():
        try:
            __import__(import_name)
            print(f"  ✓ {package_name} - already installed")
            continue
        except ImportError:
            pass

        print(f"  Installing {package_name}...", end=" ", flush=True)
        try:
            subprocess.check_call([
                sys.executable,
                "-m", "pip", "install", package_name,
                "--user", "--quiet", "--no-cache-dir",
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("✓ Done")
        except subprocess.CalledProcessError:
            try:
                subprocess.check_call([
                    sys.executable,
                    "-m", "pip", "install", package_name,
                    "--quiet", "--no-cache-dir",
                ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                print("✓ Done")
            except subprocess.CalledProcessError as e:
                print(f"\n✗ Failed to install {package_name}: {e}")
                return False

    print("\n✓ All required dependencies installed!")
    print("\n" + "=" * 60)
    print("RESTART REQUIRED")
    print("=" * 60)
    print("\nThe script needs to restart to load the new packages.")
    print("Restarting automatically in 3 seconds...")

    time.sleep(1)
    print(" 2...")
    time.sleep(1)
    print(" 1...")
    time.sleep(1)

    restart_script()
    return True

# Try to import the required third-party packages.
# On a normal run this is instant. On a fresh machine it fails,
# and we fall back to the installer.
try:
    import numpy
    import pyqtgraph
    import pyvisa
    import PyQt5
    import pyvisa_py
    _deps_ok = True
    _import_error_msg = None
except ImportError as _e:
    _deps_ok = False
    _import_error_msg = str(_e)

if not _deps_ok:
    if os.environ.get('TEMP_LOGGER_RESTARTED') == '1':
        print("=" * 60)
        print("ERROR: dependencies still missing after an automatic restart.")
        print("=" * 60)
        print(f"Import failed with: {_import_error_msg}")
        print("\nThis usually means 'pip install' targeted a different")
        print("Python interpreter than the one running this script, or a")
        print("package failed to install correctly. Try installing manually")
        print("with the exact interpreter shown below:")
        print(f"  {sys.executable} -m pip install numpy pyqtgraph pyvisa PyQt5 pyvisa-py")
        input("Press Enter to exit...")
        sys.exit(1)

    print("Required packages missing. Running installer...")
    if not install_dependencies():
        print("\nERROR: Could not install required dependencies.")
        print("Please install them manually:")
        print("  pip install numpy pyqtgraph pyvisa PyQt5 pyvisa-py")
        input("Press Enter to exit...")
        sys.exit(1)
    sys.exit(0)

# ===== END BOOTSTRAP — program starts here ================


# ── Import everything and normal run ──────────────────────

import random
import socket
import json
import hashlib
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

os.environ.setdefault('PYQTGRAPH_QT_LIB', 'PyQt5')

import numpy as np
import pyqtgraph as pg
import pyvisa as visa

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

from pathlib import Path

# ── Crash safety net ──────────────────────────────────────────────────────────

def _excepthook(exc_type, exc_value, exc_tb):
    import traceback
    traceback.print_exception(exc_type, exc_value, exc_tb)

sys.excepthook = _excepthook

# ── Config file ───────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent

CONFIG_FILE  = SCRIPT_DIR / '.keysight_config.json'
SESSIONS_DIR = SCRIPT_DIR / 'sessions'
VIEWS_DIR = SCRIPT_DIR / 'window_settings'
SESSION_FILE = SCRIPT_DIR / '.keysight_session.json'

# ── Default Settings ──────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    'dark_mode': False,
    'font_family': 'Segoe UI',
    'font_size': 11,
    'channel_font_size': 10,
    'channel_grid_columns': 10,
    'graph_update_interval': 500,
    'sample_rate': 2.0,
    'show_min': False,
    'show_max': False,
    'filter_max_roc': 5.0,
    'filter_min_run': 3,
    'filter_range_min': -100.0,
    'filter_range_max': 800.0,
    'hold_warning_seconds': 30.0,
    'hold_warning_message': 'Out of Filter Range',
    'max_channels': 40,
    'channels_per_cassette': 20,
    'channel_address_offset': 0,
}

DEFAULT_VIEW_SETTINGS = {
    'font_size': 11,
    'channel_font_size': 10,
    'channel_grid_columns': 10,
}


# ── Theme palettes ────────────────────────────────────────────────────────────
#
# Colors for the two themes. Every entry has the same key in both dicts.
# Named for the role it plays, not the color value, so the stylesheet
# template below is palette-agnostic.

DARK_PALETTE = {
    'window_bg':              '#2d2d2d',
    'group_bg':               '#3d3d3d',
    'group_border':           '#555555',
    'text':                   '#e0e0e0',

    'input_bg':               '#3d3d3d',
    'input_border':           '#555555',
    'input_focus_border':     '#4a9eff',

    'button_bg':              '#3d3d3d',
    'button_border':          '#555555',
    'button_hover_bg':        '#4d4d4d',
    'button_hover_border':    '#666666',
    'button_pressed_bg':      '#2d2d2d',

    'scrollbar_bg':           '#2d2d2d',
    'scrollbar_handle':       '#555555',

    'menu_bg':                '#3d3d3d',
    'menu_highlight':         '#4a9eff',

    'tooltip_bg':             '#3d3d3d',
    'tooltip_border':         '#555555',

    'tab_bg':                 '#3d3d3d',
    'tab_selected_bg':        '#4d4d4d',
    'tab_hover_bg':           '#4d4d4d',
    'tab_border':             '#555555',
    'tab_selected_underline': '#4a9eff',
}

LIGHT_PALETTE = {
    'window_bg':              '#f0f0f0',
    'group_bg':               '#ffffff',
    'group_border':           '#cccccc',
    'text':                   '#000000',

    'input_bg':               '#ffffff',
    'input_border':           '#cccccc',
    'input_focus_border':     '#4a9eff',

    'button_bg':              '#f0f0f0',
    'button_border':          '#cccccc',
    'button_hover_bg':        '#e0e0e0',
    'button_hover_border':    '#aaaaaa',
    'button_pressed_bg':      '#d0d0d0',

    'scrollbar_bg':           '#f0f0f0',
    'scrollbar_handle':       '#cccccc',

    'menu_bg':                '#ffffff',
    'menu_highlight':         '#4a9eff',

    'tooltip_bg':             '#ffffff',
    'tooltip_border':         '#cccccc',

    'tab_bg':                 '#e0e0e0',
    'tab_selected_bg':        '#f0f0f0',
    'tab_hover_bg':           '#e8e8e8',
    'tab_border':             '#cccccc',
    'tab_selected_underline': '#4a9eff',
}

# ── Constants ────────────────────────────────────────────────────────────

CHECKBOX_INDICATOR_HEIGHT = 1.2
CHECKBOX_INDICATOR_WIDTH = 1.2


def _build_app_stylesheet(palette, settings):
    """Build the app-wide Qt stylesheet.

    All pixel values are derived from the UI font size in `settings`, so
    the entire chrome scales together when the user changes the font.

    Border widths and border radii are fixed: a 1px border scaled down
    doesn't render, and radii need to match the widget size to look
    right at any scale. Everything else (padding, scrollbar width,
    indicator size, tab padding, group box margins) scales with the
    font.
    """
    ui_font = settings['font_size']

    # ── Derived sizes ─────────────────────────────────────────────────
    # Floors are chosen so the defaults at ui_font=11 match the values
    # that were hardcoded before this function existed.
    pad_input        = max(4, int(ui_font * 0.4))
    pad_button_v     = max(5, int(ui_font * 0.45))
    pad_button_h     = max(10, int(ui_font * 0.9))
    pad_spin         = max(2, int(ui_font * 0.2))

    indicator_size   = max(16, int(ui_font * 1.45))

    scrollbar_width  = max(12, int(ui_font * 1.1))
    scrollbar_min    = max(20, int(ui_font * 1.8))

    tab_pad_v        = max(5, int(ui_font * 0.45))
    tab_pad_h        = max(10, int(ui_font * 0.9))

    group_margin     = max(10, int(ui_font * 0.9))
    group_pad        = max(10, int(ui_font * 0.9))
    group_title_pad  = max(5, int(ui_font * 0.45))
    group_title_x    = max(10, int(ui_font * 0.9))

    return f"""
        QWidget {{ background-color: {palette['window_bg']}; color: {palette['text']}; }}
        QMainWindow {{ background-color: {palette['window_bg']}; }}
        QGroupBox {{
            background-color: {palette['group_bg']};
            border: 1px solid {palette['group_border']};
            border-radius: 4px;
            margin-top: {group_margin}px;
            padding-top: {group_pad}px;
            color: {palette['text']};
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: {group_title_x}px;
            padding: 0 {group_title_pad}px 0 {group_title_pad}px;
            color: {palette['text']};
        }}
        QLabel {{ color: {palette['text']}; background-color: transparent; }}
        QLineEdit {{
            background-color: {palette['input_bg']};
            color: {palette['text']};
            border: 1px solid {palette['input_border']};
            border-radius: 2px;
            padding: {pad_input}px;
        }}
        QLineEdit:focus {{ border: 1px solid {palette['input_focus_border']}; }}
        QPushButton {{
            background-color: {palette['button_bg']};
            color: {palette['text']};
            border: 1px solid {palette['button_border']};
            border-radius: 3px;
            padding: {pad_button_v}px {pad_button_h}px;
        }}
        QPushButton:hover {{ background-color: {palette['button_hover_bg']}; border: 1px solid {palette['button_hover_border']}; }}
        QPushButton:pressed {{ background-color: {palette['button_pressed_bg']}; }}
        QCheckBox {{ color: {palette['text']}; background-color: transparent; }}
        QCheckBox::indicator {{ width: {indicator_size}px; height: {indicator_size}px; }}
        QSpinBox, QDoubleSpinBox, QDateEdit, QComboBox {{
            background-color: {palette['input_bg']};
            color: {palette['text']};
            border: 1px solid {palette['input_border']};
            border-radius: 2px;
            padding: {pad_spin}px;
        }}
        QScrollArea {{ background-color: {palette['window_bg']}; border: none; }}
        QScrollBar:vertical {{
            background-color: {palette['scrollbar_bg']};
            width: {scrollbar_width}px;
            border-radius: {scrollbar_width // 2}px;
        }}
        QScrollBar::handle:vertical {{
            background-color: {palette['scrollbar_handle']};
            border-radius: {scrollbar_width // 2}px;
            min-height: {scrollbar_min}px;
        }}
        QScrollBar:horizontal {{
            background-color: {palette['scrollbar_bg']};
            height: {scrollbar_width}px;
            border-radius: {scrollbar_width // 2}px;
        }}
        QScrollBar::handle:horizontal {{
            background-color: {palette['scrollbar_handle']};
            border-radius: {scrollbar_width // 2}px;
            min-width: {scrollbar_min}px;
        }}
        QStatusBar {{ background-color: {palette['window_bg']}; color: {palette['text']}; }}
        QMenuBar {{ background-color: {palette['window_bg']}; color: {palette['text']}; }}
        QMenu {{ background-color: {palette['menu_bg']}; color: {palette['text']}; }}
        QMenu::item:selected {{ background-color: {palette['menu_highlight']}; }}
        QToolTip {{ background-color: {palette['tooltip_bg']}; color: {palette['text']}; border: 1px solid {palette['tooltip_border']}; }}
        QTabWidget::pane {{ background-color: {palette['window_bg']}; border: 1px solid {palette['group_border']}; }}
        QTabBar::tab {{
            background-color: {palette['tab_bg']};
            color: {palette['text']};
            padding: {tab_pad_v}px {tab_pad_h}px;
            border: 1px solid {palette['tab_border']};
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
        }}
        QTabBar::tab:selected {{ background-color: {palette['tab_selected_bg']}; border-bottom: 1px solid {palette['tab_selected_underline']}; }}
        QTabBar::tab:hover {{ background-color: {palette['tab_hover_bg']}; }}
        QDialog {{ background-color: {palette['window_bg']}; }}
        QMessageBox {{ background-color: {palette['window_bg']}; }}
        QScrollArea QWidget {{ background-color: transparent; }}
    """

# ── Instrument helpers ────────────────────────────────────────────────────────

# USB vendor IDs for Keysight and legacy Agilent instruments, as they
# appear in a VISA USB resource string (e.g. "USB0::0x2A8D::0x0101::...").
INSTRUMENT_VIDS = ('0X2A8D', '0X0957')

# Sentinel value the DAQ970A returns for a channel with no reading.
INVALID_READING = 9.9e37

def is_supported_usb_resource(resource_string):
    """True if the USB resource string looks like a Keysight/Agilent instrument.
    """
    s = resource_string.upper()
    if s.startswith('USB'):
        parts = s.split('::')
        if len(parts) > 1 and parts[1] in INSTRUMENT_VIDS:
            return True
    return 'KEYSIGHT' in s or 'AGILENT' in s

# ── Main UI window ──────────────────────────────────────────────────────────

def get_sizes(settings):
    # All sizes derive proportionally from the two font sizes.
    # The settings dialog's spin-box minimums are the only floor on
    # how small the UI can get

    ui_font = settings['font_size']
    channel_font = settings['channel_font_size']

    return {
        # UI sizes (based on UI font)
        'ui_font': ui_font,
        'ui_timer': int(ui_font * 1.5),
        'left_panel_width': int(ui_font * 18),
        'button_height': int(ui_font * 2.2),
        'input_height': int(ui_font * 2.2),
        'label_height': int(ui_font * 1.8),
        'group_spacing': int(ui_font * 0.5),

        # Channel sizes (based on channel font)
        'channel_font': channel_font,
        'row_height': int(channel_font * 2.8),
        'font_small': int(channel_font * 0.85),
        'font_large': int(channel_font * 1.2),
        'color_dot_size': int(channel_font * 1.2),
        'channel_number_width': int(channel_font * 3.5),
        'temp_width': int(channel_font * 4.8),
        'minmax_width': int(channel_font * 16),
        'spacing': int(channel_font * 0.25),

        # The number of columns (only non-size parameter here)
        'columns': settings['channel_grid_columns'],
    }

def load_settings():
    """Load saved main-window settings, merged over defaults."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return DEFAULT_SETTINGS.copy()
        settings = DEFAULT_SETTINGS.copy()
        settings.update(cfg.get('ui_settings', {}))
        return settings
    except (FileNotFoundError, json.JSONDecodeError):
        return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    """Write main-window settings to CONFIG_FILE, preserving other sections."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}

    cfg['ui_settings'] = dict(settings)

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save settings ({e})")

# ── View secondary windows ──────────────────────────────────────────────────────────

def get_view_sizes(view_settings):
    """Sizes for a ViewWindow, using that view's own settings."""
    return get_sizes({**DEFAULT_VIEW_SETTINGS, **view_settings})

def _ensure_views_dir():
    VIEWS_DIR.mkdir(exist_ok=True)

def _view_path(view_id):
    """Path to a view's settings file (view_id is the filename stem)."""
    return VIEWS_DIR / f"{view_id}.json"

def load_all_view_settings():
    """Return {view_id: settings_dict} for all valid saved views.

    Files that don't match the expected structure are skipped.
    """
    _ensure_views_dir()
    out = {}
    for p in VIEWS_DIR.glob('*.json'):
        view_id = p.stem
        try:
            with open(p) as f:
                data = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        # Must have the required keys; extras are preserved.
        if not all(k in data for k in DEFAULT_VIEW_SETTINGS):
            continue
        merged = dict(DEFAULT_VIEW_SETTINGS)
        merged.update(data)
        out[view_id] = merged
    return out

def load_view_settings(view_id):
    """Return one view's settings, or None if the file is missing/invalid.

    Uses the same strict-compatibility check as load_all_view_settings:
    all DEFAULT_VIEW_SETTINGS keys must be present.
    """
    _ensure_views_dir()
    p = _view_path(view_id)
    if not p.exists():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if not all(k in data for k in DEFAULT_VIEW_SETTINGS):
        return None
    merged = dict(DEFAULT_VIEW_SETTINGS)
    merged.update(data)
    return merged

def save_view_settings(view_id, view_settings):
    """Write a view's settings to its own file."""
    _ensure_views_dir()
    p = _view_path(view_id)
    try:
        with open(p, 'w') as f:
            json.dump(view_settings, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save view settings ({view_id}): {e}")

def delete_view_settings(view_id):
    """Remove a view's saved settings file."""
    p = _view_path(view_id)
    try:
        p.unlink()
    except FileNotFoundError:
        pass
    except OSError as e:
        print(f"Warning: could not delete view settings ({view_id}): {e}")

def rename_view_settings(old_id, new_id):
    """Rename a view's settings file. Returns True on success.

    Fails if old_id doesn't exist, new_id already exists, or the
    filesystem rejects the rename.
    """
    _ensure_views_dir()
    src = _view_path(old_id)
    dst = _view_path(new_id)
    if not src.exists():
        return False
    if dst.exists():
        return False
    try:
        src.rename(dst)
        return True
    except OSError:
        return False

# ── Lab metadata ──────────────────────────────────────────────────────────────

def load_lab_metadata(max_channels):
    """Load saved lab metadata, merged over defaults.
    """
    try:
        with open(SESSION_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return _default_lab_metadata(max_channels)
        md = _default_lab_metadata(max_channels)
        md.update(cfg.get('lab_metadata', {}))
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_lab_metadata(max_channels)

    names = list(md.get('channel_names', []))[:max_channels]
    names += [''] * (max_channels - len(names))
    md['channel_names'] = names
    md['channels_checked'] = [i for i in md.get('channels_checked', [])
                               if isinstance(i, int) and 0 <= i < max_channels]
    return md

def save_lab_metadata(metadata):
    """Write lab metadata to SESSION_FILE."""
    try:
        with open(SESSION_FILE, 'w') as f:
            json.dump({'lab_metadata': dict(metadata)}, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save lab metadata ({e})")

def _default_lab_metadata(max_channels):
    """Return a fresh defaults dict sized to max_channels."""
    return {
        'serial_number':   '',
        'customer_number': '',
        'channel_names':   [''] * max_channels,
        'channels_checked': list(range(max_channels)),
        'extra_fields':    [],
    }

# ── Channel limit lines ───────────────────────────────────────────────────────

def _default_channel_limits(max_channels):
    return [{'min': None, 'max': None} for _ in range(max_channels)]

def _merge_channel_limits(raw, max_channels):
    """Coerce arbitrary JSON (from CONFIG_FILE or an imported config file)
    into a valid max_channels-entry channel-limits list. Anything malformed
    just falls back to "no limit" for that channel/field rather than
    raising.
    """
    limits = _default_channel_limits(max_channels)
    if isinstance(raw, list):
        for i, entry in enumerate(raw[:max_channels]):
            if not isinstance(entry, dict):
                continue
            mn, mx = entry.get('min'), entry.get('max')
            limits[i]['min'] = float(mn) if isinstance(mn, (int, float)) else None
            limits[i]['max'] = float(mx) if isinstance(mx, (int, float)) else None
    return limits

def load_channel_limits(max_channels):
    """Load saved per-channel limit lines, merged over defaults (all None)."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return _default_channel_limits(max_channels)
        return _merge_channel_limits(cfg.get('channel_limits'), max_channels)
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_channel_limits(max_channels)

def save_channel_limits(limits):
    """Write per-channel limits to CONFIG_FILE, preserving other sections
    (matches the read-merge-write pattern save_settings already uses, so
    the two coexist in the same file without clobbering each other)."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}

    cfg['channel_limits'] = limits

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save channel limits ({e})")

def _apply_limit_lines(min_line, max_line, limit, color, channel_enabled, show_min, show_max):
    """Show/hide/position one channel's min and max limit lines.

    Shared by TemperatureLogger.update_plots and ViewWindow.refresh_view so
    both draw limit lines identically. A limit line is shown whenever the
    channel is enabled (checked) AND the relevant Show Min/Show Max box is
    checked AND that field has a value set -- independent of whether the
    channel currently has any plotted data, since a limit is a static
    reference rather than something derived from a particular sample.
    """
    pen = pg.mkPen(color=(color.red(), color.green(), color.blue()),
                    width=1, style=Qt.DashLine)

    if channel_enabled and show_min and limit.get('min') is not None:
        min_line.setPen(pen)
        min_line.setValue(limit['min'])
        min_line.setVisible(True)
    else:
        min_line.setVisible(False)

    if channel_enabled and show_max and limit.get('max') is not None:
        max_line.setPen(pen)
        max_line.setValue(limit['max'])
        max_line.setVisible(True)
    else:
        max_line.setVisible(False)

# ── Channel address table ─────────────────────────────────────────────────────


ADDRESS_MIN, ADDRESS_MAX = 0, 999   # sanity bounds for a 3-digit SCPI address

def generate_channel_addresses(max_channels, channels_per_cassette, offset):
    """The slot/position formula a DAQ970A-style address follows: flat index
    -> (index + offset) split into a cassette slot and a position within it
    -> slot*100 + position. channels_per_cassette must be at least 1.
    """
    channels_per_cassette = max(1, int(channels_per_cassette))
    addresses = []
    for idx in range(max_channels):
        effective = idx + int(offset)
        slot = effective // channels_per_cassette + 1
        position = effective % channels_per_cassette + 1
        addresses.append(slot * 100 + position)
    return addresses

def _default_channel_addresses(max_channels, channels_per_cassette, offset):
    return generate_channel_addresses(max_channels, channels_per_cassette, offset)

def _merge_channel_addresses(raw, max_channels, channels_per_cassette, offset):
    """Coerce arbitrary JSON into a valid max_channels-entry address list.

    Keeps whatever valid entries are present (so hand-edited addresses --
    the whole point of a custom table -- survive a restart or a max_channels
    change); anything missing, malformed, or out of range is filled in from
    the generator formula for that index, so growing max_channels extends
    the table sensibly rather than leaving new slots at a nonsensical 0.
    """
    generated = generate_channel_addresses(max_channels, channels_per_cassette, offset)
    if not isinstance(raw, list):
        return generated
    addresses = list(generated)
    for i, val in enumerate(raw[:max_channels]):
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)) and ADDRESS_MIN <= val <= ADDRESS_MAX:
            addresses[i] = int(val)
    return addresses

def load_channel_addresses(max_channels, channels_per_cassette, offset):
    """Load the saved channel-address table, merged over a freshly
    generated default (see _merge_channel_addresses)."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            return _default_channel_addresses(max_channels, channels_per_cassette, offset)
        return _merge_channel_addresses(cfg.get('channel_addresses'),
                                        max_channels, channels_per_cassette, offset)
    except (FileNotFoundError, json.JSONDecodeError):
        return _default_channel_addresses(max_channels, channels_per_cassette, offset)

def save_channel_addresses(addresses):
    """Write the channel-address table to CONFIG_FILE, preserving other
    sections (same read-modify-write pattern as save_channel_limits)."""
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
        if not isinstance(cfg, dict):
            cfg = {}
    except (FileNotFoundError, json.JSONDecodeError):
        cfg = {}

    cfg['channel_addresses'] = list(addresses)

    try:
        with open(CONFIG_FILE, 'w') as f:
            json.dump(cfg, f, indent=2)
    except OSError as e:
        print(f"Warning: could not save channel addresses ({e})")

# ── Time helpers ──────────────────────────────────────────────────────────────


def elapsed_to_clock(elapsed):
    hours = int(elapsed // 3600)
    minutes = int((elapsed % 3600) // 60)
    seconds = int(elapsed % 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"

def clock_to_elapsed(clock_str):
    try:
        h, m, s = [int(x) for x in clock_str.strip().split(':')]
        return h * 3600 + m * 60 + s
    except ValueError:
        return None

# ── Session log format ────────────────────────────────────────────────────────
#
# Line-oriented, self-describing, append-only. Every line carries its own
# SHA-256 hash of everything before the " H=" token, so any single line can
# be verified without needing the rest of the file.
#
# Line types:
#
#   META T=<iso> E=<elapsed> SR=<interval> CH=<indices> N=<names> S=<serial>
#        C=<customer> X=<extras> H=<sha256>
#
#       Session metadata. Emitted at session start and re-emitted whenever
#       any of the metadata (channel names, serial, customer, extra fields)
#       changes mid-session. `T` is wall-clock, `E` is elapsed seconds since
#       session start.
#
#   D E=<elapsed> CH=<indices> RAW="<instrument response>" H=<sha256>
#
#       One sample. `CH` lists the channel indices covered by this sample,
#       in the order the instrument returned them. `RAW` is the exact string
#       the instrument sent, double-quoted.
#
#   E E=<elapsed> L=<label> H=<sha256>
#
#       Event marker. Labels currently in use: PAUSED, RESUMED,
#       SESSION_IMPORTED.
#
# There is no END line. A session that stopped cleanly is marked by an
# event line (PAUSED, RESUMED) or by the file simply not growing further.
# A file that ends mid-line is detected by the last line failing its hash
# check. This is intentional — we can't distinguish a crash from a clean
# stop at the file level, so we don't pretend to.

SESSION_LOG_TAG_META  = "META"
SESSION_LOG_TAG_DATA  = "D"
SESSION_LOG_TAG_EVENT = "E"

SESSION_LOG_HASH_SEP = " H="


def _hash_content(content):
    """SHA-256 of the given line content, as a lowercase hex string."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def _emit_hashed(f, content):
    """Append a hashed line to an open file object, then flush.

    Returns the line as written (without trailing newline).
    """
    h = _hash_content(content)
    line = f"{content}{SESSION_LOG_HASH_SEP}{h}"
    f.write(line + "\n")
    f.flush()
    return line


def _quote(s):
    """Wrap a string in double quotes, escaping internal quotes and backslashes."""
    return '"' + s.replace('\\', '\\\\').replace('"', '\\"') + '"'


def _unquote(s):
    """Reverse of _quote. Assumes s starts and ends with double quotes."""
    if len(s) < 2 or s[0] != '"' or s[-1] != '"':
        return s
    inner = s[1:-1]
    return inner.replace('\\"', '"').replace('\\\\', '\\')


def _format_meta_line(meta_dict):
    """Build the content portion of a META line."""
    ch = meta_dict['channels']
    names = meta_dict['names']
    extras = meta_dict['extra_fields']    # list of (name, value) tuples

    ch_str = ",".join(str(i) for i in ch)
    name_str = ",".join(_quote(n) for n in names)
    extra_str = ",".join(_quote(f"{k}={v}") for k, v in extras)

    return (
        f"{SESSION_LOG_TAG_META} "
        f"T={meta_dict['wall_clock']} "
        f"E={meta_dict['elapsed']:.6f} "
        f"SR={meta_dict['sample_rate']} "
        f"CH={ch_str} "
        f"N={name_str} "
        f"S={_quote(meta_dict['serial'])} "
        f"C={_quote(meta_dict['customer'])} "
        f"X={extra_str}"
    )


def _format_data_line(elapsed, channels, raw_response):
    """Build the content portion of a D line."""
    ch_str = ",".join(str(i) for i in channels)
    return (
        f"{SESSION_LOG_TAG_DATA} "
        f"E={elapsed:.6f} "
        f"CH={ch_str} "
        f"RAW={_quote(raw_response)}"
    )


def _format_event_line(elapsed, label):
    """Build the content portion of an E line."""
    return f"{SESSION_LOG_TAG_EVENT} E={elapsed:.6f} L={label}"


def _verify_line(line):
    """Check the hash on a line. Returns True if it verifies.

    A malformed line (no hash separator) returns False.
    """
    if SESSION_LOG_HASH_SEP not in line:
        return False
    content, _, claimed = line.rpartition(SESSION_LOG_HASH_SEP)
    return _hash_content(content) == claimed


def _split_kv(s):
    """Split a space-separated string into a dict of KEY=VALUE pairs.

    A value is either a bare token with no embedded spaces or quotes
    (e.g. a number), a single double-quoted string, or — for N= and X=
    specifically — a comma-separated run of double-quoted strings with no
    spaces between them. A value always ends at the first *unquoted*
    space.
    """
    out = {}
    i = 0
    n = len(s)
    while i < n:
        # skip whitespace
        while i < n and s[i] == ' ':
            i += 1
        if i >= n:
            break
        # read key
        j = s.find('=', i)
        if j == -1:
            break
        key = s[i:j]
        # read value: run to the first unquoted space, tracking quote
        # state so embedded commas and quoted content don't end it early.
        k = j + 1
        m = k
        in_quotes = False
        while m < n:
            c = s[m]
            if c == '\\' and in_quotes:
                m += 2
                continue
            if c == '"':
                in_quotes = not in_quotes
                m += 1
                continue
            if c == ' ' and not in_quotes:
                break
            m += 1
        value = s[k:m]
        i = m
        out[key] = value
    return out


def _parse_line(line):
    """Parse a log line into (tag, fields_dict) or None if malformed.

    The caller is expected to have verified the hash first (or not —
    parsing works regardless).
    """
    # Strip the hash suffix before parsing the content
    if SESSION_LOG_HASH_SEP in line:
        content, _, _ = line.rpartition(SESSION_LOG_HASH_SEP)
    else:
        content = line

    content = content.strip()
    if not content:
        return None

    if content.startswith(SESSION_LOG_TAG_META + " "):
        tag = SESSION_LOG_TAG_META
        body = content[len(SESSION_LOG_TAG_META) + 1:]
    elif content.startswith(SESSION_LOG_TAG_DATA + " "):
        tag = SESSION_LOG_TAG_DATA
        body = content[len(SESSION_LOG_TAG_DATA) + 1:]
    elif content.startswith(SESSION_LOG_TAG_EVENT + " "):
        tag = SESSION_LOG_TAG_EVENT
        body = content[len(SESSION_LOG_TAG_EVENT) + 1:]
    else:
        return None

    fields = _split_kv(body)
    return (tag, fields)


def parse_raw_response(raw, channels):
    """Parse an instrument response string into a dict of {channel_index: float}.

    Channels not present in the response, or whose value is unparseable,
    or whose value is the instrument's invalid-reading sentinel, are
    simply omitted from the result. Callers should treat missing channels
    as "no reading for this sample."
    """
    out = {}
    if not raw:
        return out
    parts = raw.split(',')
    for idx, ch in enumerate(channels):
        if idx >= len(parts):
            break
        token = parts[idx].strip()
        if not token:
            continue
        try:
            val = float(token)
        except ValueError:
            continue
        # Reject NaN and the DAQ970A's invalid sentinel
        if val != val:               # NaN check
            continue
        if abs(val) >= INVALID_READING * 0.5:
            continue
        out[ch] = val
    return out


class SessionWriter:
    """Append-only writer for a session log file.

    Each call writes exactly one line and flushes. No rewriting, no
    buffering across calls. Safe to interrupt at any point — the worst
    case is a partially-written last line, which will fail its hash check
    on read.
    """

    def __init__(self, path):
        self.path = path
        self.file = open(path, 'a', encoding='utf-8')

    def write_meta(self, meta_dict):
        """meta_dict: see _format_meta_line."""
        content = _format_meta_line(meta_dict)
        _emit_hashed(self.file, content)

    def write_sample(self, elapsed, channels, raw_response):
        content = _format_data_line(elapsed, channels, raw_response)
        _emit_hashed(self.file, content)

    def write_event(self, elapsed, label):
        content = _format_event_line(elapsed, label)
        _emit_hashed(self.file, content)

    def close(self):
        if self.file is not None:
            self.file.close()
            self.file = None


def read_session(path):
    """Read a session log.

    Returns a dict:
        records:   list of ('META', fields) | ('DATA', elapsed, ch_list, raw)
                   | ('EVENT', elapsed, label), in file order
        meta:      the most recent META fields dict, or None
        verified:  True if every line's hash matched
        bad_lines: list of (line_number, raw_line) for any line that failed
        channels:  union of all channel indices mentioned in any line
    """
    records = []
    meta = None
    verified = True
    bad_lines = []
    channels_seen = set()

    with open(path, encoding='utf-8') as f:
        for lineno, raw_line in enumerate(f, start=1):
            line = raw_line.rstrip('\n')
            if not line:
                continue
            if not _verify_line(line):
                verified = False
                bad_lines.append((lineno, line))
                continue
            parsed = _parse_line(line)
            if parsed is None:
                continue
            tag, fields = parsed

            if tag == SESSION_LOG_TAG_META:
                # Split CH and N into lists
                ch_list = []
                if fields.get('CH'):
                    ch_list = [int(x) for x in fields['CH'].split(',') if x]
                name_list = []
                if fields.get('N'):
                    name_list = [_unquote(x) for x in _split_quoted_list(fields['N'])]
                extras = []
                if fields.get('X'):
                    extras = [_unquote(x) for x in _split_quoted_list(fields['X'])]
                m = {
                    'wall_clock': fields.get('T', ''),
                    'elapsed': float(fields.get('E', '0')),
                    'sample_rate': fields.get('SR', ''),
                    'channels': ch_list,
                    'names': name_list,
                    'serial': _unquote(fields.get('S', '""')),
                    'customer': _unquote(fields.get('C', '""')),
                    'extra_fields': extras,
                }
                meta = m
                records.append(('META', m))
                channels_seen.update(ch_list)

            elif tag == SESSION_LOG_TAG_DATA:
                elapsed = float(fields.get('E', '0'))
                ch_list = []
                if fields.get('CH'):
                    ch_list = [int(x) for x in fields['CH'].split(',') if x]
                raw = _unquote(fields.get('RAW', '""'))
                records.append(('DATA', elapsed, ch_list, raw))
                channels_seen.update(ch_list)

            elif tag == SESSION_LOG_TAG_EVENT:
                elapsed = float(fields.get('E', '0'))
                label = fields.get('L', '')
                records.append(('EVENT', elapsed, label))

    return {
        'records': records,
        'meta': meta,
        'verified': verified,
        'bad_lines': bad_lines,
        'channels': sorted(channels_seen),
    }


def _split_quoted_list(s):
    """Split a comma-separated list where each element may be a quoted string.

    Handles the case where quoted elements contain commas.
    """
    out = []
    i = 0
    n = len(s)
    while i < n:
        if s[i] == '"':
            j = i + 1
            while j < n:
                if s[j] == '\\':
                    j += 2
                    continue
                if s[j] == '"':
                    break
                j += 1
            out.append(s[i:j+1])
            i = j + 1
            if i < n and s[i] == ',':
                i += 1
        else:
            j = s.find(',', i)
            if j == -1:
                j = n
            out.append(s[i:j])
            i = j
            if i < n and s[i] == ',':
                i += 1
    return out


def export_csv(log_path, csv_path):
    """Read a session log and write a wide-format CSV.

    The CSV is a derived artifact: all interpretation (parsing floats,
    deciding what counts as a valid reading) is applied at export time,
    not baked into the log.
    """
    import csv

    session = read_session(log_path)
    channels = session['channels']
    meta = session['meta']

    # Build a name map from the latest META
    name_map = {}
    if meta:
        for ch, name in zip(meta['channels'], meta['names']):
            name_map[ch] = name

    header = ['time_s', 'time_clock', 'event']
    for ch in channels:
        label = name_map.get(ch, '')
        header.append(f"Ch{ch+1}_{label}" if label else f"Ch{ch+1}")

    rows = []
    for rec in session['records']:
        if rec[0] == 'DATA':
            _, elapsed, ch_list, raw = rec
            vals = parse_raw_response(raw, ch_list)
            row = [f"{elapsed:.3f}", elapsed_to_clock(elapsed), ""]
            for ch in channels:
                row.append(f"{vals[ch]:.4f}" if ch in vals else "")
            rows.append(row)
        elif rec[0] == 'EVENT':
            _, elapsed, label = rec
            row = [f"{elapsed:.3f}", elapsed_to_clock(elapsed), label] + [""] * len(channels)
            rows.append(row)
        # META records are dropped from the CSV (they're the file header's job)

    with open(csv_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def session_log_path_for(timestamp=None):
    """Return a new session log path in SESSIONS_DIR."""
    SESSIONS_DIR.mkdir(exist_ok=True)
    if timestamp is None:
        timestamp = datetime.now()
    stamp = timestamp.strftime('%Y%m%d_%H%M%S')
    return str(SESSIONS_DIR / f"session_{stamp}.log")


# ── Incremental session filtering ─────────────────────────────────────────────

class RateOfChangeFilter:
    """Incremental per-channel rate-of-change / min-run-length filter.

    Per channel this keeps only the last CONFIRMED value/time/row ("anchor")
    and a short buffer of not-yet-trusted candidate samples ("pending"),
    capped at min_run - 1 entries. Feeding one sample is O(1) per channel.

    Rules, per channel, per sample (0.0 / NaN = "no reading", matching the
    app's existing convention):
      - No reading or out of range: rejected, pending discarded, anchor
        untouched. Bad data can therefore never move the filter's reference.
      - Otherwise, if the anchor is fresh and the sample is within the
        allowed rate of change from it: confirmed immediately, and any
        pending candidate run is dropped (a match with the known-good value
        means the excursion was noise).
      - Otherwise the sample joins/starts a candidate run (each member must
        be within the rate limit of the previous one). Once min_run
        consecutive samples agree with each other the whole run is promoted
        at once and the anchor jumps to it -- this is how a genuine step
        change, or a channel's very first readings, earn trust.
      - An anchor goes stale after hold_rows rows without being refreshed
        (default max(2*min_run, 5)). A stale anchor cannot vouch for a
        single sample: the rate check divides by elapsed time, so without
        this a long stretch of garbage would make the check ever more
        lenient until garbage "matched" the anchor.
    """

    def __init__(self, n_channels, max_roc, min_run, range_min, range_max, hold_rows=None):
        self.n_channels = n_channels
        self.max_roc = max_roc
        self.min_run = max(1, int(min_run))
        self.range_min = range_min
        self.range_max = range_max
        self._hold_rows_override = hold_rows

        self.anchor_value = np.full(n_channels, np.nan)
        self.anchor_time = np.full(n_channels, np.nan)
        self.anchor_idx = np.full(n_channels, -1, dtype=np.int64)

        # Must be a list comprehension: [[]] * n would alias every channel
        # to the same list object.
        self._pending = [[] for _ in range(n_channels)]

    @property
    def hold_rows(self):
        if self._hold_rows_override is not None:
            return self._hold_rows_override
        return max(2 * self.min_run, 5)

    def reset(self, max_roc=None, min_run=None, range_min=None, range_max=None):
        """Clear all per-channel state, optionally updating thresholds."""
        if max_roc is not None:
            self.max_roc = max_roc
        if min_run is not None:
            self.min_run = max(1, int(min_run))
        if range_min is not None:
            self.range_min = range_min
        if range_max is not None:
            self.range_max = range_max
        self.anchor_value[:] = np.nan
        self.anchor_time[:] = np.nan
        self.anchor_idx[:] = -1
        for p in self._pending:
            p.clear()

    def feed_row(self, idx, elapsed_t, row_values):
        """Feed one sample (all channels at one time point).

        Returns a list of (channel, row_idx, value) tuples newly confirmed
        by this call: usually 0 or 1 entries, but promoting a run also
        backfills its earlier buffered points (at most min_run entries per
        channel).
        """
        row_values = np.asarray(row_values, dtype=float)

        # Vectorized across channels: independent of any channel's history.
        has_reading = ~np.isnan(row_values) & (row_values != 0)
        in_range = (row_values >= self.range_min) & (row_values <= self.range_max)
        candidate = has_reading & in_range

        hold = self.hold_rows
        confirmed = []
        for ch in range(self.n_channels):
            if not candidate[ch]:
                self._pending[ch].clear()
                continue
            confirmed.extend(
                self._feed_channel(ch, idx, elapsed_t, float(row_values[ch]), hold))
        return confirmed

    def _feed_channel(self, ch, idx, t, v, hold):
        pending = self._pending[ch]
        anchor_v = self.anchor_value[ch]

        # Anchor first, even when a candidate run is pending: a sample that
        # matches the trusted value ends the excursion immediately instead of
        # having to rebuild a whole min_run-length run.
        if not np.isnan(anchor_v) and (idx - self.anchor_idx[ch]) <= hold:
            dt = t - self.anchor_time[ch]
            if dt > 0 and abs(v - anchor_v) / dt <= self.max_roc:
                pending.clear()
                self.anchor_value[ch] = v
                self.anchor_time[ch] = t
                self.anchor_idx[ch] = idx
                return [(ch, idx, v)]

        # Not vouched for by the anchor: try to build/extend a candidate run.
        if pending:
            last_t, last_v = pending[-1][1], pending[-1][2]
            dt = t - last_t
            if not (dt > 0 and abs(v - last_v) / dt <= self.max_roc):
                pending.clear()   # noise, not a coherent trend: reseed
        pending.append((idx, t, v))

        if len(pending) >= self.min_run:
            confirmed = [(ch, i, val) for (i, _, val) in pending]
            self.anchor_value[ch] = pending[-1][2]
            self.anchor_time[ch] = pending[-1][1]
            self.anchor_idx[ch] = pending[-1][0]
            pending.clear()
            return confirmed
        return []

    def replay(self, data):
        """Reprocess a whole array (col 0 = time, cols 1.. = channels) from
        scratch and return a same-shape array with unconfirmed cells zeroed.
        The one remaining O(N) operation -- used only for a threshold change
        or a bulk import, never per refresh tick. Reuses feed_row, so live
        and replayed data go through exactly one definition of "trusted"."""
        data = np.asarray(data, dtype=float)
        filtered = np.zeros_like(data)
        filtered[:, 0] = data[:, 0]
        self.reset()
        for idx in range(len(data)):
            for (ch, cidx, val) in self.feed_row(idx, data[idx, 0], data[idx, 1:]):
                filtered[cidx, ch + 1] = val
        return filtered


class SessionBuffer:
    """Growable raw-sample buffer plus its incrementally-filtered twin."""

    _INITIAL_CAPACITY = 1024

    def __init__(self, n_channels, max_roc, min_run, range_min, range_max):
        self.n_channels = n_channels
        self._n_cols = n_channels + 1
        self._n = 0
        self._raw = np.zeros((self._INITIAL_CAPACITY, self._n_cols))
        self._filt = np.zeros((self._INITIAL_CAPACITY, self._n_cols))
        self.filter = RateOfChangeFilter(n_channels, max_roc, min_run, range_min, range_max)

    def __len__(self):
        return self._n

    @property
    def data(self):
        return self._raw[:self._n]

    @property
    def filtered(self):
        return self._filt[:self._n]

    def _ensure_capacity(self, needed):
        cap = self._raw.shape[0]
        if needed <= cap:
            return
        # Headroom beyond `needed` so an exact-fit bulk import (append_rows)
        # doesn't make the very next live append reallocate again.
        new_cap = max(needed + needed // 4, cap * 2)
        raw = np.zeros((new_cap, self._n_cols))
        filt = np.zeros((new_cap, self._n_cols))
        raw[:self._n] = self._raw[:self._n]
        filt[:self._n] = self._filt[:self._n]
        self._raw, self._filt = raw, filt

    def append_row(self, row):
        n = self._n
        self._ensure_capacity(n + 1)
        self._raw[n] = row
        self._filt[n] = 0.0           # rows past the end may hold stale data
        self._filt[n, 0] = self._raw[n, 0]
        self._n = n + 1
        for (ch, cidx, val) in self.filter.feed_row(n, self._raw[n, 0], self._raw[n, 1:]):
            self._filt[cidx, ch + 1] = val

    def append_rows(self, rows):
        rows = np.asarray(rows, dtype=float)
        if rows.ndim != 2 or rows.shape[1] != self._n_cols:
            raise ValueError(f"expected rows of width {self._n_cols}, got shape {rows.shape}")
        self._ensure_capacity(self._n + len(rows))
        for row in rows:
            self.append_row(row)

    def clear(self):
        self._n = 0
        self.filter.reset()
        if self._raw.shape[0] > 8 * self._INITIAL_CAPACITY:
            self._raw = np.zeros((self._INITIAL_CAPACITY, self._n_cols))
            self._filt = np.zeros((self._INITIAL_CAPACITY, self._n_cols))

    def set_data(self, rows):
        """Replace the whole buffer's contents (filtering them from scratch)."""
        self.clear()
        rows = np.asarray(rows, dtype=float)
        if len(rows):
            self.append_rows(rows)

    def filter_params_changed(self, max_roc, min_run, range_min, range_max):
        f = self.filter
        return (max_roc, max(1, int(min_run)), range_min, range_max) != \
               (f.max_roc, f.min_run, f.range_min, f.range_max)

    def set_filter_params(self, max_roc, min_run, range_min, range_max):
        """Apply new thresholds. Past accept/reject decisions may no longer
        hold under them, so history is replayed once. Returns True if
        anything changed."""
        if not self.filter_params_changed(max_roc, min_run, range_min, range_max):
            return False
        self.filter.reset(max_roc=max_roc, min_run=min_run,
                          range_min=range_min, range_max=range_max)
        self.rebuild_filtered()
        return True

    def rebuild_filtered(self):
        n = self._n
        self._filt[:n] = self.filter.replay(self._raw[:n])

    def hold_duration(self, now):
        """Seconds since each channel's last CONFIRMED value, as of `now`
        (an elapsed-time value, e.g. the latest row's time column).
        """
        return now - self.filter.anchor_time


# ── Clock axis ────────────────────────────────────────────────────────────────

class ClockAxis(pg.AxisItem):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def tickStrings(self, values, scale, spacing):
        out = []
        for v in values:
            try:
                out.append(elapsed_to_clock(v))
            except (TypeError, ValueError):
                out.append('')
        return out

# ── Clickable label ───────────────────────────────────────────────────────────

class ClickableLabel(QLabel):
    """A QLabel that emits `clicked` on a left click.
    """
    clicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

# ── Network scanner ───────────────────────────────────────────────────────────

class NetworkScanner(QThread):
    found = pyqtSignal(str)
    status = pyqtSignal(str)
    done = pyqtSignal()

    IDN_PORT = 5025
    CONNECT_TIMEOUT = 0.4   # seconds, per-IP TCP connect
    IDN_TIMEOUT = 0.4       # seconds, per-IP *IDN? response
    MAX_WORKERS = 32        # concurrent connect attempts

    def run(self):
        self.status.emit("Scanning network...")

        subnet = self._determine_subnet()
        if subnet is None:
            self.status.emit("Could not determine subnet")
            self.done.emit()
            return

        self.status.emit(f"Scanning subnet {subnet}.0/24...")
        found_count = 0

        with ThreadPoolExecutor(max_workers=self.MAX_WORKERS) as pool:
            futures = {
                pool.submit(self._check_ip, f"{subnet}.{i}"): i
                for i in range(1, 255)
            }
            for fut in as_completed(futures):
                if self.isInterruptionRequested():
                    pool.shutdown(wait=False, cancel_futures=True)
                    break
                ip = fut.result()
                if ip:
                    found_count += 1
                    self.found.emit(ip)

        self.status.emit(f"Found {found_count} instrument(s)")
        self.done.emit()

    def _determine_subnet(self):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            return '.'.join(local_ip.split('.')[:3])
        except OSError:
            return None

    def _check_ip(self, ip):
        """Return ip if a KEYSIGHT/AGILENT instrument answers *IDN?, else None."""
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(self.CONNECT_TIMEOUT)
                if s.connect_ex((ip, self.IDN_PORT)) != 0:
                    return None
                s.settimeout(self.IDN_TIMEOUT)
                s.sendall(b'*IDN?\n')
                resp = s.recv(256).decode(errors='replace').strip()
            if 'KEYSIGHT' in resp.upper() or 'AGILENT' in resp.upper():
                return ip
        except OSError:
            pass
        return None

# ── Connection thread ─────────────────────────────────────────────────────────

class ConnectWorker(QThread):
    """Runs connection attempts off the GUI thread."""
    result = pyqtSignal(str, object, str)   # (method, instrument or None, description)
    progress = pyqtSignal(str)              # status text

    def __init__(self, method, ip=None, parent=None):
        super().__init__(parent)
        self.method = method    # 'lan_ip' | 'usb' | 'direct' | 'try_all'
        self.ip = ip

    def run(self):
        if self.method == 'lan_ip':
            inst, desc = self._try_lan_ip(self.ip)
            self.result.emit(self.method, inst, desc)
        elif self.method == 'usb':
            inst, desc = self._try_usb()
            self.result.emit(self.method, inst, desc)
        elif self.method == 'direct':
            self._try_direct()
        elif self.method == 'try_all':
            self._try_all()

    def _try_lan_ip(self, ip):
        if not ip:
            return None, "No IP entered"
        try:
            rm = visa.ResourceManager()
            inst = rm.open_resource(f'TCPIP::{ip}::inst0::INSTR')
            inst.timeout = 3000
            idn = inst.query('*IDN?')
            return inst, idn.split(',')[1].strip() if ',' in idn else idn.strip()
        except (visa.VisaIOError, OSError) as e:
            return None, str(e)

    def _try_usb(self):
        try:
            rm = visa.ResourceManager()
            resources = rm.list_resources()
            match = next((r for r in resources if is_supported_usb_resource(r)), None)
            if not match:
                return None, "No USB device found"
            inst = rm.open_resource(match)
            inst.timeout = 3000
            idn = inst.query('*IDN?')
            return inst, idn.split(',')[1].strip() if ',' in idn else idn.strip()
        except (visa.VisaIOError, OSError) as e:
            return None, str(e)

    def _try_direct(self):
        common_ips = [
            "192.168.1.100", "192.168.1.101", "192.168.0.100",
            "10.0.0.100", "169.254.1.100", "169.254.1.50",
        ]
        for ip in common_ips:
            if self.isInterruptionRequested():
                return
            self.progress.emit(f"Trying {ip}...")
            inst, desc = self._try_lan_ip(ip)
            if inst:
                self.result.emit(self.method, inst, ip)
                return
        self.result.emit(self.method, None, "No instrument found on common IPs")

    def _try_all(self):
        if self.ip:
            self.progress.emit(f"Trying {self.ip}...")
            inst, desc = self._try_lan_ip(self.ip)
            if inst:
                self.result.emit(self.method, inst, self.ip)
                return
        self.progress.emit("Trying USB...")
        inst, desc = self._try_usb()
        if inst:
            self.result.emit(self.method, inst, "USB")
            return
        self.result.emit(self.method, None, "No connection found")

# ── Connection dialog ─────────────────────────────────────────────────────────

class ConnectionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Connect to Instrument")
        self.instrument = None
        self.scanner = None
        self.worker = None

        layout = QVBoxLayout(self)

        self.status_label = QLabel("Select connection method or scan for instruments")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        sg = QGroupBox("Connection Status")
        sl = QGridLayout(sg)
        self.lan_ip_status   = QLabel("⬜ LAN (IP)")
        self.lan_auto_status = QLabel("⬜ LAN (Auto)")
        self.usb_status      = QLabel("⬜ USB")
        sl.addWidget(self.lan_ip_status,   0, 0)
        sl.addWidget(self.lan_auto_status, 1, 0)
        sl.addWidget(self.usb_status,      2, 0)
        layout.addWidget(sg)

        ig = QGroupBox("LAN - IP Address")
        il = QHBoxLayout(ig)
        self.ip_combo = QComboBox()
        self.ip_combo.setEditable(True)
        self.ip_combo.setPlaceholderText("192.168.1.100")
        il.addWidget(self.ip_combo)
        self.scan_btn = QPushButton("Scan Network")
        self.scan_btn.clicked.connect(self.scan_network)
        il.addWidget(self.scan_btn)
        self.direct_btn = QPushButton("Direct Connect")
        self.direct_btn.setToolTip("Try common IPs for direct Ethernet connection")
        self.direct_btn.clicked.connect(self.direct_connect)
        il.addWidget(self.direct_btn)
        layout.addWidget(ig)

        bl = QHBoxLayout()
        for label, slot in [("Connect via IP", self.connect_lan_ip),
                            ("Connect via USB", self.connect_usb),
                            ("Try All", self.try_all)]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            bl.addWidget(btn)
            if label == "Try All":
                self.try_all_btn = btn
        layout.addLayout(bl)

        btm = QHBoxLayout()
        demo = QPushButton("Offline Mode")
        demo.setToolTip("Run without instrument - will auto-connect when instrument is available")
        demo.clicked.connect(self.reject)
        btm.addWidget(demo)
        self.ok_btn = QPushButton("Use Connection")
        self.ok_btn.clicked.connect(self.accept)
        self.ok_btn.setEnabled(False)
        btm.addWidget(self.ok_btn)
        layout.addLayout(btm)

    def scan_network(self):
        self.scan_btn.setEnabled(False)
        self.ip_combo.clear()
        self.lan_auto_status.setText("🔄 LAN (Auto) - Scanning...")
        self.scanner = NetworkScanner()
        self.scanner.found.connect(self._on_scan_found)
        self.scanner.status.connect(self.status_label.setText)
        self.scanner.done.connect(self._on_scan_done)
        self.scanner.start()

    def _on_scan_found(self, ip):
        self.ip_combo.addItem(ip)
        self.lan_auto_status.setText(f"✅ LAN (Auto) - Found {ip}")

    def _on_scan_done(self):
        self.scan_btn.setEnabled(True)
        self.status_label.setText(
            "Scan complete" if self.ip_combo.count() else "No instruments found"
        )

    def connect_lan_ip(self):
        ip = self.ip_combo.currentText().strip()
        if not ip:
            self.status_label.setText("Please enter an IP address")
            return
        self._start_worker('lan_ip', ip=ip)

    def connect_usb(self):
        self._start_worker('usb')

    def direct_connect(self):
        self._start_worker('direct')

    def try_all(self):
        ip = self.ip_combo.currentText().strip()
        self._start_worker('try_all', ip=ip or None)

    def _start_worker(self, method, ip=None):
        if self.worker and self.worker.isRunning():
            return
        self._set_buttons_enabled(False)
        self.worker = ConnectWorker(method, ip=ip, parent=self)
        self.worker.progress.connect(self.status_label.setText)
        self.worker.result.connect(self._on_worker_result)
        self.worker.finished.connect(lambda: self._set_buttons_enabled(True))
        self.worker.start()

    def _on_worker_result(self, method, inst, desc):
        if inst is None:
            self.status_label.setText(f"Failed: {desc}")
            self._update_status_labels_for_failure(method, desc)
            return
        self.instrument = inst
        self.ok_btn.setEnabled(True)
        self.status_label.setText(f"Connected! ({desc})")
        self._update_status_labels_for_success(method, desc)

    def _update_status_labels_for_success(self, method, desc):
        if method in ('lan_ip', 'direct', 'try_all'):
            self.lan_ip_status.setText(f"✅ LAN (IP) - {desc}")
        elif method == 'usb':
            self.usb_status.setText(f"✅ USB - {desc}")

    def _update_status_labels_for_failure(self, method, desc):
        if method in ('lan_ip', 'direct', 'try_all'):
            self.lan_ip_status.setText(f"❌ LAN (IP) - {desc}")
        elif method == 'usb':
            self.usb_status.setText(f"❌ USB - {desc}")

    def _set_buttons_enabled(self, on):
        for w in (self.scan_btn, self.direct_btn, self.try_all_btn, self.ok_btn):
            if w is self.ok_btn:
                w.setEnabled(on and self.instrument is not None)
            else:
                w.setEnabled(on)

    def closeEvent(self, event):
        if self.scanner and self.scanner.isRunning():
            self.scanner.requestInterruption()
            self.scanner.wait(1500)
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption()
            self.worker.wait(1500)
        event.accept()

# ── Retry thread ──────────────────────────────────────────────────────────────

class RetryThread(QThread):
    connected = pyqtSignal(object)

    RETRY_INTERVAL = 5.0    # seconds between attempts
    CONNECT_TIMEOUT = 3000  # ms

    def __init__(self, ip=None):
        super().__init__()
        self.ip = ip
        self.running = True

    def run(self):
        rm = visa.ResourceManager()
        while self.running:
            inst = self._attempt(rm)
            if inst is not None and self.running:
                self.connected.emit(inst)
                return
            if not self._sleep_interruptible(self.RETRY_INTERVAL):
                return

    def _attempt(self, rm):
        try:
            if self.ip:
                inst = rm.open_resource(f'TCPIP::{self.ip}::inst0::INSTR')
                inst.timeout = self.CONNECT_TIMEOUT
                inst.query('*IDN?')
                return inst

            match = next(
                (r for r in rm.list_resources() if is_supported_usb_resource(r)),
                None,
            )
            if not match:
                return None
            inst = rm.open_resource(match)
            inst.timeout = self.CONNECT_TIMEOUT
            inst.query('*IDN?')
            return inst
        except (visa.VisaIOError, OSError):
            return None

    def _sleep_interruptible(self, seconds):
        steps = int(seconds / 0.1)
        for _ in range(steps):
            if not self.running:
                return False
            time.sleep(0.1)
        return True

    def stop(self):
        self.running = False

# ── Measurement thread ────────────────────────────────────────────────────────

class MeasurementThread(QThread):
    """Polls the instrument and emits the raw SCPI response for each sample.

    Emits (elapsed_seconds, channels_queried, raw_response_string). Parsing
    into floats happens downstream, so the session log carries the exact
    bytes the instrument sent.
    """
    data_received = pyqtSignal(float, list, str)
    read_error = pyqtSignal(str)

    def __init__(self, instrument, enabled_channels, sample_rate, session_start, channel_addresses):
        super().__init__()
        self.instrument = instrument
        self.enabled_channels = list(enabled_channels)
        self.sample_rate = sample_rate       # seconds between samples
        self.session_start = session_start   # time.monotonic() baseline for elapsed=0
        self.last_sample_elapsed = 0.0
        self.channel_addresses = list(channel_addresses)

    def start_measurement(self):
        self.last_sample_elapsed = time.monotonic() - self.session_start
        self.start()

    def stop_measurement(self):
        self.requestInterruption()
        self.wait()

    def update_channels(self, enabled_channels):
        self.enabled_channels = list(enabled_channels)

    def run(self):
        while not self.isInterruptionRequested():
            elapsed = time.monotonic() - self.session_start

            if elapsed - self.last_sample_elapsed >= self.sample_rate:
                self.last_sample_elapsed = elapsed
                channels = list(self.enabled_channels)

                if channels and self.instrument:
                    ch_str = ','.join(str(self.channel_addresses[i])
                                      for i in channels)
                    try:
                        self.instrument.write(f'MEAS:TEMP:TC? K, (@{ch_str})')
                        response = self.instrument.read()
                    except (visa.VisaIOError, OSError) as e:
                        self.read_error.emit(f"Read error: {e}")
                        response = None
                    if response is not None:
                        raw = response.rstrip('\r\n')
                        self.data_received.emit(elapsed, channels, raw)

            time.sleep(0.01)

# ── Settings dialog ──────────────────────────────────────────────────────────

class SettingsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)
        self._owner = parent
        self.setWindowTitle("Settings")

        self.settings = load_settings()
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        # ── Appearance tab ──────────────────────────────────────────────────
        appearance_tab = QWidget()
        app_layout = QVBoxLayout(appearance_tab)

        self.dark_mode_cb = QCheckBox("Dark Mode")
        self.dark_mode_cb.setChecked(self.settings['dark_mode'])
        app_layout.addWidget(self.dark_mode_cb)

        app_layout.addSpacing(10)

        font_group = QGroupBox("Font Settings")
        font_layout = QGridLayout(font_group)

        font_layout.addWidget(QLabel("Font Family:"), 0, 0)
        self.font_family = QComboBox()
        self.font_family.addItems(['Segoe UI', 'Arial', 'Helvetica', 'Verdana', 'Tahoma', 'Courier New'])
        self.font_family.setCurrentText(self.settings['font_family'])
        font_layout.addWidget(self.font_family, 0, 1)

        font_layout.addWidget(QLabel("UI Font Size:"), 1, 0)
        self.font_size = QSpinBox()
        self.font_size.setRange(4, 40)
        self.font_size.setValue(self.settings['font_size'])
        font_layout.addWidget(self.font_size, 1, 1)

        font_layout.addWidget(QLabel("Channel Font Size:"), 2, 0)
        self.channel_font_size = QSpinBox()
        self.channel_font_size.setRange(4, 40)
        self.channel_font_size.setValue(self.settings['channel_font_size'])
        font_layout.addWidget(self.channel_font_size, 2, 1)

        app_layout.addWidget(font_group)

        grid_group = QGroupBox("Channel Grid")
        grid_layout = QGridLayout(grid_group)

        grid_layout.addWidget(QLabel("Columns:"), 0, 0)
        self.channel_columns = QSpinBox()
        self.channel_columns.setRange(1, 100)
        self.channel_columns.setValue(self.settings['channel_grid_columns'])
        grid_layout.addWidget(self.channel_columns, 0, 1)

        app_layout.addWidget(grid_group)
        app_layout.addStretch()
        tabs.addTab(appearance_tab, "Appearance")

        # ── Performance tab ──────────────────────────────────────────────────
        perf_tab = QWidget()
        perf_layout = QVBoxLayout(perf_tab)

        perf_group = QGroupBox("Performance")
        perf_grid = QGridLayout(perf_group)

        perf_grid.addWidget(QLabel("Graph Update Interval (ms):"), 0, 0)
        self.graph_update = QSpinBox()
        self.graph_update.setRange(1, 100000)
        self.graph_update.setSingleStep(50)
        self.graph_update.setValue(self.settings['graph_update_interval'])
        perf_grid.addWidget(self.graph_update, 0, 1)

        perf_grid.addWidget(QLabel("Sample Rate (s):"), 1, 0)
        self.sample_rate = QDoubleSpinBox()
        self.sample_rate.setRange(0.01, 1000.0)
        self.sample_rate.setSingleStep(0.5)
        self.sample_rate.setValue(self.settings['sample_rate'])
        perf_grid.addWidget(self.sample_rate, 1, 1)

        perf_layout.addWidget(perf_group)

        hw_group = QGroupBox("Channel Hardware")
        hw_grid = QGridLayout(hw_group)

        hw_grid.addWidget(QLabel("Max Channels:"), 0, 0)
        self.max_channels_spin = QSpinBox()
        self.max_channels_spin.setRange(1, 999)
        self.max_channels_spin.setValue(self.settings['max_channels'])
        self.max_channels_spin.setToolTip(
            "How many logical channels the app tracks (UI grid, data buffer,\n"
            "saved names/colors/limits). Set this higher than what's\n"
            "physically connected if you like -- unpopulated channels just\n"
            "come back empty, same as any other channel with no reading.")
        hw_grid.addWidget(self.max_channels_spin, 0, 1)
        max_channels_note = QLabel("(applies after restarting the app)")
        max_channels_note.setStyleSheet("color: gray; font-style: italic;")
        hw_grid.addWidget(max_channels_note, 0, 2)

        session_in_progress = bool(self._owner) and self._owner.session_channels is not None
        lock_tip = "Locked while a session is in progress -- use Clear Session first."

        hw_grid.addWidget(QLabel("Cassette Size:"), 1, 0)
        self.cassette_size = QSpinBox()
        self.cassette_size.setRange(1, 999)
        self.cassette_size.setValue(self.settings['channels_per_cassette'])
        self.cassette_size.setToolTip(
            "How many address positions one cassette/module spans (e.g. 20\n"
            "for a 20-channel multiplexer card) -- used to regenerate the\n"
            "channel-address table, not applied directly at query time."
            + (f"\n\n{lock_tip}" if session_in_progress else ""))
        self.cassette_size.setEnabled(not session_in_progress)
        hw_grid.addWidget(self.cassette_size, 1, 1)

        hw_grid.addWidget(QLabel("Address Offset:"), 2, 0)
        self.channel_offset = QSpinBox()
        self.channel_offset.setRange(0, 9999)
        self.channel_offset.setValue(self.settings['channel_address_offset'])
        self.channel_offset.setToolTip(
            "Shift applied before the cassette-size split when regenerating\n"
            "the address table -- e.g. set this to one cassette's worth of\n"
            "positions to skip an empty or otherwise-unused first cassette."
            + (f"\n\n{lock_tip}" if session_in_progress else ""))
        self.channel_offset.setEnabled(not session_in_progress)
        hw_grid.addWidget(self.channel_offset, 2, 1)

        self.edit_addresses_btn = QPushButton("Edit Channel Addresses...")
        self.edit_addresses_btn.clicked.connect(self._open_address_dialog)
        self.edit_addresses_btn.setEnabled(not session_in_progress)
        if session_in_progress:
            self.edit_addresses_btn.setToolTip(lock_tip)
        hw_grid.addWidget(self.edit_addresses_btn, 3, 0, 1, 3)

        perf_layout.addWidget(hw_group)
        perf_layout.addStretch()
        tabs.addTab(perf_tab, "Performance")

        # ── Filter tab ──────────────────────────────────────────────────────
        filter_tab = QWidget()
        filter_layout = QVBoxLayout(filter_tab)

        filter_group = QGroupBox("Data Filtering")
        filter_grid = QGridLayout(filter_group)

        filter_grid.addWidget(QLabel("Max Rate of Change (°C/s):"), 0, 0)
        self.filter_roc = QDoubleSpinBox()
        self.filter_roc.setRange(0.0, 10000.0)
        self.filter_roc.setSingleStep(0.5)
        self.filter_roc.setValue(self.settings['filter_max_roc'])
        filter_grid.addWidget(self.filter_roc, 0, 1)

        filter_grid.addWidget(QLabel("Min Run Length:"), 1, 0)
        self.filter_min_run = QSpinBox()
        self.filter_min_run.setRange(0, 10000)
        self.filter_min_run.setValue(self.settings['filter_min_run'])
        filter_grid.addWidget(self.filter_min_run, 1, 1)

        filter_grid.addWidget(QLabel("Range Min (°C):"), 2, 0)
        self.filter_range_min = QDoubleSpinBox()
        self.filter_range_min.setRange(-10000.0, 10000.0)
        self.filter_range_min.setValue(self.settings['filter_range_min'])
        filter_grid.addWidget(self.filter_range_min, 2, 1)

        filter_grid.addWidget(QLabel("Range Max (°C):"), 3, 0)
        self.filter_range_max = QDoubleSpinBox()
        self.filter_range_max.setRange(-10000.0, 10000.0)
        self.filter_range_max.setValue(self.settings['filter_range_max'])
        filter_grid.addWidget(self.filter_range_max, 3, 1)

        filter_layout.addWidget(filter_group)

        hold_group = QGroupBox("Held-Value Warning")
        hold_grid = QGridLayout(hold_group)

        hold_grid.addWidget(QLabel("Warn After (s):"), 0, 0)
        self.hold_warning_seconds = QDoubleSpinBox()
        self.hold_warning_seconds.setRange(0.0, 100000.0)
        self.hold_warning_seconds.setSingleStep(5.0)
        self.hold_warning_seconds.setToolTip(
            "A channel that keeps receiving readings, but where every one\n"
            "of them keeps failing the filter (rate of change or range) so\n"
            "the displayed value hasn't actually updated in this long, will\n"
            "show the warning message below instead of the stale number.\n"
            "A channel simply not reporting at all is unaffected by this --\n"
            "that's the existing 'invalid' state, not this one.")
        self.hold_warning_seconds.setValue(self.settings['hold_warning_seconds'])
        hold_grid.addWidget(self.hold_warning_seconds, 0, 1)

        hold_grid.addWidget(QLabel("Message:"), 1, 0)
        self.hold_warning_message = QLineEdit()
        self.hold_warning_message.setText(self.settings['hold_warning_message'])
        hold_grid.addWidget(self.hold_warning_message, 1, 1)

        filter_layout.addWidget(hold_group)
        filter_layout.addStretch()
        tabs.addTab(filter_tab, "Filtering")

        layout.addWidget(tabs)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        self.apply_btn = btn_box.button(QDialogButtonBox.Apply)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_settings)
        layout.addWidget(btn_box)

        self._connect_dirty_signals()

    def _connect_dirty_signals(self):
        for widget in (self.dark_mode_cb, self.font_family, self.font_size,
                       self.channel_font_size, self.channel_columns,
                       self.graph_update, self.sample_rate,
                       self.filter_roc, self.filter_min_run,
                       self.filter_range_min, self.filter_range_max,
                       self.hold_warning_seconds, self.hold_warning_message,
                       self.max_channels_spin, self.cassette_size, self.channel_offset):
            if isinstance(widget, QCheckBox):
                widget.stateChanged.connect(self._mark_dirty)
            elif isinstance(widget, QComboBox):
                widget.currentIndexChanged.connect(self._mark_dirty)
            elif isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._mark_dirty)
            else:
                widget.valueChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *args):
        self.apply_btn.setEnabled(True)

    def apply_settings(self):
        self.settings['dark_mode'] = self.dark_mode_cb.isChecked()
        self.settings['font_family'] = self.font_family.currentText()
        self.settings['font_size'] = self.font_size.value()
        self.settings['channel_font_size'] = self.channel_font_size.value()
        self.settings['channel_grid_columns'] = self.channel_columns.value()
        self.settings['graph_update_interval'] = self.graph_update.value()
        self.settings['sample_rate'] = self.sample_rate.value()
        self.settings['filter_max_roc'] = self.filter_roc.value()
        self.settings['filter_min_run'] = self.filter_min_run.value()
        self.settings['filter_range_min'] = self.filter_range_min.value()
        self.settings['filter_range_max'] = self.filter_range_max.value()

        self.settings['hold_warning_seconds'] = self.hold_warning_seconds.value()
        self.settings['hold_warning_message'] = self.hold_warning_message.text() or 'Out of Filter Range'

        self.settings['max_channels'] = self.max_channels_spin.value()
        self.settings['channels_per_cassette'] = self.cassette_size.value()
        self.settings['channel_address_offset'] = self.channel_offset.value()

        save_settings(self.settings)
        self.apply_btn.setEnabled(False)

        if self._owner:
            self._owner.apply_settings(self.settings, False)

    def accept(self):
        if self.apply_btn.isEnabled():
            self.apply_settings()
        super().accept()

    def _open_address_dialog(self):
        dlg = ChannelAddressDialog(self._owner, self.cassette_size.value(), self.channel_offset.value())
        dlg.exec_()

# ── View settings dialog (per-view) ──────────────────────────────────────────

class ViewSettingsDialog(QDialog):
    """Per-view font / column settings. Saved to window_settings/<view_id>.json."""

    def __init__(self, view_window):
        super().__init__(view_window)
        self.view = view_window
        self.setWindowTitle(f"View Settings - {view_window.view_id}")
        self.setWindowModality(Qt.WindowModal)

        vs = view_window.view_settings
        layout = QVBoxLayout(self)

        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self.name_edit = QLineEdit()
        self.name_edit.setText(view_window.view_id)
        name_row.addWidget(self.name_edit)
        layout.addLayout(name_row)

        font_group = QGroupBox("Font Sizes")
        fg = QGridLayout(font_group)

        fg.addWidget(QLabel("View UI Font Size:"), 0, 0)
        self.view_font_size = QSpinBox()
        self.view_font_size.setRange(4, 40)
        self.view_font_size.setValue(vs['font_size'])
        fg.addWidget(self.view_font_size, 0, 1)

        fg.addWidget(QLabel("View Channel Font Size:"), 1, 0)
        self.view_channel_font_size = QSpinBox()
        self.view_channel_font_size.setRange(4, 40)
        self.view_channel_font_size.setValue(vs['channel_font_size'])
        fg.addWidget(self.view_channel_font_size, 1, 1)

        fg.addWidget(QLabel("View Columns:"), 2, 0)
        self.view_columns = QSpinBox()
        self.view_columns.setRange(1, 100)
        self.view_columns.setValue(vs['channel_grid_columns'])
        fg.addWidget(self.view_columns, 2, 1)

        layout.addWidget(font_group)

        match_btn = QPushButton("Match Main Window Settings")
        match_btn.clicked.connect(self._match_main)
        layout.addWidget(match_btn)

        layout.addStretch()

        bb = QDialogButtonBox(QDialogButtonBox.Ok
                              | QDialogButtonBox.Cancel
                              | QDialogButtonBox.Apply)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        bb.button(QDialogButtonBox.Apply).clicked.connect(self._apply)
        layout.addWidget(bb)

    def _match_main(self):
        main = load_settings()
        self.view_font_size.setValue(main['font_size'])
        self.view_channel_font_size.setValue(main['channel_font_size'])
        self.view_columns.setValue(main['channel_grid_columns'])

    def _apply(self):
        new_name = self.name_edit.text().strip()
        if not new_name:
            QMessageBox.warning(self, "Invalid Name", "The view name cannot be empty.")
            return

        old_name = self.view.view_id
        if new_name != old_name:
            if not rename_view_settings(old_name, new_name):
                QMessageBox.warning(
                    self, "Rename Failed",
                    f"Could not rename '{old_name}' to '{new_name}'. "
                    "A view with that name may already exist.")
                return
            self.view.view_id = new_name
            self.view.setWindowTitle(f"View - {new_name}")
            self.setWindowTitle(f"View Settings - {new_name}")

        self.view.view_settings['font_size'] = self.view_font_size.value()
        self.view.view_settings['channel_font_size'] = self.view_channel_font_size.value()
        self.view.view_settings['channel_grid_columns'] = self.view_columns.value()

        save_view_settings(self.view.view_id, self.view.snapshot_settings())
        self.view.refresh_view_settings()

    def accept(self):
        self._apply()
        super().accept()

# ── Channel limits dialog ─────────────────────────────────────────────────────

class LimitsDialog(QDialog):
    """Per-channel min/max limit-line editor."""

    def __init__(self, main, focus_channel=None, focus_field=None):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Channel Limits")
        self.resize(560, 520)

        self.min_edits = []
        self.max_edits = []
        self._row_widgets = []

        layout = QVBoxLayout(self)

        info = QLabel(
            "Set a minimum and/or maximum limit line per channel. Leave a "
            "box blank for no limit. Lines are drawn in the channel's color "
            "and only show while 'Show Min' / 'Show Max' is checked -- they "
            "are a visual aid only and are not recorded in the session log.")
        info.setWordWrap(True)
        layout.addWidget(info)

        header = QHBoxLayout()
        num_hdr = QLabel("Ch")
        num_hdr.setFixedWidth(28)
        header.addWidget(num_hdr)
        header.addSpacing(16 + 6)   # matches the color swatch width + spacing below
        name_hdr = QLabel("Name")
        name_hdr.setFixedWidth(170)
        header.addWidget(name_hdr)
        min_hdr = QLabel("Min")
        min_hdr.setFixedWidth(90)
        header.addWidget(min_hdr)
        max_hdr = QLabel("Max")
        max_hdr.setFixedWidth(90)
        header.addWidget(max_hdr)
        for lbl in (num_hdr, name_hdr, min_hdr, max_hdr):
            lbl.setStyleSheet("font-weight: bold;")
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_widget = QWidget()
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setSpacing(2)

        limits = main.channel_limits
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.StandardNotation)

        for i in range(main.max_channels):
            row = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(2, 2, 2, 2)

            num_lbl = QLabel(str(i + 1))
            num_lbl.setFixedWidth(28)
            row_l.addWidget(num_lbl)

            c = main.get_channel_color(i)
            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(
                f"background-color: rgb({c.red()}, {c.green()}, {c.blue()}); "
                f"border: 1px solid #888888; border-radius: 3px;")
            row_l.addWidget(swatch)
            row_l.addSpacing(6)

            name = main.channel_name_edits[i].text().strip() or f"Ch {i+1}"
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(170)
            row_l.addWidget(name_lbl)

            min_edit = QLineEdit()
            min_edit.setFixedWidth(90)
            min_edit.setPlaceholderText("none")
            min_edit.setValidator(validator)
            existing_min = limits[i]['min'] if i < len(limits) else None
            if existing_min is not None:
                min_edit.setText(f"{existing_min:g}")
            min_edit.textChanged.connect(self._mark_dirty)
            row_l.addWidget(min_edit)
            self.min_edits.append(min_edit)

            max_edit = QLineEdit()
            max_edit.setFixedWidth(90)
            max_edit.setPlaceholderText("none")
            max_edit.setValidator(validator)
            existing_max = limits[i]['max'] if i < len(limits) else None
            if existing_max is not None:
                max_edit.setText(f"{existing_max:g}")
            max_edit.textChanged.connect(self._mark_dirty)
            row_l.addWidget(max_edit)
            self.max_edits.append(max_edit)

            row_l.addStretch()
            rows_layout.addWidget(row)
            self._row_widgets.append(row)

        rows_layout.addStretch()
        scroll.setWidget(rows_widget)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        self.apply_btn = btn_box.button(QDialogButtonBox.Apply)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_limits)
        layout.addWidget(btn_box)

        if focus_channel is not None and 0 <= focus_channel < main.max_channels:
            target = (self.max_edits[focus_channel] if focus_field == 'max'
                      else self.min_edits[focus_channel])
            row = self._row_widgets[focus_channel]
            # Deferred so it runs after the dialog is actually laid out and
            # shown (exec_() hasn't started the event loop yet at __init__
            # time) -- ensureWidgetVisible/setFocus are no-ops on a widget
            # that hasn't been shown.
            QTimer.singleShot(0, lambda: self._focus_row(scroll, row, target))

    def _focus_row(self, scroll, row, target):
        scroll.ensureWidgetVisible(row)
        target.setFocus()
        target.selectAll()

    def _mark_dirty(self, *_args):
        self.apply_btn.setEnabled(True)

    @staticmethod
    def _parse(edit):
        text = edit.text().strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def apply_limits(self):
        new_limits = [
            {'min': self._parse(self.min_edits[i]), 'max': self._parse(self.max_edits[i])}
            for i in range(self.main.max_channels)
        ]
        self.main.channel_limits = new_limits
        save_channel_limits(new_limits)
        self.apply_btn.setEnabled(False)

        # Refresh immediately so a newly set/cleared limit line shows up
        # right away rather than waiting for the next periodic timer tick.
        self.main.update_plots()
        for view in self.main._view_windows:
            view._safe_refresh()

    def accept(self):
        if self.apply_btn.isEnabled():
            self.apply_limits()
        super().accept()

# ── Channel address dialog ────────────────────────────────────────────────────

class ChannelAddressDialog(QDialog):
    """Per-channel SCPI address table editor."""

    def __init__(self, main, initial_cassette_size, initial_offset):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Channel Addresses")
        self.resize(560, 560)

        self.address_edits = []
        layout = QVBoxLayout(self)

        info = QLabel(
            "Each channel queries the SCPI address shown below (e.g. 101 = "
            "cassette 1, position 1). Edit any row directly for non-standard "
            "wiring, or use Regenerate All to refill the whole table from "
            "Cassette Size and Offset below.")
        info.setWordWrap(True)
        layout.addWidget(info)

        gen_group = QGroupBox("Regenerate")
        gen_layout = QHBoxLayout(gen_group)
        gen_layout.addWidget(QLabel("Cassette Size:"))
        self.gen_cassette_size = QSpinBox()
        self.gen_cassette_size.setRange(1, 999)
        self.gen_cassette_size.setValue(initial_cassette_size)
        gen_layout.addWidget(self.gen_cassette_size)
        gen_layout.addWidget(QLabel("Offset:"))
        self.gen_offset = QSpinBox()
        self.gen_offset.setRange(0, 9999)
        self.gen_offset.setValue(initial_offset)
        gen_layout.addWidget(self.gen_offset)
        regen_btn = QPushButton("Regenerate All")
        regen_btn.setToolTip("Overwrites every row below using these two values.")
        regen_btn.clicked.connect(self._regenerate)
        gen_layout.addWidget(regen_btn)
        gen_layout.addStretch()
        layout.addWidget(gen_group)

        header = QHBoxLayout()
        num_hdr = QLabel("Ch")
        num_hdr.setFixedWidth(28)
        header.addWidget(num_hdr)
        header.addSpacing(16 + 6)   # matches the color swatch width + spacing below
        name_hdr = QLabel("Name")
        name_hdr.setFixedWidth(170)
        header.addWidget(name_hdr)
        addr_hdr = QLabel("Address")
        addr_hdr.setFixedWidth(90)
        header.addWidget(addr_hdr)
        for lbl in (num_hdr, name_hdr, addr_hdr):
            lbl.setStyleSheet("font-weight: bold;")
        header.addStretch()
        layout.addLayout(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        rows_widget = QWidget()
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setSpacing(2)

        addresses = main.channel_addresses
        for i in range(main.max_channels):
            row = QWidget()
            row_l = QHBoxLayout(row)
            row_l.setContentsMargins(2, 2, 2, 2)

            num_lbl = QLabel(str(i + 1))
            num_lbl.setFixedWidth(28)
            row_l.addWidget(num_lbl)

            c = main.get_channel_color(i)
            swatch = QLabel()
            swatch.setFixedSize(16, 16)
            swatch.setStyleSheet(
                f"background-color: rgb({c.red()}, {c.green()}, {c.blue()}); "
                f"border: 1px solid #888888; border-radius: 3px;")
            row_l.addWidget(swatch)
            row_l.addSpacing(6)

            name = main.channel_name_edits[i].text().strip() or f"Ch {i+1}"
            name_lbl = QLabel(name)
            name_lbl.setFixedWidth(170)
            row_l.addWidget(name_lbl)

            addr_edit = QSpinBox()
            addr_edit.setRange(ADDRESS_MIN, ADDRESS_MAX)
            addr_edit.setFixedWidth(90)
            addr_edit.setValue(addresses[i] if i < len(addresses) else 0)
            addr_edit.valueChanged.connect(self._mark_dirty)
            row_l.addWidget(addr_edit)
            self.address_edits.append(addr_edit)

            row_l.addStretch()
            rows_layout.addWidget(row)

        rows_layout.addStretch()
        scroll.setWidget(rows_widget)
        layout.addWidget(scroll)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Apply)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        self.apply_btn = btn_box.button(QDialogButtonBox.Apply)
        self.apply_btn.setEnabled(False)
        self.apply_btn.clicked.connect(self.apply_addresses)
        layout.addWidget(btn_box)

    def _mark_dirty(self, *_args):
        self.apply_btn.setEnabled(True)

    def _regenerate(self):
        reply = QMessageBox.question(
            self, "Regenerate All",
            "This will overwrite every address below using the Cassette "
            "Size and Offset shown above. Any manual edits will be lost.\n\n"
            "Continue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply != QMessageBox.Yes:
            return
        generated = generate_channel_addresses(
            self.main.max_channels, self.gen_cassette_size.value(), self.gen_offset.value())
        for edit, addr in zip(self.address_edits, generated):
            edit.setValue(addr)
        self._mark_dirty()

    def apply_addresses(self):
        new_addresses = [edit.value() for edit in self.address_edits]
        self.main.channel_addresses = new_addresses
        save_channel_addresses(new_addresses)
        self.apply_btn.setEnabled(False)

    def accept(self):
        if self.apply_btn.isEnabled():
            self.apply_addresses()
        super().accept()

# ── File operations dialog ────────────────────────────────────────────────────

class FileOperationsDialog(QDialog):
    """Grouped entry point for export/import actions.

    Modal to the main window. Each button fires the corresponding method on
    the owner and the dialog stays open, so the user can run several
    operations in sequence without reopening it. Closed via the Close button.
    """

    def __init__(self, owner):
        super().__init__(owner)
        self._owner = owner
        self.setWindowTitle("File Operations")
        self.setMinimumWidth(360)

        layout = QVBoxLayout(self)

        # ── Session Data ──────────────────────────────────────────────────
        session_group = QGroupBox("Session Data")
        session_layout = QVBoxLayout(session_group)
        for label, slot in [
            ("Save Data (npy + csv)", self._owner.save_data),
            ("Import Session",        self._owner.import_session),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            session_layout.addWidget(btn)
        layout.addWidget(session_group)

        # ── Graph Export ──────────────────────────────────────────────────
        graph_group = QGroupBox("Graph Export")
        graph_layout = QVBoxLayout(graph_group)
        for label, slot in [
            ("Export Graph",         self._owner.export_graph),
            ("Export Graph + Stats", self._owner.export_graph_with_stats),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            graph_layout.addWidget(btn)
        layout.addWidget(graph_group)

        # ── Configuration ─────────────────────────────────────────────────
        config_group = QGroupBox("Configuration")
        config_layout = QVBoxLayout(config_group)
        for label, slot in [
            ("Export Configuration", self._owner.export_config),
            ("Import Configuration", self._owner.import_config),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            config_layout.addWidget(btn)
        layout.addWidget(config_group)

        # ── Close ─────────────────────────────────────────────────────────
        close_box = QDialogButtonBox(QDialogButtonBox.Close)
        close_box.rejected.connect(self.reject)
        layout.addWidget(close_box)

    def closeEvent(self, event):
        event.accept()

# ── View picker dialog ────────────────────────────────────────────────────────

class ViewPickerDialog(QDialog):
    """Pick an existing saved view to open, or create a new one."""

    def __init__(self, main):
        super().__init__(main)
        self.main = main
        self.setWindowTitle("Open View Window")
        self.setMinimumWidth(400)

        self.selected_view_id = None
        self.is_new = False

        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Saved view windows:"))

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._open_selected)
        self.list_widget.currentItemChanged.connect(self._on_selection_changed)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        self.delete_btn = QPushButton("Delete Selected")
        self.delete_btn.setEnabled(False)
        self.delete_btn.clicked.connect(self._delete_selected)
        btn_row.addWidget(self.delete_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray;")
        layout.addWidget(self.status_label)

        bb = QDialogButtonBox()
        self.new_btn = bb.addButton("New View", QDialogButtonBox.ActionRole)
        self.open_btn = bb.addButton("Open", QDialogButtonBox.AcceptRole)
        bb.addButton(QDialogButtonBox.Cancel)
        self.new_btn.clicked.connect(self._create_new)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        layout.addWidget(bb)

        self._refresh_list()

    def _refresh_list(self):
        self.list_widget.clear()
        all_views = load_all_view_settings()
        all_files = sorted(p.stem for p in VIEWS_DIR.glob('*.json')) if VIEWS_DIR.exists() else []
        invalid = [v for v in all_files if v not in all_views]

        for view_id in sorted(all_views.keys()):
            item = QListWidgetItem(view_id)
            item.setData(Qt.UserRole, view_id)
            self.list_widget.addItem(item)

        for view_id in invalid:
            item = QListWidgetItem(f"{view_id}    [invalid — cannot open]")
            item.setData(Qt.UserRole, view_id)
            item.setData(Qt.UserRole + 1, 'invalid')
            item.setForeground(QColor(150, 150, 150))
            self.list_widget.addItem(item)

        if self.list_widget.count() == 0:
            self.status_label.setText("No saved views yet. Click 'New View' to create one.")
        else:
            self.status_label.setText("")

    def _on_selection_changed(self, current, previous):
        if current is None:
            self.delete_btn.setEnabled(False)
            return
        self.delete_btn.setEnabled(True)
        is_invalid = current.data(Qt.UserRole + 1) == 'invalid'
        self.open_btn.setEnabled(not is_invalid)

    def _selected_view_id(self):
        item = self.list_widget.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _open_selected(self, item):
        if item.data(Qt.UserRole + 1) == 'invalid':
            QMessageBox.warning(
                self, "Invalid View",
                f"The saved settings for '{item.data(Qt.UserRole)}' "
                "are corrupt or incompatible and cannot be opened.")
            return
        self.selected_view_id = item.data(Qt.UserRole)
        self.is_new = False
        self.accept()

    def _create_new(self):
        view_id = self._next_free_name()
        self.selected_view_id = view_id
        self.is_new = True
        self.accept()

    def _next_free_name(self):
        if not VIEWS_DIR.exists():
            return "new view 1"
        existing = {p.stem for p in VIEWS_DIR.glob('*.json')}
        n = 1
        while f"new view {n}" in existing:
            n += 1
        return f"new view {n}"

    def accept(self):
        if self.selected_view_id is None:
            item = self.list_widget.currentItem()
            if item is None:
                return
            if item.data(Qt.UserRole + 1) == 'invalid':
                QMessageBox.warning(
                    self, "Invalid View",
                    f"The saved settings for '{item.data(Qt.UserRole)}' "
                    "are corrupt or incompatible and cannot be opened.")
                return
            self.selected_view_id = item.data(Qt.UserRole)
            self.is_new = False
        super().accept()

    def _delete_selected(self):
        view_id = self._selected_view_id()
        if not view_id:
            return

        is_open = any(w.view_id == view_id for w in self.main._view_windows)
        msg = f"Delete view '{view_id}'?\n\nThe saved settings file will be removed."
        if is_open:
            msg += "\n\nThe window for this view is currently open and will be closed."

        reply = QMessageBox.question(
            self, "Delete View", msg,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        if is_open:
            for w in list(self.main._view_windows):
                if w.view_id == view_id:
                    w.close()
                    break

        delete_view_settings(view_id)
        self._refresh_list()


# ── View window ───────────────────────────────────────────────────────────────

class ViewWindow(QWidget):
    refresh_error = pyqtSignal(str)

    def __init__(self, main, view_id):
        super().__init__()
        self.main = main
        self.view_id = view_id
        self.setWindowTitle(f"View - {view_id}")
        self.setGeometry(220, 220, 1100, 750)
        self.setWindowFlags(Qt.Window)

        self.settings = load_settings()
        self.view_settings = load_view_settings(view_id)
        if self.view_settings is None:
            self.view_settings = dict(DEFAULT_VIEW_SETTINGS)
        self.dark_mode = self.settings['dark_mode']

        self.visible_channels = set(range(self.main.max_channels))

        self.view_color_swatches = []
        self.view_checkboxes    = []
        self.view_temp_labels   = []
        self.view_name_labels   = []
        self.view_min_labels    = []
        self.view_max_labels    = []
        self.view_plots         = []
        self.view_limit_min_lines = []
        self.view_limit_max_lines = []
        self._view_cells        = []
        self._old_view_columns  = None
        self._view_settings_dialog = None

        self._build_ui()
        self._build_view_plots()
        self.apply_persisted_state(self.view_settings)
        self._rebuild_channel_panel()

        self.timer = QTimer()
        self.timer.timeout.connect(self._safe_refresh)
        self.timer.start(self.settings['graph_update_interval'])

    def _build_view_plots(self):
        for _ in range(self.main.max_channels):
            self.view_plots.append(self.plot.plot([], []))
            min_line = pg.InfiniteLine(angle=0, movable=False)
            min_line.setVisible(False)
            self.plot.addItem(min_line)
            self.view_limit_min_lines.append(min_line)
            max_line = pg.InfiniteLine(angle=0, movable=False)
            max_line.setVisible(False)
            self.plot.addItem(max_line)
            self.view_limit_max_lines.append(max_line)

    def _build_ui(self):
        sizes = get_view_sizes(self.view_settings)

        layout = QHBoxLayout(self)

        ctrl = QWidget()
        cl = QVBoxLayout(ctrl)
        cl.setSpacing(sizes['group_spacing'])

        tg = QGroupBox("Time Range")
        tl = QVBoxLayout(tg)
        fl = QHBoxLayout()
        fl.addWidget(QLabel("From:"))
        self.time_from = QLineEdit()
        self.time_from.setPlaceholderText("HH:MM:SS")
        fl.addWidget(self.time_from)
        tl.addLayout(fl)
        el = QHBoxLayout()
        el.addWidget(QLabel("To:   "))
        self.time_to = QLineEdit()
        self.time_to.setPlaceholderText("HH:MM:SS or live")
        el.addWidget(self.time_to)
        tl.addLayout(el)
        ab = QPushButton("Apply")
        ab.clicked.connect(self._safe_refresh)
        tl.addWidget(ab)
        cb = QPushButton("Clear (show all)")
        cb.clicked.connect(lambda: (self.time_from.clear(),
                                    self.time_to.clear(),
                                    self._safe_refresh()))
        tl.addWidget(cb)
        cl.addWidget(tg)

        yg = QGroupBox("Temperature Range (°C)")
        yl = QVBoxLayout(yg)
        yml = QHBoxLayout()
        yml.addWidget(QLabel("Min:"))
        self.y_min = QLineEdit()
        self.y_min.setPlaceholderText("auto")
        yml.addWidget(self.y_min)
        yl.addLayout(yml)
        yml2 = QHBoxLayout()
        yml2.addWidget(QLabel("Max:"))
        self.y_max = QLineEdit()
        self.y_max.setPlaceholderText("auto")
        yml2.addWidget(self.y_max)
        yl.addLayout(yml2)
        yab = QPushButton("Apply Y Range")
        yab.clicked.connect(self._safe_refresh)
        yl.addWidget(yab)
        asb = QPushButton("Autoscale")
        asb.clicked.connect(lambda: (self.y_min.clear(),
                                     self.y_max.clear(),
                                     self.plot.enableAutoRange()))
        yl.addWidget(asb)
        cl.addWidget(yg)

        cg = QGroupBox("Channel Range Filter")
        cglay = QVBoxLayout(cg)
        crl = QHBoxLayout()
        self.view_ch_from = QSpinBox()
        self.view_ch_from.setMinimum(1)
        self.view_ch_from.setMaximum(self.main.max_channels)
        self.view_ch_from.setValue(1)
        self.view_ch_from.setPrefix("Ch ")
        crl.addWidget(self.view_ch_from)
        crl.addWidget(QLabel("to"))
        self.view_ch_to = QSpinBox()
        self.view_ch_to.setMinimum(1)
        self.view_ch_to.setMaximum(self.main.max_channels)
        self.view_ch_to.setValue(self.main.max_channels)
        self.view_ch_to.setPrefix("Ch ")
        crl.addWidget(self.view_ch_to)
        cglay.addLayout(crl)
        cab = QPushButton("Apply Channel Range")
        cab.clicked.connect(self._apply_channel_range)
        cglay.addWidget(cab)
        cl.addWidget(cg)

        vg = QGroupBox("Displayed Channels")
        vgl = QVBoxLayout(vg)
        show_all_btn = QPushButton("Show All")
        show_all_btn.clicked.connect(self._show_all_channels)
        vgl.addWidget(show_all_btn)
        hide_all_btn = QPushButton("Hide All")
        hide_all_btn.clicked.connect(self._hide_all_channels)
        vgl.addWidget(hide_all_btn)
        cl.addWidget(vg)

        minmax_row = QHBoxLayout()
        self.show_min = QCheckBox("Show Min")
        self.show_min.stateChanged.connect(self._safe_refresh)
        minmax_row.addWidget(self.show_min)

        self.show_max = QCheckBox("Show Max")
        self.show_max.stateChanged.connect(self._safe_refresh)
        minmax_row.addWidget(self.show_max)

        limits_btn = QPushButton("Add Limits")
        limits_btn.clicked.connect(lambda: self.main.open_limits_dialog())
        minmax_row.addWidget(limits_btn)
        cl.addLayout(minmax_row)

        cl.addSpacing(6)

        for label, slot in [
            ("Export Graph + Stats", self.export_graph_with_stats),
            ("Screenshot",           self.take_screenshot),
            ("View Settings",        self.open_view_settings),
        ]:
            btn = QPushButton(label)
            btn.clicked.connect(slot)
            cl.addWidget(btn)

        cl.addStretch()

        right = QWidget()
        rl = QVBoxLayout(right)

        self.graph = pg.GraphicsLayoutWidget()
        self.graph.setBackground('#2d2d2d' if self.dark_mode else 'w')

        self.plot = self.graph.addPlot(
            axisItems={'bottom': ClockAxis(orientation='bottom')})
        self.plot.showGrid(x=1, y=1, alpha=0.2)
        self.plot.setLabel('bottom', "Time")
        self.plot.setLabel('left', 'Temperature [°C]')
        self.plot.setMenuEnabled(False)
        self.plot.getViewBox().setBackgroundColor(
            '#2d2d2d' if self.dark_mode else 'w')
        self._apply_axis_colors()
        rl.addWidget(self.graph, stretch=0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.ch_widget = QWidget()
        self.channel_layout = QGridLayout(self.ch_widget)
        self.channel_layout.setSpacing(4)
        scroll.setWidget(self.ch_widget)
        rl.addWidget(scroll, stretch=0)

        layout.addWidget(ctrl, stretch=2)
        layout.addWidget(right, stretch=8)

    def _apply_axis_colors(self):
        if self.dark_mode:
            self.plot.getAxis('bottom').setPen('w')
            self.plot.getAxis('left').setPen('w')
            self.plot.getAxis('bottom').setTextPen('w')
            self.plot.getAxis('left').setTextPen('w')
        else:
            self.plot.getAxis('bottom').setPen('k')
            self.plot.getAxis('left').setPen('k')
            self.plot.getAxis('bottom').setTextPen('k')
            self.plot.getAxis('left').setTextPen('k')

    def _show_all_channels(self):
        self.visible_channels = set(range(self.main.max_channels))
        for i, cb in enumerate(self.view_checkboxes):
            cb.blockSignals(True)
            cb.setChecked(True)
            cb.blockSignals(False)
        self._safe_refresh()

    def _hide_all_channels(self):
        self.visible_channels = set()
        for i, cb in enumerate(self.view_checkboxes):
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._safe_refresh()

    def _on_visibility_changed(self, idx):
        cb = self.view_checkboxes[idx]
        if cb.isChecked():
            self.visible_channels.add(idx)
        else:
            self.visible_channels.discard(idx)
        self._safe_refresh()

    def _on_limit_label_clicked(self, channel_idx, field):
        if field == 'min' and not self.show_min.isChecked():
            return
        if field == 'max' and not self.show_max.isChecked():
            return
        self.main.open_limits_dialog(focus_channel=channel_idx, focus_field=field)

    def _rebuild_channel_panel(self):
        assert len(self.view_plots) == self.main.max_channels, (
            f"view_plots invariant broken: expected {self.main.max_channels}, "
            f"got {len(self.view_plots)}"
        )

        sizes = get_view_sizes(self.view_settings)
        columns      = sizes['columns']
        row_height   = sizes['row_height']
        font_small   = sizes['font_small']
        channel_font = sizes['channel_font']

        dark_mode = self.settings['dark_mode']
        bg_color     = "#2a2a2a" if dark_mode else "#ffffff"
        cell_bg      = "#2d2d2d" if dark_mode else "#f0f0f0"
        text_color   = "#e0e0e0" if dark_mode else "#000000"
        border_color = "#444444" if dark_mode else "#cccccc"
        btn_border   = "#777777" if dark_mode else "#444444"

        while self.channel_layout.count():
            item = self.channel_layout.takeAt(0)
            w = item.widget()
            if w:
                w.setParent(None)
                w.deleteLater()

        self.view_color_swatches.clear()
        self.view_checkboxes.clear()
        self.view_temp_labels.clear()
        self.view_name_labels.clear()
        self.view_min_labels.clear()
        self.view_max_labels.clear()
        self._view_cells.clear()

        for col in range(columns):
            self.channel_layout.setColumnStretch(col, 0)

        num_channels = self.main.max_channels
        rows = (num_channels + columns - 1) // columns

        for i in range(num_channels):
            row = i % rows
            col = i // rows

            cell = QWidget()
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cell.setFixedHeight(row_height)
            cell.setStyleSheet(f"background-color: {cell_bg}; border: none;")
            if dark_mode:
                cell.setAutoFillBackground(True)
                pal = cell.palette()
                pal.setColor(cell.backgroundRole(), QColor(45, 45, 45))
                cell.setPalette(pal)

            hb = QHBoxLayout(cell)
            hb.setContentsMargins(2, 1, 2, 1)
            hb.setSpacing(sizes['spacing'])

            cb = QCheckBox(f"{i+1}")
            cb.setFixedWidth(sizes['channel_number_width'])
            cb.setStyleSheet(f"""
                QCheckBox {{
                    font-size: {channel_font}px;
                    font-weight: bold;
                    color: {text_color};
                    background-color: transparent;
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
            """)
            cb.setChecked(i in self.visible_channels)
            cb.stateChanged.connect(lambda _, idx=i: self._on_visibility_changed(idx))
            self.view_checkboxes.append(cb)
            hb.addWidget(cb)

            c = self.main.get_channel_color(i)
            swatch = QLabel()
            swatch.setFixedSize(sizes['color_dot_size'] + 6,
                                sizes['color_dot_size'] + 6)
            swatch.setStyleSheet(f"""
                background-color: rgb({c.red()}, {c.green()}, {c.blue()});
                border: 2px solid {btn_border};
                border-radius: 4px;
            """)
            self.view_color_swatches.append(swatch)
            hb.addWidget(swatch)

            temp_lbl = QLabel("---")
            temp_lbl.setFixedWidth(sizes['temp_width'])
            temp_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            temp_lbl.setStyleSheet(f"""
                font-family: monospace;
                font-size: {font_small}px;
                color: {text_color};
                background-color: transparent;
            """)
            self.view_temp_labels.append(temp_lbl)
            hb.addWidget(temp_lbl)

            name_lbl = QLabel(self.main.channel_name_edits[i].text())
            name_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            name_lbl.setStyleSheet(f"""
                font-size: {channel_font}px;
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 2px;
                padding: 2px 4px;
            """)
            name_lbl.setWordWrap(False)
            self.view_name_labels.append(name_lbl)
            hb.addWidget(name_lbl, stretch=0)

            mm_widget = QWidget()
            mm_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            mm_widget.setStyleSheet("background-color: transparent;")
            mm_layout = QHBoxLayout(mm_widget)
            mm_layout.setContentsMargins(0, 0, 0, 0)
            mm_layout.setSpacing(sizes['spacing'])

            min_lbl = ClickableLabel("")  
            min_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            min_lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #4fc3f7;
                font-size: {font_small}px;
                background-color: transparent;
            """)
            min_lbl.clicked.connect(lambda idx=i: self._on_limit_label_clicked(idx, 'min'))
            self.view_min_labels.append(min_lbl)
            mm_layout.addWidget(min_lbl, stretch=0)

            max_lbl = ClickableLabel("")  
            max_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            max_lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #ef5350;
                font-size: {font_small}px;
                background-color: transparent;
            """)
            max_lbl.clicked.connect(lambda idx=i: self._on_limit_label_clicked(idx, 'max'))
            self.view_max_labels.append(max_lbl)
            mm_layout.addWidget(max_lbl, stretch=0)

            hb.addWidget(mm_widget, stretch=0)

            self.channel_layout.addWidget(cell, row, col)
            self._view_cells.append(cell)

        self._safe_refresh()

    def _update_channel_styles(self):
        sizes = get_view_sizes(self.view_settings)
        dark_mode = self.settings['dark_mode']
        text_color = "#e0e0e0" if dark_mode else "#000000"
        bg_color = "#2a2a2a" if dark_mode else "#ffffff"
        cell_bg = "#2d2d2d" if dark_mode else "#f0f0f0"
        border_color = "#444444" if dark_mode else "#cccccc"
        btn_border = "#777777" if dark_mode else "#444444"

        channel_font = sizes['channel_font']
        font_small = sizes['font_small']

        # Cells
        for cell in self._view_cells:
            cell.setStyleSheet(f"background-color: {cell_bg}; border: none;")
            cell.setFixedHeight(sizes['row_height'])
            if cell.layout() is not None:
                cell.layout().setSpacing(sizes['spacing'])
            if dark_mode:
                cell.setAutoFillBackground(True)
                pal = cell.palette()
                pal.setColor(cell.backgroundRole(), QColor(45, 45, 45))
                cell.setPalette(pal)

        # Color swatches
        for i, sw in enumerate(self.view_color_swatches):
            c = self.main.get_channel_color(i)
            sw.setFixedSize(sizes['color_dot_size'] + 6, sizes['color_dot_size'] + 6)
            sw.setStyleSheet(f"""
                background-color: rgb({c.red()}, {c.green()}, {c.blue()});
                border: 2px solid {btn_border};
                border-radius: 4px;
            """)

        # Checkboxes
        for cb in self.view_checkboxes:
            cb.setFixedWidth(sizes['channel_number_width'])
            cb.setStyleSheet(f"""
                QCheckBox {{
                    font-size: {channel_font}px;
                    font-weight: bold;
                    color: {text_color};
                    background-color: transparent;
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
                QCheckBox::indicator:checked {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
            """)

        # Temp labels
        for lbl in self.view_temp_labels:
            lbl.setFixedWidth(sizes['temp_width'])
            lbl.setStyleSheet(f"""
                font-family: monospace;
                font-size: {font_small}px;
                color: {text_color};
                background-color: transparent;
            """)

        # Name labels (also syncs names from main window)
        for i, lbl in enumerate(self.view_name_labels):
            lbl.setStyleSheet(f"""
                font-size: {channel_font}px;
                background-color: {bg_color};
                color: {text_color};
                border: 1px solid {border_color};
                border-radius: 2px;
                padding: 2px 4px;
            """)
            if i < len(self.main.channel_name_edits):
                lbl.setText(self.main.channel_name_edits[i].text())

        # Min/Max labels
        for lbl in self.view_min_labels:
            lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #4fc3f7;
                font-size: {font_small}px;
                background-color: transparent;
            """)
        for lbl in self.view_max_labels:
            lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #ef5350;
                font-size: {font_small}px;
                background-color: transparent;
            """)

    def _apply_channel_range(self):
        start = self.view_ch_from.value() - 1
        end   = self.view_ch_to.value()
        self.visible_channels = set(range(start, end))
        for i, cb in enumerate(self.view_checkboxes):
            cb.blockSignals(True)
            cb.setChecked(i in self.visible_channels)
            cb.blockSignals(False)
        self._safe_refresh()

    def open_view_settings(self):
        if self._view_settings_dialog is None or not self._view_settings_dialog.isVisible():
            self._view_settings_dialog = ViewSettingsDialog(self)
            self._view_settings_dialog.show()
        else:
            self._view_settings_dialog.raise_()
            self._view_settings_dialog.activateWindow()

    def refresh_view_settings(self):
        loaded = load_view_settings(self.view_id)
        if loaded is None:
            return
        self.view_settings = loaded
        self.apply_persisted_state(self.view_settings)

        sizes = get_view_sizes(self.view_settings)
        if self._old_view_columns != sizes['columns']:
            self._rebuild_channel_panel()
            self._old_view_columns = sizes['columns']
        else:
            self._update_channel_styles()
        self._safe_refresh()

    def update_colors(self):
        self.settings = load_settings()
        self.dark_mode = self.settings['dark_mode']

        self.graph.setBackground('#2d2d2d' if self.dark_mode else 'w')
        self.plot.getViewBox().setBackgroundColor(
            '#2d2d2d' if self.dark_mode else 'w')
        self._apply_axis_colors()
        self.plot.update()

        self._update_channel_styles()

    def update_name_labels(self):
        for i, lbl in enumerate(self.view_name_labels):
            if i < len(self.main.channel_name_edits):
                lbl.setText(self.main.channel_name_edits[i].text())

    def _safe_refresh(self, *args):
        try:
            self.refresh_view()
        except Exception as e:
            self.refresh_error.emit(f"[View {self.view_id}] refresh error: {e}")

    def get_filtered_data(self):
        t_from = (clock_to_elapsed(self.time_from.text())
                  if self.time_from.text().strip() else None)
        t_to = (clock_to_elapsed(self.time_to.text())
                if self.time_to.text().strip() else None)
        return self.main.get_filtered_data(t_from, t_to)

    def _view_temp_label_style(self, override_color=None):
        """Stylesheet for a channel's temp label: normal theme-matched
        color, or a color override for the invalid/held states.
        """
        sizes = get_view_sizes(self.view_settings)
        dark_mode = self.settings['dark_mode']
        color = override_color or ("#e0e0e0" if dark_mode else "#000000")
        weight = "font-weight: bold;" if override_color else ""
        return f"""
            font-family: monospace;
            font-size: {sizes['font_small']}px;
            color: {color};
            background-color: transparent;
            {weight}
        """

    def refresh_view(self):
        data, t_from, t_to = self.get_filtered_data()
        show_min = self.show_min.isChecked()
        show_max = self.show_max.isChecked()
        live     = not self.time_to.text().strip()
        main_enabled = self.main.get_enabled_channels()

        if live:
            main_data = self.main.data
            now = main_data[-1, 0] if len(main_data) > 0 else 0.0
            hold_durations = self.main.buffer.hold_duration(now)
            hold_threshold = self.main.settings.get('hold_warning_seconds', 30.0)
            hold_message = self.main.settings.get('hold_warning_message') or 'Out of Filter Range'

        for i in range(self.main.max_channels):
            enabled = i in main_enabled
            visible = i in self.visible_channels

            c = self.main.get_channel_color(i)
            limit = (self.main.channel_limits[i] if i < len(self.main.channel_limits)
                      else {'min': None, 'max': None})
            _apply_limit_lines(self.view_limit_min_lines[i], self.view_limit_max_lines[i],
                                limit, c, enabled and visible, show_min, show_max)

            if enabled and visible and len(data) > 0:
                col_idx = i + 1
                if col_idx < data.shape[1]:
                    t_data   = data[:, 0]
                    tmp_data = data[:, col_idx]
                    valid    = tmp_data != 0
                    if valid.any():
                        c = self.main.get_channel_color(i)
                        self.view_plots[i].setData(
                            t_data[valid], tmp_data[valid],
                            pen=pg.mkPen(color=(c.red(), c.green(), c.blue()),
                                         width=1))

                        raw_recently_silent = False
                        if live:
                            main_raw_col = (main_data[:, col_idx]
                                            if col_idx < main_data.shape[1] else np.array([]))
                            has_any_raw = (main_raw_col != 0).any()
                            last_raw = main_raw_col[-30:] if len(main_raw_col) >= 30 else main_raw_col
                            raw_recently_silent = has_any_raw and not (last_raw != 0).any()

                        if raw_recently_silent:
                            self.view_temp_labels[i].setStyleSheet(self._view_temp_label_style('#F44336'))
                            self.view_temp_labels[i].setText("invalid")
                        elif live and hold_durations[i] > hold_threshold:
                            self.view_temp_labels[i].setStyleSheet(self._view_temp_label_style('#FFA726'))
                            self.view_temp_labels[i].setText(hold_message)
                        else:
                            self.view_temp_labels[i].setStyleSheet(self._view_temp_label_style())
                            self.view_temp_labels[i].setText(
                                f"{tmp_data[valid][-1]:.2f} °C")

                        if show_min:
                            mn = tmp_data[valid].min()
                            mn_t = elapsed_to_clock(
                                t_data[valid][tmp_data[valid].argmin()])
                            self.view_min_labels[i].setText(f"↓ {mn:.2f} @ {mn_t}")
                        else:
                            self.view_min_labels[i].setText("")

                        if show_max:
                            mx = tmp_data[valid].max()
                            mx_t = elapsed_to_clock(
                                t_data[valid][tmp_data[valid].argmax()])
                            self.view_max_labels[i].setText(f"↑ {mx:.2f} @ {mx_t}")
                        else:
                            self.view_max_labels[i].setText("")
                        continue

            self.view_plots[i].setData([], [])
            self.view_temp_labels[i].setStyleSheet(self._view_temp_label_style())
            self.view_temp_labels[i].setText("---")
            self.view_min_labels[i].setText("")
            self.view_max_labels[i].setText("")

        try:
            self.plot.setYRange(float(self.y_min.text()),
                                float(self.y_max.text()))
        except ValueError:
            self.plot.enableAutoRange(axis='y')

        if live and len(data) > 0:
            self.plot.enableAutoRange(axis='x')
        elif not live and t_from is not None and t_to is not None:
            self.plot.setXRange(t_from, t_to)

    def _get_view_channel_stats(self):
        """Channel stats scoped to THIS view's own time range and visible-
        channel selection, instead of the main window's."""
        data, _, _ = self.get_filtered_data()
        if len(data) == 0:
            return []
        main_enabled = self.main.get_enabled_channels()
        channels = [i for i in main_enabled if i in self.visible_channels]
        stats = []
        for i in channels:
            col_idx = i + 1
            if col_idx >= data.shape[1]:
                continue
            t_data = data[:, 0]
            tmp_data = data[:, col_idx]
            valid = tmp_data != 0
            if not valid.any():
                continue
            name = self.main.channel_name_edits[i].text().strip() or f"Ch {i+1}"
            c = self.main.get_channel_color(i)
            vals = tmp_data[valid]
            times = t_data[valid]
            stats.append({
                'channel':  i + 1,
                'name':     name,
                'color':    (c.red(), c.green(), c.blue()),
                'current':  vals[-1],
                'min':      vals.min(),
                'max':      vals.max(),
                'time_min': elapsed_to_clock(times[vals.argmin()]),
                'time_max': elapsed_to_clock(times[vals.argmax()]),
            })
        return stats

    def export_graph_with_stats(self):
        stats = self._get_view_channel_stats()
        if not stats:
            QMessageBox.warning(self, "Warning", "No enabled+visible channels with data in this view's range!")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Graph + Stats", os.path.expanduser('~'),
            "PNG Images (*.png)")
        if not path:
            return
        if not path.endswith('.png'):
            path += '.png'
        self.main._build_and_save_export_image(
            self.graph, stats, path,
            show_min=self.show_min.isChecked(),
            show_max=self.show_max.isChecked()
        )

    def take_screenshot(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_name = f"view_screenshot_{timestamp}.png"
        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot",
            os.path.join(os.path.expanduser('~'), default_name),
            "PNG Images (*.png);;JPEG Images (*.jpg);;All Files (*)")
        if not path:
            return
        if not path.lower().endswith(('.png', '.jpg', '.jpeg')):
            path += '.png'

        pixmap = self.grab()
        if not pixmap:
            QMessageBox.warning(self, "Error", "Could not capture screenshot.")
            return
        try:
            pixmap.save(path)
            self.main.status_bar.showMessage(
                f"View screenshot saved to {os.path.basename(path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Error",
                                f"Could not save screenshot: {e}")

    def snapshot_settings(self):
        return {
            'font_size': self.view_settings['font_size'],
            'channel_font_size': self.view_settings['channel_font_size'],
            'channel_grid_columns': self.view_settings['channel_grid_columns'],
            'visible_channels': sorted(self.visible_channels),
            'time_from': self.time_from.text(),
            'time_to': self.time_to.text(),
            'y_min': self.y_min.text(),
            'y_max': self.y_max.text(),
            'show_min': self.show_min.isChecked(),
            'show_max': self.show_max.isChecked(),
        }

    def apply_persisted_state(self, settings):
        self.time_from.blockSignals(True)
        self.time_to.blockSignals(True)
        self.y_min.blockSignals(True)
        self.y_max.blockSignals(True)
        self.show_min.blockSignals(True)
        self.show_max.blockSignals(True)

        self.time_from.setText(settings.get('time_from', ''))
        self.time_to.setText(settings.get('time_to', ''))
        self.y_min.setText(settings.get('y_min', ''))
        self.y_max.setText(settings.get('y_max', ''))
        self.show_min.setChecked(settings.get('show_min', False))
        self.show_max.setChecked(settings.get('show_max', False))

        self.time_from.blockSignals(False)
        self.time_to.blockSignals(False)
        self.y_min.blockSignals(False)
        self.y_max.blockSignals(False)
        self.show_min.blockSignals(False)
        self.show_max.blockSignals(False)

        self.visible_channels = set(settings.get('visible_channels', range(self.main.max_channels)))

    def closeEvent(self, event):
        self.timer.stop()
        if self in self.main._view_windows:
            self.main._view_windows.remove(self)
        event.accept()


# ── Main window ───────────────────────────────────────────────────────────────

class TemperatureLogger(QMainWindow):
    def __init__(self):
        super().__init__()

        self.settings = load_settings()
        self.apply_settings(self.settings, init=True)
        self.max_channels = self.settings['max_channels']

        self.setWindowTitle("Temperature Logger")
        self.setGeometry(100, 100, 1600, 900)

        self.instrument   = None
        self.retry_thread = None
        self.buffer = SessionBuffer(
            self.max_channels,
            self.settings['filter_max_roc'],
            self.settings['filter_min_run'],
            self.settings['filter_range_min'],
            self.settings['filter_range_max'],
        )
        self.capturing    = False
        self.start_time   = 0
        self.measurement_thread = None

        self.session_markers = []
        self.pause_elapsed   = 0.0

        # Session log
        self.session_writer = None      # SessionWriter or None
        self.session_channels = None    # locked channel set for this session
        self.session_path = None

        self.channel_colors       = []
        self.channel_temp_labels  = []
        self.channel_min_labels   = []
        self.channel_max_labels   = []
        self.channel_name_edits   = []
        self.plots                = []
        self.channel_cells        = []
        self.channel_checkboxes   = []
        self.extra_fields         = []
        self._view_windows        = []

        self.channel_limits = load_channel_limits(self.max_channels)
        self.limit_min_lines = []
        self.limit_max_lines = []

        self.channel_addresses = load_channel_addresses(
            self.max_channels,
            self.settings['channels_per_cassette'],
            self.settings['channel_address_offset'],
        )

        self._last_ui_font      = None
        self._last_channel_font = None
        self._last_timer_font   = None
        self._last_dark_mode    = None
        self._old_columns = None

        self.left_panel_widgets = {
            'buttons': [],
            'line_edits': [],
            'spin_boxes': [],
            'double_spin_boxes': [],
            'date_edits': [],
            'checkboxes': [],
            'labels': [],
        }

        self._pending_graph_update = False
        self._suppress_dirty = False

        self.init_ui()

        self._apply_lab_metadata(load_lab_metadata(self.max_channels))
        self.update_plots()

        self.show_connection_dialog()

        self.timer = QTimer()
        self.timer.timeout.connect(self.update_loop)
        self.timer.start(100)

        self._config_dirty = False
        self._config_write_timer = QTimer()
        self._config_write_timer.setSingleShot(True)
        self._config_write_timer.timeout.connect(self._flush_config)

    # ── Settings ──────────────────────────────────────────────────────────────

    def apply_settings(self, settings, init=False):
        self.settings = settings

        theme_changed = (getattr(self, '_last_dark_mode', None) != settings['dark_mode'])

        sizes = get_sizes(settings) if not init else None
        ui_font_changed = (not init) and (self._last_ui_font != sizes['ui_font'])

        # Only touch app-wide chrome when the UI font or theme changed.
        # A channel-font-only change must not disturb the left panel.
        if init or theme_changed or ui_font_changed:
            if settings['dark_mode']:
                self._apply_dark_mode()
            else:
                self._apply_light_mode()
            font = QFont(settings['font_family'], settings['font_size'])
            QApplication.instance().setFont(font)

        if hasattr(self, 'sample_rate'):
            self.sample_rate.blockSignals(True)
            self.sample_rate.setValue(settings['sample_rate'])
            self.sample_rate.blockSignals(False)
            if self.measurement_thread and self.measurement_thread.isRunning():
                self.measurement_thread.sample_rate = settings['sample_rate']

        self.filter_max_roc = settings['filter_max_roc']
        self.filter_min_run = settings['filter_min_run']
        self.filter_range_min = settings['filter_range_min']
        self.filter_range_max = settings['filter_range_max']

        if hasattr(self, 'buffer'):
            new_params = (settings['filter_max_roc'], settings['filter_min_run'],
                          settings['filter_range_min'], settings['filter_range_max'])
            if self.buffer.filter_params_changed(*new_params):
                if len(self.buffer) > 5000 and hasattr(self, 'status_bar'):
                    self.status_bar.showMessage("Re-applying filter to session history...")
                    QApplication.processEvents()
                self.buffer.set_filter_params(*new_params)
                if getattr(self, 'channel_checkboxes', None):
                    self.update_plots()

        if not init and hasattr(self, 'channel_layout') and hasattr(self, 'left_panel_widgets'):
            sizes = get_sizes(settings)

            ui_font_changed      = (self._last_ui_font      != sizes['ui_font'])
            channel_font_changed = (self._last_channel_font != sizes['channel_font'])
            columns_changed      = (self._old_columns       != sizes['columns'])

            if ui_font_changed or theme_changed:
                self._update_left_panel()
                self._last_ui_font = sizes['ui_font']

            if columns_changed:
                self._rebuild_channel_panel()
                self._old_columns = sizes['columns']
                self._last_channel_font = sizes['channel_font']
            elif channel_font_changed or theme_changed:
                self._update_channel_styles()
                self._last_channel_font = sizes['channel_font']

            if self._last_timer_font != sizes['ui_timer'] or theme_changed:
                timer_font = sizes['ui_timer']
                color = '#e0e0e0' if settings['dark_mode'] else '#000000'
                self.timer_display.setStyleSheet(
                    f"font-family: monospace; font-size: {timer_font}px; "
                    f"font-weight: bold; color: {color};"
                )
                self._last_timer_font = sizes['ui_timer']

            if hasattr(self, '_view_windows'):
                self.update_view_windows_colors()

        self._last_dark_mode = settings['dark_mode']

        QTimer.singleShot(0, self._finalize_layout)

    def _finalize_layout(self):
        cw = self.centralWidget()
        if cw is None:
            return
        for w in cw.findChildren(QWidget):
            w.updateGeometry()
        cw.updateGeometry()
        cw.adjustSize()
        self.updateGeometry()
        self.update()

    def _update_left_panel(self):
        if not hasattr(self, 'left_panel_widgets'):
            return

        sizes = get_sizes(self.settings)
        ui_font = sizes['ui_font']

        for btn in self.left_panel_widgets['buttons']:
            btn.setStyleSheet(f"font-size: {ui_font}px;")
        for edit in self.left_panel_widgets['line_edits']:
            edit.setStyleSheet(f"font-size: {ui_font}px;")
        for spin in self.left_panel_widgets['spin_boxes']:
            spin.setStyleSheet(f"font-size: {ui_font}px;")
        for dspin in self.left_panel_widgets['double_spin_boxes']:
            dspin.setStyleSheet(f"font-size: {ui_font}px;")
        for date_edit in self.left_panel_widgets['date_edits']:
            date_edit.setStyleSheet(f"font-size: {ui_font}px;")
        for cb in self.left_panel_widgets['checkboxes']:
            cb.setStyleSheet(f"font-size: {ui_font}px;")

    def _update_channel_styles(self):
        sizes = get_sizes(self.settings)
        dark_mode = self.settings['dark_mode']
        text_color = "#e0e0e0" if dark_mode else "#000000"
        bg_color = "#2a2a2a" if dark_mode else "#ffffff"
        cell_bg = "#2d2d2d" if dark_mode else "#f0f0f0"
        border_color = "#444444" if dark_mode else "#cccccc"
        placeholder_color = "#666666" if dark_mode else "#999999"

        channel_font = sizes['channel_font']
        font_small = sizes['font_small']

        # Cells
        for cell in self.channel_cells:
            cell.setStyleSheet(f"background-color: {cell_bg}; border: none;")
            cell.setFixedHeight(sizes['row_height'])
            if cell.layout() is not None:
                cell.layout().setSpacing(sizes['spacing'])
            if dark_mode:
                cell.setAutoFillBackground(True)
                pal = cell.palette()
                pal.setColor(cell.backgroundRole(), QColor(45, 45, 45))
                cell.setPalette(pal)

        for btn in self.channel_colors:
            btn.setFixedSize(sizes['color_dot_size'] + 6, sizes['color_dot_size'] + 6)

        # Checkboxes
        for cb in self.channel_checkboxes:
            cb.setFixedWidth(sizes['channel_number_width'])
            cb.setStyleSheet(f"""
                QCheckBox {{
                    font-size: {channel_font}px;
                    font-weight: bold;
                    color: {text_color};
                    background-color: transparent;
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
                QCheckBox::indicator:checked {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
            """)

        # Name edits
        for edit in self.channel_name_edits:
            if edit:
                edit.setStyleSheet(f"""
                    QLineEdit {{
                        font-size: {channel_font}px;
                        background-color: {bg_color};
                        color: {text_color};
                        border: 1px solid {border_color};
                        border-radius: 2px;
                        padding: 2px 4px;
                    }}
                    QLineEdit:focus {{
                        border: 1px solid #4a9eff;
                    }}
                    QLineEdit::placeholder {{
                        color: {placeholder_color};
                    }}
                """)

        # Value labels
        for lbl in self.channel_temp_labels:
            if lbl:
                lbl.setFixedWidth(sizes['temp_width'])
                lbl.setStyleSheet(f"""
                    font-family: monospace;
                    font-size: {font_small}px;
                    color: {text_color};
                    background-color: transparent;
                """)

    def _apply_dark_mode(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(35, 35, 35))
        palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
        palette.setColor(QPalette.Base, QColor(25, 25, 25))
        palette.setColor(QPalette.AlternateBase, QColor(45, 45, 45))
        palette.setColor(QPalette.Text, QColor(220, 220, 220))
        palette.setColor(QPalette.Button, QColor(50, 50, 50))
        palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
        palette.setColor(QPalette.Highlight, QColor(70, 130, 180))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipBase, QColor(50, 50, 50))
        palette.setColor(QPalette.ToolTipText, QColor(220, 220, 220))
        QApplication.instance().setPalette(palette)

        QApplication.instance().setStyleSheet(
            _build_app_stylesheet(DARK_PALETTE, self.settings)
        )

        if hasattr(self, 'graph'):
            self.graph.setBackground("#2d2d2d")
        if hasattr(self, 'plot'):
            self.plot.getViewBox().setBackgroundColor("#2d2d2d")
            self.plot.getAxis('bottom').setPen('w')
            self.plot.getAxis('left').setPen('w')
            self.plot.getAxis('bottom').setTextPen('w')
            self.plot.getAxis('left').setTextPen('w')
            self.plot.setLabel('bottom', "Time", color='w')
            self.plot.setLabel('left', 'Temperature [°C]', color='w')
            self.plot.showGrid(x=1, y=1, alpha=0.15)
            self.plot.update()

    def _apply_light_mode(self):
        palette = QPalette()
        palette.setColor(QPalette.Window, QColor(240, 240, 240))
        palette.setColor(QPalette.WindowText, QColor(0, 0, 0))
        palette.setColor(QPalette.Base, QColor(255, 255, 255))
        palette.setColor(QPalette.AlternateBase, QColor(245, 245, 245))
        palette.setColor(QPalette.Text, QColor(0, 0, 0))
        palette.setColor(QPalette.Button, QColor(240, 240, 240))
        palette.setColor(QPalette.ButtonText, QColor(0, 0, 0))
        palette.setColor(QPalette.Highlight, QColor(70, 130, 180))
        palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
        palette.setColor(QPalette.ToolTipText, QColor(0, 0, 0))
        QApplication.instance().setPalette(palette)

        QApplication.instance().setStyleSheet(
            _build_app_stylesheet(LIGHT_PALETTE, self.settings)
        )

        if hasattr(self, 'graph'):
            self.graph.setBackground('w')
        if hasattr(self, 'plot'):
            self.plot.getViewBox().setBackgroundColor('w')
            self.plot.getAxis('bottom').setPen('k')
            self.plot.getAxis('left').setPen('k')
            self.plot.getAxis('bottom').setTextPen('k')
            self.plot.getAxis('left').setTextPen('k')
            self.plot.setLabel('bottom', "Time", color='k')
            self.plot.setLabel('left', 'Temperature [°C]', color='k')
            self.plot.showGrid(x=1, y=1, alpha=0.15)
            self.plot.update()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec_()

    def open_file_operations(self):
        dlg = FileOperationsDialog(self)
        dlg.exec_()

    def open_limits_dialog(self, focus_channel=None, focus_field=None):
        dlg = LimitsDialog(self, focus_channel=focus_channel, focus_field=focus_field)
        dlg.exec_()

    def _on_limit_label_clicked(self, channel_idx, field):
        if field == 'min' and not self.show_min.isChecked():
            return
        if field == 'max' and not self.show_max.isChecked():
            return
        self.open_limits_dialog(focus_channel=channel_idx, focus_field=field)

    # ── View windows ──────────────────────────────────────────────────────────

    def update_view_windows(self):
        for view in self._view_windows:
            view.update_name_labels()

    def update_view_windows_colors(self):
        for view in self._view_windows:
            view.update_colors()

    def open_view_window(self):
        dlg = ViewPickerDialog(self)
        if dlg.exec_() != QDialog.Accepted or not dlg.selected_view_id:
            return

        view_id = dlg.selected_view_id

        for w in self._view_windows:
            if w.view_id == view_id:
                w.raise_()
                w.activateWindow()
                return

        if dlg.is_new:
            save_view_settings(view_id, dict(DEFAULT_VIEW_SETTINGS))

        w = ViewWindow(self, view_id=view_id)
        self._view_windows.append(w)
        w.show()

    # ── Config and metadata ───────────────────────────────────────────────────

    def _mark_config_dirty(self):
        if getattr(self, '_suppress_dirty', False):
            return
        self._config_dirty = True
        self._config_write_timer.start(500)

    def _flush_config(self):
        if not self._config_dirty:
            return
        self._config_dirty = False
        self.lab_metadata = self._build_lab_metadata()
        save_settings(self.settings)
        save_lab_metadata(self.lab_metadata)

        # If a session is in progress, re-emit META so the log reflects
        # any name/metadata changes at the moment they happened.
        if self.session_writer is not None:
            self.session_writer.write_meta(self._build_session_meta())

    def _build_lab_metadata(self):
        return {
            'serial_number':   self.s_number.text(),
            'customer_number': self.c_number.text(),
            'channel_names':   [e.text() for e in self.channel_name_edits],
            'channels_checked': [i for i, cb in enumerate(self.channel_checkboxes) if cb.isChecked()],
            'extra_fields':    [{'name': f[0].text(), 'value': f[1].text()}
                                for f in self.extra_fields],
        }

    def _build_session_meta(self):
        """Build the dict used to write a META line to the session log."""
        md = self._build_lab_metadata()
        enabled = md['channels_checked']
        elapsed = self.pause_elapsed
        if self.capturing:
            elapsed = time.monotonic() - self._session_start_monotonic

        return {
            'wall_clock': datetime.now().isoformat(timespec='seconds'),
            'elapsed': elapsed,
            'sample_rate': self.settings['sample_rate'],
            'channels': list(enabled),
            'names': [md['channel_names'][i] for i in enabled],
            'serial': md['serial_number'],
            'customer': md['customer_number'],
            'extra_fields': [(f['name'], f['value']) for f in md['extra_fields']],
        }

    def _apply_lab_metadata(self, md):
        self._suppress_dirty = True
        try:
            self.s_number.blockSignals(True)
            self.c_number.blockSignals(True)
            self.s_number.setText(md.get('serial_number', ''))
            self.c_number.setText(md.get('customer_number', ''))
            self.s_number.blockSignals(False)
            self.c_number.blockSignals(False)

            names = md.get('channel_names', [])
            for i, name in enumerate(names):
                if i < len(self.channel_name_edits):
                    self.channel_name_edits[i].setText(name)

            checked = set(md.get('channels_checked', range(self.max_channels)))
            for i, cb in enumerate(self.channel_checkboxes):
                cb.blockSignals(True)
                cb.setChecked(i in checked)
                cb.blockSignals(False)

            for entry in self.extra_fields[:]:
                self.remove_extra_field(entry)
            for field in md.get('extra_fields', []):
                self.add_extra_field(field.get('name', ''), field.get('value', ''))
        finally:
            self._suppress_dirty = False

    def _mark_dirty_if_changed(self, *_args):
        self._mark_config_dirty()

    # ── Screenshot ────────────────────────────────────────────────────────────

    def take_screenshot(self):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        default_name = f"screenshot_{timestamp}.png"

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Screenshot",
            os.path.join(os.path.expanduser('~'), default_name),
            "PNG Images (*.png);;JPEG Images (*.jpg);;All Files (*)")
        if not path:
            return

        if not path.lower().endswith(('.png', '.jpg', '.jpeg')):
            path += '.png'

        pixmap = self.grab()
        if not pixmap:
            QMessageBox.warning(self, "Error", "Could not capture screenshot.")
            return

        try:
            pixmap.save(path)
            self.status_bar.showMessage(f"Screenshot saved to {os.path.basename(path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not save screenshot: {e}")

    # ── Import session ────────────────────────────────────────────────────────

    def import_session(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import Session", str(SESSIONS_DIR),
            "Session Logs (*.log);;All Files (*)")
        if not path:
            return

        try:
            session = read_session(path)
        except OSError as e:
            QMessageBox.warning(self, "Error", f"Could not read file: {e}")
            return

        if not session['verified']:
            QMessageBox.warning(
                self, "Integrity Warning",
                f"{len(session['bad_lines'])} line(s) failed their hash check. "
                "The file may have been truncated or tampered with. "
                "Importing anyway — unverified rows will still be loaded.")
        if not session['records']:
            QMessageBox.warning(self, "Error", "File is empty or has no records.")
            return

        data_rows = []
        imported_markers = []

        for rec in session['records']:
            if rec[0] == 'DATA':
                _, elapsed, ch_list, raw = rec
                new_row = np.zeros(self.max_channels + 1)
                new_row[0] = elapsed
                vals = parse_raw_response(raw, ch_list)
                for ch, v in vals.items():
                    if ch < self.max_channels:
                        new_row[ch + 1] = v
                data_rows.append(new_row)
            elif rec[0] == 'EVENT':
                _, elapsed, label = rec
                imported_markers.append((elapsed, label))

        if not data_rows:
            QMessageBox.warning(self, "Error", "No valid data rows found in file.")
            return

        imported_array = np.array(data_rows)

        if len(self.data) > 0:
            current_end = self.data[-1, 0]
            import_start = imported_array[0, 0]
            offset = current_end - import_start + 1.0
            imported_array[:, 0] += offset
            imported_markers = [(t + offset, lbl) for t, lbl in imported_markers]

        self.buffer.append_rows(imported_array)

        self.pause_elapsed = self.data[-1, 0]

        join_elapsed = imported_array[0, 0]
        self.session_markers.extend(imported_markers)
        self.session_markers.append((join_elapsed, 'SESSION_IMPORTED'))

        # If the imported log had a channel set, enable those channels so
        # the user sees them in the current UI.
        for ch in session['channels']:
            if 0 <= ch < self.max_channels:
                cb = self.channel_checkboxes[ch]
                cb.blockSignals(True)
                cb.setChecked(True)
                cb.blockSignals(False)

        self.update_plots()

        self.status_bar.showMessage(
            f"Session imported from {os.path.basename(path)} — "
            f"{len(data_rows)} rows loaded "
            f"({'verified' if session['verified'] else 'UNVERIFIED'}).",
            6000)

    # ── Connection ────────────────────────────────────────────────────────────

    def show_connection_dialog(self):
        already_connected = self.instrument is not None

        if already_connected and self.capturing:
            reply = QMessageBox.question(
                self, "Reconnect",
                "Recording is currently in progress on the existing "
                "connection.\n\nOpening a new connection will stop the "
                "current recording and reset the instrument. Continue?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply != QMessageBox.Yes:
                return

        dlg = ConnectionDialog(self)
        if dlg.exec_() == QDialog.Accepted and dlg.instrument:
            if self.capturing:
                self.stop_capture()
            if self.instrument is not None and self.instrument is not dlg.instrument:
                try:
                    self.instrument.close()
                except visa.VisaIOError:
                    pass

            self.instrument = dlg.instrument
            self.status_bar.showMessage("Resetting instrument...")
            try:
                self.instrument.write('*RST')
                time.sleep(2)
            except (visa.VisaIOError, OSError) as e:
                QMessageBox.warning(self, "Warning", f"Instrument reset failed: {e}")
            self.update_connection_status(True)
        elif not already_connected:
            self.update_connection_status(False)
            ip = dlg.ip_combo.currentText().strip() or None
            self.start_retry(ip)
        # else: dialog cancelled while already connected -- leave the
        # existing connection alone.

    def start_retry(self, ip):
        if self.retry_thread:
            self.retry_thread.stop()
            self.retry_thread.wait(1500)
            try:
                self.retry_thread.connected.disconnect(self.on_reconnected)
            except TypeError:
                pass
        self.retry_thread = RetryThread(ip)
        self.retry_thread.connected.connect(self.on_reconnected)
        self.retry_thread.start()

    def on_reconnected(self, inst):
        if self.instrument is not None:
            return
        self.instrument = inst
        self.update_connection_status(True)
        QMessageBox.information(self, "Connected", "Instrument connected!")

    def update_connection_status(self, connected):
        if connected:
            self.setWindowTitle("Temperature Logger - Connected")
            self.status_bar.showMessage("Instrument connected")
        else:
            self.setWindowTitle("Temperature Logger - Offline Mode (retrying...)")
            self.status_bar.showMessage("No instrument - offline mode, retrying...")

    # ── Extra metadata fields ─────────────────────────────────────────────────

    def add_extra_field(self, name='', value=''):
        sizes = get_sizes(self.settings)
        ui_font = sizes['ui_font']
        row_widget = QWidget()
        row_layout = QVBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(2)
        top = QHBoxLayout()
        name_edit = QLineEdit()
        name_edit.setPlaceholderText("Field name")
        name_edit.setText(name)
        name_edit.setStyleSheet(f"font-size: {ui_font}px;")
        top.addWidget(name_edit)
        remove_btn = QPushButton("✕")
        remove_btn.setFixedSize(max(20, int(ui_font * 1.8)), max(18, int(ui_font * 1.6)))
        remove_btn.setStyleSheet(f"font-size: {ui_font}px; padding: 0;")
        top.addWidget(remove_btn)
        row_layout.addLayout(top)
        value_edit = QLineEdit()
        value_edit.setPlaceholderText("Value")
        value_edit.setText(value)
        value_edit.setStyleSheet(f"font-size: {ui_font}px;")
        row_layout.addWidget(value_edit)

        entry = (name_edit, value_edit, remove_btn, row_widget)
        self.extra_fields.append(entry)
        self.extra_fields_layout.addWidget(row_widget)
        remove_btn.clicked.connect(lambda: self.remove_extra_field(entry))
        self._mark_config_dirty()

        name_edit.editingFinished.connect(
            lambda e=name_edit, orig=name: self._mark_dirty_if_changed(e.text(), orig))
        value_edit.editingFinished.connect(
            lambda e=value_edit, orig=value: self._mark_dirty_if_changed(e.text(), orig))

    def remove_extra_field(self, entry):
        _, _, _, widget = entry
        self.extra_fields.remove(entry)
        self.extra_fields_layout.removeWidget(widget)
        widget.deleteLater()
        self._mark_config_dirty()

    # ── Channel range + Y range ───────────────────────────────────────────────

    def apply_channel_range(self):
        start = self.ch_from.value() - 1
        end   = self.ch_to.value()
        if start >= end:
            QMessageBox.warning(self, "Invalid Range", "'From' channel must be less than 'To' channel")
            return
        for i, cb in enumerate(self.channel_checkboxes):
            cb.blockSignals(True)
            cb.setChecked(start <= i < end)
            cb.blockSignals(False)
        self.update_plots()
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.update_channels(self.get_enabled_channels())

    def apply_y_range(self):
        try:
            self.plot.setYRange(float(self.main_y_min.text()), float(self.main_y_max.text()))
        except ValueError:
            pass

    def autoscale_main(self):
        self.main_y_min.clear()
        self.main_y_max.clear()
        self.plot.enableAutoRange()

    # ── Clear session ─────────────────────────────────────────────────────────

    def clear_session(self):
        if len(self.data) > 0:
            reply = QMessageBox.question(
                self, "Clear Session",
                "This will clear all current data from the display.\n"
                "Saved session files in the sessions folder will NOT be deleted.\n\n"
                "Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply != QMessageBox.Yes:
                return

        if self.capturing:
            self.stop_capture()

        # Close any lingering writer without writing anything else
        self._close_session_writer()

        self.data = np.empty((0, self.max_channels + 1))
        self.session_markers = []
        self.pause_elapsed = 0.0
        self.start_time = 0
        self.session_path = None
        self.session_channels = None

        empty_md = _default_lab_metadata(self.max_channels)
        self._apply_lab_metadata(empty_md)
        save_lab_metadata(empty_md)

        self.ch_from.setValue(1)
        self.ch_to.setValue(self.max_channels)
        self.date_edit.setDate(QDate.currentDate())

        for plot in self.plots:
            plot.setData([], [])

        for i, cb in enumerate(self.channel_checkboxes):
            self.channel_temp_labels[i].setText("---")
            self.channel_min_labels[i].setText("")
            self.channel_max_labels[i].setText("")
            cb.setStyleSheet(self._channel_checkbox_stylesheet())

        self.timer_display.setText("00:00:00")
        self.status_bar.showMessage("Session cleared - ready to start new recording", 3000)
        self.update_plots()

    # ── UI ────────────────────────────────────────────────────────────────────

    def init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        self.status_bar = self.statusBar()

        sizes = get_sizes(self.settings)
        ui_font = sizes['ui_font']

        left_scroll = QScrollArea()
        left_scroll.setWidgetResizable(True)
        left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setSpacing(sizes['group_spacing'])
        left_layout.setContentsMargins(5, 5, 5, 5)

        left_layout.addWidget(QLabel("Elapsed Time:"))
        self.timer_display = QLabel("00:00:00")
        self.timer_display.setStyleSheet(f"font-family: monospace; font-size: {sizes['ui_timer']}px; font-weight: bold; color: {'#e0e0e0' if self.settings.get('dark_mode', False) else '#000000'};")
        self.timer_display.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(self.timer_display)

        left_layout.addWidget(QLabel("Project Number:"))
        self.s_number = QLineEdit()
        self.s_number.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['line_edits'].append(self.s_number)
        left_layout.addWidget(self.s_number)
        self.s_number.editingFinished.connect(self._mark_config_dirty)

        left_layout.addWidget(QLabel("Sample Number:"))
        self.c_number = QLineEdit()
        self.c_number.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['line_edits'].append(self.c_number)
        left_layout.addWidget(self.c_number)
        self.c_number.editingFinished.connect(self._mark_config_dirty)

        left_layout.addWidget(QLabel("Date:"))
        self.date_edit = QDateEdit()
        self.date_edit.setDateTime(QDateTime.currentDateTime())
        self.date_edit.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['date_edits'].append(self.date_edit)
        left_layout.addWidget(self.date_edit)

        extra_header = QHBoxLayout()
        extra_header.addWidget(QLabel("Extra Fields:"))
        add_btn = QPushButton("+")
        add_btn.setFixedSize(max(24, int(ui_font * 2)), max(20, int(ui_font * 1.8)))
        add_btn.clicked.connect(lambda: self.add_extra_field())
        self.left_panel_widgets['buttons'].append(add_btn)
        extra_header.addWidget(add_btn)
        left_layout.addLayout(extra_header)

        self.extra_fields_layout = QVBoxLayout()
        self.extra_fields_layout.setSpacing(4)
        left_layout.addLayout(self.extra_fields_layout)

        left_layout.addWidget(QLabel("Sample Rate (s):"))
        self.sample_rate = QDoubleSpinBox()
        self.sample_rate.setRange(0.01, 1000.0)
        self.sample_rate.setSingleStep(0.5)
        self.sample_rate.setValue(self.settings.get('sample_rate', 2.0))
        self.sample_rate.setStyleSheet(f"font-size: {ui_font}px;")
        self.sample_rate.valueChanged.connect(self._on_sample_rate_changed)
        self.left_panel_widgets['double_spin_boxes'].append(self.sample_rate)
        left_layout.addWidget(self.sample_rate)

        left_layout.addWidget(QLabel("Active Channels:"))
        rl = QHBoxLayout()
        self.ch_from = QSpinBox()
        self.ch_from.setMinimum(1)
        self.ch_from.setMaximum(self.max_channels)
        self.ch_from.setValue(1)
        self.ch_from.setPrefix("Ch ")
        self.ch_from.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['spin_boxes'].append(self.ch_from)
        rl.addWidget(self.ch_from)
        rl.addWidget(QLabel("to"))
        self.ch_to = QSpinBox()
        self.ch_to.setMinimum(1)
        self.ch_to.setMaximum(self.max_channels)
        self.ch_to.setValue(self.max_channels)
        self.ch_to.setPrefix("Ch ")
        self.ch_to.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['spin_boxes'].append(self.ch_to)
        rl.addWidget(self.ch_to)
        left_layout.addLayout(rl)
        arb = QPushButton("Apply Range")
        arb.setStyleSheet(f"font-size: {ui_font}px;")
        arb.clicked.connect(self.apply_channel_range)
        self.left_panel_widgets['buttons'].append(arb)
        left_layout.addWidget(arb)

        left_layout.addWidget(QLabel("Y Axis (°C):"))
        yrl = QHBoxLayout()
        self.main_y_min = QLineEdit()
        self.main_y_min.setPlaceholderText("min")
        self.main_y_min.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['line_edits'].append(self.main_y_min)
        yrl.addWidget(self.main_y_min)
        yrl.addWidget(QLabel("–"))
        self.main_y_max = QLineEdit()
        self.main_y_max.setPlaceholderText("max")
        self.main_y_max.setStyleSheet(f"font-size: {ui_font}px;")
        self.left_panel_widgets['line_edits'].append(self.main_y_max)
        yrl.addWidget(self.main_y_max)
        left_layout.addLayout(yrl)
        ybl = QHBoxLayout()
        ayb = QPushButton("Apply")
        ayb.setStyleSheet(f"font-size: {ui_font}px;")
        ayb.clicked.connect(self.apply_y_range)
        self.left_panel_widgets['buttons'].append(ayb)
        ybl.addWidget(ayb)
        asb = QPushButton("Auto")
        asb.setStyleSheet(f"font-size: {ui_font}px;")
        asb.clicked.connect(self.autoscale_main)
        self.left_panel_widgets['buttons'].append(asb)
        ybl.addWidget(asb)
        left_layout.addLayout(ybl)

        minmax_row = QHBoxLayout()
        self.show_min = QCheckBox("Show Min")
        self.show_min.setStyleSheet(f"font-size: {ui_font}px;")
        self.show_min.stateChanged.connect(self.update_plots)
        self.left_panel_widgets['checkboxes'].append(self.show_min)
        minmax_row.addWidget(self.show_min)

        self.show_max = QCheckBox("Show Max")
        self.show_max.setStyleSheet(f"font-size: {ui_font}px;")
        self.show_max.stateChanged.connect(self.update_plots)
        self.left_panel_widgets['checkboxes'].append(self.show_max)
        minmax_row.addWidget(self.show_max)

        limits_btn = QPushButton("Add Limits")
        limits_btn.setStyleSheet(f"font-size: {ui_font}px;")
        limits_btn.clicked.connect(lambda: self.open_limits_dialog())
        self.left_panel_widgets['buttons'].append(limits_btn)
        minmax_row.addWidget(limits_btn)
        left_layout.addLayout(minmax_row)

        left_layout.addSpacing(4)

        settings_btn = QPushButton("⚙ Settings")
        settings_btn.setStyleSheet(f"font-size: {ui_font}px;")
        settings_btn.clicked.connect(self.open_settings)
        self.left_panel_widgets['buttons'].append(settings_btn)
        left_layout.addWidget(settings_btn)

        for label, slot in [
            ("Open View Window", self.open_view_window),
            ("Reconnect",        self.show_connection_dialog),
            ("File Operations",  self.open_file_operations),
            ("Start",            self.start_capture),
            ("Stop",             self.stop_capture),
            ("Clear Session",    self.clear_session),
            ("Screenshot",       self.take_screenshot),
            ("Quit",             self.close),
        ]:
            btn = QPushButton(label)
            btn.setStyleSheet(f"font-size: {ui_font}px;")
            btn.clicked.connect(slot)
            self.left_panel_widgets['buttons'].append(btn)
            left_layout.addWidget(btn)

        left_layout.addStretch()
        left_scroll.setWidget(left_panel)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        self.graph = pg.GraphicsLayoutWidget()
        bg_color = '#2d2d2d' if self.settings.get('dark_mode', False) else 'w'
        self.graph.setBackground(bg_color)
        self.plot = self.graph.addPlot(axisItems={'bottom': ClockAxis(orientation='bottom')})
        self.plot.showGrid(x=1, y=1, alpha=0.2)
        self.plot.setLabel('bottom', "Time")
        self.plot.setLabel('left', 'Temperature [°C]')
        self.plot.setMenuEnabled(True)
        self.plot.getViewBox().setMouseMode(pg.ViewBox.RectMode)

        self.plot.getViewBox().setBackgroundColor(bg_color)
        if self.settings.get('dark_mode', False):
            self.plot.getAxis('bottom').setPen('w')
            self.plot.getAxis('left').setPen('w')
            self.plot.getAxis('bottom').setTextPen('w')
            self.plot.getAxis('left').setTextPen('w')

        right_layout.addWidget(self.graph, stretch=0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.ch_widget = QWidget()
        self.channel_layout = QGridLayout(self.ch_widget)
        self.channel_layout.setSpacing(4)
        scroll.setWidget(self.ch_widget)
        right_layout.addWidget(scroll, stretch=0)

        main_layout.addWidget(left_scroll, stretch=2)
        main_layout.addWidget(right_panel, stretch=8)

        self._build_plots()
        self._rebuild_channel_panel()

    def _build_plots(self):
        for _ in range(self.max_channels):
            self.plots.append(self.plot.plot([], []))
            min_line = pg.InfiniteLine(angle=0, movable=False)
            min_line.setVisible(False)
            self.plot.addItem(min_line)
            self.limit_min_lines.append(min_line)
            max_line = pg.InfiniteLine(angle=0, movable=False)
            max_line.setVisible(False)
            self.plot.addItem(max_line)
            self.limit_max_lines.append(max_line)

    def _rebuild_channel_panel(self):
        current_names = [edit.text() for edit in self.channel_name_edits] if hasattr(self, 'channel_name_edits') else [""] * self.max_channels

        current_colors = []
        for color_btn in self.channel_colors:
            if hasattr(color_btn, '_color'):
                current_colors.append(color_btn._color)
            else:
                current_colors.append(None)

        current_active = []
        if hasattr(self, 'get_enabled_channels'):
            try:
                current_active = self.get_enabled_channels()
            except AttributeError:
                current_active = list(range(self.max_channels))
        else:
            current_active = list(range(self.max_channels))

        while self.channel_layout.count():
            item = self.channel_layout.takeAt(0)
            w = item.widget()
            if w:
                w.hide()
                w.deleteLater()

        self.channel_colors.clear()
        self.channel_temp_labels.clear()
        self.channel_min_labels.clear()
        self.channel_max_labels.clear()
        self.channel_name_edits.clear()
        self.channel_cells.clear()
        self.channel_checkboxes.clear()

        sizes = get_sizes(self.settings)
        columns = sizes['columns']
        row_height = sizes['row_height']
        font_small = sizes['font_small']
        channel_font = sizes['channel_font']

        dark_mode = self.settings.get('dark_mode', False)
        bg_color = "#2a2a2a" if dark_mode else "#ffffff"
        cell_bg = "#2d2d2d" if dark_mode else "#f0f0f0"
        text_color = "#e0e0e0" if dark_mode else "#000000"
        placeholder_color = "#666666" if dark_mode else "#999999"
        border_color = "#444444" if dark_mode else "#cccccc"
        btn_border = "#777777" if dark_mode else "#444444"
        btn_border_hover = "#aaaaaa" if dark_mode else "#666666"

        for col in range(columns):
            self.channel_layout.setColumnStretch(col, 0)

        num_channels = self.max_channels
        rows = (num_channels + columns - 1) // columns

        def create_color_button(initial_color=None):
            if initial_color is None:
                initial_color = QColor(
                    random.randint(50, 255),
                    random.randint(50, 255),
                    random.randint(50, 255)
                )

            btn = QPushButton()
            btn.setFixedSize(sizes['color_dot_size'] + 6, sizes['color_dot_size'] + 6)
            btn.setFlat(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: rgb({initial_color.red()}, {initial_color.green()}, {initial_color.blue()});
                    border: 2px solid {btn_border};
                    border-radius: 4px;
                }}
                QPushButton:hover {{
                    border: 2px solid {btn_border_hover};
                }}
            """)
            btn._color = initial_color

            def change_color():
                new_color = QColorDialog.getColor(btn._color, self, "Select Channel Color")
                if new_color.isValid():
                    btn._color = new_color
                    btn.setStyleSheet(f"""
                        QPushButton {{
                            background-color: rgb({new_color.red()}, {new_color.green()}, {new_color.blue()});
                            border: 2px solid {btn_border};
                            border-radius: 4px;
                        }}
                        QPushButton:hover {{
                            border: 2px solid {btn_border_hover};
                        }}
                    """)
                    self.update_plots()
                    self.update_view_windows()

            btn.clicked.connect(change_color)
            return btn

        for i in range(num_channels):
            row = i % rows
            col = i // rows

            cell = QWidget()
            cell.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            cell.setFixedHeight(row_height)
            cell.setStyleSheet(f"""
                background-color: {cell_bg};
                border: none;
            """)
            if dark_mode:
                cell.setAutoFillBackground(True)
                pal = cell.palette()
                pal.setColor(cell.backgroundRole(), QColor(45, 45, 45))
                cell.setPalette(pal)

            hb = QHBoxLayout(cell)
            hb.setContentsMargins(2, 1, 2, 1)
            hb.setSpacing(sizes['spacing'])

            cb = QCheckBox(f"{i+1}")
            cb.setFixedWidth(sizes['channel_number_width'])
            cb.setStyleSheet(f"""
                QCheckBox {{
                    font-size: {channel_font}px;
                    font-weight: bold;
                    color: {text_color};
                    background-color: transparent;
                    spacing: 6px;
                }}
                QCheckBox::indicator {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
                QCheckBox::indicator:checked {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
            """)
            if i in current_active:
                cb.setChecked(True)
            cb.stateChanged.connect(self.update_plots)
            cb.stateChanged.connect(self._mark_config_dirty)
            cb.stateChanged.connect(self._on_channel_toggled)
            hb.addWidget(cb)

            saved_color = current_colors[i] if i < len(current_colors) else None
            color = create_color_button(saved_color)
            self.channel_colors.append(color)
            hb.addWidget(color)

            value_lbl = QLabel("---")
            value_lbl.setFixedWidth(sizes['temp_width'])
            value_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            value_lbl.setStyleSheet(f"""
                font-family: monospace;
                font-size: {font_small}px;
                color: {text_color};
                background-color: transparent;
            """)
            self.channel_temp_labels.append(value_lbl)
            hb.addWidget(value_lbl)

            name_edit = QLineEdit()
            name_edit.setPlaceholderText("name")
            name_edit.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            name_edit.setStyleSheet(f"""
                QLineEdit {{
                    font-size: {channel_font}px;
                    background-color: {bg_color};
                    color: {text_color};
                    border: 1px solid {border_color};
                    border-radius: 2px;
                    padding: 2px 4px;
                }}
                QLineEdit:focus {{
                    border: 1px solid #4a9eff;
                }}
                QLineEdit::placeholder {{
                    color: {placeholder_color};
                }}
            """)
            if i < len(current_names):
                name_edit.setText(current_names[i])

            original_name = name_edit.text()

            def update_name_width(text, widget=name_edit):
                fm = widget.fontMetrics()
                text_width = fm.boundingRect(text + "  ").width() + 10
                widget.setMinimumWidth(text_width)

            name_edit.textChanged.connect(update_name_width)
            name_edit.textChanged.connect(lambda: self.update_view_windows())
            name_edit.editingFinished.connect(
                lambda e=name_edit, orig=original_name:
                    self._mark_dirty_if_changed(e.text(), orig))
            update_name_width(name_edit.text())

            self.channel_name_edits.append(name_edit)
            hb.addWidget(name_edit, stretch=0)

            mm_widget = QWidget()
            mm_widget.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            mm_widget.setStyleSheet("background-color: transparent;")
            mm_layout = QHBoxLayout(mm_widget)
            mm_layout.setContentsMargins(0, 0, 0, 0)
            mm_layout.setSpacing(sizes['spacing'])

            min_lbl = ClickableLabel("")
            min_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            min_lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #4fc3f7;
                font-size: {font_small}px;
                background-color: transparent;
            """)
            min_lbl.clicked.connect(lambda idx=i: self._on_limit_label_clicked(idx, 'min'))
            self.channel_min_labels.append(min_lbl)
            mm_layout.addWidget(min_lbl, stretch=0)

            max_lbl = ClickableLabel("")   
            max_lbl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            max_lbl.setStyleSheet(f"""
                font-family: monospace;
                color: #ef5350;
                font-size: {font_small}px;
                background-color: transparent;
            """)
            max_lbl.clicked.connect(lambda idx=i: self._on_limit_label_clicked(idx, 'max'))
            self.channel_max_labels.append(max_lbl)
            mm_layout.addWidget(max_lbl, stretch=0)

            hb.addWidget(mm_widget, stretch=0)

            self.channel_layout.addWidget(cell, row, col)
            self.channel_cells.append(cell)
            self.channel_checkboxes.append(cb)

        for row in range(rows):
            self.channel_layout.setRowStretch(row, 0)

        self.update_plots()

    # ── Capture ───────────────────────────────────────────────────────────────

    def _on_channel_toggled(self, *_args):
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.update_channels(self.get_enabled_channels())

    def _on_sample_rate_changed(self):
        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.sample_rate = self.sample_rate.value()
        self.settings['sample_rate'] = self.sample_rate.value()
        save_settings(self.settings)

    def get_enabled_channels(self):
        if not self.channel_checkboxes:
            return list(range(self.max_channels))
        return [i for i, cb in enumerate(self.channel_checkboxes) if cb.isChecked()]

    def _channel_checkbox_stylesheet(self):
        sizes = get_sizes(self.settings)
        dark_mode = self.settings['dark_mode']
        text_color = "#e0e0e0" if dark_mode else "#000000"
        channel_font = sizes['channel_font']
        return f"""
            QCheckBox {{
                font-size: {channel_font}px;
                font-weight: bold;
                color: {text_color};
                background-color: transparent;
                spacing: 6px;
            }}
                QCheckBox::indicator {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
            }}
                QCheckBox::indicator:checked {{
                    width: {int(channel_font * CHECKBOX_INDICATOR_WIDTH)}px;
                    height: {int(channel_font * CHECKBOX_INDICATOR_HEIGHT)}px;
                }}
        """

    def start_capture(self):
        enabled = self.get_enabled_channels()
        if not enabled:
            QMessageBox.warning(self, "Warning", "No channels enabled!")
            return

        if self.capturing:
            return
        
        is_resume = self.session_writer is not None

        if is_resume:
            # Continuing an existing session — same file, same channel set
            self._session_start_monotonic = time.monotonic() - self.pause_elapsed
            elapsed = self.pause_elapsed
            self.session_markers.append((elapsed, 'RESUMED'))
            self.session_writer.write_event(elapsed, 'RESUMED')
            self.status_bar.showMessage("Resumed recording", 3000)
        else:
            had_imported_data = len(self.data) > 0
            if not had_imported_data:
                self.data = np.empty((0, self.max_channels + 1))
                self.session_markers = []
                self.pause_elapsed = 0.0
            self.session_channels = list(enabled)

            self.session_path = session_log_path_for()
            try:
                self.session_writer = SessionWriter(self.session_path)
            except OSError as e:
                QMessageBox.warning(
                    self, "Error",
                    f"Could not open session log for writing: {e}")
                self.session_writer = None
                self.session_path = None
                return

            self._session_start_monotonic = time.monotonic() - self.pause_elapsed
            self.session_writer.write_meta(self._build_session_meta())
            if had_imported_data:
                self.session_writer.write_event(self.pause_elapsed, 'SESSION_IMPORTED')
            self.status_bar.showMessage(
                f"Recording started — logging to {os.path.basename(self.session_path)}",
                4000)

        self.capturing = True

        if self.instrument:
            self.measurement_thread = MeasurementThread(
                self.instrument,
                enabled,
                self.settings.get('sample_rate', 2.0),
                self._session_start_monotonic,   
                self.channel_addresses,          
            )
            self.measurement_thread.data_received.connect(self._on_data_received)
            self.measurement_thread.read_error.connect(self._on_read_error)
            self.measurement_thread.start_measurement()
        else:
            self.status_bar.showMessage("Offline mode - simulating data", 3000)

    def _on_read_error(self, msg):
        self.status_bar.showMessage(msg, 3000)

    def _on_data_received(self, elapsed, channels, raw):
        if not channels:
            return

        # Build the row for in-memory plotting / stats
        new_row = np.zeros(self.max_channels + 1)
        new_row[0] = elapsed
        vals = parse_raw_response(raw, channels)
        for ch, v in vals.items():
            new_row[ch + 1] = v

        self.buffer.append_row(new_row)
        self._update_live_display()
        self._schedule_graph_update()

        if self.session_writer is not None:
            try:
                self.session_writer.write_sample(elapsed, channels, raw)
            except OSError as e:
                print(f"Session log write failed: {e}")

    def _update_live_display(self):
        if len(self.data) == 0:
            return
        latest = self.data[-1]
        enabled = self.get_enabled_channels()
        for i in enabled:
            col_idx = i + 1
            if col_idx < len(latest):
                val = latest[col_idx]
                if val != 0:
                    self.channel_temp_labels[i].setText(f"{val:.2f} °C")
                    cb = self.channel_checkboxes[i]
                    cb.setStyleSheet(self._channel_checkbox_stylesheet())
                else:
                    self.channel_temp_labels[i].setText("---")

    def stop_capture(self):
        if not self.capturing:
            return

        self.capturing = False

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop_measurement()
            self.measurement_thread = None

        self.pause_elapsed = time.monotonic() - self._session_start_monotonic
        elapsed = self.pause_elapsed
        self.session_markers.append((elapsed, 'PAUSED'))
        if self.session_writer is not None:
            self.session_writer.write_event(elapsed, 'PAUSED')

        self.status_bar.showMessage(
            f"Paused at {elapsed_to_clock(elapsed)} — press Start to resume", 5000)

    def _close_session_writer(self):
        if self.session_writer is not None:
            try:
                self.session_writer.close()
            except OSError:
                pass
            self.session_writer = None

    def _schedule_graph_update(self):
        if not self._pending_graph_update:
            self._pending_graph_update = True
            QTimer.singleShot(self.settings.get('graph_update_interval', 500), self._throttled_update)

    def _throttled_update(self):
        self._pending_graph_update = False
        self.update_plots()

    def update_loop(self):
        if self.capturing:
            elapsed = time.monotonic() - self._session_start_monotonic
            hours   = int(elapsed // 3600)
            minutes = int((elapsed % 3600) // 60)
            seconds = int(elapsed % 60)
            self.timer_display.setText(f"{hours:02d}:{minutes:02d}:{seconds:02d}")

    # ── Filter ────────────────────────────────────────────────────────────────

    @property
    def data(self):
        return self.buffer.data

    @data.setter
    def data(self, rows):
        self.buffer.set_data(rows)

    @property
    def filtered_data(self):
        return self.buffer.filtered

    def get_filtered_data(self, t_from=None, t_to=None):
        """Return (filtered_data, t_from, t_to), optionally sliced to a time range.
        The returned array is a VIEW of internal state when no time range
        is given: callers must treat it as read-only.
        """
        data = self.filtered_data
        if len(data) == 0:
            return data, None, None

        if t_from is not None and t_to is not None and t_from >= t_to:
            self.status_bar.showMessage(
                "'From' time must be before 'To' time — showing unfiltered data", 3000)
            return data, None, None

        if t_from is not None or t_to is not None:
            mask = np.ones(len(data), dtype=bool)
            if t_from is not None:
                mask &= data[:, 0] >= t_from
            if t_to is not None:
                mask &= data[:, 0] <= t_to
            data = data[mask]

        return data, t_from, t_to

    # ── Plots ─────────────────────────────────────────────────────────────────

    def update_plots(self):
        filtered_data, _, _ = self.get_filtered_data()
        enabled = self.get_enabled_channels()
        show_min = self.show_min.isChecked()
        show_max = self.show_max.isChecked()

        now = self.data[-1, 0] if len(self.data) > 0 else 0.0
        hold_durations = self.buffer.hold_duration(now)
        hold_threshold = self.settings.get('hold_warning_seconds', 30.0)
        hold_message = self.settings.get('hold_warning_message') or 'Out of Filter Range'

        for i, cb in enumerate(self.channel_checkboxes):
            self.channel_min_labels[i].setVisible(show_min)
            self.channel_max_labels[i].setVisible(show_max)

            # reference, shown whenever the channel is enabled.
            color = self.channel_colors[i]._color if hasattr(self.channel_colors[i], '_color') else QColor(100, 100, 100)
            limit = self.channel_limits[i] if i < len(self.channel_limits) else {'min': None, 'max': None}
            _apply_limit_lines(self.limit_min_lines[i], self.limit_max_lines[i], limit, color,
                                i in enabled, show_min, show_max)

            if i in enabled and len(filtered_data) > 0:
                col_idx = i + 1
                if col_idx < filtered_data.shape[1]:
                    t_data   = filtered_data[:, 0]
                    tmp_data = filtered_data[:, col_idx]
                    valid    = tmp_data != 0

                    raw_col = self.data[:, col_idx] if col_idx < self.data.shape[1] else np.array([])
                    has_any_raw = (raw_col != 0).any()
                    last_raw = raw_col[-30:] if len(raw_col) >= 30 else raw_col
                    raw_recently_silent = has_any_raw and not (last_raw != 0).any()

                    if valid.any():
                        name = self.channel_name_edits[i].text().strip()
                        color = self.channel_colors[i]._color if hasattr(self.channel_colors[i], '_color') else QColor(100, 100, 100)
                        self.plots[i].setData(t_data[valid], tmp_data[valid],
                            pen=pg.mkPen(color=(color.red(), color.green(), color.blue()), width=1),
                            name=name if name else f"Ch {i+1}")
                        cur = tmp_data[valid][-1]

                        if raw_recently_silent:
                            cb.setStyleSheet(self._channel_checkbox_stylesheet() +
                                             "QCheckBox { color: #F44336; font-weight: bold; }")
                            self.channel_temp_labels[i].setText("invalid")
                        elif hold_durations[i] > hold_threshold:
                            cb.setStyleSheet(self._channel_checkbox_stylesheet() +
                                             "QCheckBox { color: #FFA726; font-weight: bold; }")
                            self.channel_temp_labels[i].setText(hold_message)
                        else:
                            self.channel_temp_labels[i].setText(f"{cur:.2f} °C")
                            cb.setStyleSheet(self._channel_checkbox_stylesheet())

                        if show_min:
                            mn = tmp_data[valid].min()
                            mn_time = elapsed_to_clock(t_data[valid][tmp_data[valid].argmin()])
                            self.channel_min_labels[i].setText(f"↓ {mn:.2f} @ {mn_time}")
                        else:
                            self.channel_min_labels[i].setText("")
                        if show_max:
                            mx = tmp_data[valid].max()
                            mx_time = elapsed_to_clock(t_data[valid][tmp_data[valid].argmax()])
                            self.channel_max_labels[i].setText(f"↑ {mx:.2f} @ {mx_time}")
                        else:
                            self.channel_max_labels[i].setText("")
                        continue

                    else:
                        if raw_recently_silent:
                            cb.setStyleSheet(self._channel_checkbox_stylesheet() +
                                             "QCheckBox { color: #F44336; font-weight: bold; }")
                            self.channel_temp_labels[i].setText("invalid")
                        else:
                            cb.setStyleSheet(self._channel_checkbox_stylesheet())
                            self.channel_temp_labels[i].setText("---")

                        self.plots[i].setData([], [])
                        self.channel_min_labels[i].setText("")
                        self.channel_max_labels[i].setText("")
                        continue

            self.plots[i].setData([], [])
            self.channel_temp_labels[i].setText("---")
            self.channel_min_labels[i].setText("")
            self.channel_max_labels[i].setText("")
            cb.setStyleSheet(self._channel_checkbox_stylesheet())

    # ── Channel stats helper ──────────────────────────────────────────────────

    def _get_channel_stats(self):
        filtered_data, _, _ = self.get_filtered_data()
        if len(filtered_data) == 0:
            return []
        enabled = self.get_enabled_channels()
        stats = []
        for i in enabled:
            col_idx = i + 1
            if col_idx >= filtered_data.shape[1]:
                continue
            t_data   = filtered_data[:, 0]
            tmp_data = filtered_data[:, col_idx]
            valid    = tmp_data != 0
            if not valid.any():
                continue
            name = self.channel_name_edits[i].text().strip() or f"Ch {i+1}"
            color = self.channel_colors[i]._color if hasattr(self.channel_colors[i], '_color') else QColor(100, 100, 100)
            vals = tmp_data[valid]
            times = t_data[valid]
            stats.append({
                'channel':  i + 1,
                'name':     name,
                'color':    (color.red(), color.green(), color.blue()),
                'current':  vals[-1],
                'min':      vals.min(),
                'max':      vals.max(),
                'time_min': elapsed_to_clock(times[vals.argmin()]),
                'time_max': elapsed_to_clock(times[vals.argmax()]),
            })
        return stats

    # ── Export graph ──────────────────────────────────────────────────────────

    def export_graph(self):
        if len(self.data) == 0:
            QMessageBox.warning(self, "Warning", "No data to export!")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Graph", os.path.expanduser('~'),
            "PNG Images (*.png)")
        if not path:
            return
        if not path.endswith('.png'):
            path += '.png'
        try:
            if hasattr(self.plot, 'grab'):
                pixmap = self.plot.grab()
            elif hasattr(self.plot, 'getViewWidget'):
                pixmap = self.plot.getViewWidget().grab()
            else:
                pixmap = self.grab()
            pixmap.save(path, 'PNG')
            self.status_bar.showMessage(f"Graph exported to {os.path.basename(path)}", 3000)
        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not export graph: {e}")

    def export_graph_with_stats(self):
        if len(self.data) == 0:
            QMessageBox.warning(self, "Warning", "No data to export!")
            return
        stats = self._get_channel_stats()
        if not stats:
            QMessageBox.warning(self, "Warning", "No enabled channels with data!")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Graph + Stats", os.path.expanduser('~'),
            "PNG Images (*.png)")
        if not path:
            return
        if not path.endswith('.png'):
            path += '.png'
        self._build_and_save_export_image(self.graph, stats, path)

    def _build_and_save_export_image(self, graph_widget, stats, path,
                                     show_min=None, show_max=None):
        if show_min is None:
            show_min = self.show_min.isChecked()
        if show_max is None:
            show_max = self.show_max.isChecked()

        col_widths = [60, 160, 110]
        headers    = ['Ch', 'Name', 'Current (°C)']
        if show_min:
            col_widths += [110, 150]
            headers    += ['Min (°C)', 'Time of Min']
        if show_max:
            col_widths += [110, 150]
            headers    += ['Max (°C)', 'Time of Max']

        table_w = sum(col_widths)
        row_h   = 36

        try:
            graph_img = graph_widget.grab().toImage()
            graph_w, graph_h = graph_img.width(), graph_img.height()
            table_h = row_h * (len(stats) + 1) + 16

            total_w = max(graph_w, table_w)
            total_h = graph_h + table_h

            final = QImage(total_w, total_h, QImage.Format_RGB32)
            final.fill(QColor(255, 255, 255))

            painter = QPainter(final)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.drawImage(0, 0, graph_img)

            tx = (total_w - table_w) // 2
            ty = graph_h + 8

            font_hdr = QFont("Arial", 9, QFont.Bold)
            font_row = QFont("Arial", 9)
            font_dot = QFont("Arial", 14, QFont.Bold)

            painter.fillRect(tx, ty, table_w, row_h, QColor(50, 50, 50))
            painter.setFont(font_hdr)
            painter.setPen(QColor(255, 255, 255))
            x = tx
            for w, h in zip(col_widths, headers):
                painter.drawText(x + 6, ty, w, row_h, Qt.AlignVCenter | Qt.AlignLeft, h)
                x += w

            for row_i, s in enumerate(stats):
                ry = ty + row_h * (row_i + 1)
                bg = QColor(245, 245, 245) if row_i % 2 == 0 else QColor(255, 255, 255)
                painter.fillRect(tx, ry, table_w, row_h, bg)
                values = [str(s['channel']), s['name'], f"{s['current']:.2f}"]
                if show_min:
                    values += [f"{s['min']:.2f}", s['time_min']]
                if show_max:
                    values += [f"{s['max']:.2f}", s['time_max']]
                x = tx
                for col_i, (w, val) in enumerate(zip(col_widths, values)):
                    if col_i == 0:
                        painter.setFont(font_dot)
                        painter.setPen(QColor(*s['color']))
                        painter.drawText(x + 4, ry, 20, row_h, Qt.AlignVCenter | Qt.AlignLeft, "●")
                        painter.setFont(font_row)
                        painter.setPen(QColor(30, 30, 30))
                        painter.drawText(x + 20, ry, w - 20, row_h, Qt.AlignVCenter | Qt.AlignLeft, val)
                    else:
                        painter.setFont(font_row)
                        painter.setPen(QColor(30, 30, 30))
                        painter.drawText(x + 6, ry, w, row_h, Qt.AlignVCenter | Qt.AlignLeft, val)
                    x += w
                painter.setPen(QColor(220, 220, 220))
                painter.drawLine(tx, ry + row_h - 1, tx + table_w, ry + row_h - 1)

            painter.end()
            final.save(path)
            self.status_bar.showMessage(f"Graph + stats exported to {os.path.basename(path)}", 3000)

        except Exception as e:
            QMessageBox.warning(self, "Error", f"Could not export graph: {e}")

    # ── Save data ─────────────────────────────────────────────────────────────

    def save_data(self):
        """Export the current in-memory session to a CSV via the session log.

        If a session log is open, it's the source of truth; we export from it.
        If no log exists (e.g. user cleared and re-imported), we export from
        whatever is in the buffer.
        """
        if len(self.data) == 0 and self.session_path is None:
            QMessageBox.warning(self, "Warning", "No data to save!")
            return

        folder = QFileDialog.getExistingDirectory(self, "Select Save Folder")
        if not folder:
            return

        # Always save the raw npy for programmatic use
        try:
            np.save(f"{folder}/data.npy", self.data)
        except OSError as e:
            QMessageBox.warning(self, "Error", f"Could not save data file: {e}")
            return

        # If we have a session log, export it to CSV
        if self.session_path is not None:
            csv_path = f"{folder}/data.csv"
            try:
                export_csv(self.session_path, csv_path)
            except OSError as e:
                QMessageBox.warning(self, "Error", f"Could not export CSV: {e}")
                return

        QMessageBox.information(self, "Saved", f"Data saved to {folder}")

    # ── Config export / import ────────────────────────────────────────────────

    def get_channel_color(self, i):
        c = self.channel_colors[i]
        return c._color if hasattr(c, '_color') else QColor(100, 100, 100)

    def export_config(self):
        path = QFileDialog.getSaveFileName(
            self, "Export Configuration", os.path.expanduser('~'),
            "JSON Files (*.json)")[0]
        if not path:
            return
        if not path.endswith('.json'):
            path += '.json'

        combined = {
            'ui_settings':  dict(self.settings),
            'lab_metadata': self._build_lab_metadata(),
            'channel_limits': self.channel_limits,      
            'channel_addresses': self.channel_addresses,  
        }
        try:
            with open(path, 'w') as f:
                json.dump(combined, f, indent=2)
            self.status_bar.showMessage(f"Config exported to {path}", 3000)
        except OSError as e:
            QMessageBox.warning(self, "Error", f"Could not export config: {e}")

    def import_config(self):
        path = QFileDialog.getOpenFileName(
            self, "Import Configuration", os.path.expanduser('~'),
            "JSON Files (*.json)")[0]
        if not path:
            return
        try:
            with open(path) as f:
                cfg = json.load(f)
        except OSError as e:
            QMessageBox.warning(self, "Error", f"Could not read file: {e}")
            return
        except json.JSONDecodeError as e:
            QMessageBox.warning(self, "Error", f"Config file corrupted: {e}")
            return

        if not isinstance(cfg, dict):
            QMessageBox.warning(self, "Error", "Config file has unexpected structure.")
            return
        if not any(k in cfg for k in ('ui_settings', 'lab_metadata', 'channel_limits', 'channel_addresses')):
            QMessageBox.warning(self, "Error", "Config file has no recognizable sections.")
            return

        if 'ui_settings' in cfg and isinstance(cfg['ui_settings'], dict):
            # A different max_channels in here only takes effect next
            # launch (see __init__), same as editing it in Settings --
            # self.max_channels (used just below) stays the CURRENT value.
            merged = {**DEFAULT_SETTINGS, **cfg['ui_settings']}
            self.apply_settings(merged, False)
            self.settings = merged
        if 'lab_metadata' in cfg and isinstance(cfg['lab_metadata'], dict):
            md = _default_lab_metadata(self.max_channels)
            md.update(cfg['lab_metadata'])
            md['channel_names'] = (list(md.get('channel_names', []))[:self.max_channels]
                                   + [''] * self.max_channels)[:self.max_channels]
            md['channels_checked'] = [i for i in md.get('channels_checked', [])
                                      if isinstance(i, int) and 0 <= i < self.max_channels]
            self._apply_lab_metadata(md)
        if 'channel_limits' in cfg:
            self.channel_limits = _merge_channel_limits(cfg['channel_limits'], self.max_channels)
            save_channel_limits(self.channel_limits)
            self.update_plots()
        if 'channel_addresses' in cfg:
            if self.session_channels is not None:
                # Same lock as the Settings dialog's address editor --
                # importing is another route to the same live table, and
                # changing it mid-session is exactly what the lock exists
                # to prevent.
                self.status_bar.showMessage(
                    "Channel addresses NOT imported -- locked while a session is in progress", 5000)
            else:
                self.channel_addresses = _merge_channel_addresses(
                    cfg['channel_addresses'], self.max_channels,
                    self.settings['channels_per_cassette'], self.settings['channel_address_offset'])
                save_channel_addresses(self.channel_addresses)

        self._config_dirty = True
        self._flush_config()

        self.status_bar.showMessage(f"Config imported from {path}", 3000)

    # ── Close ─────────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        if self.capturing or (self.session_path and len(self.data) > 0):
            reply = QMessageBox.question(
                self, "Quit Temperature Logger",
                "Recording is in progress or the current session has unsaved data.\n\n"
                "Quit anyway?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                event.ignore()
                return

        event.accept()

        self._config_write_timer.stop()
        self._flush_config()

        if self.capturing:
            self.stop_capture()

        self._close_session_writer()

        if self.measurement_thread and self.measurement_thread.isRunning():
            self.measurement_thread.stop_measurement()

        for w in list(self._view_windows):
            w.timer.stop()
            w.close()
        if self.retry_thread:
            self.retry_thread.stop()
            self.retry_thread.wait(1000)
        if self.instrument:
            try:
                self.instrument.close()
            except visa.VisaIOError:
                pass


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = TemperatureLogger()
    window.show()
    sys.exit(app.exec_())