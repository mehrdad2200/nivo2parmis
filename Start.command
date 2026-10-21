#!/bin/sh
cd "$(dirname "$0")"
python3 -c "import cryptography, tzdata, tkinter" 2>/dev/null || python3 -m pip install --user cryptography tzdata
python3 run_gui.py
