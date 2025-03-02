import asyncio
import logging
import os
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    def __init__(self, config_path: Path, reload_callback, main_loop=None):
        self.config_path = config_path
        self.reload_callback = reload_callback
        self.main_loop = main_loop  # Store reference to the main event loop
        self.last_modified = os.path.getmtime(config_path) if config_path.exists() else 0
        self.debounce_timer = None
        
    def on_modified(self, event):
        if not event.is_directory and Path(event.src_path).resolve() == self.config_path.resolve():
            try:
                current_modified = os.path.getmtime(self.config_path)
                # Avoid duplicate events by checking modification time
                if current_modified > self.last_modified:
                    self.last_modified = current_modified
                    logger.info(f"Config file changed: {self.config_path}")
                    
                    # Debounce by delaying the reload call
                    if self.debounce_timer:
                        self.debounce_timer.cancel()
                    
                    # Schedule in a thread-safe way
                    # Use threading.Timer instead of asyncio here since we're in a thread
                    import threading
                    self.debounce_timer = threading.Timer(0.5, self._trigger_reload)
                    self.debounce_timer.daemon = True
                    self.debounce_timer.start()
            except Exception as e:
                logger.error(f"Error processing config file change: {e}", exc_info=True)
    
    def _trigger_reload(self):
        """Trigger the reload callback in a thread-safe way"""
        try:
            if self.main_loop is None:
                logger.error("Cannot trigger reload: No event loop reference provided")
                return
                
            # Use the stored reference to the main loop
            asyncio.run_coroutine_threadsafe(self.reload_callback(), self.main_loop)
        except Exception as e:
            logger.error(f"Error triggering reload: {e}", exc_info=True)

class ConfigWatcher:
    def __init__(self, config_path: Path, reload_callback, main_loop=None):
        self.config_path = config_path
        self.observer = Observer()
        self.main_loop = main_loop  # Store reference to the main event loop
        self.event_handler = ConfigFileHandler(config_path, reload_callback, main_loop)
        
    def set_loop(self, loop):
        """Set the main event loop reference"""
        self.main_loop = loop
        self.event_handler.main_loop = loop
    
    def start(self):
        """Start watching the config file"""
        try:
            # Watch the directory containing the config file
            parent_dir = self.config_path.parent
            self.observer.schedule(
                self.event_handler,
                str(parent_dir),
                recursive=False
            )
            self.observer.start()
            logger.info(f"Started watching config file: {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to start config watcher: {e}", exc_info=True)
    
    def stop(self):
        """Stop the config watcher - only called during final shutdown"""
        try:
            if self.observer.is_alive():
                # Just stop without joining - more reliable during shutdown
                self.observer.stop()
                logger.info("Stopped config watcher")
        except Exception as e:
            logger.error(f"Error stopping config watcher: {e}", exc_info=True)
