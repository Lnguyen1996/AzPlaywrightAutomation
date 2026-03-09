#!/usr/bin/env python3
"""
Removal Bot - Modern desktop app with agent pipeline visualization.
Attaches to existing Firefox via Marionette and automates Removals Central.
"""

import re
import threading
import time
import tkinter as tk
from tkinter import messagebox

try:
    import customtkinter as ctk
except ImportError:
    import subprocess, sys
    subprocess.check_call([sys.executable, "-m", "pip", "install", "customtkinter"])
    import customtkinter as ctk

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.firefox import GeckoDriverManager

URL = "https://removals-central-na.removal.scot.amazon.dev/createremovals/checkinventorypo"

# ──────────────────────────────────────────────
#  Pipeline Node States
# ──────────────────────────────────────────────
STATE_IDLE = "idle"
STATE_RUNNING = "running"
STATE_DONE = "done"
STATE_ERROR = "error"

COLORS = {
    "bg": "#0f0f0f",
    "card": "#1a1a2e",
    "card_border": "#2a2a4a",
    "accent": "#7c3aed",
    "accent_hover": "#6d28d9",
    "green": "#10b981",
    "green_hover": "#059669",
    "orange": "#f59e0b",
    "red": "#ef4444",
    "text": "#e2e8f0",
    "text_dim": "#64748b",
    "text_muted": "#475569",
    "input_bg": "#16162a",
    "node_idle": "#1e293b",
    "node_running": "#1e1b4b",
    "node_done": "#052e16",
    "node_error": "#450a0a",
    "connector": "#334155",
    "connector_active": "#7c3aed",
}

PIPELINE_STEPS = [
    {"id": "connect",  "label": "Connect",    "icon": "\u26a1", "desc": "Attach to Firefox"},
    {"id": "navigate", "label": "Navigate",   "icon": "\u2192", "desc": "Open Removals Central"},
    {"id": "fill",     "label": "Fill FNSKU",  "icon": "\u270e", "desc": "Enter ASIN values"},
    {"id": "options",  "label": "Options",     "icon": "\u2699", "desc": "Set IOGS & Reasons"},
    {"id": "search",   "label": "Search",     "icon": "\u2713", "desc": "Submit the form"},
]

# Global
driver = None


# ──────────────────────────────────────────────
#  Pipeline Canvas Widget
# ──────────────────────────────────────────────
class PipelineCanvas(tk.Canvas):
    """n8n-style horizontal pipeline visualization."""

    def __init__(self, master, steps, **kwargs):
        super().__init__(master, bg=COLORS["bg"], highlightthickness=0, height=100, **kwargs)
        self.steps = steps
        self.states = {s["id"]: STATE_IDLE for s in steps}
        self.bind("<Configure>", lambda e: self.draw())

    def set_state(self, step_id, state):
        self.states[step_id] = state
        self.draw()

    def reset(self):
        for s in self.steps:
            self.states[s["id"]] = STATE_IDLE
        self.draw()

    def draw(self):
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 10:
            return

        n = len(self.steps)
        node_w = 110
        node_h = 64
        gap = 32
        total_w = n * node_w + (n - 1) * gap
        start_x = (w - total_w) / 2

        for i, step in enumerate(self.steps):
            x = start_x + i * (node_w + gap)
            y = (h - node_h) / 2
            state = self.states[step["id"]]

            # Draw connector line to next node
            if i < n - 1:
                cx_start = x + node_w
                cx_end = x + node_w + gap
                cy = h / 2
                # Determine if connector is active
                prev_done = all(
                    self.states[self.steps[j]["id"]] in (STATE_DONE,)
                    for j in range(i + 1)
                )
                line_color = COLORS["connector_active"] if prev_done else COLORS["connector"]
                self.create_line(
                    cx_start, cy, cx_end, cy,
                    fill=line_color, width=2, arrow=tk.LAST, arrowshape=(8, 10, 4),
                )

            # Node background
            bg = {
                STATE_IDLE: COLORS["node_idle"],
                STATE_RUNNING: COLORS["node_running"],
                STATE_DONE: COLORS["node_done"],
                STATE_ERROR: COLORS["node_error"],
            }[state]

            border = {
                STATE_IDLE: COLORS["card_border"],
                STATE_RUNNING: COLORS["accent"],
                STATE_DONE: COLORS["green"],
                STATE_ERROR: COLORS["red"],
            }[state]

            # Rounded rectangle
            r = 10
            self._round_rect(x, y, x + node_w, y + node_h, r, fill=bg, outline=border, width=2)

            # Pulsing dot for running state
            if state == STATE_RUNNING:
                self.create_oval(
                    x + node_w - 16, y + 6, x + node_w - 6, y + 16,
                    fill=COLORS["accent"], outline="",
                )

            # Check mark for done
            if state == STATE_DONE:
                self.create_oval(
                    x + node_w - 18, y + 4, x + node_w - 4, y + 18,
                    fill=COLORS["green"], outline="",
                )
                self.create_text(
                    x + node_w - 11, y + 11,
                    text="\u2713", fill="white", font=("Segoe UI", 8, "bold"),
                )

            # X for error
            if state == STATE_ERROR:
                self.create_oval(
                    x + node_w - 18, y + 4, x + node_w - 4, y + 18,
                    fill=COLORS["red"], outline="",
                )
                self.create_text(
                    x + node_w - 11, y + 11,
                    text="\u2717", fill="white", font=("Segoe UI", 8, "bold"),
                )

            # Icon + Label
            self.create_text(
                x + node_w / 2, y + 22,
                text=step["icon"], fill="white", font=("Segoe UI", 14),
            )
            self.create_text(
                x + node_w / 2, y + 44,
                text=step["label"], fill=COLORS["text"], font=("Segoe UI", 9, "bold"),
            )
            # Subtitle below node
            self.create_text(
                x + node_w / 2, y + node_h + 12,
                text=step["desc"], fill=COLORS["text_dim"], font=("Segoe UI", 8),
            )

    def _round_rect(self, x1, y1, x2, y2, r, **kwargs):
        points = [
            x1 + r, y1,  x2 - r, y1,  x2, y1,  x2, y1 + r,
            x2, y2 - r,  x2, y2,  x2 - r, y2,  x1 + r, y2,
            x1, y2,  x1, y2 - r,  x1, y1 + r,  x1, y1,
        ]
        return self.create_polygon(points, smooth=True, **kwargs)


