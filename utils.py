import tkinter as tk

# --- GLOBAL STYLE VARIABLES ---
BG_COLOR = "#0b161a"      
ACCENT_COLOR = "#00d1ff"  
TEXT_COLOR = "#ffffff"    
SECONDARY_BG = "#16262c"  

# --- GLOBAL RIGHT-CLICK MENU ---

def add_right_click(widget):
    """Standard context menu (Cut/Copy/Paste) for all input fields."""
    menu = tk.Menu(widget, tearoff=0, bg=SECONDARY_BG, fg=TEXT_COLOR, activebackground=ACCENT_COLOR)
    menu.add_command(label="Cut", command=lambda: widget.event_generate("<<Cut>>"))
    menu.add_command(label="Copy", command=lambda: widget.event_generate("<<Copy>>"))
    menu.add_command(label="Paste", command=lambda: widget.event_generate("<<Paste>>"))
    widget.bind("<Button-3>", lambda event: menu.tk_popup(event.x_root, event.y_root))
    
# --- TOOLTIP ---
    
class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        # Using add="+" so it doesn't overwrite other event bindings
        self.widget.bind("<Enter>", self.show_tip, add="+")
        self.widget.bind("<Leave>", self.hide_tip, add="+")

    def show_tip(self, event=None):
        if self.tip_window or not self.text:
            return
        
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 5
        
        self.tip_window = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(1)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify="left",
                         bg="#16262c", fg="#00d1ff", relief="solid", bd=1,
                         font=("Segoe UI", 9, "normal"), padx=5, pady=5)
        label.pack()

    def hide_tip(self, event=None):
        tw = self.tip_window
        self.tip_window = None
        if tw:
            tw.destroy()
            
# --- SCROLLABLE FRAME Y ---
            
class ScrollableFrameY(tk.Frame):
    """Universal vertically scrollable container."""
    def __init__(self, container, bg_color, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.configure(bg=bg_color)

        # Create Canvas and Scrollbar
        self.canvas = tk.Canvas(self, bg=bg_color, bd=0, highlightthickness=0, height=120)  # Height limited to fit neatly in UI
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        
        # Inner Frame
        self.scrollable_frame = tk.Frame(self.canvas, bg=bg_color)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # Pack layouts
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        
        # Global mousewheel support 
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

# --- SCROLLABLE FRAME X ---

class ScrollableFrameX(tk.Frame):
    """Universal horizontally scrollable container."""
    def __init__(self, container, bg_color, *args, **kwargs):
        super().__init__(container, *args, **kwargs)
        self.configure(bg=bg_color)

        # Create Canvas and HORIZONTAL Scrollbar at the bottom
        self.canvas = tk.Canvas(self, bg=bg_color, bd=0, highlightthickness=0, height=40)
        self.scrollbar = tk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        
        # Inner Frame for housing checkboxes or widgets
        self.scrollable_frame = tk.Frame(self.canvas, bg=bg_color)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(xscrollcommand=self.scrollbar.set)

        # Pack layouts: canvas on top, horizontal scrollbar below it
        self.canvas.pack(side="top", fill="x", expand=True)
        self.scrollbar.pack(side="bottom", fill="x")
        
        # --- SMART MOUSEWHEEL BINDING (Only triggers when mouse hovers over the frame) ---
        self.canvas.bind("<Enter>", self._bound_to_mousewheel)
        self.canvas.bind("<Leave>", self._unbound_to_mousewheel)

    def _bound_to_mousewheel(self, event):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbound_to_mousewheel(self, event):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_mousewheel(self, event):
        if self.canvas.winfo_exists():
            # Scroll horizontally when spinning the mousewheel
            self.canvas.xview_scroll(int(-1 * (event.delta / 120)), "units")
            
# --- HOVER EFFECT ---

def add_hover_effect(button, original_font=("Arial", 9), hover_font=("Arial", 9, "bold"), original_bg=None, hover_bg=None):
    
    def on_enter(e):
        if button.cget("state") != "disabled":  # Only apply if button is active
            # Cache the actual current background color right before hover (so custom colors like green aren't lost!)
            button.current_actual_bg = button.cget("bg")
            
            button.configure(font=hover_font)
            if hover_bg:
                button.configure(bg=hover_bg)

    def on_leave(e):
        button.configure(font=original_font)
        # Restore the exact background color that was active prior to hovering
        if hasattr(button, "current_actual_bg"):
            button.configure(bg=button.current_actual_bg)
        else:
            init_bg = original_bg if original_bg else button.cget("bg")
            button.configure(bg=init_bg)

    # Safely attach events using add="+"
    button.bind("<Enter>", on_enter, add="+")
    button.bind("<Leave>", on_leave, add="+")