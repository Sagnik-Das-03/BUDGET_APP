import logging
import subprocess

from app.config import settings

logger = logging.getLogger("budget_tracker.backup")


def trigger_backup() -> None:
    """Launches the external backup_program/start.bat in its own detached
    console window. Fire-and-forget: that script does its own venv setup,
    runs backup.py, and ends with a `pause` for the user to dismiss - none of
    which this app should block shutdown to wait on."""
    script = settings.backup_script
    if not script.exists():
        logger.warning("Backup script not found at %s - skipping", script)
        return
    try:
        subprocess.Popen(["cmd", "/c", "start", "Budget Tracker Backup", str(script)], cwd=str(script.parent))
        logger.info("Triggered backup script: %s", script)
    except Exception:
        logger.exception("Failed to launch backup script at %s", script)
