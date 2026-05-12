#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Pomodoro Timer - 桌面番茄钟
"""

import tkinter as tk
from tkinter import ttk, messagebox
import time
import threading
import platform
import json
import os
from datetime import datetime
from pathlib import Path


# ─── Settings ────────────────────────────────────────────────────────────────

SETTINGS_FILE = Path.home() / ".pomodoro_settings.json"

DEFAULT_SETTINGS = {
    "work_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "pomodoros_before_long": 4,
    "sound_enabled": True,
    "notifications_enabled": True,
    "always_on_top": True,
}

COLORS = {
    "bg": "#f5f0eb",
    "fg": "#4a4a4a",
    "accent": "#c45a3c",
    "accent2": "#d4856a",
    "accent3": "#b0a89c",
    "surface": "#e8e2da",
    "surface2": "#d4ccc4",
    "work": "#c45a3c",
    "break": "#7a9a6d",
    "text_dim": "#8a8a8a",
}

FONTS = {
    "timer": ("Segoe UI", 72, "bold"),
    "status": ("Segoe UI", 18, "bold"),
    "counter": ("Segoe UI", 12),
    "button": ("Segoe UI", 11),
    "label": ("Segoe UI", 10),
    "title": ("Segoe UI", 14, "bold"),
}


# ─── Sound ───────────────────────────────────────────────────────────────────

def play_sound():
    """Play a notification sound."""
    if platform.system() == "Windows":
        import winsound
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    elif platform.system() == "Darwin":
        os.system("afplay /System/Library/Sounds/Ping.aiff &")
    else:
        try:
            import subprocess
            subprocess.Popen(["paplay", "/usr/share/sounds/freedesktop/stereo/complete.oga"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            print("\a")  # fallback bell


# ─── Notification ─────────────────────────────────────────────────────────────

def show_notification(title, message):
    """Show system notification."""
    if platform.system() == "Windows":
        try:
            from plyer import notification
            notification.notify(title=title, message=message, timeout=5)
        except ImportError:
            try:
                import ctypes
                ctypes.windll.user32.MessageBoxW(0, message, title, 0x40 | 0x1000)
            except Exception:
                pass
    elif platform.system() == "Darwin":
        os.system(f'osascript -e \'display notification "{message}" with title "{title}"\'')
    else:
        os.system(f'notify-send "{title}" "{message}"')


# ─── Main Application ───────────────────────────────────────────────────────

class PomodoroTimer:
    def __init__(self):
        self.settings = self._load_settings()
        self.root = tk.Tk()
        self.root.title("番茄钟")
        self.root.geometry("360x520")
        self.root.configure(bg=COLORS["bg"])
        self.root.resizable(False, False)
        self.root.attributes("-topmost", self.settings["always_on_top"])

        # Center window
        self.root.update_idletasks()
        w, h = 360, 520
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        self.root.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

        # State
        self.state = "idle"  # idle | work | short_break | long_break
        self.remaining = self.settings["work_minutes"] * 60
        self.pomodoro_count = 0
        self.running = False
        self.paused = False
        self.start_time = 0.0  # timestamp when current session started

        self._build_ui()
        self._update_timer_display()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.mainloop()

    # ── Settings ─────────────────────────────────────────────────────────

    def _load_settings(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r") as f:
                    data = json.load(f)
                    return {**DEFAULT_SETTINGS, **data}
        except Exception:
            pass
        return dict(DEFAULT_SETTINGS)

    def _save_settings(self):
        try:
            with open(SETTINGS_FILE, "w") as f:
                json.dump(self.settings, f, indent=2)
        except Exception:
            pass

    # ── UI Builder ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.root.columnconfigure(0, weight=1)

        # ── Status label ──
        self.status_var = tk.StringVar(value="🍅 准备开始")
        self.status_label = tk.Label(
            self.root, textvariable=self.status_var,
            font=FONTS["status"], fg=COLORS["fg"], bg=COLORS["bg"],
        )
        self.status_label.pack(pady=(30, 5))

        # ── Timer display ──
        self.timer_var = tk.StringVar(value="25:00")
        self.timer_label = tk.Label(
            self.root, textvariable=self.timer_var,
            font=FONTS["timer"], fg=COLORS["accent"], bg=COLORS["bg"],
        )
        self.timer_label.pack(pady=(5, 10))

        # ── Progress bar ──
        self.progress = ttk.Progressbar(
            self.root, length=280, mode="determinate",
            style="TProgressbar",
        )
        self.progress.pack(pady=(0, 20))
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            "TProgressbar", thickness=8,
            troughcolor=COLORS["surface"],
            background=COLORS["accent"],
        )
        style.configure(
            "TSeparator", background=COLORS["surface2"],
        )

        # ── Control buttons ──
        btn_frame = tk.Frame(self.root, bg=COLORS["bg"])
        btn_frame.pack(pady=10)

        self.start_btn = self._make_button(
            btn_frame, "▶ 开始", self._on_start, COLORS["accent3"], 12
        )
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.pause_btn = self._make_button(
            btn_frame, "⏸ 暂停", self._on_pause, COLORS["accent"], 12
        )
        self.pause_btn.pack(side=tk.LEFT, padx=5)
        self.pause_btn.config(state=tk.DISABLED)

        self.reset_btn = self._make_button(
            btn_frame, "⏹ 重置", self._on_reset, COLORS["text_dim"], 12
        )
        self.reset_btn.pack(side=tk.LEFT, padx=5)
        self.reset_btn.config(state=tk.DISABLED)

        # ── Pomodoro counter ──
        self.counter_var = tk.StringVar(value="今日已完成: 0 个番茄")
        self.counter_label = tk.Label(
            self.root, textvariable=self.counter_var,
            font=FONTS["counter"], fg=COLORS["text_dim"], bg=COLORS["bg"],
        )
        self.counter_label.pack(pady=(5, 5))

        # ── Separator ──
        sep = ttk.Separator(self.root, orient="horizontal")
        sep.pack(fill=tk.X, padx=40, pady=15)

        # ── Settings section ──
        settings_frame = tk.Frame(self.root, bg=COLORS["bg"])
        settings_frame.pack(pady=(0, 10))

        tk.Label(
            settings_frame, text="设置",
            font=FONTS["title"], fg=COLORS["fg"], bg=COLORS["bg"],
        ).grid(row=0, column=0, columnspan=4, pady=(0, 8))

        labels = ["工作时间:", "短休息:", "长休息:", "轮次:"]
        keys = ["work_minutes", "short_break_minutes",
                "long_break_minutes", "pomodoros_before_long"]
        self._settings_vars = {}

        for i, (label, key) in enumerate(zip(labels, keys)):
            tk.Label(
                settings_frame, text=label,
                font=FONTS["label"], fg=COLORS["fg"], bg=COLORS["bg"],
            ).grid(row=1 + i // 2, column=(i % 2) * 2, sticky="e", padx=(0, 4), pady=3)

            var = tk.StringVar(value=str(self.settings[key]))
            self._settings_vars[key] = var
            sp = tk.Spinbox(
                settings_frame, from_=1, to=99, width=4,
                textvariable=var, font=FONTS["label"],
                bg=COLORS["surface"], fg=COLORS["fg"],
                buttonbackground=COLORS["surface2"],
                relief=tk.FLAT, bd=0,
                validatecommand=(self.root.register(lambda v: v.isdigit() or v == ""), "%P"),
                validate="key",
            )
            sp.grid(row=1 + i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=(0, 12), pady=3)

            if i % 2 == 1 or i == 3:
                tk.Label(
                    settings_frame, text="min" if i < 3 else "",
                    font=FONTS["label"], fg=COLORS["text_dim"], bg=COLORS["bg"],
                ).grid(row=1 + i // 2, column=(i % 2) * 2 + 1 if i < 3 else 3, sticky="w", padx=(22, 0), pady=3)

    def _make_button(self, parent, text, command, color, size):
        return tk.Button(
            parent, text=text, command=command,
            font=("Segoe UI", size),
            bg=COLORS["surface"], fg=color,
            activebackground=COLORS["surface2"],
            activeforeground=color,
            relief=tk.FLAT, bd=0, padx=14, pady=6,
            cursor="hand2",
        )

    # ── Core Logic ───────────────────────────────────────────────────────

    def _get_session_duration(self):
        if self.state == "work":
            return self.settings["work_minutes"] * 60
        elif self.state == "short_break":
            return self.settings["short_break_minutes"] * 60
        elif self.state == "long_break":
            return self.settings["long_break_minutes"] * 60
        return 0

    def _update_timer_display(self):
        mins, secs = divmod(self.remaining, 60)
        self.timer_var.set(f"{mins:02d}:{secs:02d}")
        total = self._get_session_duration()
        if total > 0:
            pct = ((total - self.remaining) / total) * 100
            self.progress["value"] = pct

    def _update_status_text(self):
        if self.state == "idle":
            self.status_var.set("🍅 准备开始")
            self.timer_label.config(fg=COLORS["accent3"])
            style = ttk.Style()
            style.configure("TProgressbar", background=COLORS["accent3"])
        elif self.state == "work":
            self.status_var.set("🍅 工作中...")
            self.timer_label.config(fg=COLORS["work"])
            style = ttk.Style()
            style.configure("TProgressbar", background=COLORS["work"])
        elif self.state == "short_break":
            self.status_var.set("☕ 短休息")
            self.timer_label.config(fg=COLORS["break"])
            style = ttk.Style()
            style.configure("TProgressbar", background=COLORS["break"])
        elif self.state == "long_break":
            self.status_var.set("🎉 长休息")
            self.timer_label.config(fg=COLORS["accent2"])
            style = ttk.Style()
            style.configure("TProgressbar", background=COLORS["accent2"])

    def _update_button_states(self):
        if self.running and not self.paused:
            self.start_btn.config(state=tk.DISABLED, text="▶ 开始")
            self.pause_btn.config(state=tk.NORMAL, text="⏸ 暂停")
            self.reset_btn.config(state=tk.NORMAL)
        elif self.running and self.paused:
            self.start_btn.config(state=tk.NORMAL, text="▶ 继续")
            self.pause_btn.config(state=tk.DISABLED)
            self.reset_btn.config(state=tk.NORMAL)
        else:
            self.start_btn.config(state=tk.NORMAL, text="▶ 开始")
            self.pause_btn.config(state=tk.DISABLED)
            self.reset_btn.config(state=tk.DISABLED)

    def _on_start(self):
        if self.paused:
            # Resume
            self.paused = False
            self.running = True
            self._update_button_states()
            self._tick()
            return

        # Read settings
        try:
            self.settings["work_minutes"] = int(self._settings_vars["work_minutes"].get())
            self.settings["short_break_minutes"] = int(self._settings_vars["short_break_minutes"].get())
            self.settings["long_break_minutes"] = int(self._settings_vars["long_break_minutes"].get())
            self.settings["pomodoros_before_long"] = int(self._settings_vars["pomodoros_before_long"].get())
            self._save_settings()
        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字")
            return

        self.state = "work"
        self.remaining = self.settings["work_minutes"] * 60
        self.running = True
        self.paused = False
        self.start_time = time.time()
        self._update_status_text()
        self._update_button_states()
        self._tick()

    def _on_pause(self):
        if self.running and not self.paused:
            self.paused = True
            self._update_button_states()

    def _on_reset(self):
        self.running = False
        self.paused = False
        self.state = "idle"
        self.remaining = self.settings["work_minutes"] * 60
        self._update_timer_display()
        self._update_status_text()
        self._update_button_states()
        self.progress["value"] = 0

    def _tick(self):
        if not self.running or self.paused:
            return

        # Update remaining time
        elapsed = time.time() - self.start_time
        total = self._get_session_duration()
        self.remaining = max(0, int(total - elapsed))
        self._update_timer_display()

        if self.remaining <= 0:
            self._on_session_end()
            return

        # Schedule next tick (~100ms for smooth progress bar updates)
        self.root.after(100, self._tick)

    def _on_session_end(self):
        self.running = False
        self.paused = False

        # Sound & notification
        if self.settings["sound_enabled"]:
            threading.Thread(target=play_sound, daemon=True).start()

        if self.state == "work":
            self.pomodoro_count += 1
            self.counter_var.set(f"今日已完成: {self.pomodoro_count} 个番茄")

            if self.settings["notifications_enabled"]:
                threading.Thread(
                    target=show_notification,
                    args=("番茄钟", f"✅ 完成! 已专注 {self.settings['work_minutes']} 分钟"),
                    daemon=True,
                ).start()

            # Decide break type
            if self.pomodoro_count % self.settings["pomodoros_before_long"] == 0:
                self.state = "long_break"
                self.remaining = self.settings["long_break_minutes"] * 60
            else:
                self.state = "short_break"
                self.remaining = self.settings["short_break_minutes"] * 60

            # Auto-start break
            self.running = True
            self.paused = False
            self.start_time = time.time()
            self._update_status_text()
            self._update_button_states()
            self._tick()

        else:  # break ended
            if self.settings["notifications_enabled"]:
                threading.Thread(
                    target=show_notification,
                    args=("番茄钟", "⏰ 休息结束，开始新的一轮!"),
                    daemon=True,
                ).start()

            self.state = "idle"
            self.remaining = self.settings["work_minutes"] * 60
            self._update_timer_display()
            self._update_status_text()
            self._update_button_states()
            self.progress["value"] = 0

    def _on_close(self):
        if self.running:
            if not messagebox.askyesno("退出", "番茄钟正在运行，确定要退出吗?"):
                return
        self._save_settings()
        self.root.destroy()


# ─── Entry Point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    PomodoroTimer()
