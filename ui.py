import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import time
import os
import sys
import subprocess

from logger import Logger
from controller import Controller
from watchdog import IPWatchdog
from network import Network
from docker_mgr import DockerManager
from Wallet_modal import wallet_modal

from utils import (
    BG_COLOR, ACCENT_COLOR, TEXT_COLOR, SECONDARY_BG, 
    add_right_click, ToolTip, ScrollableFrameX, ScrollableFrameY, add_hover_effect
)


class UnbufferedLogger:
    """
    Stream redirector (stdout/stderr) ensuring that all print() statements 
    and system messages remain visible in the GUI log window when compiled into a .exe file.
    """
    def __init__(self, text_widget, original_stream):
        self.text_widget = text_widget
        self.original_stream = original_stream

    def write(self, message):
        if self.original_stream:
            try:
                self.original_stream.write(message)
                self.original_stream.flush()
            except Exception:
                pass
        
        if message and self.text_widget:
            def append():
                try:
                    if self.text_widget.winfo_exists():
                        self.text_widget.insert(tk.END, message)
                        self.text_widget.see(tk.END)
                except Exception:
                    pass
            
            # If invoked from a secondary thread, safely route to the main GUI thread
            if threading.current_thread() is threading.main_thread():
                append()
            else:
                try:
                    self.text_widget.after(0, append)
                except Exception:
                    pass

    def flush(self):
        if self.original_stream:
            try:
                self.original_stream.flush()
            except Exception:
                pass


