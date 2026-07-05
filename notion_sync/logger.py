import logging
from rich.logging import RichHandler
from rich.console import Console

# Create a shared console instance
console = Console()

def setup_logger(name: str = "notion_sync") -> logging.Logger:
    """Sets up a beautiful logger using Rich."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)]
    )
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logger()
