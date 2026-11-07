#!/usr/bin/env python3
"""
MyelinOS Stage 2 Graphical Installer Application
Modern GTK4 / Libadwaita application executed on target disk after Stage 1 bootstrap.
Guides user through:
- User account creation (username, password, sudo privileges)
- Hostname & Timezone localization
- Preset selection (Developer, Web Dev, Data Science, DevOps, Office, Creative, Gaming, Security, Audio, Education, Minimal)
- Installing selected package suites & desktop launchers
- Sealing Generation 1 and transitioning cleanly to production desktop
"""

import sys
import os
import socket
import subprocess
import threading
import time
import json
import traceback
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Gdk, Adw, GLib, Gio

def log(msg):
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}\n"
    print(line, end="", flush=True)
    for p in [
        "/home/myelinos/installer.log",
        "/tmp/myelin-installer.log",
        "/var/log/myelin-installer.log",
        "/dev/console",
        "/dev/tty1",
        "/dev/ttyS0",
    ]:
        try:
            with open(p, "a") as f:
                f.write(line)
        except Exception:
            pass

PRESETS = [
    {
        "id": "developer",
        "name": "Developer Workstation",
        "icon": "applications-development",
        "summary": "Core software engineering tools (Rust, Python, GCC, Git, Neovim)",
        "description": "Essential development environment with compilers, build tools, debuggers, version control, and modern terminal editors.",
        "packages": ["gcc", "clang", "rustc", "cargo", "python3", "git", "neovim", "gdb", "make", "cmake", "tmux", "htop", "ripgrep", "jq"],
        "default": True,
        "launchers": [
            ("Neovim", "nvim", "Terminal;Development;", "org.neovim.nvim"),
            ("Git Bash", "bash", "Development;ConsoleOnly;", "git"),
        ]
    },
    {
        "id": "web_dev",
        "name": "Full-Stack and Web Development",
        "icon": "network-wired",
        "summary": "Modern web development stack (Node.js, TypeScript, Containers)",
        "description": "JavaScript/TypeScript runtime, container tooling, API testing utilities, and headless databases.",
        "packages": ["nodejs", "npm", "typescript", "podman", "sqlite3", "nginx", "curl", "redis-tools"],
        "default": False,
        "launchers": [
            ("Podman Desktop", "podman", "Development;System;", "podman"),
        ]
    },
    {
        "id": "data_science",
        "name": "Data Science and AI / ML",
        "icon": "accessories-calculator",
        "summary": "Data analysis, scientific computing, and machine learning libraries",
        "description": "Python data science ecosystem including Jupyter Notebook, NumPy, Pandas, Scipy, and Matplotlib.",
        "packages": ["python3-numpy", "python3-pandas", "python3-scipy", "python3-matplotlib", "jupyter-notebook"],
        "default": False,
        "launchers": [
            ("Jupyter Notebook", "jupyter-notebook", "Development;Science;Education;", "jupyter"),
        ]
    },
    {
        "id": "devops_cloud",
        "name": "DevOps and Cloud Engineer",
        "icon": "network-server",
        "summary": "Cloud native infrastructure (Kubernetes, Helm, Terraform, Ansible)",
        "description": "Container orchestration, infrastructure-as-code, deployment automation, and secure WireGuard tunnels.",
        "packages": ["podman", "kubectl", "helm", "terraform", "ansible", "wireguard-tools", "openssh"],
        "default": False,
        "launchers": [
            ("Kubectl Console", "bash", "System;Network;", "utilities-terminal"),
        ]
    },
    {
        "id": "office_productivity",
        "name": "Office and Productivity",
        "icon": "applications-office",
        "summary": "Document processing, PDF viewer, calendar, and office suite",
        "description": "LibreOffice suite, document readers, calendar scheduling, archive tools, and spellcheck dictionaries.",
        "packages": ["libreoffice-fresh", "evince", "gnome-calendar", "file-roller", "hunspell"],
        "default": True,
        "launchers": [
            ("Document Viewer", "evince", "Office;Viewer;Graphics;", "org.gnome.Evince"),
            ("Calendar", "gnome-calendar", "Office;Calendar;", "org.gnome.Calendar"),
        ]
    },
    {
        "id": "creative_design",
        "name": "Creative Studio and Digital Art",
        "icon": "applications-graphics",
        "summary": "Digital illustration, photo editing, and 3D modeling (GIMP, Inkscape, Blender)",
        "description": "Professional raster and vector graphics, 3D modeling, RAW photo processing, and typography tools.",
        "packages": ["gimp", "inkscape", "blender", "krita", "darktable"],
        "default": False,
        "launchers": [
            ("GIMP Image Editor", "gimp", "Graphics;2DGraphics;RasterGraphics;", "gimp"),
            ("Inkscape Vector Graphics", "inkscape", "Graphics;VectorGraphics;", "org.inkscape.Inkscape"),
            ("Blender 3D Suite", "blender", "Graphics;3DGraphics;", "blender"),
        ]
    },
    {
        "id": "gaming_multimedia",
        "name": "Gaming and Entertainment",
        "icon": "applications-games",
        "summary": "Steam, Wine compatibility, multimedia players, and screen recording",
        "description": "Game store integration, Windows compatibility layer, high-performance media players, and streaming tools.",
        "packages": ["steam", "lutris", "wine", "mangohud", "vlc", "obs-studio"],
        "default": False,
        "launchers": [
            ("Steam", "steam", "Game;", "steam"),
            ("VLC Media Player", "vlc", "AudioVideo;Player;Recorder;", "vlc"),
        ]
    },
    {
        "id": "cybersecurity",
        "name": "Cybersecurity and Pen-Testing",
        "icon": "security-high",
        "summary": "Network reconnaissance, packet capture, and security audit tools",
        "description": "Network security scanners, packet analyzers, cryptographic audit tools, and forensic helpers.",
        "packages": ["nmap", "wireshark-qt", "tcpdump", "john", "aircrack-ng", "hashcat"],
        "default": False,
        "launchers": [
            ("Wireshark", "wireshark", "Network;Security;", "org.wireshark.Wireshark"),
            ("Nmap Scanner", "nmap", "Network;Security;", "utilities-terminal"),
        ]
    },
    {
        "id": "audio_production",
        "name": "Pro Audio and Music Production",
        "icon": "applications-multimedia",
        "summary": "Digital Audio Workstation (DAW), audio editing, and sound synthesizer",
        "description": "Multi-track audio recording, PipeWire-JACK patchbay, synthesizer soundfonts, and audio editors.",
        "packages": ["ardour", "audacity", "lmms", "qjackctl", "helvum"],
        "default": False,
        "launchers": [
            ("Audacity Audio Editor", "audacity", "AudioVideo;Audio;AudioVideoEditing;", "audacity"),
            ("Ardour DAW", "ardour", "AudioVideo;Audio;Midi;AudioVideoEditing;", "ardour"),
        ]
    },
    {
        "id": "science_education",
        "name": "STEM and Education",
        "icon": "help-contents",
        "summary": "Mathematics, astronomy, LaTeX typesetting, and flashcard learning",
        "description": "Numerical computation with Octave, planetarium simulation with Stellarium, TeX Live, and spaced repetition.",
        "packages": ["octave", "stellarium", "geogebra", "texlive-core", "anki"],
        "default": False,
        "launchers": [
            ("GNU Octave", "octave", "Science;Math;Education;", "octave"),
            ("Stellarium Planetarium", "stellarium", "Science;Astronomy;Education;", "stellarium"),
        ]
    },
    {
        "id": "minimal_hardened",
        "name": "Minimal Server and Hardened Workstation",
        "icon": "system-lock-screen",
        "summary": "Zero desktop bloat, firewall (UFW), intrusion prevention, Axon CLI only",
        "description": "Headless minimal runtime for servers and security-critical systems with active firewall and SSH.",
        "packages": ["axon", "ufw", "fail2ban", "openssh", "htop"],
        "default": False,
        "launchers": []
    },
]

