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
    # Ensure console handles unicode characters safely
    if hasattr(console_handler.stream, "reconfigure"):
        try:
            console_handler.stream.reconfigure(encoding="utf-8")
        except AttributeError:
            # Standard streams like sys.stdout might not support reconfiguration
            pass

    # File handler
    if log_file_path is None:
        project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        log_file = os.path.join(project_root, "jbot.log")
    else:
        log_file = log_file_path

    file_handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=1024 * 1024 * 5, backupCount=2, encoding="utf-8"
    )
    file_handler.setFormatter(log_formatter)

    # Configure the root logger so all logging.info() / logging.warning() etc.
    # calls throughout the codebase are captured, regardless of which logger
    # module they originate from.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Remove all existing handlers to avoid duplicating them
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # The named "jbot" logger inherits handlers from root via propagation.
    # Explicitly set its level so child loggers (jbot.*) are not filtered.
    logging.getLogger("jbot").setLevel(logging.INFO)