class App:
    def __init__(self, root):
        self.root = root
        self.root.title("XeqM SN Factory - Mainnet")
        self.root.geometry("650x780")  
        
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "xeqm.ico")
        if os.path.exists(icon_path):
             self.root.iconbitmap(icon_path)
        self.root.configure(bg=BG_COLOR)

        # --- SCROLLBAR SYSTEM ---
        main_container = tk.Frame(self.root, bg=BG_COLOR)
        main_container.pack(fill="both", expand=True)

        self.main_canvas = tk.Canvas(main_container, bg=BG_COLOR, highlightthickness=0)
        self.main_canvas.pack(side="left", fill="both", expand=True)

        scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=self.main_canvas.yview)
        scrollbar.pack(side="right", fill="y")

        self.main_canvas.configure(yscrollcommand=scrollbar.set)
        
        # Deployment locks
        self.is_deploying = False
        self._deploy_lock = threading.Lock()
        
        # Inner container for all UI content
        self.content_frame = tk.Frame(self.main_canvas, bg=BG_COLOR)
        self.canvas_window = self.main_canvas.create_window((0, 0), window=self.content_frame, anchor="nw")

        def configure_scroll(event):
            self.main_canvas.configure(scrollregion=self.main_canvas.bbox("all"))
        self.content_frame.bind("<Configure>", configure_scroll)

        def configure_width(event):
            self.main_canvas.itemconfig(self.canvas_window, width=event.width)
        self.main_canvas.bind("<Configure>", configure_width)

        def _on_mousewheel(event):
            if self.main_canvas.winfo_exists():
                self.main_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.root.bind_all("<MouseWheel>", _on_mousewheel)
        # ----------------------------------------------

        # 1. Control variables
        self.folder_path = tk.StringVar()
        self.nodes_count = tk.StringVar(value="0")
        self.wallet_addr = tk.StringVar()
        self.stake_amount = tk.StringVar(value="200000")
        self.current_ip_var = tk.StringVar(value="Detecting IP...")
        self.net_height_var = tk.StringVar(value="Height: ---")
        self.net_status_var = tk.StringVar(value="Status: Offline")
        self.max_out_peers = tk.StringVar(value="16")
        self.auto_restart = tk.BooleanVar(value=False)

        # 2. Setup internal components
        self.node_vars = []
        self.status_labels = []
        self.status_strips = []
        self.running = True
        self.snapshot_event = threading.Event()
        self.ui_snapshot_data = {}
        self.last_status_cache = {}
        self.watchdog_cooldown = 0

        # Progress bar setup
        self.style = ttk.Style(self.root)
        self.style.theme_use("default")
        self.style.configure(
            "Custom.Horizontal.TProgressbar",
            troughcolor=SECONDARY_BG,
            background=ACCENT_COLOR,
            thickness=8,
            borderwidth=0,
            relief="flat"
        )

        # 3. Inside content_frame UI setup
        self.setup_ui()

        # 4. Redirect stdout and stderr for .exe logging output
        sys.stdout = UnbufferedLogger(self.log_widget, sys.stdout)
        sys.stderr = UnbufferedLogger(self.log_widget, sys.stderr)

        # 5. Initialize Logger and Controller 
        self.logger = Logger(self.log_widget)
        self.ctrl = Controller(self, self.logger)

        # 6. Fetch initial IP immediately and start Watchdog
        self.update_ip_display()

        self.ip_watchdog = IPWatchdog(self)
        self.ip_watchdog.start()

        threading.Thread(target=self.status_updater, daemon=True).start()

    def setup_ui(self):
        # Top section layout configuration
        self.content_frame.grid_columnconfigure(0, weight=3, uniform="group1")
        self.content_frame.grid_columnconfigure(1, weight=2, uniform="group1")

        # ==========================================
        # LEFT SIDE: CONFIGURATION PANEL
        # ==========================================
        config_base_frame = tk.Frame(self.content_frame, bg=BG_COLOR)
        config_base_frame.grid(row=0, column=0, sticky="nsew", padx=(15, 7), pady=15)

        folder_frame = tk.LabelFrame(config_base_frame, text=" 📂 Deployment Directory ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        folder_frame.pack(fill="x", pady=(0, 10))

        folder_inner = tk.Frame(folder_frame, bg=BG_COLOR)
        folder_inner.pack(fill="x", padx=10, pady=8)

        self.lbl_folder = tk.Label(folder_inner, text="No directory selected", fg="#8aa0a6", bg=SECONDARY_BG, anchor="w", font=("Arial", 9, "italic"), height=2, bd=1, relief="flat", padx=8)
        self.lbl_folder.pack(side="left", fill="x", expand=True, padx=(0, 8))
        add_right_click(self.lbl_folder)

        self.browse_btn = tk.Button(folder_inner, text="Browse", command=self.browse_folder, bg=SECONDARY_BG, fg=TEXT_COLOR, activebackground=ACCENT_COLOR, activeforeground=BG_COLOR, bd=0, font=("Arial", 9, "bold"), padx=12, pady=4, cursor="hand2")
        self.browse_btn.pack(side="right")

        settings_frame = tk.LabelFrame(config_base_frame, text=" ⚙️ Factory Settings ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        settings_frame.pack(fill="x", pady=(0, 10))

        settings_inner = tk.Frame(settings_frame, bg=BG_COLOR)
        settings_inner.pack(fill="x", padx=12, pady=10)
       
        settings_inner.grid_columnconfigure(0, weight=1, uniform="settings_col")
        settings_inner.grid_columnconfigure(1, weight=1, uniform="settings_col")

        tk.Label(settings_inner, text="Max Out Peers:", fg=TEXT_COLOR, bg=BG_COLOR, font=("Arial", 9, "bold"), anchor="w").grid(row=0, column=0, sticky="w", pady=4)
        
        peers_container = tk.Frame(settings_inner, bg=BG_COLOR)
        peers_container.grid(row=0, column=1, sticky="w", pady=4)
        
        self.peers_entry = tk.Entry(peers_container, textvariable=self.max_out_peers, bg=SECONDARY_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, bd=1, relief="flat", font=("Arial", 9, "bold"), width=12, justify="center")
        self.peers_entry.pack(side="left")
        
        self.peers_warn_lbl = tk.Label(peers_container, text="", bg=BG_COLOR, font=("Segoe UI", 8, "bold"))
        self.peers_warn_lbl.pack(side="left", padx=5)

        def on_peers_change(*args):
            val_str = self.max_out_peers.get().strip()
            if not val_str or val_str == "0":
                self.peers_entry.config(fg="#00d1ff") 
                self.peers_warn_lbl.config(text="[0=16]", fg="#a0a0a0")
                return
            try:
                val = int(val_str)
                if val <= 8:
                    self.peers_entry.config(fg="#ff3333") 
                    self.peers_warn_lbl.config(text="⚠️ Low", fg="#ff3333")
                else:
                    self.peers_entry.config(fg="#00d1ff") 
                    self.peers_warn_lbl.config(text="✓", fg="#00ff66")
            except ValueError:
                self.peers_entry.config(fg="#ff3333")
                self.peers_warn_lbl.config(text="❌ No!", fg="#ff3333")

        self.max_out_peers.trace_add("write", on_peers_change)
        on_peers_change()
        add_right_click(self.peers_entry)
        ToolTip(self.peers_entry, "Controls the maximum number of outgoing connections.")

        tk.Label(settings_inner, text="Nodes Count:", fg=TEXT_COLOR, bg=BG_COLOR, font=("Arial", 9, "bold"), anchor="w").grid(row=1, column=0, sticky="w", pady=4)
        
        self.entry_nodes = tk.Entry(settings_inner, textvariable=self.nodes_count, bg=SECONDARY_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, bd=1, relief="flat", font=("Arial", 9, "bold"), width=12, justify="center")
        self.entry_nodes.grid(row=1, column=1, sticky="w", pady=4)
        self.nodes_count.trace_add("write", self.update_node_checkboxes)
        add_right_click(self.entry_nodes)
        ToolTip(self.entry_nodes, "Enter how many nodes you want to spin up.")

        self.chk_watchdog = tk.Checkbutton(
            settings_inner, text="Enable Auto-Watchdog", variable=self.auto_restart,
            bg=BG_COLOR, fg=TEXT_COLOR, selectcolor=SECONDARY_BG, activebackground=BG_COLOR, activeforeground=ACCENT_COLOR, font=("Arial", 9)
        )
        self.chk_watchdog.grid(row=2, column=0, columnspan=2, sticky="w", pady=5)

        grid_frame = tk.LabelFrame(config_base_frame, text=" 🖥️ Node Manager Selection ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        grid_frame.pack(fill="both", expand=True, pady=(5, 0))

        sel_buttons_frame = tk.Frame(grid_frame, bg=BG_COLOR)
        sel_buttons_frame.pack(fill="x", padx=10, pady=(6, 2))

        self.btn_toggle_select = tk.Button(sel_buttons_frame, text="SELECT ALL", command=self.toggle_all_checkboxes, bg=SECONDARY_BG, fg=TEXT_COLOR, activebackground=ACCENT_COLOR, activeforeground=BG_COLOR, bd=0, font=("Arial", 8, "bold"), padx=8, pady=2, cursor="hand2")
        self.btn_toggle_select.pack(side="left")

        self.scroll_container = ScrollableFrameX(grid_frame, bg_color=BG_COLOR)
        self.scroll_container.pack(fill="x", padx=10, pady=5)
        self.scroll_container.canvas.configure(height=60)
        self.check_frame = self.scroll_container.scrollable_frame

        # ==========================================
        # RIGHT SIDE: STATISTICS AND ACTIONS
        # ==========================================
        stats_base_frame = tk.Frame(self.content_frame, bg=BG_COLOR)
        stats_base_frame.grid(row=0, column=1, sticky="nsew", padx=(7, 15), pady=15)

        net_box = tk.LabelFrame(stats_base_frame, text=" 🌐 Network Pulse ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        net_box.pack(fill="x", pady=(0, 10))

        net_inner = tk.Frame(net_box, bg=BG_COLOR)
        net_inner.pack(fill="x", padx=12, pady=10)

        self.lbl_ip = tk.Label(net_inner, textvariable=self.current_ip_var, fg=TEXT_COLOR, bg=BG_COLOR, font=("Consolas", 9, "bold"), anchor="w")
        self.lbl_ip.pack(fill="x", pady=2)
        
        self.lbl_status = tk.Label(net_inner, textvariable=self.net_status_var, fg=TEXT_COLOR, bg=BG_COLOR, font=("Consolas", 9, "bold"), anchor="w")
        self.lbl_status.pack(fill="x", pady=2)

        self.lbl_height = tk.Label(net_inner, textvariable=self.net_height_var, fg=TEXT_COLOR, bg=BG_COLOR, font=("Consolas", 9), anchor="w")
        self.lbl_height.pack(fill="x", pady=2)

        progress_frame = tk.Frame(net_inner, bg=BG_COLOR)
        progress_frame.pack(fill="x", pady=(6, 2))

        self.bar = ttk.Progressbar(progress_frame, style="Custom.Horizontal.TProgressbar", orient="horizontal", mode="determinate")
        self.bar.pack(fill="x")

        ops_box = tk.LabelFrame(stats_base_frame, text=" 🚀 Factory Actions ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        ops_box.pack(fill="both", expand=True)

        ops_inner = tk.Frame(ops_box, bg=BG_COLOR)
        ops_inner.pack(fill="both", expand=True, padx=12, pady=10)
        
        self.btn_deploy = tk.Button(ops_inner, text="DEPLOY NODES", command=self.deploy, bg=ACCENT_COLOR, fg=BG_COLOR, font=("Arial", 10, "bold"), height=2, cursor="hand2", bd=0)
        self.btn_deploy.pack(fill="x", pady=(0, 6))
        
        self.btn_wallet_cli = tk.Button(ops_inner, text="OPEN WALLET CLI", command=self.open_wallet, bg=SECONDARY_BG, fg=TEXT_COLOR, font=("Arial", 9, "bold"), cursor="hand2", bd=0, pady=4)
        self.btn_wallet_cli.pack(fill="x", pady=(0, 6))

        self.btn_check_updates = tk.Button(ops_inner, text="CHECK IMAGE UPDATES", command=self.check_image_updates, bg=SECONDARY_BG, fg=TEXT_COLOR, font=("Arial", 9, "bold"), cursor="hand2", bd=0, pady=4)
        self.btn_check_updates.pack(fill="x", pady=(0, 6))
        ToolTip(self.btn_check_updates, "Check for any updates regarding Docker Node Images.")

        self.btn_clear_logs = tk.Button(ops_inner, text="CLEAR CONSOLE LOGS", command=self.clear_console_logs, bg=SECONDARY_BG, fg=TEXT_COLOR, font=("Arial", 9, "bold"), cursor="hand2", bd=0, pady=4)
        self.btn_clear_logs.pack(fill="x", pady=(0, 6))
        ToolTip(self.btn_clear_logs, "Flush and clean the main console log window below.")
        
        self.btn_restart = tk.Button(ops_inner, text="RESTART DOCKER", command=self.hard_restart_docker, bg="#e74c3c", fg="white", font=("Arial", 9, "bold"), cursor="hand2", bd=0, pady=4)
        self.btn_restart.pack(fill="x", pady=(0, 2))
        ToolTip(self.btn_restart, "Use only in emergency situations (restarts Docker Desktop)")

        # ==========================================
        # BOTTOM SIDE: REGISTRATION AND LOGS
        # ==========================================
        reg = tk.LabelFrame(self.content_frame, text=" REGISTRATION ", bg=BG_COLOR, fg=ACCENT_COLOR, font=("Arial", 10, "bold"), padx=15, pady=10, bd=1, relief="solid")
        reg.grid(row=1, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 10))

        reg_grid = tk.Frame(reg, bg=BG_COLOR)
        reg_grid.pack(fill="x")
        reg_grid.grid_columnconfigure(0, weight=1)
        reg_grid.grid_columnconfigure(1, weight=1)

        f_w = tk.Frame(reg_grid, bg=BG_COLOR)
        f_w.grid(row=0, column=0, sticky="ew", padx=(0, 10))
        tk.Label(f_w, text="Reward Wallet Address:", bg=BG_COLOR, fg=TEXT_COLOR, font=("Arial", 9, "bold")).pack(anchor="w")
        self.entry_wallet = tk.Entry(f_w, textvariable=self.wallet_addr, bg=SECONDARY_BG, fg=TEXT_COLOR, bd=1, relief="flat", insertbackground=ACCENT_COLOR, font=("Arial", 9))
        self.entry_wallet.pack(fill="x", ipady=3, pady=2)

        f_s = tk.Frame(reg_grid, bg=BG_COLOR)
        f_s.grid(row=0, column=1, sticky="ew")
        tk.Label(f_s, text="Staking Amount (XEQM):", bg=BG_COLOR, fg=TEXT_COLOR, font=("Arial", 9, "bold")).pack(anchor="w")
        self.entry_stake = tk.Entry(f_s, textvariable=self.stake_amount, bg=SECONDARY_BG, fg=TEXT_COLOR, bd=1, relief="flat", insertbackground=ACCENT_COLOR, font=("Arial", 9, "bold"), justify="center")
        self.entry_stake.pack(fill="x", ipady=3, pady=2)

        self.reg_btn = tk.Button(reg, text="GENERATE REGISTRATION COMMANDS", command=self.generate_reg, bg="#34495e", fg="#7f8c8d", state="disabled", font=("Arial", 9, "bold"), bd=0, height=2, cursor="hand2")
        self.reg_btn.pack(fill="x", pady=(10, 5))
        self.reg_tooltip = ToolTip(self.reg_btn, "Please wait until blockchain synchronization is 100% finished.")

        cmd_frame = tk.Frame(reg, bg=BG_COLOR)
        cmd_frame.pack(fill="x", pady=5)

        self.out_text = tk.Text(
            cmd_frame, 
            height=6, 
            bg="#050a0c", 
            fg=ACCENT_COLOR, 
            font=("Consolas", 9), 
            bd=0, 
            padx=10, 
            pady=10, 
            insertbackground=ACCENT_COLOR,
            wrap="word"
        )
        
        cmd_scrollbar = ttk.Scrollbar(cmd_frame, orient="vertical", command=self.out_text.yview)
        self.out_text.configure(yscrollcommand=cmd_scrollbar.set)

        cmd_scrollbar.pack(side="right", fill="y")
        self.out_text.pack(side="left", fill="both", expand=True)
        self.out_text.bind("<Button-1>", self.copy_on_click)

        log_frame = tk.LabelFrame(self.content_frame, text=" 📝 Factory Console Output Logs ", fg=ACCENT_COLOR, bg=BG_COLOR, font=("Arial", 10, "bold"), bd=1, relief="solid")
        log_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=15, pady=(0, 15))

        self.log_widget = tk.Text(log_frame, height=6, bg="#050a0c", fg="#a0abb0", font=("Consolas", 8), bd=0, wrap="word")
        self.log_widget.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        add_hover_effect(self.btn_toggle_select, original_font=("Arial", 8, "bold"), hover_font=("Arial", 8, "bold"), hover_bg="#1c323a")
        add_hover_effect(self.btn_deploy, original_font=("Arial", 10, "bold"), hover_font=("Arial", 10, "bold"), original_bg=ACCENT_COLOR, hover_bg="#00778c")
        add_hover_effect(self.btn_restart, original_font=("Arial", 9, "bold"), hover_font=("Arial", 9, "bold"), original_bg="#e74c3c", hover_bg="#c0392b")
        add_hover_effect(self.btn_wallet_cli, original_font=("Arial", 9, "bold"), hover_font=("Arial", 9, "bold"), hover_bg="#1c323a")
        add_hover_effect(self.btn_check_updates, original_font=("Arial", 9, "bold"), hover_font=("Arial", 9, "bold"), hover_bg="#1c323a")
        add_hover_effect(self.btn_clear_logs, original_font=("Arial", 9, "bold"), hover_font=("Arial", 9, "bold"), hover_bg="#1c323a")
        add_hover_effect(self.browse_btn, original_font=("Arial", 9, "bold"), hover_font=("Arial", 9, "bold"), hover_bg="#1c323a")
        add_hover_effect(self.reg_btn, original_font=("Arial", 9, "bold"), hover_font=("Arial", 10, "bold"))

        for widget in [
            self.lbl_folder,
            self.peers_entry,
            self.entry_nodes,
            self.entry_wallet,
            self.entry_stake,
            self.out_text,
            self.log_widget
        ]:
            add_right_click(widget)
            
    def clear_console_logs(self):
        self.log_widget.delete("1.0", tk.END)
        self.logger.log("🧹 Console logs cleared successfully.")

    def check_image_updates(self):
        path = self.folder_path.get()
        if not path or path.strip() == "":
            messagebox.showwarning(
                "Folder Required", 
                "Please select your XeqM installation folder before checking for updates."
            )
            self.logger.log("⚠️ Update check skipped: Installation folder not selected.")
            return

        def _thread_task():
            self.logger.log("🔍 Checking for XeqM SN Docker image updates...")
            try:
                has_update = self.ctrl.check_for_updates(self.folder_path.get())
                if has_update:
                    self.logger.log("💡 A newer image version is available on the registry!")
                    self.root.after(0, self.prompt_for_update)
                else:
                    self.logger.log("✅ All Docker images are already up to date.")
            except Exception as e:
                self.logger.log(f"❌ Error during image update check: {e}")

        threading.Thread(target=_thread_task, daemon=True).start()

    def prompt_for_update(self):
        if messagebox.askyesno("Update Available", "A new Docker image version was found. Do you want to update and restart your nodes now?"):
            self.logger.log("🚀 User confirmed update. Recreating containers with the new version...")
            
            def _apply_task():
                self.root.after(0, self.deploy)
                self.logger.log("✅ Nodes update process triggered successfully.")
            
            threading.Thread(target=_apply_task, daemon=True).start()
        else:
            self.logger.log("⏸️ Update deferred. Remaining on the current version.")

    def toggle_all_checkboxes(self):
        if self.btn_toggle_select.cget("text") == "SELECT ALL":
            for var in self.node_vars:
                var.set(True)
            self.btn_toggle_select.configure(text="DESELECT ALL")
        else:
            for var in self.node_vars:
                var.set(False)
            self.btn_toggle_select.configure(text="SELECT ALL")

    def update_toggle_button_text(self):
        if not self.node_vars:
            self.btn_toggle_select.configure(text="SELECT ALL")
            return
        all_checked = all(var.get() for var in self.node_vars)
        if all_checked:
            self.btn_toggle_select.configure(text="DESELECT ALL")
        else:
            self.btn_toggle_select.configure(text="SELECT ALL")

    def browse_folder(self):
        path = filedialog.askdirectory()
        if path:
            self.folder_path.set(path)
            display_text = path if len(path) <= 45 else f"...{path[-42:]}"
            self.lbl_folder.configure(text=display_text, fg=TEXT_COLOR, font=("Arial", 9, "bold"))

    def update_node_checkboxes(self, *args):
        for lbl in self.status_labels:
            lbl.destroy()
        self.status_labels = []
        self.status_strips = []  
        self.node_vars = []

        try:
            nodes_count_int = int(self.nodes_count.get())
        except ValueError:
            nodes_count_int = 0

        try:
            running_containers = DockerManager.list_running_containers()
        except Exception:
            running_containers = []

        for i in range(nodes_count_int):
            var = tk.BooleanVar(value=True)
            self.node_vars.append(var)

            cell_frame = tk.Frame(self.check_frame, bg=SECONDARY_BG)
            cell_frame.pack(side="left", padx=5, pady=5)

            name = f"sn{i+1:02d}"
            
            cb = tk.Checkbutton(
                cell_frame,
                text=name,
                variable=var,
                command=self.update_toggle_button_text,
                bg=SECONDARY_BG,
                fg=TEXT_COLOR,
                selectcolor=BG_COLOR,
                activebackground=SECONDARY_BG,
                activeforeground=ACCENT_COLOR,
                font=("Segoe UI", 10, "bold"),
                padx=10,
                pady=5
            )
            cb.pack(side="top")

            color = "#2ecc71" if name in running_containers else "#e74c3c"
            strip = tk.Frame(cell_frame, height=4, bg=color)
            strip.pack(side="bottom", fill="x")

            self.status_labels.append(cell_frame)
            self.status_strips.append(strip)

        self.update_toggle_button_text()

    def update_ip_display(self):
        """Safely retrieves the IP address and prevents sticking at 'Detecting IP...'"""
        def fetch():
            try:
                ip = Network.get_public_ip()
                if ip and ip != "Unknown" and self.running and self.root.winfo_exists():
                    self.root.after(0, lambda: self.current_ip_var.set(f"IP: {ip}"))
                elif self.running and self.root.winfo_exists():
                    # Retry request after 5 seconds if IP acquisition failed
                    self.root.after(5000, self.update_ip_display)
            except Exception:
                if self.running and self.root.winfo_exists():
                    self.root.after(5000, self.update_ip_display)

        threading.Thread(target=fetch, daemon=True).start()

    def ip_changed(self, new_ip):
        """Ensures that the IP address is updated cleanly without getting stuck in 'Detecting IP...' state."""
        if not self.running or not self.root.winfo_exists():
            return

        if new_ip and new_ip != "Unknown":
            self.root.after(0, lambda: self.current_ip_var.set(f"IP: {new_ip}"))

        if getattr(self, 'is_deploying', False):
            self.logger.log(f"🌐 IP change detected ({new_ip}), but deployment is already in progress.")
            return

        if self.auto_restart.get():
            self.logger.log(f"⚠️ WATCHDOG: IP Change detected -> {new_ip}. Triggering auto-redeploy...")
            self.root.after(0, self.deploy)

    def deploy(self):
        with self._deploy_lock:
            if self.is_deploying:
                self.logger.log("⚠️ WATCHDOG/DEPLOY: Deployment already in progress. Command ignored.")
                return
            self.is_deploying = True
            
        path = self.folder_path.get()
        if not path:
            self.logger.log("❌ WATCHDOG/DEPLOY ERROR: Data folder not selected!")
            self.is_deploying = False
            return
            
        try:
            nodes_count_int = int(self.nodes_count.get())
            peers_str = self.max_out_peers.get().strip()
            peers_val = 16 if (not peers_str or peers_str == "0") else int(peers_str)
        except ValueError:
            self.logger.log("❌ DEPLOY ERROR: Invalid numeric fields.")
            self.is_deploying = False
            return
            
        if nodes_count_int <= 0:
            self.logger.log("❌ DEPLOY ERROR: Nodes Count is equal to 0!")
            self.is_deploying = False
            return

        selected = [i for i, v in enumerate(self.node_vars) if v.get()]
        if not selected:
            self.is_deploying = False
            return
        
        is_safe, error_msg = DockerManager.validate_ram_safety(selected)
        if not is_safe:
            messagebox.showerror("Resource Limit", error_msg)
            self.logger.log("❌ DEPLOY ABORTED: Insufficient system RAM available.")
            self.is_deploying = False
            return  
        
        current_ip = Network.get_public_ip()
        self.logger.log(f"🚀 Deploying nodes... IP: {current_ip} | Max Out Peers: {peers_val}")
        
        self.ctrl.run_async(
            self.ctrl.deploy_nodes, 
            self.on_deploy_finished,
            path, 
            selected, 
            current_ip,
            peers_val
        )

    def on_deploy_finished(self, result):
        self.is_deploying = False
        if result is False:
            self.logger.log("❌ DOCKER ERROR: Failed to deploy nodes!")
        else:
            self.logger.log("✅ Docker configuration applied successfully.")

    def hard_restart_docker(self):
        if messagebox.askyesno("Docker", "Emergency restart Docker Desktop?"):
            subprocess.run('taskkill /F /IM "Docker Desktop.exe"', shell=True)
            time.sleep(2)
            os.startfile("docker-desktop://")
            self.logger.log("🔄 Docker restart sent.")

    def generate_reg(self):
        if "SYNCED" not in self.net_status_var.get():
            self.logger.log("⚠️ Registration blocked: Network is not SYNCED yet.")
            return

        selected = [i for i, v in enumerate(self.node_vars) if v.get()]
        if not selected:
            self.logger.log("⚠️ Registration failed: No nodes selected in the grid.")
            return

        self.logger.log(f"⚙️ Generating registration commands for selected nodes...")

        try:
            res = Network.get_registration_cmd(selected, self.stake_amount.get(), self.wallet_addr.get())
            
            self.out_text.delete("1.0", tk.END)
            if isinstance(res, list):
                for r in res:
                    self.out_text.insert(tk.END, f"{r}\n\n")
            else:
                self.out_text.insert(tk.END, f"{res}\n\n")

            self.logger.log("✅ Registration commands generated successfully.")
        except Exception as e:
            self.logger.log(f"❌ Error generating registration commands: {e}")

    def copy_on_click(self, event):
        try:
            line_start = self.out_text.index(f"@{event.x},{event.y} linestart")
            line_end = self.out_text.index(f"@{event.x},{event.y} lineend")
            text = self.out_text.get(line_start, line_end).strip()
            
            if text:
                if ":" in text and text.startswith("SN"):
                    text = text.split(":", 1)[1].strip()
                
                if text and not text.startswith("SN") and not text.startswith("Error"):
                    self.root.clipboard_clear()
                    self.root.clipboard_append(text)
                    self.logger.log("📋 Command auto-copied!")
        except (tk.TclError, RuntimeError, AttributeError):
            pass

    def open_wallet(self):
        selected = [i for i, v in enumerate(self.node_vars) if v.get()]
        wallet_modal(f"sn{selected[0]+1:02d}" if selected else "sn01")

    def _safe_update_ui(self, ip, container_status_map, sync_status_data):
        if not self.running or not self.root.winfo_exists():
            return

        # Update IP display only when a valid IP is available (do not overwrite active IP with 'Detecting IP...')
        if hasattr(self, 'current_ip_var') and ip and ip != "Detecting IP..." and ip != "Unknown":
            self.current_ip_var.set(f"IP: {ip}")

        if hasattr(self, 'status_strips') and container_status_map:
            for i, strip in enumerate(self.status_strips):
                try:
                    if strip.winfo_exists():
                        name = f"sn{i+1:02d}"
                        color = "#2ecc71" if container_status_map.get(name, False) else "#e74c3c"
                        strip.config(bg=color)
                except tk.TclError:
                    continue

        if sync_status_data:
            h, t, is_synced = sync_status_data
            display_target = max(t, h)
            
            if hasattr(self, 'net_height_var'):
                self.net_height_var.set(f"Height: {h} / {display_target}")

            if hasattr(self, 'net_status_var'):
                if is_synced:
                    self.net_status_var.set("✅ SYNCED")
                else:
                    self.net_status_var.set("⏳ SYNCING")

            if hasattr(self, 'bar') and display_target > 0:
                percent = min((h / display_target) * 100, 100)
                self.bar.configure(value=percent)
        else:
            if hasattr(self, 'net_status_var'):
                self.net_status_var.set("❌ OFFLINE")
            if hasattr(self, 'net_height_var'):
                self.net_height_var.set("Height: 0 / 0")
            if hasattr(self, 'bar'):
                self.bar.configure(value=0)

        if hasattr(self, 'reg_btn'):
            self.reg_btn.config(state="normal", bg="#2ecc71", fg="#000000")

    def _snapshot_ui_state(self):
        try:
            nodes_count_int = 0
            try:
                nodes_count_int = int(self.nodes_count.get())
            except (ValueError, AttributeError):
                nodes_count_int = 0

            self.ui_snapshot_data = {
                "nodes_count_int": nodes_count_int,
                "auto_restart_enabled": self.auto_restart.get(),
                "node_vars_snapshot": [var.get() for var in self.node_vars],
                "current_ip_display": self.current_ip_var.get().replace("IP: ", "")
            }
        except Exception as e:
            print(f"UI snapshot error: {e}")
        finally:
            self.snapshot_event.set()

    def status_updater(self):
        last_watchdog_trigger = 0.0

        while self.running:
            try:
                if not self.running or not self.root.winfo_exists():
                    break

                # 1. SAFE DIRECT READ OF UI DATA
                try:
                    nodes_count_int = int(self.nodes_count.get() or 0)
                except (ValueError, AttributeError):
                    nodes_count_int = 0

                try:
                    auto_restart_enabled = self.auto_restart.get()
                except AttributeError:
                    auto_restart_enabled = False

                # Take a snapshot of node variables, protected against dynamic list resizing
                try:
                    node_vars_snapshot = [var.get() for var in list(self.node_vars)]
                except Exception:
                    node_vars_snapshot = []

                try:
                    current_ip_display = self.current_ip_var.get().replace("IP: ", "")
                except AttributeError:
                    current_ip_display = ""

                # 2. CHECK DOCKER CONTAINERS STATUS
                try:
                    running_containers = DockerManager.list_running_containers()
                except Exception:
                    running_containers = []

                container_status_map = {
                    f"sn{i+1:02d}": (f"sn{i+1:02d}" in running_containers) 
                    for i in range(len(node_vars_snapshot))
                }

                current_time = time.time()
                is_currently_deploying = getattr(self, 'is_deploying', False)

                # 3. AUTO-WATCHDOG LOGIC
                if auto_restart_enabled and not is_currently_deploying and (current_time - last_watchdog_trigger > 30):
                    dead_nodes_found = False
                    safe_limit = min(nodes_count_int, len(node_vars_snapshot))
                    
                    for i in range(safe_limit):
                        name = f"sn{i+1:02d}"
                        if node_vars_snapshot[i] and name not in running_containers:
                            dead_nodes_found = True
                            break

                    if dead_nodes_found:
                        self.logger.log("⚠️ WATCHDOG: Stopped node detected! Redeploying...")
                        last_watchdog_trigger = current_time
                        self.root.after(0, self.deploy)

                # 4. BLOCKCHAIN AND RPC STATUS CHECKING
                all_nodes_synced = True
                latest_sync_data = None

                for i, is_checked in enumerate(node_vars_snapshot):
                    name = f"sn{i+1:02d}"
                    rpc_port = 9231 + (i * 10)
                    
                    if is_checked and name in running_containers:
                        info = Network.get_info(rpc_port)

                        if not isinstance(info, dict) or "error" in info:
                            err_msg = str(info.get("error", "No response") if isinstance(info, dict) else info)
                            
                            if "timed out" in err_msg.lower() or "busy" in err_msg.lower():
                                status_str = "Syncing blocks (Node busy writing DB...)"
                                log_prefix = "⏳"
                            else:
                                status_str = f"Waiting for RPC... Status: {err_msg}"
                                log_prefix = "🔍"

                            if self.last_status_cache.get(name) != status_str:
                                self.last_status_cache[name] = status_str
                                self.logger.log(f"{log_prefix} [DIAGNOSTICS] {name} (RPC Port {rpc_port}): {status_str}")
                                
                            all_nodes_synced = False
                            continue

                        try:
                            h = int(info.get("height", 0))
                            t = int(info.get("target_height", 0))
                            outgoing = int(info.get("outgoing_connections_count", 0))
                            incoming = int(info.get("incoming_connections_count", 0))
                        except (ValueError, TypeError):
                            h, t, outgoing, incoming = 0, 0, 0, 0

                        total_peers = outgoing + incoming
                        target_display = max(t, h)

                        is_synced = (h > 0 and h >= target_display)

                        if h > 0:
                            latest_sync_data = (h, target_display, is_synced)

                        if h == 0:
                            all_nodes_synced = False
                            status_str = "Initializing blockchain data..."
                        elif not is_synced:
                            all_nodes_synced = False
                            left = target_display - h
                            status_str = f"Syncing blocks... ({h}/{target_display}) - {left} blocks left."
                        elif total_peers == 0:
                            all_nodes_synced = False
                            status_str = f"Blocks synced ({h}/{target_display}), searching for peers..."
                        else:
                            status_str = f"Fully Synced ({h}/{target_display}) | Active Peers: {total_peers}"

                        if self.last_status_cache.get(name) != status_str:
                            self.last_status_cache[name] = status_str
                            prefix = "✅" if is_synced and total_peers > 0 else ("⚠️" if is_synced else "🔍")
                            self.logger.log(f"{prefix} [DIAGNOSTICS] {name}: {status_str}")

                sync_status_data = latest_sync_data

                # 5. SAFELY UPDATE THE USER INTERFACE IN THE MAIN THREAD
                if self.running and self.root.winfo_exists():
                    self.root.after(
                        0, 
                        lambda c_map=container_status_map, s_data=sync_status_data, ip=current_ip_display: 
                            self._safe_update_ui(ip, c_map, s_data)
                    )

            except Exception as e:
                import traceback
                print(f"⚠️ Status updater error: {e}")
                traceback.print_exc()

            time.sleep(5)     

    def on_closing(self):
        if messagebox.askokcancel("Quit", "Do you really want to exit?"):
            self.running = False
            
            if hasattr(self, 'ip_watchdog'):
                self.ip_watchdog.stop()

            if hasattr(self, 'ctrl'):
                self.ctrl.shutdown()

            self.root.destroy()    

if __name__ == "__main__":
    import traceback

    temp_root = tk.Tk()
    temp_root.withdraw()

    docker_running = False
    try:
        output = subprocess.check_output(
            'tasklist /FI "IMAGENAME eq Docker Desktop.exe"', shell=True
        ).decode("UTF-8", errors="ignore")
        if "Docker Desktop.exe" in output:
            docker_running = True
    except Exception:
        pass

    if not docker_running:
        response = messagebox.askyesno(
            "Docker Daemon Error",
            "Docker is not running. Would you like to try starting it automatically?\n\n(If you click No, the application will still launch, but nodes might stay offline).",
            parent=temp_root
        )
        if response:
            try:
                subprocess.Popen(
                    "start docker-desktop://",
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
                direct_path = os.path.join(prog_files, "Docker", "Docker", "Docker Desktop.exe")

                if os.path.exists(direct_path):
                    os.startfile(direct_path)
                else:
                    subprocess.Popen(
                        'cmd /c start "" "docker"',
                        shell=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                time.sleep(3)
            except Exception:
                pass

    temp_root.update_idletasks()
    temp_root.destroy()

    try:
        root = tk.Tk()
        app = App(root)
        root.protocol("WM_DELETE_WINDOW", app.on_closing)
        root.mainloop()
    except Exception as e:
        print("\n❌ CRITICAL LAUNCH ERROR:")
        traceback.print_exc()