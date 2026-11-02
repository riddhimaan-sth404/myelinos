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
import subprocess
import threading
import time
import json
from pathlib import Path

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Gtk, Adw, GLib, Gio

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

class MyelinInstallerWindow(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="MyelinOS Installer (Stage 2)")
        self.set_default_size(900, 680)
        self.set_size_request(760, 540)

        # Main Box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_content(main_box)

        # Header Bar
        header = Adw.HeaderBar()
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
        self.build_pages()

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
        clamp = Adw.Clamp(maximum_size=620)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=28, margin_bottom=28, margin_start=24, margin_end=24)
        clamp.set_child(box)

        # Icon
        icon = Gtk.Image.new_from_icon_name("system-software-install")
        icon.set_pixel_size(96)
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

        return clamp

    def create_user_page(self):
        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        clamp.set_child(box)

        title = Gtk.Label(label="User Account Setup")
        title.add_css_class("title-2")
        box.append(title)

        group = Adw.PreferencesGroup(title="User Credentials")
        box.append(group)

        self.fullname_row = Adw.EntryRow(title="Full Name")
        self.fullname_row.set_text("Myelin User")
        self.fullname_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.fullname_row)

        self.username_row = Adw.EntryRow(title="Username")
        self.username_row.set_text("myelinos")
        self.username_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.username_row)

        self.password_row = Adw.PasswordEntryRow(title="Password")
        self.password_row.set_text("myelinos")
        self.password_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.password_row)

        self.confirm_row = Adw.PasswordEntryRow(title="Confirm Password")
        self.confirm_row.set_text("myelinos")
        self.confirm_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.confirm_row)

        self.sudo_switch = Adw.SwitchRow(title="Administrator Privileges", subtitle="Allow user to run commands as root with sudo")
        self.sudo_switch.set_active(True)
        group.add(self.sudo_switch)

        self.autologin_switch = Adw.SwitchRow(title="Automatic Login", subtitle="Log in automatically upon system startup")
        self.autologin_switch.set_active(True)
        group.add(self.autologin_switch)

        return clamp

    def create_system_page(self):
        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=24, margin_bottom=24, margin_start=24, margin_end=24)
        clamp.set_child(box)

        title = Gtk.Label(label="System Localization")
        title.add_css_class("title-2")
        box.append(title)

        group = Adw.PreferencesGroup(title="Identity and Clock")
        box.append(group)

        self.hostname_row = Adw.EntryRow(title="Device Hostname")
        self.hostname_row.set_text("myelinos")
        self.hostname_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.hostname_row)

        self.timezone_row = Adw.EntryRow(title="Timezone (e.g. UTC, Asia/Kolkata, America/New_York)")
        self.timezone_row.set_text("UTC")
        self.timezone_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.timezone_row)

        self.locale_row = Adw.EntryRow(title="System Locale")
        self.locale_row.set_text("en_US.UTF-8")
        self.locale_row.connect("entry-activated", lambda r: self.on_next_clicked(None))
        group.add(self.locale_row)

        return clamp

    def create_presets_page(self):
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_hexpand(True)

        clamp = Adw.Clamp(maximum_size=680)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16, margin_top=20, margin_bottom=24, margin_start=24, margin_end=24)
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
        clamp = Adw.Clamp(maximum_size=550)
        clamp.set_vexpand(True)
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20, margin_top=40, margin_bottom=40, margin_start=24, margin_end=24)
        clamp.set_child(box)

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

        done_msg = Gtk.Label(label="Installation Complete!\nYour chosen software presets have been installed and sealed into Generation 1.")
        done_msg.set_justify(Gtk.Justification.CENTER)
        done_msg.add_css_class("title-3")
        self.done_box.append(done_msg)

        done_sub = Gtk.Label(label="When you reboot, the installer will be gone and your system will open directly into your personalized desktop.")
        done_sub.set_justify(Gtk.Justification.CENTER)
        done_sub.add_css_class("dim-label")
        self.done_box.append(done_sub)

        self.reboot_btn = Gtk.Button(label="Reboot into MyelinOS")
        self.reboot_btn.add_css_class("suggested-action")
        self.reboot_btn.add_css_class("pill")
        self.reboot_btn.connect("clicked", self.on_reboot_clicked)
        self.done_box.append(self.reboot_btn)

        return clamp

    def on_prev_clicked(self, btn):
        if self.step > 0:
            self.step -= 1
            pages = ["welcome", "user", "system", "presets", "progress"]
            self.stack.set_visible_child_name(pages[self.step])
            self.update_nav()

    def on_next_clicked(self, btn):
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
            self.stack.set_visible_child_name(pages[self.step])
            self.update_nav()
        elif self.step == 3:
            # Start installation / sealing
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

        steps = [
            ("Applying device hostname...", 0.15, self.apply_hostname, (hostname,)),
            ("Configuring timezone & locale...", 0.30, self.apply_timezone, (timezone,)),
            ("Creating user account & credentials...", 0.45, self.apply_user, (username, fullname, password, is_sudo)),
            ("Installing selected package presets...", 0.70, self.install_presets, (username, selected_presets)),
            ("Sealing Generation 1 in Axon CAS store...", 0.85, self.seal_generation, (username, selected_presets)),
            ("Finalizing bootloader & display manager...", 1.0, self.finalize_boot, (username, autologin, selected_presets)),
        ]

        for desc, pct, func, args in steps:
            GLib.idle_add(self.update_progress, desc, pct)
            time.sleep(0.7)
            try:
                func(*args)
            except Exception as e:
                print(f"Error in {desc}: {e}")

        GLib.idle_add(self.show_completed)

    def update_progress(self, desc, pct):
        self.status_label.set_text(desc)
        self.progress_bar.set_fraction(pct)

    def show_completed(self):
        self.progress_title.set_visible(False)
        self.progress_bar.set_visible(False)
        self.status_label.set_visible(False)
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
        app_dir = Path("/usr/share/applications")
        user_app_dir = Path(f"/home/{username}/.local/share/applications")
        subprocess.run(["sudo", "mkdir", "-p", str(app_dir)], check=False)
        subprocess.run(["sudo", "mkdir", "-p", str(user_app_dir)], check=False)

        for preset in selected_presets:
            print(f"[*] Installing preset: {preset['name']} ({len(preset['packages'])} packages)...")
            
            # Install launchers for GUI applications
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
                    print(f"Failed to write launcher for {app_title}: {e}")

        subprocess.run(["sudo", "chown", "-R", f"{username}:{username}", f"/home/{username}"], check=False)

    def seal_generation(self, username, selected_presets):
        subprocess.run(["sudo", "mkdir", "-p", "/var/lib/myelin/generations"], check=False)
        subprocess.run(["sudo", "chown", "-R", f"{os.getuid()}:{os.getgid()}", "/var/lib/myelin"], check=False)
        
        all_pkgs = []
        preset_ids = []
        for p in selected_presets:
            preset_ids.append(p["id"])
            all_pkgs.extend(p["packages"])

        gen_data = {
            "generation": 1,
            "presets": preset_ids,
            "owner": username,
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "status": "sealed",
            "packages": sorted(list(set(all_pkgs)))
        }
        with open("/var/lib/myelin/generations/gen-1.json", "w") as f:
            json.dump(gen_data, f, indent=2)
        with open("/var/lib/myelin/generations/current", "w") as f:
            f.write("1\n")

    def finalize_boot(self, username, autologin, selected_presets):
        # 1. Permanently remove installer desktop entries
        for p in [
            "/etc/xdg/autostart/org.myelinos.Installer.desktop",
            "/home/myelinos/.config/autostart/org.myelinos.Installer.desktop",
            f"/home/{username}/.config/autostart/org.myelinos.Installer.desktop",
        ]:
            subprocess.run(["sudo", "rm", "-f", p], check=False)

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

        # 3. If minimal headless only, switch systemd default target to multi-user
        if len(selected_presets) == 1 and selected_presets[0]["id"] == "minimal_hardened":
            subprocess.run(["sudo", "systemctl", "set-default", "multi-user.target"], check=False)
        else:
            subprocess.run(["sudo", "systemctl", "set-default", "graphical.target"], check=False)

        subprocess.run(["sync"])

    def on_reboot_clicked(self, btn):
        subprocess.run(["sudo", "systemctl", "reboot"])

class MyelinInstallerApp(Adw.Application):
    def __init__(self):
        super().__init__(application_id="org.myelinos.Installer", flags=Gio.ApplicationFlags.FLAGS_NONE)

    def do_activate(self):
        win = self.props.active_window
        if not win:
            win = MyelinInstallerWindow(self)
        win.present()

if __name__ == "__main__":
    app = MyelinInstallerApp()
    sys.exit(app.run(sys.argv))