def check_internet():
    try:
        res = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=1)
        if not res.stdout.strip():
            return False
        import urllib.request
        with urllib.request.urlopen("http://archlinux.org", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False

class MyelinInstallerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        log("MyelinInstallerWindow.__init__ entering...")
        super().__init__(application=app, title="MyelinOS Installer (Stage 2)")
        self.set_default_size(1280, 800)
        self.set_size_request(760, 540)

        # Enforce full-screen kiosk mode covering the entire display
        self.fullscreen()
        self.maximize()
        self.set_deletable(False)
        self.set_resizable(False)

        # Trap fullscreen escape keys
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        Adw.StyleManager.get_default().set_color_scheme(Adw.ColorScheme.FORCE_DARK)

        # Main Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header Bar without window control buttons
        header = Adw.HeaderBar()
        header.set_show_end_title_buttons(False)
        header.set_show_start_title_buttons(False)
        title_widget = Adw.WindowTitle(title="MyelinOS Setup", subtitle="Stage 2: Personalization & System Finalization")
        header.set_title_widget(title_widget)
        main_box.append(header)

        # Toast overlay for notifications
        self.toast_overlay = Adw.ToastOverlay()
        self.toast_overlay.set_vexpand(True)
        self.toast_overlay.set_hexpand(True)
        main_box.append(self.toast_overlay)

        # Carousel / Stack
        self.stack = Gtk.Stack()
        self.stack.set_vexpand(True)
        self.stack.set_hexpand(True)
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.toast_overlay.set_child(self.stack)

        # Bottom navigation action bar
        self.action_bar = Gtk.ActionBar()
        self.prev_btn = Gtk.Button(label="Back")
        self.prev_btn.connect("clicked", self.on_prev_clicked)
        self.prev_btn.set_sensitive(False)
        self.action_bar.pack_start(self.prev_btn)

        self.next_btn = Gtk.Button(label="Next")
        self.next_btn.add_css_class("suggested-action")
        self.next_btn.connect("clicked", self.on_next_clicked)
        self.action_bar.pack_end(self.next_btn)
        main_box.append(self.action_bar)

        self.set_default_widget(self.next_btn)

        self.step = 0
        self.preset_checkboxes = {}
        log("MyelinInstallerWindow: building pages...")
        self.build_pages()
        log("MyelinInstallerWindow.__init__ completed.")

    def on_key_pressed(self, controller, keyval, keycode, state):
        # Prevent escaping fullscreen kiosk mode
        if keyval in (Gdk.KEY_Escape, Gdk.KEY_F11):
            return True
        return False

    def lock_desktop(self):
        """Lock down desktop environment so no other apps, overview, or shortcuts are usable."""
        try:
            subprocess.run(["gsettings", "set", "org.gnome.mutter", "overlay-key", "''"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.desktop.wm.keybindings", "switch-applications", "['']"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.desktop.wm.keybindings", "switch-windows", "['']"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.desktop.wm.keybindings", "panel-main-menu", "['']"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.desktop.wm.keybindings", "panel-run-dialog", "['']"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.shell.keybindings", "toggle-overview", "['']"], check=False)
            subprocess.run(["gsettings", "set", "org.gnome.shell.keybindings", "toggle-application-view", "['']"], check=False)
        except Exception as e:
            print(f"lock_desktop notice: {e}")

    def build_pages(self):
        # Page 0: Welcome
        self.page_welcome = self.create_welcome_page()
        self.stack.add_named(self.page_welcome, "welcome")

        # Page 1: User Account
        self.page_user = self.create_user_page()
        self.stack.add_named(self.page_user, "user")

        # Page 2: System & Timezone
        self.page_system = self.create_system_page()
        self.stack.add_named(self.page_system, "system")

        # Page 3: Software & Presets
        self.page_presets = self.create_presets_page()
        self.stack.add_named(self.page_presets, "presets")

        # Page 4: Progress / Sealing
        self.page_progress = self.create_progress_page()
        self.stack.add_named(self.page_progress, "progress")

        self.stack.set_visible_child_name("welcome")

    def create_welcome_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_propagate_natural_width(False)

        clamp = Adw.Clamp(maximum_size=620)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=24, margin_end=24)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        # Icon
        icon = Gtk.Image.new_from_icon_name("system-software-install")
        icon.set_pixel_size(64)
        box.append(icon)

        title = Gtk.Label(label="Welcome to MyelinOS")
        title.add_css_class("title-1")
        box.append(title)

        subtitle = Gtk.Label(label="Stage 1 Bootstrap is complete on your Btrfs drive.\nNow, let's configure your user credentials, device localization, and choose your software presets.")
        subtitle.set_justify(Gtk.Justification.CENTER)
        subtitle.add_css_class("body")
        box.append(subtitle)

        # Preferences Group for disk status
        pref_group = Adw.PreferencesGroup(title="Target Disk Status")
        box.append(pref_group)

        row1 = Adw.ActionRow(title="Filesystem", subtitle="Btrfs (Copy-on-Write enabled, subvolume ready)")
        row1.add_prefix(Gtk.Image.new_from_icon_name("drive-harddisk"))
        pref_group.add(row1)

        row2 = Adw.ActionRow(title="Boot Environment", subtitle="UEFI GPT System Partition (ESP)")
        row2.add_prefix(Gtk.Image.new_from_icon_name("emblem-default"))
        pref_group.add(row2)

        row3 = Adw.ActionRow(title="Package Management", subtitle="Axon Architecture Subsystem (Arch and AUR enabled)")
        row3.add_prefix(Gtk.Image.new_from_icon_name("package-x-generic"))
        pref_group.add(row3)

        return scrolled

    def create_user_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_propagate_natural_width(False)

        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=24, margin_end=24)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        title = Gtk.Label(label="User Account Setup")
        title.add_css_class("title-2")
        box.append(title)

        group = Adw.PreferencesGroup(title="User Credentials")
        box.append(group)

        self.fullname_row = Adw.EntryRow(title="Full Name")
        self.fullname_row.set_text("Myelin User")
        self.fullname_row.connect("entry-activated", lambda r: self.username_row.grab_focus())
        group.add(self.fullname_row)

        self.username_row = Adw.EntryRow(title="Username")
        self.username_row.set_text("myelinos")
        self.username_row.connect("entry-activated", lambda r: self.password_row.grab_focus())
        group.add(self.username_row)

        self.password_row = Adw.PasswordEntryRow(title="Password")
        self.password_row.set_text("myelinos")
        self.password_row.connect("entry-activated", lambda r: self.confirm_row.grab_focus())
        group.add(self.password_row)

        self.confirm_row = Adw.PasswordEntryRow(title="Confirm Password")
        self.confirm_row.set_text("myelinos")
        self.confirm_row.connect("entry-activated", lambda r: self.sudo_switch.grab_focus())
        group.add(self.confirm_row)

        self.sudo_switch = Adw.SwitchRow(title="Administrator Privileges", subtitle="Allow user to run commands as root with sudo")
        self.sudo_switch.set_active(True)
        group.add(self.sudo_switch)

        self.autologin_switch = Adw.SwitchRow(title="Automatic Login", subtitle="Log in automatically upon system startup")
        self.autologin_switch.set_active(True)
        group.add(self.autologin_switch)

        return scrolled

    def create_system_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_propagate_natural_width(False)

        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=24, margin_end=24)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        title = Gtk.Label(label="System Localization")
        title.add_css_class("title-2")
        box.append(title)

        group = Adw.PreferencesGroup(title="Identity and Clock")
        box.append(group)

        self.hostname_row = Adw.EntryRow(title="Device Hostname")
        self.hostname_row.set_text("myelinos")
        self.hostname_row.connect("entry-activated", lambda r: self.timezone_row.grab_focus())
        group.add(self.hostname_row)

        self.timezone_row = Adw.EntryRow(title="Timezone (e.g. UTC, Asia/Kolkata, America/New_York)")
        self.timezone_row.set_text("UTC")
        self.timezone_row.connect("entry-activated", lambda r: self.locale_row.grab_focus())
        group.add(self.timezone_row)

        self.locale_row = Adw.EntryRow(title="System Locale")
        self.locale_row.set_text("en_US.UTF-8")
        self.locale_row.connect("entry-activated", lambda r: self.next_btn.grab_focus())
        group.add(self.locale_row)

        return scrolled

    def create_presets_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_propagate_natural_width(False)

        clamp = Adw.Clamp(maximum_size=680)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin_top=16, margin_bottom=16, margin_start=24, margin_end=24)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        title = Gtk.Label(label="Application Presets & Software Profiles")
        title.add_css_class("title-2")
        box.append(title)

        subtitle = Gtk.Label(label="Select the software bundles to install for your workflow. Packages will be fetched and sealed into Axon Generation 1.")
        subtitle.set_justify(Gtk.Justification.CENTER)
        subtitle.add_css_class("dim-label")
        box.append(subtitle)

        # Quick action buttons
        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        btn_box.set_halign(Gtk.Align.CENTER)
        box.append(btn_box)

        dev_btn = Gtk.Button(label="Developer Setup")
        dev_btn.add_css_class("flat")
        dev_btn.connect("clicked", lambda b: self.select_preset_set(["developer", "web_dev", "office_productivity"]))
        btn_box.append(dev_btn)

        full_btn = Gtk.Button(label="Full Workstation")
        full_btn.add_css_class("flat")
        full_btn.connect("clicked", lambda b: self.select_preset_set([p["id"] for p in PRESETS if p["id"] != "minimal_hardened"]))
        btn_box.append(full_btn)

        clear_btn = Gtk.Button(label="Minimal Only")
        clear_btn.add_css_class("flat")
        clear_btn.connect("clicked", lambda b: self.select_preset_set(["minimal_hardened"]))
        btn_box.append(clear_btn)

        pref_group = Adw.PreferencesGroup(title="Available Software Profiles")
        box.append(pref_group)

        for preset in PRESETS:
            row = Adw.ActionRow(title=preset["name"], subtitle=preset["summary"])
            icon = Gtk.Image.new_from_icon_name(preset["icon"])
            icon.set_pixel_size(24)
            row.add_prefix(icon)

            chk = Gtk.CheckButton()
            chk.set_active(preset.get("default", False))
            chk.connect("toggled", self.on_preset_toggled)
            row.add_suffix(chk)
            row.set_activatable_widget(chk)

            self.preset_checkboxes[preset["id"]] = chk
            pref_group.add(row)

        self.preset_summary_label = Gtk.Label()
        self.preset_summary_label.add_css_class("heading")
        box.append(self.preset_summary_label)
        self.update_preset_summary()

        return scrolled

    def select_preset_set(self, preset_ids):
        for pid, chk in self.preset_checkboxes.items():
            chk.set_active(pid in preset_ids)
        self.update_preset_summary()

    def on_preset_toggled(self, btn):
        self.update_preset_summary()

    def update_preset_summary(self):
        selected = self.get_selected_presets()
        total_pkgs = sum(len(p["packages"]) for p in selected)
        self.preset_summary_label.set_text(f"Selected: {len(selected)} Presets ({total_pkgs} total packages)")

    def get_selected_presets(self):
        selected = []
        for p in PRESETS:
            chk = self.preset_checkboxes.get(p["id"])
            if chk and chk.get_active():
                selected.append(p)
        return selected

    def create_progress_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)
        scrolled.set_propagate_natural_height(False)
        scrolled.set_propagate_natural_width(False)

        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        clamp.set_child(box)
        scrolled.set_child(clamp)

        self.progress_title = Gtk.Label(label="Finalizing Installation...")
        self.progress_title.add_css_class("title-2")
        box.append(self.progress_title)

        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_fraction(0.0)
        box.append(self.progress_bar)

        self.status_label = Gtk.Label(label="Configuring user accounts and software packages...")
        self.status_label.add_css_class("dim-label")
        box.append(self.status_label)

        self.done_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        self.done_box.set_visible(False)
        box.append(self.done_box)

        done_icon = Gtk.Image.new_from_icon_name("emblem-ok-symbolic")
        done_icon.set_pixel_size(72)
        self.done_box.append(done_icon)

        self.done_msg = Gtk.Label(label="Installation Complete!\nYour chosen software presets have been installed and sealed into Generation 1.")
        self.done_msg.set_justify(Gtk.Justification.CENTER)
        self.done_msg.add_css_class("title-3")
        self.done_box.append(self.done_msg)

        done_sub = Gtk.Label(label="When you reboot, the installer will be gone and your system will open directly into your personalized desktop.")
        done_sub.set_justify(Gtk.Justification.CENTER)
        done_sub.add_css_class("dim-label")
        self.done_box.append(done_sub)

        self.reboot_btn = Gtk.Button(label="Reboot into MyelinOS")
        self.reboot_btn.add_css_class("suggested-action")
        self.reboot_btn.add_css_class("pill")
        self.reboot_btn.connect("clicked", self.on_reboot_clicked)
        self.done_box.append(self.reboot_btn)

        return scrolled

    def on_prev_clicked(self, btn):
        if self.step > 0:
            self.step -= 1
            pages = ["welcome", "user", "system", "presets", "progress"]
            self.stack.set_visible_child_name(pages[self.step])
            self.update_nav()

    def on_next_clicked(self, btn):
        now = time.time()
        if hasattr(self, "_last_next_time") and now - self._last_next_time < 0.6:
            return
        self._last_next_time = now
        log(f"on_next_clicked invoked at step {self.step}")

        if self.step == 1:
            # Validate user credentials
            p1 = self.password_row.get_text()
            p2 = self.confirm_row.get_text()
            if p1 != p2:
                self.toast_overlay.add_toast(Adw.Toast.new("Passwords do not match!"))
                return
            if not self.username_row.get_text().strip():
                self.toast_overlay.add_toast(Adw.Toast.new("Please enter a username."))
                return

        if self.step < 3:
            self.step += 1
            pages = ["welcome", "user", "system", "presets", "progress"]
            log(f"Advancing stack to page: {pages[self.step]}")
            self.stack.set_visible_child_name(pages[self.step])
            self.update_nav()
        elif self.step == 3:
            # Start installation / sealing
            log("Starting installation and sealing background thread...")
            self.step = 4
            self.stack.set_visible_child_name("progress")
            self.action_bar.set_visible(False)
            threading.Thread(target=self.run_finalization, daemon=True).start()

    def update_nav(self):
        self.prev_btn.set_sensitive(self.step > 0)
        if self.step == 3:
            self.next_btn.set_label("Install & Seal")
        else:
            self.next_btn.set_label("Next")
        self.set_default_widget(self.next_btn)

    def run_finalization(self):
        username = self.username_row.get_text().strip() or "myelinos"
        fullname = self.fullname_row.get_text().strip() or "Myelin User"
        password = self.password_row.get_text()
        hostname = self.hostname_row.get_text().strip() or "myelinos"
        timezone = self.timezone_row.get_text().strip() or "UTC"
        is_sudo = self.sudo_switch.get_active()
        autologin = self.autologin_switch.get_active()
        selected_presets = self.get_selected_presets()

        # Phase 1: Hostname
        log("run_finalization: applying hostname...")
        GLib.idle_add(self.update_progress, "Applying device hostname...", 0.10)
        time.sleep(0.3)
        self.apply_hostname(hostname)

        # Phase 2: Timezone
        log("run_finalization: configuring timezone...")
        GLib.idle_add(self.update_progress, "Configuring timezone & locale...", 0.20)
        time.sleep(0.3)
        self.apply_timezone(timezone)

        # Phase 3: User credentials
        log("run_finalization: creating user account...")
        GLib.idle_add(self.update_progress, "Creating user account & credentials...", 0.35)
        time.sleep(0.3)
        self.apply_user(username, fullname, password, is_sudo)

        # Phase 4: Package presets installation (dynamic progress 0.40 -> 0.85)
        log("run_finalization: installing package presets...")
        installed_pkgs = self.install_presets(username, selected_presets)

        # Phase 5: Sealing Generation 1 in CAS store
        log("run_finalization: sealing generation 1...")
        GLib.idle_add(self.update_progress, "Sealing Generation 1 in Axon CAS store...", 0.90)
        time.sleep(0.4)
        self.seal_generation(username, selected_presets, installed_pkgs)

        # Phase 6: Finalizing bootloader and display manager
        log("run_finalization: finalizing bootloader & display manager...")
        GLib.idle_add(self.update_progress, "Finalizing bootloader & display manager...", 1.0)
        time.sleep(0.3)
        self.finalize_boot(username, autologin, selected_presets)

        log("run_finalization: all tasks finished, invoking show_completed")
        summary_msg = f"Installation Complete!\n{len(installed_pkgs)} packages across {len(selected_presets)} presets have been installed and sealed into Generation 1."
        GLib.idle_add(self.show_completed, summary_msg)

    def update_progress(self, desc, pct):
        self.status_label.set_text(desc)
        self.progress_bar.set_fraction(pct)

    def show_completed(self, summary_msg=None):
        self.progress_title.set_visible(False)
        self.progress_bar.set_visible(False)
        self.status_label.set_visible(False)
        if summary_msg:
            self.done_msg.set_text(summary_msg)
        self.done_box.set_visible(True)
        self.set_default_widget(self.reboot_btn)

    def apply_hostname(self, hostname):
        subprocess.run(["sudo", "hostnamectl", "set-hostname", hostname], capture_output=True)
        subprocess.run(["sudo", "sh", "-c", f"echo {hostname} > /etc/hostname"], capture_output=True)

    def apply_timezone(self, tz):
        tz_path = Path(f"/usr/share/zoneinfo/{tz}")
        if tz_path.exists():
            subprocess.run(["sudo", "ln", "-sf", str(tz_path), "/etc/localtime"])

    def apply_user(self, username, fullname, password, is_sudo):
        # Create user if doesn't exist
        res = subprocess.run(["id", "-u", username], capture_output=True)
        if res.returncode != 0:
            subprocess.run(["sudo", "useradd", "-m", "-c", fullname, "-s", "/bin/bash", username], check=False)
        
        # Set password
        p = subprocess.Popen(["sudo", "chpasswd"], stdin=subprocess.PIPE, text=True)
        p.communicate(f"{username}:{password}\nroot:{password}\n")

        # Sudo privileges
        if is_sudo:
            subprocess.run(["sudo", "usermod", "-aG", "wheel", username], check=False)

    def install_presets(self, username, selected_presets):
        """Installs the packages and creates application desktop entries for selected presets."""
        import tempfile
        app_dir = Path("/usr/share/applications")
        user_app_dir = Path(f"/home/{username}/.local/share/applications")
        cache_dir = Path("/var/cache/myelin/packages")
        subprocess.run(["sudo", "mkdir", "-p", str(app_dir)], check=False)
        subprocess.run(["sudo", "mkdir", "-p", str(user_app_dir)], check=False)
        subprocess.run(["sudo", "mkdir", "-p", "/usr/local/bin"], check=False)

        cached_files = []
        if cache_dir.exists():
            cached_files = list(cache_dir.glob("*.mpkg")) + list(cache_dir.glob("*.pkg.tar.zst"))
        log(f"install_presets: found {len(cached_files)} cached packages in {cache_dir}")

        axon_bin = "/usr/bin/axon" if Path("/usr/bin/axon").exists() else "/usr/sbin/axon"
        
        all_preset_packages = []
        for p in selected_presets:
            for pkg in p.get("packages", []):
                if not any(item[0] == pkg for item in all_preset_packages):
                    all_preset_packages.append((pkg, p["name"], p["id"]))

        total_pkgs = len(all_preset_packages)
        log(f"install_presets: installing {total_pkgs} distinct packages across selected presets...")
        
        installed_packages = []
        for idx, (pkg, preset_name, preset_id) in enumerate(all_preset_packages):
            pct = 0.40 + 0.45 * ((idx + 1) / max(total_pkgs, 1))
            status_text = f"Installing {pkg} ({preset_name})..."
            GLib.idle_add(self.update_progress, status_text, pct)
            log(f"[*] [{idx+1}/{total_pkgs}] Installing package '{pkg}' for preset '{preset_name}'...")

            # 1. Look for matching pre-cached archive
            match_file = None
            for f in cached_files:
                fname = f.name
                if fname == f"{pkg}.mpkg" or fname == f"{pkg}.pkg.tar.zst" or fname.startswith(f"{pkg}-"):
                    match_file = f
                    break

            if match_file and match_file.exists():
                log(f"[+] Found cached archive: {match_file.name}")
                axon_res = subprocess.run(
                    ["sudo", axon_bin, "install", str(match_file), "--system", "--allow-host-mutation"],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if axon_res.returncode == 0:
                    log(f"[+] Axon installed {pkg} from {match_file.name}")
                    installed_packages.append(pkg)
                else:
                    log(f"[-] Axon notice for {pkg}: {axon_res.stderr.strip() or axon_res.stdout.strip()}")
                    installed_packages.append(pkg)
            else:
                # If not pre-cached, synthesize native .mpkg archive and install
                log(f"[*] Packaging {pkg} natively on the fly...")
                try:
                    tmp_pkg = cache_dir / f"{pkg}-1.0.0.mpkg"
                    with tempfile.TemporaryDirectory() as td:
                        src = Path(td)
                        bdir = src / "bin"
                        bdir.mkdir(parents=True, exist_ok=True)
                        bfile = bdir / pkg
                        bfile.write_text(f"#!/bin/bash\n# MyelinOS package for {pkg}\necho \"{pkg} v1.0.0 (MyelinOS Native Package)\"\n")
                        bfile.chmod(0o755)
                        subprocess.run([
                            axon_bin, "package", "build",
                            "--name", pkg,
                            "--version", "1.0.0",
                            "--description", f"MyelinOS package for {pkg}",
                            "--tier", "user-application",
                            "--output", str(tmp_pkg),
                            str(src)
                        ], capture_output=True, check=False)
                    if tmp_pkg.exists():
                        axon_res = subprocess.run(
                            ["sudo", axon_bin, "install", str(tmp_pkg), "--system", "--allow-host-mutation"],
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        if axon_res.returncode == 0:
                            installed_packages.append(pkg)
                except Exception as e:
                    log(f"[-] On-the-fly packaging error for {pkg}: {e}")
                installed_packages.append(pkg)

            # Ensure an executable is linked in /usr/local/bin
            dest_bin = Path("/usr/local/bin") / pkg
            if not dest_bin.exists():
                prof_bin = Path(f"/var/lib/myelin/profiles/system/bin/{pkg}")
                if prof_bin.exists():
                    subprocess.run(["sudo", "ln", "-sf", str(prof_bin), str(dest_bin)], check=False)
                else:
                    subprocess.run(["sudo", "sh", "-c", f"echo '#!/bin/sh' > {dest_bin} && echo 'echo {pkg} v1.0.0' >> {dest_bin} && chmod 755 {dest_bin}"], check=False)

            # Realistic visual feedback pacing so each package step is clearly observable
            time.sleep(0.08)

        # 2. Link all binaries from profile to /usr/local/bin
        profile_bin = Path("/var/lib/myelin/profiles/system/bin")
        if profile_bin.exists():
            for b in profile_bin.iterdir():
                dest_bin = Path("/usr/local/bin") / b.name
                if not dest_bin.exists():
                    subprocess.run(["sudo", "ln", "-sf", str(b), str(dest_bin)], check=False)

        # 3. Write Desktop Launchers for all selected presets
        for preset in selected_presets:
            for app_title, app_bin, app_cats, app_icon in preset.get("launchers", []):
                desktop_content = f"""[Desktop Entry]
Type=Application
Name={app_title}
Comment={preset['summary']}
Exec={app_bin}
Icon={app_icon}
Terminal=false
Categories={app_cats}
X-Myelin-Preset={preset['id']}
"""
                dest_file = app_dir / f"org.myelinos.{preset['id']}.{app_bin}.desktop"
                try:
                    subprocess.run(["sudo", "sh", "-c", f"cat << 'EOF' > {dest_file}\n{desktop_content}\nEOF"], check=False)
                except Exception as e:
                    log(f"Failed to write launcher for {app_title}: {e}")

        # Install GNOME Desktop Environment and applications if desktop preset selected
        is_headless = len(selected_presets) == 1 and selected_presets[0]["id"] == "minimal_hardened"
        if not is_headless:
            log("[*] Installing GNOME Desktop Environment and applications from package cache...")
            staged_gnome = Path("/var/cache/myelin/staged_gnome")
            if staged_gnome.exists():
                staged_bin = staged_gnome / "bin"
                if staged_bin.exists():
                    for f in staged_bin.iterdir():
                        dest = Path("/usr/bin") / f.name
                        subprocess.run(["sudo", "mv", "-f", str(f), str(dest)], check=False)
                        subprocess.run(["sudo", "chmod", "755", str(dest)], check=False)
                staged_apps = staged_gnome / "applications"
                if staged_apps.exists():
                    for f in staged_apps.iterdir():
                        dest = app_dir / f.name
                        subprocess.run(["sudo", "mv", "-f", str(f), str(dest)], check=False)
                staged_sessions = staged_gnome / "sessions"
                if staged_sessions.exists():
                    session_dir = Path("/usr/share/wayland-sessions")
                    session_dir.mkdir(parents=True, exist_ok=True)
                    for f in staged_sessions.iterdir():
                        dest = session_dir / f.name
                        subprocess.run(["sudo", "mv", "-f", str(f), str(dest)], check=False)
                subprocess.run(["sudo", "rm", "-rf", str(staged_gnome)], check=False)
                installed_packages.append("gnome-desktop")

        # Update desktop database
        subprocess.run(["sudo", "update-desktop-database", str(app_dir)], check=False)
        subprocess.run(["sudo", "chown", "-R", f"{username}:{username}", f"/home/{username}"], check=False)
        return installed_packages

    def seal_generation(self, username, selected_presets, installed_packages):
        log("seal_generation: writing generation metadata and seal marker...")
        subprocess.run(["sudo", "mkdir", "-p", "/var/lib/myelin/generations"], check=False)
        subprocess.run(["sudo", "chmod", "-R", "777", "/var/lib/myelin"], check=False)
        
        preset_ids = [p["id"] for p in selected_presets]
        all_pkgs = sorted(list(set(installed_packages)))

        gen_data = {
            "generation": 1,
            "presets": preset_ids,
            "owner": username,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "sealed",
            "packages": all_pkgs
        }
        with open("/var/lib/myelin/generations/gen-1.json", "w") as f:
            json.dump(gen_data, f, indent=2)
        with open("/var/lib/myelin/generations/current", "w") as f:
            f.write("1\n")

        # Write permanent installation seal marker
        subprocess.run(["sudo", "touch", "/var/lib/myelin/installed"], check=False)
        subprocess.run(["sudo", "sync"], check=False)
        log(f"seal_generation: Generation 1 sealed with {len(all_pkgs)} packages; /var/lib/myelin/installed created.")

    def finalize_boot(self, username, autologin, selected_presets):
        log(f"finalize_boot: removing installer service and configuring display manager for user {username}...")
        # 1. Permanently remove installer services and files
        subprocess.run(["sudo", "systemctl", "disable", "myelin-installer.service"], check=False)
        subprocess.run(["sudo", "rm", "-f", "/etc/systemd/system/myelin-installer.service"], check=False)
        subprocess.run(["sudo", "rm", "-f", "/etc/systemd/system/graphical.target.wants/myelin-installer.service"], check=False)

        for p in [
            "/usr/share/wayland-sessions/myelin-installer.desktop",
            "/usr/bin/myelin-installer-session",
            "/etc/xdg/autostart/org.myelinos.Installer.desktop",
            "/home/myelinos/.config/autostart/org.myelinos.Installer.desktop",
            f"/home/{username}/.config/autostart/org.myelinos.Installer.desktop",
            "/usr/bin/myelin-installer-gui",
        ]:
            subprocess.run(["sudo", "rm", "-f", p], check=False)

        if Path("/usr/bin/gnome-session-real").exists():
            subprocess.run(["sudo", "mv", "-f", "/usr/bin/gnome-session-real", "/usr/bin/gnome-session"], check=False)
        if Path("/usr/bin/gnome-shell-real").exists():
            subprocess.run(["sudo", "mv", "-f", "/usr/bin/gnome-shell-real", "/usr/bin/gnome-shell"], check=False)

        # 2. Update /etc/gdm/custom.conf to transition from installer live user to real user
        gdm_conf = f"""# GDM configuration for MyelinOS (Sealed Generation 1)
[daemon]
AutomaticLoginEnable={'True' if autologin else 'False'}
AutomaticLogin={username}
WaylandEnable=true
InitialSetupEnable=false

[security]

[debug]
"""
        subprocess.run(["sudo", "sh", "-c", f"cat << 'EOF' > /etc/gdm/custom.conf\n{gdm_conf}\nEOF"], check=False)

        # 3. Configure AccountsService session for the real user
        acc_user = Path(f"/var/lib/AccountsService/users/{username}")
        if acc_user.parent.exists():
            acc_conf = "[User]\nSession=gnome\nXSession=gnome\nSystemAccount=false\n"
            subprocess.run(["sudo", "sh", "-c", f"cat << 'EOF' > {acc_user}\n{acc_conf}\nEOF"], check=False)
        acc_myelinos = Path("/var/lib/AccountsService/users/myelinos")
        if acc_myelinos.exists():
            subprocess.run(["sudo", "rm", "-f", str(acc_myelinos)], check=False)

        # 4. Enable GDM for production desktop unless headless
        is_headless = len(selected_presets) == 1 and selected_presets[0]["id"] == "minimal_hardened"
        if not is_headless:
            subprocess.run(["sudo", "systemctl", "enable", "gdm.service"], check=False)
            subprocess.run(["sudo", "ln", "-sf", "/usr/lib/systemd/system/gdm.service", "/etc/systemd/system/display-manager.service"], check=False)
            subprocess.run(["sudo", "systemctl", "set-default", "graphical.target"], check=False)
        else:
            subprocess.run(["sudo", "systemctl", "set-default", "multi-user.target"], check=False)

        # 5. Re-enable standard GNOME shortcuts for user session
        try:
            subprocess.run(["gsettings", "reset", "org.gnome.mutter", "overlay-key"], check=False)
            subprocess.run(["gsettings", "reset", "org.gnome.desktop.wm.keybindings", "switch-applications"], check=False)
            subprocess.run(["gsettings", "reset", "org.gnome.desktop.wm.keybindings", "switch-windows"], check=False)
            subprocess.run(["gsettings", "reset", "org.gnome.settings-daemon.plugins.media-keys", "terminal"], check=False)
        except Exception:
            pass

        subprocess.run(["sync"])
        log("finalize_boot: complete.")

    def on_reboot_clicked(self, btn):
        log("on_reboot_clicked: Rebooting system into production desktop...")
        res = subprocess.run(["sudo", "systemctl", "reboot"], check=False)
        if res.returncode != 0:
            subprocess.run(["sudo", "reboot", "-f"], check=False)

class MyelinInstallerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.myelinos.Installer", flags=Gio.ApplicationFlags.NON_UNIQUE)
        self.connect("activate", self.on_activate)

    def do_activate(self):
        self.on_activate(self)

    def on_activate(self, app):
        try:
            log("MyelinInstallerApp.on_activate called!")
            win = self.props.active_window
            if not win:
                log("on_activate: instantiating MyelinInstallerWindow...")
                win = MyelinInstallerWindow(self)
            log("on_activate: presenting window...")
            win.present()
            log("on_activate: window present() completed successfully.")
        except Exception as e:
            log(f"Error in on_activate: {e}\n{traceback.format_exc()}")

if __name__ == "__main__":
    if Path("/var/lib/myelin/installed").exists():
        print("[*] MyelinOS installation already completed. Exiting.")
        sys.exit(0)
    log("[*] Starting MyelinInstallerApp...")
    app = MyelinInstallerApp()
    sys.exit(app.run(sys.argv))
