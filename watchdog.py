import time
import threading
from network import Network

class IPWatchdog:
    def __init__(self, app):
        self.app = app
        self.last_ip = None
        self.running = False

    def start(self):
        self.running = True
        thread = threading.Thread(target=self._run, daemon=True)
        thread.start()

    def stop(self):
        self.running = False

    def _run(self):
        while self.running:
            try:
                current_ip = Network.get_public_ip()
                if current_ip != "Unknown" and current_ip != self.last_ip:
                    self.last_ip = current_ip
                    
                    # Notify application about the IP change (this also updates current_ip_var safely)
                    if self.app.running:
                        self.app.ip_changed(current_ip)
            except Exception as e:
                print(f"IPWatchdog error: {e}")

            # Check every 30 seconds to avoid API rate-limiting
            time.sleep(30)