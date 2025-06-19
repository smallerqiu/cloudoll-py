import itertools
import sys
import time

def spinner_running(stop_flag):
    for c in itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"):
        if stop_flag["stop"]:
            break
        sys.stdout.write(f"\r⏳ creating... {c}")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 30 + "\r")