# ──────────────────────────────────────────────
#  Automation Logic
# ──────────────────────────────────────────────
def get_driver(pipeline, status_callback):
    """Connect to existing Firefox running with Marionette on port 2828."""
    global driver

    if driver is not None:
        try:
            driver.title
            return driver
        except Exception:
            driver = None

    pipeline.set_state("connect", STATE_RUNNING)
    status_callback("Connecting to Firefox on port 2828...")

    options = Options()
    service = Service(
        executable_path=GeckoDriverManager().install(),
        service_args=["--connect-existing", "--marionette-port", "2828"],
    )

    last_err = None
    for attempt in range(5):
        try:
            driver = webdriver.Firefox(service=service, options=options)
            pipeline.set_state("connect", STATE_DONE)
            status_callback("Attached to your Firefox session!")
            return driver
        except Exception as e:
            last_err = e
            status_callback(f"Waiting for Firefox... (attempt {attempt + 1}/5)")
            time.sleep(2)

    pipeline.set_state("connect", STATE_ERROR)
    msg = (
        "Could not connect to Firefox. "
        "Run RemovalBot.bat or start Firefox with: "
        "firefox --marionette --start-debugger-server 2828"
    )
    status_callback(msg)
    raise ConnectionError(f"Cannot attach to Firefox: {last_err}")


def parse_asins(raw_text):
    """Parse pasted text and extract first column (ASIN/FNSKU values).

    Handles formats like:
        B00DU18AXK US ALL ALL ALL
        B07FVCTXPW US ALL ALL ALL
    Also handles header lines like 'Channel: All' or 'ASIN Detail: ...'
    and comma-separated input.
    """
    asins = []
    for line in raw_text.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        # Skip header/label lines
        if ":" in line and not re.match(r'^[A-Z0-9]{5,}', line):
            continue
        # Extract first whitespace-separated token
        token = line.split()[0]
        # Validate it looks like an ASIN/FNSKU (alphanumeric, 5+ chars)
        if re.match(r'^[A-Z0-9]{5,}$', token):
            asins.append(token)
    # If no lines parsed, try comma-separated fallback
    if not asins:
        for token in raw_text.replace(",", " ").split():
            token = token.strip()
            if re.match(r'^[A-Z0-9]{5,}$', token):
                asins.append(token)
    return asins


