import threading
import logging
import subprocess
import os
import sys
from signal_processor import start_signal_processing_loop
from profit_trailing import ProfitTrailing
from logger import setup_logging

def profit_trailing_thread():
    pt = ProfitTrailing(check_interval=1)
    pt.track()

def main():
    setup_logging()
    logger = logging.getLogger(__name__)

    # ✅ Dynamic paths: works on Windows, Linux, macOS
    base_dir = os.path.dirname(__file__)
    yt_script_path = os.path.join(base_dir, "youtube_ocr.py")
    venv_python = sys.executable  # <-- uses current interpreter (works on any OS)

    print("✅ Using Python interpreter:", venv_python)
    print("📹 Launching YouTube OCR script:", yt_script_path)

    try:
        subprocess.Popen([venv_python, yt_script_path])
        logger.info("YouTube OCR process started successfully.")
    except Exception as e:
        logger.error("Failed to start YouTube OCR script: %s", e)

    # 🔁 Start profit trailing in background
    pt_thread = threading.Thread(target=profit_trailing_thread, daemon=True)
    pt_thread.start()

    # 🔁 Start signal processing loop
    start_signal_processing_loop()

if __name__ == '__main__':
    main()
