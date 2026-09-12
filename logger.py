import tkinter as tk
from datetime import datetime

class Logger:
    def __init__(self, widget=None, root=None, max_lines=500):
        self.widget = widget
        self.root = root
        self.max_lines = max_lines
        
    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        msg = f"[{ts}] {message}\n"

        if self.widget:
            try:
                self.widget.insert("end", msg)
                lines = int(self.widget.index('end-1c').split('.')[0])
                if lines > self.max_lines:
                    self.widget.delete("1.0", f"{lines - self.max_lines}.0")
                    
                self.widget.see("end")
            except (tk.TclError, AttributeError, RuntimeError) as e:
                print(f"Logger GUI write warning ({e}): {msg.strip()}")
        else:
            print(msg.strip())