import os

def _find_aimaos_root():
    p = os.path.dirname(os.path.abspath(__file__))
    while p != os.path.dirname(p) and not os.path.exists(os.path.join(p, "aimaos_config.yaml")):
        p = os.path.dirname(p)
    return p
AIMAOS_ROOT = os.environ.get("AIMAOS_ROOT") or _find_aimaos_root()
import sys
import time
import threading
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".json", ".csv"}

class InboxWatcher:
    """
    Background file watcher for Alix-AI.
    Monitors workspace inbox and user download folders for new intake files.

    Flags each new file for triage rather than trying to auto-file it: a
    bare dropped file doesn't say which client it's for (that needs a human
    glance, or real email metadata once incoming-mail fetching exists) --
    Kai's process_incoming_file is the next real step once that's known.
    """
    def __init__(self, watch_dirs, document_digester=None, poll_interval=5.0):
        self.watch_dirs = [os.path.abspath(d) for d in watch_dirs]
        self.digester = document_digester  # unused now, kept for constructor compatibility
        self.poll_interval = poll_interval
        self.processed_files = set()
        self._running = False
        self._thread = None

        # Ensure directories exist
        for d in self.watch_dirs:
            os.makedirs(d, exist_ok=True)
            self._scan_initial_files(d)

    def _scan_initial_files(self, directory):
        """Mark existing files as known on startup to prevent re-processing unless new."""
        try:
            for root, _, files in os.walk(directory):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        path = os.path.abspath(os.path.join(root, file))
                        self.processed_files.add((path, os.path.getmtime(path)))
        except Exception as e:
            logger.warning(f"Error scanning initial files in {directory}: {e}")

    def start(self):
        """Start watcher background daemon thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._watch_loop, daemon=True)
        self._thread.start()
        logger.info(f"InboxWatcher started. Monitoring directories: {self.watch_dirs}")

    def stop(self):
        """Stop watcher loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

    def _watch_loop(self):
        while self._running:
            try:
                self.check_new_files()
            except Exception as e:
                logger.error(f"Error in InboxWatcher poll loop: {e}")
            time.sleep(self.poll_interval)

    def check_new_files(self):
        """Scans directories for new or modified intake files."""
        new_discoveries = []
        for d in self.watch_dirs:
            if not os.path.exists(d):
                continue
            for root, _, files in os.walk(d):
                for file in files:
                    ext = os.path.splitext(file)[1].lower()
                    if ext in SUPPORTED_EXTENSIONS:
                        full_path = os.path.abspath(os.path.join(root, file))
                        try:
                            mtime = os.path.getmtime(full_path)
                            file_key = (full_path, mtime)
                            if file_key not in self.processed_files:
                                self.processed_files.add(file_key)
                                new_discoveries.append(full_path)
                        except OSError:
                            continue

        for file_path in new_discoveries:
            self.digest_file(file_path)

    def digest_file(self, file_path):
        """Posts a triage task for Kai instead of silently guessing which
        client a bare dropped file belongs to. Kept the name `digest_file`
        for compatibility with anything still calling it directly."""
        try:
            sys.path.insert(0, AIMAOS_ROOT)
            from core.comms.office_board import OfficeBoard
            board = OfficeBoard()
            task_id = board.post_task(
                title=f"Triage new file: {os.path.basename(file_path)}",
                requester="InboxWatcher",
                target_agent="Kai",
                priority="NORMAL",
                details={"file_path": file_path,
                        "note": "Identify which client this belongs to, then use "
                                "process_incoming_file to file it properly."},
            )
            logger.info(f"InboxWatcher flagged {file_path} for triage (task {task_id}).")
            return task_id
        except Exception as e:
            logger.error(f"Failed to post triage task for {file_path}: {e}")
        return None
