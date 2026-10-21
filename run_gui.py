"""نقطه‌ی ورود برای دوبار کلیک / ساخت exe:  python run_gui.py"""
import os, sys
if getattr(sys, "frozen", False):          # exe ساخته‌شده با PyInstaller
    start = os.path.dirname(sys.executable)
else:
    start = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, start)
from nivo2parmis.gui import main
main(start)
