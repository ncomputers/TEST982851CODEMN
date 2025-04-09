import threading
import logging
from signal_processor import start_signal_processing_loop
from profit_trailing import ProfitTrailing
from logger import setup_logging


def profit_trailing_thread():
    pt = ProfitTrailing(check_interval=1)
    pt.track()                              

def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Start profit trailing in a daemon thread.
    pt_thread = threading.Thread(target=profit_trailing_thread, daemon=True)
    pt_thread.start()  
    
    
    # Start signal processing loop in the main thread.
    start_signal_processing_loop()

if __name__ == '__main__':
    main()
