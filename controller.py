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
    # 3. UPDATE CHECKER & APPLY LOGIC
    # =========================================================================
    def check_for_updates(self, path):
        """Checks GHCR registry for new image version using cached manifest comparison."""
        self.log("🔍 Checking for XeqM SN Docker image updates...")
        
        if not path:
            self.log("❌ Update check failed: Folder path is empty.")
            return False

        try:
            image_name = DockerManager.IMAGE

            # Fetch remote registry manifest raw output without pulling
            remote_inspect = subprocess.run(
                ["docker", "buildx", "imagetools", "inspect", image_name, "--raw"],
                capture_output=True, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                timeout=30
            )

            if remote_inspect.returncode != 0:
                remote_inspect = subprocess.run(
                    ["docker", "manifest", "inspect", image_name],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    timeout=30
                )

            if remote_inspect.returncode != 0:
                self.log("⚠️ Remote registry check failed (Connection issue).")
                return False

            remote_data = remote_inspect.stdout.strip()
            cache_path = os.path.join(path, ".last_image_digest")

            # Read cached digest if exists
            cached_data = ""
            if os.path.exists(cache_path):
                with open(cache_path, "r", encoding="utf-8") as f:
                    cached_data = f.read().strip()

            # If cache does not exist yet, save baseline and return false
            if not cached_data:
                with open(cache_path, "w", encoding="utf-8") as f:
                    f.write(remote_data)
                return False

            # Compare current registry manifest with cache
            if remote_data == cached_data:
                self.log("ℹ️ Docker image is already up to date.")
                return False
            else:
                self.log("✨ New Docker image version detected on registry!")
                return True

        except Exception as e:
            self.log(f"❌ Update check error: {str(e)}")
            return False

    def apply_update(self, path):
        """Pulls latest image layers, updates cache, and recreates running containers."""
        self.log("🚀 Downloading update and restarting Docker containers...")
        try:
            pull_res = subprocess.run(
                ["docker", "compose", "pull"],
                cwd=path, capture_output=True, text=True,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                timeout=120
            )
            if pull_res.returncode == 0:
                # Update cache baseline after successful pull
                image_name = DockerManager.IMAGE
                remote_inspect = subprocess.run(
                    ["docker", "buildx", "imagetools", "inspect", image_name, "--raw"],
                    capture_output=True, text=True,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    timeout=30
                )
                if remote_inspect.returncode == 0:
                    cache_path = os.path.join(path, ".last_image_digest")
                    with open(cache_path, "w", encoding="utf-8") as f:
                        f.write(remote_inspect.stdout.strip())

                up_res = DockerManager.compose_up(path)
                if up_res.returncode == 0:
                    self.log("✅ Docker nodes successfully updated and restarted!")
                    return True
            self.log("❌ Failed to apply Docker update.")
            return False
        except Exception as e:
            self.log(f"❌ Error applying update: {e}")
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