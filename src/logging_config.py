import logging
import logging.handlers
import os

def setup_logging():
    """
    Configures the logging for the application.
    """
    log_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(log_formatter)
    
    # File handler
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
    log_file = os.path.join(project_root, 'jbot.log')
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=1024*1024*5, backupCount=2)
    file_handler.setFormatter(log_formatter)
    
    # TODO: replace the root logger with module-specific loggers
    #       This will prevent extra log messages from other libraries
    #       https://stackoverflow.com/questions/35325042
    # TODO: make configurable by admin cmd
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
