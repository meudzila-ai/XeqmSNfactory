import subprocess
import tkinter as tk
import os
import sys
import time  
import re    
from tkinter import messagebox
from utils import BG_COLOR, ACCENT_COLOR, TEXT_COLOR, SECONDARY_BG, add_right_click, add_hover_effect

def _get_creationflags():
    """Returns CREATE_NO_WINDOW flag only if running on Windows OS."""
    if os.name == 'nt':
        return getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    return 0

def wallet_modal(target_node="sn01"):
    """Main UI for the XEQM Wallet Manager."""
    
    try:
        node_idx = int(target_node.replace("sn", "")) - 1
    except ValueError:
        node_idx = 0
        
    rpc_port = 9231 + (node_idx * 10)
    
    w = tk.Toplevel()
    w.title("XEQM WALLET MANAGER")
    w.transient(w.master)
    
    try:
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "xeqm.ico")
        if os.path.exists(icon_path):
            w.iconbitmap(icon_path)
    except Exception as e:
        print(f"Icon loading warning: {e}")
        
    w.configure(bg=BG_COLOR)
    w.geometry("420x450")
    w.resizable(False, False)

    mode = tk.StringVar(value="open")

    # Header
    tk.Label(w, text="WALLET GATEWAY", bg=BG_COLOR, fg=ACCENT_COLOR, 
             font=("Segoe UI", 12, "bold"), pady=20).pack()

    # Mode Selection
    m_frame = tk.Frame(w, bg=BG_COLOR)
    m_frame.pack(pady=10)
    
    rb_style = {
        "bg": BG_COLOR, "fg": TEXT_COLOR, "activebackground": BG_COLOR, 
        "activeforeground": ACCENT_COLOR, "selectcolor": SECONDARY_BG, 
        "font": ("Segoe UI", 9)
    }
    
    tk.Radiobutton(m_frame, text="OPEN EXISTING", variable=mode, value="open", **rb_style).pack(side="left", padx=15)
    tk.Radiobutton(m_frame, text="CREATE NEW", variable=mode, value="create", **rb_style).pack(side="left", padx=15)

    # Input field
    tk.Label(w, text="WALLET FILENAME", bg=BG_COLOR, fg="#667c84", font=("Segoe UI", 8, "bold")).pack(pady=(20, 0))
    
    name_ent = tk.Entry(w, width=30, bg=SECONDARY_BG, fg=TEXT_COLOR, 
                        insertbackground=ACCENT_COLOR, bd=0, font=("Consolas", 11), justify="center")
    name_ent.insert(0, "main_wallet")
    name_ent.pack(pady=10, ipady=8)
    
    add_right_click(name_ent)

    def launch():
        wallet_name = name_ent.get().strip()
        if not wallet_name:
            messagebox.showerror("Error", "Wallet file name cannot be empty.", parent=w)
            return

        if not re.match(r"^[a-zA-Z0-9_\-]+$", wallet_name):
            messagebox.showerror(
                "Security Error", 
                "Invalid characters in wallet name.\nUse only letters, numbers, hyphens, and underscores.", 
                parent=w
            )
            return

        w.config(cursor="watch")
        launch_btn.config(state="disabled")
        w.update_idletasks()

        creation_flags = _get_creationflags()
        selected_mode = mode.get()

        # --- 1. CHECK WALLET FILE EXISTENCE ---
        if selected_mode == "open":
            check_cmd = ["docker", "exec", target_node, "test", "-f", f"/data/{wallet_name}"]
            res = subprocess.run(check_cmd, capture_output=True, creationflags=creation_flags)
            
            # --- 2. PROMPT CREATION IF MISSING ---
            if res.returncode != 0:
                w.config(cursor="")
                launch_btn.config(state="normal")
                
                create_new = messagebox.askyesno(
                    "Wallet Not Found", 
                    f"Wallet '{wallet_name}' does not exist!\n\nWould you like to CREATE a new wallet with this name?",
                    parent=w
                )
                if create_new:
                    selected_mode = "create"
                    mode.set("create")
                    w.config(cursor="watch")
                    launch_btn.config(state="disabled")
                    w.update_idletasks()
                else:
                    return

        # --- 3. CONFIGURE LAUNCH COMMANDS ---
        action = "--wallet-file" if selected_mode == "open" else "--generate-new-wallet"
        wallet_path = f"/data/{wallet_name}"
        daemon_addr = f"127.0.0.1:{rpc_port}"

        # --- 4. CLEANUP LOCKS AND RUNNING INSTANCES ---
        try:
            subprocess.run(
                ["docker", "exec", target_node, "pkill", "-f", "xeqm-wallet"],
                capture_output=True,
                timeout=5,
                creationflags=creation_flags
            )
            time.sleep(0.5)
            lock_path = f"/data/{wallet_name}.lck"
            subprocess.run(
                ["docker", "exec", target_node, "rm", "-f", lock_path],
                capture_output=True,
                timeout=5,
                creationflags=creation_flags
            )
        except (subprocess.SubprocessError, OSError) as e:
            print(f"Cleanup non-fatal warning: {e}")

        # --- 5. BUILD ARGUMENTS & LAUNCH CLI TERMINAL ---
        wallet_args = [
            "/usr/local/bin/xeqm-wallet",
            action, wallet_path,
            "--daemon-address", daemon_addr
        ]
        if selected_mode == "create":
            wallet_args.append("--use-english-language-names")

        full_cmd = [
            "cmd.exe", "/c", "start",
            f"{target_node} Wallet CLI",
            "docker", "exec", "-it", target_node
        ] + wallet_args

        try:
            subprocess.Popen(full_cmd)
            w.destroy()
        except Exception as e:
            w.config(cursor="")
            launch_btn.config(state="normal")
            messagebox.showerror("Error", f"Terminal execution failed: {str(e)}", parent=w)

    launch_btn = tk.Button(
        w, 
        text="LAUNCH WALLET CLI", 
        command=launch, 
        bg=ACCENT_COLOR, 
        fg=BG_COLOR, 
        font=("Segoe UI", 10, "bold"),
        relief="flat", 
        bd=0, 
        width=22, 
        height=2,
        cursor="hand2"
    )
    launch_btn.pack(pady=15) 
    add_hover_effect(launch_btn, original_font=("Segoe UI", 10, "bold"), hover_font=("Segoe UI", 11, "bold"))    
    
    warning_text = "WARNING: If creating a new wallet, do not forget to\nwrite down your 25-word Mnemonic Seed."
    tk.Label(w, text=warning_text, bg=BG_COLOR, fg="#e74c3c", 
             font=("Segoe UI", 8, "bold"), justify="center").pack(side="bottom", pady=20)