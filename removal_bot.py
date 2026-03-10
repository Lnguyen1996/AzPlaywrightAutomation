#!/usr/bin/env python3
"""
Removal Bot - Modern desktop app with agent pipeline visualization.
Attaches to existing Firefox via Marionette and automates Removals Central.
"""

import base64
import datetime
import io
import os
import re
import struct
import tempfile
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


def _generate_icon_ico(size=32):
    """Generate a simple .ico file (purple bot icon) using raw pixel data.

    Returns the path to a temp .ico file, or None on failure.
    """
    try:
        # Build a 32x32 RGBA image as raw pixels
        pixels = []
        cx, cy = size // 2, size // 2
        for y in range(size):
            for x in range(size):
                dx, dy = x - cx, y - cy
                dist = (dx * dx + dy * dy) ** 0.5
                # Circular background
                if dist <= 14:
                    # Purple gradient base
                    r, g, b, a = 124, 58, 237, 255  # #7c3aed
                    # Lightning bolt shape (simple centered zigzag)
                    # Bolt: columns 13-19, rows 6-26
                    in_bolt = False
                    if 8 <= y <= 14 and (14 - (y - 8)) <= x <= (18 - (y - 8)):
                        in_bolt = True
                    elif 14 <= y <= 16 and 11 <= x <= 20:
                        in_bolt = True
                    elif 16 <= y <= 24 and (12 + (y - 16)) <= x <= (17 + (y - 16)):
                        in_bolt = True
                    if in_bolt:
                        r, g, b = 255, 255, 255
                    # Outer ring glow
                    if 12 < dist <= 14:
                        r = min(255, r + 30)
                        g = min(255, g + 15)
                        b = min(255, b + 40)
                else:
                    r, g, b, a = 0, 0, 0, 0
                pixels.append((b, g, r, a))  # BMP uses BGRA

        # Build BMP DIB data (BITMAPINFOHEADER)
        pixel_data = b""
        for row in range(size - 1, -1, -1):  # BMP is bottom-up
            for col in range(size):
                bgra = pixels[row * size + col]
                pixel_data += struct.pack("BBBB", *bgra)

        # AND mask (1bpp) — all zeros = fully opaque (alpha channel handles it)
        and_mask = b"\x00" * (size // 8) * size

        bmp_size = 40 + len(pixel_data) + len(and_mask)
        # BITMAPINFOHEADER
        dib = struct.pack(
            "<IiiHHIIiiII",
            40,           # header size
            size,         # width
            size * 2,     # height (XOR + AND)
            1,            # planes
            32,           # bpp
            0,            # compression
            len(pixel_data) + len(and_mask),
            0, 0, 0, 0,
        )

        # ICO file structure
        ico_header = struct.pack("<HHH", 0, 1, 1)  # reserved, type=ico, count=1
        data_offset = 6 + 16  # header + 1 directory entry
        ico_dir = struct.pack(
            "<BBBBHHII",
            size if size < 256 else 0,  # width
            size if size < 256 else 0,  # height
            0,     # color count
            0,     # reserved
            1,     # planes
            32,    # bpp
            len(dib) + len(pixel_data) + len(and_mask),  # data size
            data_offset,
        )

        ico_data = ico_header + ico_dir + dib + pixel_data + and_mask

        # Write to temp file
        icon_path = os.path.join(tempfile.gettempdir(), "removal_bot.ico")
        with open(icon_path, "wb") as f:
            f.write(ico_data)
        return icon_path
    except Exception:
        return None


def _generate_icon_photo(root):
    """Generate a tkinter PhotoImage icon (fallback for Linux/Mac)."""
    try:
        img = tk.PhotoImage(width=32, height=32)
        cx, cy = 16, 16
        for y in range(32):
            for x in range(32):
                dx, dy = x - cx, y - cy
                dist = (dx * dx + dy * dy) ** 0.5
                if dist <= 14:
                    # Check if in bolt shape
                    in_bolt = False
                    if 8 <= y <= 14 and (14 - (y - 8)) <= x <= (18 - (y - 8)):
                        in_bolt = True
                    elif 14 <= y <= 16 and 11 <= x <= 20:
                        in_bolt = True
                    elif 16 <= y <= 24 and (12 + (y - 16)) <= x <= (17 + (y - 16)):
                        in_bolt = True
                    color = "#ffffff" if in_bolt else "#7c3aed"
                    img.put(color, (x, y))
        return img
    except Exception:
        return None


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
    """n8n-style horizontal pipeline with real-time animated updates."""

    def __init__(self, master, steps, **kwargs):
        super().__init__(master, bg="#111125", highlightthickness=0, height=120, **kwargs)
        self.steps = steps
        self.states = {s["id"]: STATE_IDLE for s in steps}
        self._pulse_frame = 0
        self._pulse_job = None
        self.bind("<Configure>", lambda e: self.draw())

    def set_state(self, step_id, state):
        """Thread-safe state update — always dispatches to main thread."""
        self.after(0, lambda: self._apply_state(step_id, state))

    def _apply_state(self, step_id, state):
        self.states[step_id] = state
        self.draw()
        # Start or stop the pulse animation
        has_running = any(s == STATE_RUNNING for s in self.states.values())
        if has_running and self._pulse_job is None:
            self._start_pulse()
        elif not has_running and self._pulse_job is not None:
            self._stop_pulse()

    def reset(self):
        for s in self.steps:
            self.states[s["id"]] = STATE_IDLE
        self._stop_pulse()
        self._pulse_frame = 0
        self.draw()

    def _start_pulse(self):
        """Animate the running indicator with a breathing glow."""
        self._pulse_frame += 1
        self.draw()
        self._pulse_job = self.after(80, self._start_pulse)

    def _stop_pulse(self):
        if self._pulse_job is not None:
            self.after_cancel(self._pulse_job)
            self._pulse_job = None

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
        # Pulse alpha cycles 0..15 for breathing effect
        pulse = abs((self._pulse_frame % 30) - 15)

        for i, step in enumerate(self.steps):
            x = start_x + i * (node_w + gap)
            y = (h - node_h) / 2 - 4  # shift up slightly for subtitle room
            state = self.states[step["id"]]

            # ── Connector arrow to next node ──
            if i < n - 1:
                cx_start = x + node_w
                cx_end = x + node_w + gap
                cy = y + node_h / 2
                # Active if all steps up to and including this one are done
                prev_done = all(
                    self.states[self.steps[j]["id"]] == STATE_DONE
                    for j in range(i + 1)
                )
                # Animated connector: pulse if the *next* step is running
                next_running = self.states[self.steps[i + 1]["id"]] == STATE_RUNNING
                if next_running:
                    # Animated flowing dots
                    line_color = COLORS["accent"]
                    self.create_line(
                        cx_start, cy, cx_end, cy,
                        fill=line_color, width=2, dash=(6, 4),
                        dashoffset=self._pulse_frame % 10,
                    )
                    self.create_oval(
                        cx_end - 5, cy - 5, cx_end + 5, cy + 5,
                        fill=COLORS["accent"], outline="",
                    )
                elif prev_done:
                    self.create_line(
                        cx_start, cy, cx_end, cy,
                        fill=COLORS["green"], width=2,
                        arrow=tk.LAST, arrowshape=(8, 10, 4),
                    )
                else:
                    self.create_line(
                        cx_start, cy, cx_end, cy,
                        fill=COLORS["connector"], width=2,
                        arrow=tk.LAST, arrowshape=(8, 10, 4),
                    )

            # ── Node colors ──
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

            border_w = 2

            # ── Running glow ring ──
            if state == STATE_RUNNING:
                glow_expand = 2 + pulse * 0.3
                border_w = 3
                self._round_rect(
                    x - glow_expand, y - glow_expand,
                    x + node_w + glow_expand, y + node_h + glow_expand,
                    12, fill="", outline=COLORS["accent"], width=1,
                )

            # ── Node body ──
            r = 10
            self._round_rect(x, y, x + node_w, y + node_h, r, fill=bg, outline=border, width=border_w)

            # ── Status badge (top-right) ──
            bx, by = x + node_w - 11, y + 11
            if state == STATE_RUNNING:
                # Animated pulsing dot
                sz = 5 + pulse * 0.2
                self.create_oval(
                    bx - sz, by - sz, bx + sz, by + sz,
                    fill=COLORS["accent"], outline="#a78bfa", width=1,
                )
            elif state == STATE_DONE:
                self.create_oval(bx - 7, by - 7, bx + 7, by + 7, fill=COLORS["green"], outline="")
                self.create_text(bx, by, text="\u2713", fill="white", font=("Segoe UI", 7, "bold"))
            elif state == STATE_ERROR:
                self.create_oval(bx - 7, by - 7, bx + 7, by + 7, fill=COLORS["red"], outline="")
                self.create_text(bx, by, text="\u2717", fill="white", font=("Segoe UI", 7, "bold"))

            # ── Icon ──
            icon_color = {
                STATE_IDLE: COLORS["text_dim"],
                STATE_RUNNING: "#a78bfa",
                STATE_DONE: COLORS["green"],
                STATE_ERROR: COLORS["red"],
            }[state]
            self.create_text(
                x + node_w / 2, y + 22,
                text=step["icon"], fill=icon_color, font=("Segoe UI", 14),
            )

            # ── Label ──
            label_color = COLORS["text"] if state != STATE_IDLE else COLORS["text_dim"]
            self.create_text(
                x + node_w / 2, y + 44,
                text=step["label"], fill=label_color, font=("Segoe UI", 9, "bold"),
            )

            # ── Subtitle below node ──
            sub_color = {
                STATE_IDLE: COLORS["text_muted"],
                STATE_RUNNING: COLORS["accent"],
                STATE_DONE: COLORS["green"],
                STATE_ERROR: COLORS["red"],
            }[state]
            sub_text = {
                STATE_IDLE: step["desc"],
                STATE_RUNNING: "Running...",
                STATE_DONE: "Complete",
                STATE_ERROR: "Failed",
            }[state]
            self.create_text(
                x + node_w / 2, y + node_h + 14,
                text=sub_text, fill=sub_color, font=("Segoe UI", 8),
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
        # Fill FNSKU using focus + execCommand to avoid comma conversion.
        # The page may intercept .value= and reformat; execCommand simulates typing.
        asin_str = " ".join(asins)
        drv.execute_script(
            "var el = document.getElementById('fnskus');"
            "el.value = '';"
            "el.focus();"
            "document.execCommand('selectAll', false, null);"
            "document.execCommand('insertText', false, arguments[0]);",
            asin_str,
        )
        time.sleep(0.3)
        pipeline.set_state("fill", STATE_DONE)
        status_callback(f"Filled {len(asins)} ASIN(s): {asin_str}")

        # ── Set Options (step by step with delays) ──
        pipeline.set_state("options", STATE_RUNNING)

        # Step 1: Expand IOGS section by clicking its toggle
        status_callback("Expanding IOGS section...")
        drv.execute_script("""
            var iogsToggle = document.querySelector(
                '#iogs_checkbox_container'
            );
            // Make sure the checkbox container is visible
            if (iogsToggle) iogsToggle.style.display = 'block';
            // Also click the expand arrow if it exists
            var arrows = document.querySelectorAll('.toggle-selector, .expand-selector, [onclick*="iogs"]');
            arrows.forEach(function(a) { a.click(); });
        """)
        time.sleep(0.5)

        # Step 2: Set IOGS to Amazon (1)
        status_callback("Setting IOGS to Amazon (1)...")
        drv.execute_script("""
            var iogsSelect = document.getElementById('iogs');
            if (iogsSelect) {
                for (var i = 0; i < iogsSelect.options.length; i++) {
                    iogsSelect.options[i].selected = (iogsSelect.options[i].value === '1');
                }
                iogsSelect.dispatchEvent(new Event('change', {bubbles: true}));
            }
            // Sync checkboxes
            var iogsCbs = document.querySelectorAll(
                '#iogs_checkbox_container input[type="checkbox"]'
            );
            iogsCbs.forEach(function(cb) {
                if (cb.checked) cb.click();
            });
        """)
        time.sleep(0.5)

        # Step 3: Expand Warehouses section
        status_callback("Expanding Warehouses section...")
        drv.execute_script("""
            var fcsContainer = document.getElementById('fcs_checkbox_container');
            if (fcsContainer) fcsContainer.style.display = 'block';
            var arrows = document.querySelectorAll('[onclick*="fcs"]');
            arrows.forEach(function(a) { a.click(); });
        """)
        time.sleep(0.5)

        # Step 4: Check only US warehouse
        status_callback("Setting Warehouses to US...")
        drv.execute_script("""
            var fcsCbs = document.querySelectorAll(
                '#fcs_checkbox_container input[type="checkbox"]'
            );
            // Uncheck any that are checked
            fcsCbs.forEach(function(cb) {
                if (cb.checked) cb.click();
            });
        """)
        time.sleep(0.3)
        drv.execute_script("""
            var fcsCbs = document.querySelectorAll(
                '#fcs_checkbox_container input[type="checkbox"]'
            );
            // Now click US
            fcsCbs.forEach(function(cb) {
                var label = cb.parentElement;
                if (label && label.textContent.trim() === 'US') {
                    if (!cb.checked) cb.click();
                }
            });
        """)
        time.sleep(0.5)

        # Step 5: Expand Removal Reasons section
        status_callback("Expanding Removal Reasons section...")
        drv.execute_script("""
            var reasonsContainer = document.getElementById('reasons_checkbox_container');
            if (reasonsContainer) reasonsContainer.style.display = 'block';
            var arrows = document.querySelectorAll('[onclick*="reasons"]');
            arrows.forEach(function(a) { a.click(); });
        """)
        time.sleep(0.5)

        # Step 6: Check All removal reasons
        status_callback("Setting Removal Reasons to All...")
        drv.execute_script("""
            var reasonsCbs = document.querySelectorAll(
                '#reasons_checkbox_container input[type="checkbox"]'
            );
            if (reasonsCbs.length > 0) {
                var allCb = reasonsCbs[0];
                if (!allCb.checked) {
                    allCb.click();
                }
            }
        """)
        time.sleep(0.3)
        # Also select all options in the <select> directly
        drv.execute_script("""
            var reasonsSelect = document.getElementById('reasons');
            if (reasonsSelect) {
                for (var i = 0; i < reasonsSelect.options.length; i++) {
                    reasonsSelect.options[i].selected = true;
                }
            }
            // Also check Sellable and Unsellable checkboxes individually
            var reasonsCbs = document.querySelectorAll(
                '#reasons_checkbox_container input[type="checkbox"]'
            );
            reasonsCbs.forEach(function(cb) {
                if (!cb.checked) cb.click();
            });
        """)
        time.sleep(0.5)

        # Step 7: Select Check Inventory radio
        status_callback("Setting Check Inventory...")
        drv.execute_script("""
            var checkInv = document.getElementById('check-inventory');
            if (checkInv && !checkInv.checked) {
                checkInv.click();
            }
        """)
        time.sleep(0.3)

        pipeline.set_state("options", STATE_DONE)
        status_callback("Options set: IOGS=Amazon(1), Warehouses=US, Reasons=All, Check Inventory.")

        # ── Click Search ──
        pipeline.set_state("search", STATE_RUNNING)
        status_callback("Clicking Search...")

        drv.execute_script("""
            document.getElementById('search-button').click();
        """)

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
#  Polished GUI — layered cards, depth, glow
# ──────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

C = COLORS  # shorthand

app = ctk.CTk()
app.title("Removal Bot")
app.geometry("860x780")
app.minsize(800, 700)
app.configure(fg_color="#080810")

# ── Set app icon ──
_ico_path = _generate_icon_ico()
if _ico_path and os.path.exists(_ico_path):
    try:
        app.iconbitmap(_ico_path)
    except Exception:
        pass
# Fallback: iconphoto for Linux/Mac or if iconbitmap failed
_icon_photo = _generate_icon_photo(app)
if _icon_photo:
    try:
        app.iconphoto(True, _icon_photo)
    except Exception:
        pass

# ── Scrollable container so everything fits ──
main_frame = ctk.CTkFrame(app, fg_color="#080810", corner_radius=0)
main_frame.pack(fill="both", expand=True)

# ── Header bar with accent stripe ──
header_stripe = ctk.CTkFrame(main_frame, fg_color=C["accent"], height=3, corner_radius=0)
header_stripe.pack(fill="x")

header_frame = ctk.CTkFrame(main_frame, fg_color="#0d0d1a", corner_radius=0, height=60)
header_frame.pack(fill="x")
header_frame.pack_propagate(False)

header_inner = ctk.CTkFrame(header_frame, fg_color="transparent")
header_inner.pack(fill="x", padx=28, pady=12)

ctk.CTkLabel(
    header_inner, text="Removal Bot",
    font=ctk.CTkFont(family="Segoe UI", size=22, weight="bold"),
    text_color="#ffffff",
).pack(side="left")

ctk.CTkLabel(
    header_inner, text="v4.0",
    font=ctk.CTkFont(size=11),
    text_color=C["accent"],
).pack(side="left", padx=(8, 0), pady=(4, 0))

# Connection indicator
conn_dot = ctk.CTkLabel(
    header_inner, text="\u25cf  Not connected",
    font=ctk.CTkFont(size=11),
    text_color=C["text_muted"],
)
conn_dot.pack(side="right")

# Subtle separator
ctk.CTkFrame(main_frame, fg_color="#1a1a30", height=1, corner_radius=0).pack(fill="x")

# ── Content area ──
content = ctk.CTkFrame(main_frame, fg_color="#080810", corner_radius=0)
content.pack(fill="both", expand=True, padx=24, pady=(16, 20))

# ────────────────────────────────
#  Pipeline Card — elevated style
# ────────────────────────────────
# Outer glow/shadow layer
pipe_shadow = ctk.CTkFrame(content, fg_color="#0a0a18", corner_radius=16)
pipe_shadow.pack(fill="x", pady=(0, 2))

pipeline_frame = ctk.CTkFrame(
    pipe_shadow, fg_color="#111125", corner_radius=14,
    border_width=1, border_color="#252550",
)
pipeline_frame.pack(fill="x", padx=2, pady=2)

# Pipeline header with accent dot
pipe_header = ctk.CTkFrame(pipeline_frame, fg_color="transparent")
pipe_header.pack(fill="x", padx=18, pady=(14, 0))

ctk.CTkLabel(
    pipe_header, text="\u25cf",
    font=ctk.CTkFont(size=8), text_color=C["accent"],
).pack(side="left", padx=(0, 6))

ctk.CTkLabel(
    pipe_header, text="AGENT PIPELINE",
    font=ctk.CTkFont(size=10, weight="bold"),
    text_color="#8888aa",
).pack(side="left")

pipeline = PipelineCanvas(pipeline_frame, PIPELINE_STEPS)
pipeline.configure(bg="#111125")
pipeline.pack(fill="x", padx=14, pady=(6, 14))

# ────────────────────────────────
#  Input Card — elevated style
# ────────────────────────────────
input_shadow = ctk.CTkFrame(content, fg_color="#0a0a18", corner_radius=16)
input_shadow.pack(fill="both", expand=True, pady=(10, 2))

input_card = ctk.CTkFrame(
    input_shadow, fg_color="#111125", corner_radius=14,
    border_width=1, border_color="#252550",
)
input_card.pack(fill="both", expand=True, padx=2, pady=2)

input_header = ctk.CTkFrame(input_card, fg_color="transparent")
input_header.pack(fill="x", padx=18, pady=(14, 0))

ctk.CTkLabel(
    input_header, text="\u25cf",
    font=ctk.CTkFont(size=8), text_color="#3b82f6",
).pack(side="left", padx=(0, 6))

ctk.CTkLabel(
    input_header, text="ASIN / FNSKU INPUT",
    font=ctk.CTkFont(size=10, weight="bold"),
    text_color="#8888aa",
).pack(side="left")

count_label = ctk.CTkLabel(
    input_header, text="",
    font=ctk.CTkFont(size=11, weight="bold"),
    text_color=C["green"],
)
count_label.pack(side="right")

text_input = ctk.CTkTextbox(
    input_card, font=ctk.CTkFont(family="Consolas", size=12),
    fg_color="#0c0c1e", text_color=C["text"],
    border_width=1, border_color="#1e1e40",
    corner_radius=10, wrap="word",
)
text_input.pack(fill="both", expand=True, padx=18, pady=(10, 16))

PLACEHOLDER = "Paste ASIN data here (e.g. B00DU18AXK US ALL ALL ALL)..."
text_input.insert("1.0", PLACEHOLDER)
text_input.configure(text_color=C["text_muted"])


def on_input_click(event):
    if text_input.get("1.0", "end-1c") == PLACEHOLDER:
        text_input.delete("1.0", tk.END)
        text_input.configure(text_color=C["text"])


text_input.bind("<FocusIn>", on_input_click)

# ────────────────────────────────
#  Action Buttons — gradient style
# ────────────────────────────────
btn_frame = ctk.CTkFrame(content, fg_color="transparent")
btn_frame.pack(fill="x", pady=(12, 0))

start_btn = ctk.CTkButton(
    btn_frame, text="\u25b6  Start Automation",
    font=ctk.CTkFont(size=13, weight="bold"),
    fg_color="#059669", hover_color="#047857",
    text_color="#ffffff",
    height=44, corner_radius=10, width=210,
    border_width=1, border_color="#10b981",
)
start_btn.pack(side="left")

disconnect_btn = ctk.CTkButton(
    btn_frame, text="Disconnect",
    font=ctk.CTkFont(size=12),
    fg_color="#92400e", hover_color="#78350f",
    text_color="#fbbf24",
    height=44, corner_radius=10, width=120,
    border_width=1, border_color="#b45309",
)
disconnect_btn.pack(side="left", padx=(10, 0))

clear_btn = ctk.CTkButton(
    btn_frame, text="Clear",
    font=ctk.CTkFont(size=12),
    fg_color="#1e1e3a", hover_color="#2a2a50",
    text_color="#8888aa",
    height=44, corner_radius=10, width=80,
    border_width=1, border_color="#2a2a4a",
)
clear_btn.pack(side="left", padx=(10, 0))

# ────────────────────────────────
#  Log Panel — elevated style
# ────────────────────────────────
log_shadow = ctk.CTkFrame(content, fg_color="#0a0a18", corner_radius=16)
log_shadow.pack(fill="x", pady=(12, 0))

log_card = ctk.CTkFrame(
    log_shadow, fg_color="#111125", corner_radius=14,
    border_width=1, border_color="#252550",
)
log_card.pack(fill="x", padx=2, pady=2)

log_header = ctk.CTkFrame(log_card, fg_color="transparent")
log_header.pack(fill="x", padx=18, pady=(12, 0))

ctk.CTkLabel(
    log_header, text="\u25cf",
    font=ctk.CTkFont(size=8), text_color="#f59e0b",
).pack(side="left", padx=(0, 6))

ctk.CTkLabel(
    log_header, text="ACTIVITY LOG",
    font=ctk.CTkFont(size=10, weight="bold"),
    text_color="#8888aa",
).pack(side="left")

copy_log_btn = ctk.CTkButton(
    log_header, text="Copy",
    font=ctk.CTkFont(size=9),
    fg_color="#1e1e3a", hover_color=C["accent"],
    text_color="#8888aa",
    height=22, corner_radius=6, width=55,
    border_width=1, border_color="#2a2a4a",
)
copy_log_btn.pack(side="right")

log_box = ctk.CTkTextbox(
    log_card, font=ctk.CTkFont(family="Consolas", size=10),
    fg_color="#0c0c1e", text_color="#6b7280",
    border_width=1, border_color="#1e1e40",
    corner_radius=10, height=110, wrap="word",
)
log_box.pack(fill="x", padx=18, pady=(8, 14))
log_box.configure(state="disabled")


def copy_log():
    content = log_box.get("1.0", "end-1c")
    app.clipboard_clear()
    app.clipboard_append(content)


copy_log_btn.configure(command=copy_log)


# ──────────────────────────────────────────────
#  Event Handlers
# ──────────────────────────────────────────────
def update_status(msg):
    """Append a timestamped log entry."""
    def _do():
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        log_box.configure(state="normal")
        log_box.insert("end", f"[{ts}] {msg}\n")
        log_box.see("end")
        log_box.configure(state="disabled")
        # Also update connection indicator
        if "Attached" in msg:
            conn_dot.configure(text="\u25cf  Connected", text_color=C["green"])
        elif "Disconnect" in msg:
            conn_dot.configure(text="\u25cf  Not connected", text_color=C["text_muted"])
        elif "Error" in msg:
            conn_dot.configure(text="\u25cf  Error", text_color=C["red"])
    app.after(0, _do)


def on_start():
    raw = text_input.get("1.0", "end-1c").strip()
    if raw == PLACEHOLDER or not raw:
        messagebox.showwarning("Input Required", "Please paste ASIN data (one per line).")
        return

    asins = parse_asins(raw)
    if not asins:
        messagebox.showwarning("Input Required", "No valid ASINs/FNSKUs found in the input.")
        return

    count_label.configure(text=f"{len(asins)} ASIN(s)")
    preview = " ".join(asins[:5])
    if len(asins) > 5:
        preview += f" ... (+{len(asins) - 5} more)"
    update_status(f"Parsed {len(asins)} ASIN(s): {preview}")

    # Clear previous log
    log_box.configure(state="normal")
    log_box.delete("1.0", "end")
    log_box.configure(state="disabled")

    pipeline.reset()
    start_btn.configure(state="disabled", fg_color="#374151")

    def task():
        run_automation(asins, pipeline, update_status)
        app.after(0, lambda: start_btn.configure(state="normal", fg_color="#059669"))

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
    conn_dot.configure(text="\u25cf  Not connected", text_color=C["text_muted"])
    update_status("Disconnected from Firefox.")


def on_clear():
    text_input.delete("1.0", tk.END)
    text_input.insert("1.0", PLACEHOLDER)
    text_input.configure(text_color=C["text_muted"])
    count_label.configure(text="")
    pipeline.reset()
    log_box.configure(state="normal")
    log_box.delete("1.0", "end")
    log_box.configure(state="disabled")


start_btn.configure(command=on_start)
disconnect_btn.configure(command=on_disconnect)
clear_btn.configure(command=on_clear)

app.mainloop()
