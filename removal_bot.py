#!/usr/bin/env python3
"""
Removal Bot - Desktop app that attaches to your existing Firefox browser
via Selenium/Marionette and automates the Removals Central page.

SETUP (one-time):
  Start Firefox with Marionette enabled:
    firefox --marionette --start-debugger-server 2828

  Or add to Firefox about:config:
    marionette.port = 2828
    marionette.enabled = true
"""

import threading
import tkinter as tk
from tkinter import messagebox, ttk

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

URL = "https://removals-central-na.removal.scot.amazon.dev/createremovals/checkinventorypo"

# Global reference to the driver so we can reuse the session
driver = None


def get_driver(status_callback):
    """Connect to existing Firefox or launch a new one with the user's profile."""
    global driver

    # If we already have an active session, reuse it
    if driver is not None:
        try:
            driver.title  # test if session is alive
            return driver
        except Exception:
            driver = None

    status_callback("Connecting to Firefox...")

    options = Options()

    # Try to attach to existing Firefox running with Marionette on port 2828
    try:
        options.add_argument("--marionette")
        service = Service(
            executable_path=GeckoDriverManager().install(),
            service_args=["--connect-existing", "--marionette-port", "2828"],
        )
        driver = webdriver.Firefox(service=service, options=options)
        status_callback("Attached to existing Firefox!")
        return driver
    except Exception:
        status_callback("Could not attach. Launching new Firefox with your profile...")

    # Fallback: launch new Firefox using the user's default profile
    options = Options()
    # Use the default system Firefox instead of Playwright's
    service = Service(executable_path=GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=options)
    status_callback("New Firefox window opened.")
    return driver


def run_automation(values, raw, status_callback):
    """Navigate to the page and fill in the values."""
    global driver
    try:
        drv = get_driver(status_callback)

        status_callback("Navigating to Removals Central...")
        drv.get(URL)

        status_callback("Waiting for page to load...")
        wait = WebDriverWait(drv, 30)

        # Try common selectors for the input field
        selectors = [
            (By.TAG_NAME, "textarea"),
            (By.CSS_SELECTOR, "input[type='text']"),
            (By.CSS_SELECTOR, "input:not([type='hidden'])"),
        ]

        filled = False
        for by, selector in selectors:
            try:
                el = wait.until(EC.presence_of_element_located((by, selector)))
                el.clear()
                el.send_keys(raw)
                filled = True
                status_callback(f"Filled {len(values)} value(s) into the page.")
                break
            except Exception:
                continue

        if not filled:
            status_callback("Could not find input field. Page is open - fill manually.")

    except Exception as e:
        status_callback(f"Error: {e}")


def on_start():
    """Validate input and kick off automation in a background thread."""
    raw = text_input.get("1.0", tk.END).strip()
    if not raw:
        messagebox.showwarning("Input Required", "Please enter comma-separated values.")
        return

    values = [v.strip() for v in raw.split(",") if v.strip()]
    if not values:
        messagebox.showwarning("Input Required", "No valid values found.")
        return

    count_label.config(text=f"Values parsed: {len(values)}")

    def update_status(msg):
        root.after(0, lambda: status_label.config(text=msg))

    update_status(f"Starting automation with {len(values)} value(s)...")
    start_btn.config(state="disabled")

    def task():
        run_automation(values, raw, update_status)
        root.after(0, lambda: start_btn.config(state="normal"))

    threading.Thread(target=task, daemon=True).start()


def on_disconnect():
    """Disconnect from the browser session (does not close Firefox)."""
    global driver
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None
    status_label.config(text="Disconnected from Firefox.")


def on_clear():
    text_input.delete("1.0", tk.END)
    count_label.config(text="")


# ──────────────────────────────────────────────
#  GUI
# ──────────────────────────────────────────────
root = tk.Tk()
root.title("Removal Bot - Firefox Automation")
root.geometry("650x400")
root.resizable(True, True)
root.configure(bg="#2b2b2b")

style = ttk.Style()
style.theme_use("clam")
style.configure("TLabel", background="#2b2b2b", foreground="#e0e0e0", font=("Segoe UI", 11))
style.configure("TButton", font=("Segoe UI", 10), padding=6)
style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground="#90caf9")
style.configure("Status.TLabel", font=("Segoe UI", 10), foreground="#aaaaaa")
style.configure("Count.TLabel", font=("Segoe UI", 10), foreground="#81c784")

# Header
ttk.Label(root, text="Removal Bot", style="Header.TLabel").pack(pady=(15, 5))

# Instructions
ttk.Label(
    root,
    text="Paste comma-separated PO values below, then click Start.",
    style="TLabel",
).pack(anchor="w", padx=15)

# Text input
text_frame = tk.Frame(root, bg="#2b2b2b")
text_frame.pack(fill="both", expand=True, padx=15, pady=(5, 5))

text_input = tk.Text(
    text_frame, height=8, font=("Consolas", 11), wrap="word",
    bg="#1e1e1e", fg="#d4d4d4", insertbackground="#ffffff",
    selectbackground="#264f78", relief="flat", bd=5,
)
text_input.pack(fill="both", expand=True)

# Count label
count_label = ttk.Label(root, text="", style="Count.TLabel")
count_label.pack(anchor="w", padx=15)

# Buttons
btn_frame = tk.Frame(root, bg="#2b2b2b")
btn_frame.pack(pady=10)

start_btn = tk.Button(
    btn_frame, text="Start Automation", command=on_start,
    font=("Segoe UI", 11, "bold"), bg="#4CAF50", fg="white",
    activebackground="#45a049", relief="flat", padx=20, pady=6, cursor="hand2",
)
start_btn.pack(side="left", padx=5)

tk.Button(
    btn_frame, text="Disconnect", command=on_disconnect,
    font=("Segoe UI", 11), bg="#ff9800", fg="white",
    activebackground="#e68a00", relief="flat", padx=15, pady=6, cursor="hand2",
).pack(side="left", padx=5)

tk.Button(
    btn_frame, text="Clear", command=on_clear,
    font=("Segoe UI", 11), bg="#607d8b", fg="white",
    activebackground="#546e7a", relief="flat", padx=15, pady=6, cursor="hand2",
).pack(side="left", padx=5)

# Status bar
status_label = ttk.Label(root, text="Ready. Start Firefox with: firefox --marionette --start-debugger-server 2828", style="Status.TLabel")
status_label.pack(pady=(0, 10), padx=15, anchor="w")

root.mainloop()
