import logging
import logging.handlers
import os


def setup_logging(log_file_path: str = None):
    """
    Configures the logging for the application.
    """
    log_formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)

    # File handler
    if log_file_path is None:
        project_root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        log_file = os.path.join(project_root, "jbot.log")
    else:
        log_file = log_file_path

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 5, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)

    # TODO: replace the root logger with module-specific loggers
    #       This will prevent extra log messages from other libraries
    #       https://stackoverflow.com/questions/35325042
    # TODO: make configurable by admin cmd
    # Get the root logger
    root_logger = logging.getLogger()

    # Remove all existing handlers to avoid duplicating them
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    logging.basicConfig(
        level=logging.INFO, handlers=[console_handler, file_handler], encoding="utf-8"
    )