def run_automation(asins, pipeline, status_callback):
    """Navigate to the page, fill FNSKUs, set options, and search."""
    global driver
    try:
        drv = get_driver(pipeline, status_callback)

        # ── Navigate ──
        pipeline.set_state("navigate", STATE_RUNNING)
        status_callback("Navigating to Removals Central...")
        drv.get(URL)
        pipeline.set_state("navigate", STATE_DONE)

        wait = WebDriverWait(drv, 30)

        # ── Fill FNSKU(s) ──
        pipeline.set_state("fill", STATE_RUNNING)
        status_callback("Filling FNSKU(s) field...")

        fnskus_input = wait.until(
            EC.presence_of_element_located((By.ID, "fnskus"))
        )
        fnskus_input.clear()
        # Join ASINs with a space as required by the form
        fnskus_input.send_keys(" ".join(asins))
        pipeline.set_state("fill", STATE_DONE)
        status_callback(f"Filled {len(asins)} ASIN(s) into FNSKU(s) field.")

        # ── Set Options (IOGS All, Removal Reasons All) ──
        pipeline.set_state("options", STATE_RUNNING)
        status_callback("Setting IOGS to All...")

        # Click the IOGS "All" checkbox
        # The All checkbox is inside #iogs_checkbox_container, first input with value="[]"
        iogs_all_cb = drv.find_element(
            By.CSS_SELECTOR,
            '#iogs_checkbox_container input[type="checkbox"][value="[]"]'
        )
        if not iogs_all_cb.is_selected():
            iogs_all_cb.click()
            time.sleep(0.5)

        status_callback("Ensuring all Removal Reasons are selected...")

        # Click the Removal Reasons "All" checkbox
        reasons_all_cb = drv.find_element(
            By.CSS_SELECTOR,
            '#reasons_checkbox_container input[type="checkbox"]'
        )
        if not reasons_all_cb.is_selected():
            reasons_all_cb.click()
            time.sleep(0.5)

        # Ensure "Check Inventory" radio is selected
        check_inv_radio = drv.find_element(By.ID, "check-inventory")
        if not check_inv_radio.is_selected():
            check_inv_radio.click()
            time.sleep(0.3)

        pipeline.set_state("options", STATE_DONE)
        status_callback("All options set.")

        # ── Click Search ──
        pipeline.set_state("search", STATE_RUNNING)
        status_callback("Clicking Search...")

        search_btn = drv.find_element(By.ID, "search-button")
        search_btn.click()

        pipeline.set_state("search", STATE_DONE)
        status_callback(f"Done! Searched {len(asins)} ASIN(s) with all options selected.")

    except ConnectionError:
        pass  # Already handled in get_driver
    except Exception as e:
        # Mark current running step as error
        for step in PIPELINE_STEPS:
            if pipeline.states[step["id"]] == STATE_RUNNING:
                pipeline.set_state(step["id"], STATE_ERROR)
        status_callback(f"Error: {e}")


# ──────────────────────────────────────────────
#  Modern GUI
# ──────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

app = ctk.CTk()
app.title("Removal Bot")
app.geometry("820x640")
app.minsize(760, 560)
app.configure(fg_color=COLORS["bg"])

# ── Header ──
header_frame = ctk.CTkFrame(app, fg_color=COLORS["bg"], corner_radius=0)
header_frame.pack(fill="x", padx=24, pady=(20, 0))

title_label = ctk.CTkLabel(
    header_frame, text="Removal Bot",
    font=ctk.CTkFont(family="Segoe UI", size=24, weight="bold"),
    text_color=COLORS["text"],
)
title_label.pack(side="left")

version_label = ctk.CTkLabel(
    header_frame, text="v3.0",
    font=ctk.CTkFont(size=12),
    text_color=COLORS["text_muted"],
)
version_label.pack(side="left", padx=(10, 0), pady=(8, 0))

# ── Pipeline ──
pipeline_frame = ctk.CTkFrame(app, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["card_border"])
pipeline_frame.pack(fill="x", padx=24, pady=(16, 0))

pipeline_title = ctk.CTkLabel(
    pipeline_frame, text="Agent Pipeline",
    font=ctk.CTkFont(size=11, weight="bold"),
    text_color=COLORS["text_dim"],
)
pipeline_title.pack(anchor="w", padx=16, pady=(12, 0))

pipeline = PipelineCanvas(pipeline_frame, PIPELINE_STEPS)
pipeline.pack(fill="x", padx=12, pady=(4, 16))

# ── Input Card ──
input_card = ctk.CTkFrame(app, fg_color=COLORS["card"], corner_radius=12, border_width=1, border_color=COLORS["card_border"])
input_card.pack(fill="both", expand=True, padx=24, pady=(12, 0))

input_header = ctk.CTkFrame(input_card, fg_color="transparent")
input_header.pack(fill="x", padx=16, pady=(12, 0))

ctk.CTkLabel(
    input_header, text="ASIN / FNSKU Input",
    font=ctk.CTkFont(size=13, weight="bold"),
    text_color=COLORS["text"],
).pack(side="left")

count_label = ctk.CTkLabel(
    input_header, text="",
    font=ctk.CTkFont(size=11),
    text_color=COLORS["green"],
)
count_label.pack(side="right")

text_input = ctk.CTkTextbox(
    input_card, font=ctk.CTkFont(family="Consolas", size=12),
    fg_color=COLORS["input_bg"], text_color=COLORS["text"],
    border_width=1, border_color=COLORS["card_border"],
    corner_radius=8, wrap="word",
)
text_input.pack(fill="both", expand=True, padx=16, pady=(8, 16))

