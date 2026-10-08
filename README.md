# Temperature Logger

A single-file desktop data-acquisition tool for the **Keysight DAQ970A**, 
and for other Keysight/Agilent DAQ instruments that use the same 
slot/position SCPI channel addressing and `MEAS:TEMP:TC?` command form.

Reads thermocouple channels over LAN or USB, plots them live, logs them
to a crash-safe append-only session file, and exports to CSV / PNG.

## Functionality

- **Live plotting** of thermocouple channels (40 by default,
  configurable), with per-channel colors, names, and min/max limit
  lines.
- **Crash-safe session logs** — every sample is written as a hashed
  line the moment it arrives, so an interrupted session is still
  readable and truncation is detectable. Raw instrument responses are
  preserved unprocessed; filtering and exports are derived views.
- **Incremental filtering** — a rate-of-change / min-run filter that
  judges each new sample against a channel's recent state, so refresh
  cost stays constant no matter how long the session runs.
- **Held-value warning** — a channel whose readings keep failing the
  filter shows a warning instead of a stale number.
- **Secondary view windows** — additional plots scoped to their own
  time range and channel subset.
- **CSV / PNG export**, **config export / import**, and an **offline
  mode** that retries in the background until an instrument appears.

## Requirements

- Python 3.8 or newer
- A Keysight DAQ970A, or another Keysight/Agilent DAQ instrument using
  the same `MEAS:TEMP:TC?` SCPI command and slot/position channel
  addressing
- NI-VISA (recommended) or the pure-Python `pyvisa-py` backend

The script installs its own Python dependencies on first run
(`numpy`, `pyqtgraph`, `pyvisa`, `PyQt5`, `pyvisa-py`) and restarts
itself.

## Background

Originally developed as a tool in a safety and standards testing lab,
running under non-privileged user accounts with corporate endpoint
security active — no admin rights, no ability to install software
system-wide, and direct device communication frequently flagged and
blocked.

These constraints shaped the tool's deployment path: NI-VISA proved to
be the reliable way to establish an unflagged, stable connection to
the instruments, and the Microsoft Store build of Python was the 
most convenient way to get an interpreter onto the machine without admin rights.
The script installing its own dependencies into the user's site-packages
on first run — rather than requiring a normal `pip install` — is a
response to that same environment.

The single-file design is deliberate: it can be quickly copied and set up
onto a lab machine by hand, run without any project structure, and either
installs its dependencies or fails with a clear error explaining why.

## Quick start

Download `TempLogger.py` from the repo, or clone it:

```sh
git clone https://github.com/Robi7d1/keysight-daq-templogger.git
cd keysight-daq-templogger
```

Run it:

```sh
python TempLogger.py
```

The script creates its subdirectories and config files in its own
directory on first run.

## License

GPL v3 — see [LICENSE](LICENSE).
