#!/usr/bin/env python3
"""
Removal Bot - Opens Firefox via Playwright to the Removals Central page
and auto-fills inventory PO values from a comma-separated input.
"""

import threading
import tkinter as tk
from tkinter import messagebox

from playwright.sync_api import sync_playwright

URL = "https://removals-central-na.removal.scot.amazon.dev/createremovals/checkinventorypo"


def run_browser(values, raw, status_callback):
    """Launch Firefox with Playwright and fill in the values."""
    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=False)
            page = browser.new_page()

            status_callback("Navigating to page...")
            page.goto(URL, wait_until="domcontentloaded", timeout=60000)

            status_callback("Page loaded. Looking for input field...")

            # Try common selectors for a text input / textarea on the page
            # Adjust these selectors if needed to match the actual page
            selectors = [
                "textarea",
                "input[type='text']",
                "input:not([type='hidden'])",
            ]

            filled = False
            for selector in selectors:
                try:
                    el = page.wait_for_selector(selector, timeout=10000)
                    if el:
                        el.click()
                        el.fill(raw)
                        filled = True
                        status_callback(f"Filled {len(values)} value(s). Browser is open.")
                        break
                except Exception:
                    continue

            if not filled:
                status_callback("Could not find input field. Browser is open - fill manually.")

            # Keep browser open until user closes it
            try:
                page.wait_for_event("close", timeout=0)
            except Exception:
                pass

            browser.close()

    except Exception as e:
        status_callback(f"Error: {e}")


def open_firefox():
    raw = text_input.get("1.0", tk.END).strip()
    if not raw:
        messagebox.showwarning("Input Required", "Please enter comma-separated values.")
        return

    values = [v.strip() for v in raw.split(",") if v.strip()]
    if not values:
        messagebox.showwarning("Input Required", "No valid values found.")
        return

    def update_status(msg):
        root.after(0, lambda: status_label.config(text=msg))

    update_status(f"Launching Firefox with {len(values)} value(s)...")

    # Run in a thread so the GUI doesn't freeze
    thread = threading.Thread(target=run_browser, args=(values, raw, update_status), daemon=True)
    thread.start()


# --- GUI ---
root = tk.Tk()
root.title("Removal Bot")
root.geometry("600x300")
root.resizable(True, True)

tk.Label(root, text="Enter comma-separated values:", font=("Arial", 12)).pack(
    anchor="w", padx=10, pady=(10, 5)
)

text_input = tk.Text(root, height=8, font=("Courier", 11), wrap="word")
text_input.pack(fill="both", expand=True, padx=10)

btn_frame = tk.Frame(root)
btn_frame.pack(pady=10)

tk.Button(btn_frame, text="Open Firefox", command=open_firefox, font=("Arial", 11),
          bg="#4CAF50", fg="white", padx=20, pady=5).pack(side="left", padx=5)

tk.Button(btn_frame, text="Clear", command=lambda: text_input.delete("1.0", tk.END),
          font=("Arial", 11), padx=20, pady=5).pack(side="left", padx=5)

status_label = tk.Label(root, text="", font=("Arial", 10), fg="gray")
status_label.pack(pady=(0, 10))

root.mainloop()
