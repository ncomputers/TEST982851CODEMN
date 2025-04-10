import logging

def setup_logging():
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    if logger.hasHandlers():
        logger.handlers.clear()

    # Remove this block to prevent file logging
    # file_handler = logging.FileHandler(config.LOG_FILE)
    # file_handler.setLevel(logging.DEBUG)
    # file_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    # file_handler.setFormatter(file_formatter)
    # logger.addHandler(file_handler)

    # Only log to console
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    return logger

if __name__ == "__main__":
    logger = setup_logging()
    logger.info("Logging has been configured successfully.")
