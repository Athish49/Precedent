import logging
import sys


def configure_logging(env: str = "dev") -> None:
    """Configure root logger.

    Dev mode uses DEBUG level and a human-readable format.
    Prod mode uses INFO level.
    """
    level = logging.DEBUG if env == "dev" else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
        force=True,  # reconfigure if already initialised (e.g. uvicorn's logger)
    )
    # Silence noisy third-party loggers that don't add value in normal operation.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