# Placeholder text
text_input.insert("1.0", "Paste ASIN data here (e.g. B00DU18AXK US ALL ALL ALL)...")
text_input.configure(text_color=COLORS["text_muted"])


def on_input_click(event):
    current = text_input.get("1.0", "end-1c")
    if current == "Paste ASIN data here (e.g. B00DU18AXK US ALL ALL ALL)...":
        text_input.delete("1.0", tk.END)
        text_input.configure(text_color=COLORS["text"])


text_input.bind("<FocusIn>", on_input_click)

# ── Buttons ──
btn_frame = ctk.CTkFrame(app, fg_color=COLORS["bg"])
btn_frame.pack(fill="x", padx=24, pady=(12, 0))

start_btn = ctk.CTkButton(
    btn_frame, text="  Start Automation",
    font=ctk.CTkFont(size=13, weight="bold"),
    fg_color=COLORS["green"], hover_color=COLORS["green_hover"],
    height=42, corner_radius=8, width=200,
)
start_btn.pack(side="left")

disconnect_btn = ctk.CTkButton(
    btn_frame, text="Disconnect",
    font=ctk.CTkFont(size=12),
    fg_color=COLORS["orange"], hover_color="#d97706",
    height=42, corner_radius=8, width=120,
)
disconnect_btn.pack(side="left", padx=(8, 0))

clear_btn = ctk.CTkButton(
    btn_frame, text="Clear",
    font=ctk.CTkFont(size=12),
    fg_color=COLORS["card"], hover_color=COLORS["card_border"],
    border_width=1, border_color=COLORS["card_border"],
    height=42, corner_radius=8, width=80,
)
clear_btn.pack(side="left", padx=(8, 0))

# ── Status Bar ──
status_frame = ctk.CTkFrame(app, fg_color=COLORS["card"], corner_radius=8, height=36, border_width=1, border_color=COLORS["card_border"])
status_frame.pack(fill="x", padx=24, pady=(12, 16))
status_frame.pack_propagate(False)

status_dot = ctk.CTkLabel(status_frame, text="\u25cf", text_color=COLORS["green"], font=ctk.CTkFont(size=10), width=20)
status_dot.pack(side="left", padx=(12, 0))

status_label = ctk.CTkLabel(
    status_frame, text="Ready - Click Start Automation to begin",
    font=ctk.CTkFont(size=11),
    text_color=COLORS["text_dim"],
    anchor="w",
)
status_label.pack(side="left", padx=(4, 12), fill="x", expand=True)


# ── Event Handlers ──
def update_status(msg):
    app.after(0, lambda: status_label.configure(text=msg))


def on_start():
    placeholder = "Paste ASIN data here (e.g. B00DU18AXK US ALL ALL ALL)..."
    raw = text_input.get("1.0", "end-1c").strip()
    if raw == placeholder or not raw:
        messagebox.showwarning("Input Required", "Please paste ASIN data (one per line).")
        return

    asins = parse_asins(raw)
    if not asins:
        messagebox.showwarning("Input Required", "No valid ASINs/FNSKUs found in the input.")
        return

    count_label.configure(text=f"{len(asins)} ASIN(s) parsed")
    # Show parsed ASINs preview in status
    preview = " ".join(asins[:5])
    if len(asins) > 5:
        preview += f" ... (+{len(asins) - 5} more)"
    update_status(f"Parsed: {preview}")

    pipeline.reset()
    start_btn.configure(state="disabled")
    status_dot.configure(text_color=COLORS["accent"])

    def task():
        run_automation(asins, pipeline, update_status)
        app.after(0, lambda: start_btn.configure(state="normal"))
        app.after(0, lambda: status_dot.configure(text_color=COLORS["green"]))

    threading.Thread(target=task, daemon=True).start()


def on_disconnect():
    global driver
    if driver:
        try:
            driver.quit()
        except Exception:
            pass
        driver = None
    pipeline.reset()
    status_dot.configure(text_color=COLORS["text_muted"])
    update_status("Disconnected from Firefox.")


def on_clear():
    text_input.delete("1.0", tk.END)
    text_input.insert("1.0", "Paste ASIN data here (e.g. B00DU18AXK US ALL ALL ALL)...")
    text_input.configure(text_color=COLORS["text_muted"])
    count_label.configure(text="")
    pipeline.reset()
    update_status("Ready - Click Start Automation to begin")
    status_dot.configure(text_color=COLORS["green"])


start_btn.configure(command=on_start)
disconnect_btn.configure(command=on_disconnect)
clear_btn.configure(command=on_clear)

app.mainloop()
