import os
import threading
import subprocess
from concurrent.futures import ThreadPoolExecutor
from docker_mgr import DockerManager

class Controller:
    def __init__(self, app, logger_widget=None):
        self.app = app
        self.logger = logger_widget
        
        # Limit background tasks to 4 concurrent threads to prevent resource wasting
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ControllerWorker")

    # =========================================================================
    # 1. LOGGING HELPER
    # =========================================================================
    def log(self, message):
        """Helper method to handle logging safely."""
        if self.logger:
            self.logger.log(message)
        else:
            print(message)

    # =========================================================================
    # 2. DEPLOYMENT MANAGEMENT
    # =========================================================================
    def deploy_nodes(self, path, selected_indices, public_ip, max_out_peers=16, max_in_peers=0):
        """Generates compose file and deploys selected docker nodes with peer limits."""
        self.log(f"Starting deployment for {len(selected_indices)} nodes...")
        
        # Pass both max_out_peers and max_in_peers to DockerManager
        if DockerManager.create_compose(path, selected_indices, public_ip, max_out_peers, max_in_peers):
            self.log("Docker-compose file generated successfully.")
            result = DockerManager.compose_up(path)
            if result.returncode == 0:
                self.log("Nodes started in background.")
                return True
            else:
                self.log(f"Error starting nodes: {result.stderr.decode() if result.stderr else 'Unknown error'}")
                return False
        else:
            self.log("Critical Error: Failed to generate compose file.")
            return False

    # =========================================================================
    # 3. UPDATE CHECKER
    # =========================================================================
    def check_for_updates(self, path):
        """Checks if a new version exists on GitHub Container Registry without applying it to running containers."""
        self.log("🔍 Checking for XeqM SN Docker image updates...")
        
        if not path:
            self.log("❌ Update check failed: Folder path is empty.")
            return False
            
        # Clean the windows path from hidden quotes or trailing bad slashes to fix WinError 123
        clean_path = os.path.normpath(path.strip().replace('"', ''))
        
        if not os.path.exists(clean_path):
            self.log(f"❌ Update check failed: Path does not exist ({clean_path})")
            return False

        try:
            result = subprocess.run(
                ["docker", "compose", "pull"],
                cwd=clean_path, 
                capture_output=True, 
                text=True, 
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                timeout=45
            )
            
            output = result.stdout + result.stderr
            
            # Check if Docker explicitly confirms it found and downloaded new layers
            if "Downloaded newer image" in output or "Newer image for" in output or "status: downloaded newer image" in output.lower():
                return True
                
            return False
        except subprocess.TimeoutExpired:
            self.log("❌ Update check failed: Connection timed out.")
            return False
        except Exception as e:
            self.log(f"❌ Update check failed: {str(e)}")
            return False

    # =========================================================================
    # 4. ASYNC THREAD RUNNER
    # =========================================================================
    def run_async(self, func, callback=None, *args):
        """Universal thread wrapper to run functions in the background."""
        def worker():
            try:
                res = func(*args)
                if callback and getattr(self.app, 'running', True):
                    self.app.root.after(0, callback, res)
            except Exception as e:
                self.log(f"General error in async task: {e}")
                if callback and getattr(self.app, 'running', True):
                    self.app.root.after(0, callback, False)

        self._executor.submit(worker)

    # =========================================================================
    # 5. SHUTDOWN HANDLER
    # =========================================================================
    def shutdown(self):
        """Safely shuts down the thread pool without waiting for blocking tasks."""
        try:
            # wait=False and cancel_futures=True prevents the app from hanging on exit if a background task is running
            self._executor.shutdown(wait=False, cancel_futures=True)
        except Exception as e:
            print(f"Error shutting down controller executor: {e}")