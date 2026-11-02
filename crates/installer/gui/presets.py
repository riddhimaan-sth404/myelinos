"""
MyelinOS Application Presets & Package Profiles Catalog
Defines common software bundles selectable during Stage 2 Installation.
"""

PRESETS = [
    {
        "id": "developer",
        "name": "Developer Workstation",
        "category": "Development",
        "icon": "applications-development",
        "summary": "Core software engineering tools (Rust, Python, GCC, Git, Neovim)",
        "description": "Essential development environment with compilers, build tools, debuggers, version control, and modern terminal editors.",
        "packages": ["gcc", "clang", "rustc", "cargo", "python3", "git", "neovim", "gdb", "make", "cmake", "tmux", "htop", "ripgrep", "jq"],
        "default": True,
    },
    {
        "id": "web_dev",
        "name": "Full-Stack and Web Development",
        "category": "Development",
        "icon": "network-wired",
        "summary": "Modern web development stack (Node.js, TypeScript, Containers)",
        "description": "JavaScript/TypeScript runtime, container tooling, API testing utilities, and headless databases.",
        "packages": ["nodejs", "npm", "typescript", "podman", "sqlite3", "nginx", "curl", "redis-tools"],
        "default": False,
    },
    {
        "id": "data_science",
        "name": "Data Science and AI / ML",
        "category": "Science",
        "icon": "accessories-calculator",
        "summary": "Data analysis, scientific computing, and machine learning libraries",
        "description": "Python data science ecosystem including Jupyter Notebook, NumPy, Pandas, Scipy, and Matplotlib.",
        "packages": ["python3-numpy", "python3-pandas", "python3-scipy", "python3-matplotlib", "jupyter-notebook"],
        "default": False,
    },
    {
        "id": "devops_cloud",
        "name": "DevOps and Cloud Engineer",
        "category": "Operations",
        "icon": "network-server",
        "summary": "Cloud native infrastructure (Kubernetes, Helm, Terraform, Ansible)",
        "description": "Container orchestration, infrastructure-as-code, deployment automation, and secure WireGuard tunnels.",
        "packages": ["podman", "kubectl", "helm", "terraform", "ansible", "wireguard-tools", "openssh"],
        "default": False,
    },
    {
        "id": "office_productivity",
        "name": "Office and Productivity",
        "category": "Productivity",
        "icon": "applications-office",
        "summary": "Document processing, PDF viewer, calendar, and office suite",
        "description": "LibreOffice suite, document readers, calendar scheduling, archive tools, and spellcheck dictionaries.",
        "packages": ["libreoffice-fresh", "evince", "gnome-calendar", "file-roller", "hunspell"],
        "default": True,
    },
    {
        "id": "creative_design",
        "name": "Creative Studio and Digital Art",
        "category": "Design",
        "icon": "applications-graphics",
        "summary": "Digital illustration, photo editing, and 3D modeling (GIMP, Inkscape, Blender)",
        "description": "Professional raster and vector graphics, 3D modeling, RAW photo processing, and typography tools.",
        "packages": ["gimp", "inkscape", "blender", "krita", "darktable"],
        "default": False,
    },
    {
        "id": "gaming_multimedia",
        "name": "Gaming and Entertainment",
        "category": "Entertainment",
        "icon": "applications-games",
        "summary": "Steam, Wine compatibility, multimedia players, and screen recording",
        "description": "Game store integration, Windows compatibility layer, high-performance media players, and streaming tools.",
        "packages": ["steam", "lutris", "wine", "mangohud", "vlc", "obs-studio"],
        "default": False,
    },
    {
        "id": "cybersecurity",
        "name": "Cybersecurity and Pen-Testing",
        "category": "Security",
        "icon": "security-high",
        "summary": "Network reconnaissance, packet capture, and security audit tools",
        "description": "Network security scanners, packet analyzers, cryptographic audit tools, and forensic helpers.",
        "packages": ["nmap", "wireshark-qt", "tcpdump", "john", "aircrack-ng", "hashcat"],
        "default": False,
    },
    {
        "id": "audio_production",
        "name": "Pro Audio and Music Production",
        "category": "Multimedia",
        "icon": "applications-multimedia",
        "summary": "Digital Audio Workstation (DAW), audio editing, and sound synthesizer",
        "description": "Multi-track audio recording, PipeWire-JACK patchbay, synthesizer soundfonts, and audio editors.",
        "packages": ["ardour", "audacity", "lmms", "qjackctl", "helvum"],
        "default": False,
    },
    {
        "id": "science_education",
        "name": "STEM and Education",
        "category": "Education",
        "icon": "help-contents",
        "summary": "Mathematics, astronomy, LaTeX typesetting, and flashcard learning",
        "description": "Numerical computation with Octave, planetarium simulation with Stellarium, TeX Live, and spaced repetition.",
        "packages": ["octave", "stellarium", "geogebra", "texlive-core", "anki"],
        "default": False,
    },
    {
        "id": "minimal_hardened",
        "name": "Minimal Server and Hardened Workstation",
        "category": "System",
        "icon": "system-lock-screen",
        "summary": "Zero desktop bloat, firewall (UFW), intrusion prevention, Axon CLI only",
        "description": "Headless minimal runtime for servers and security-critical systems with active firewall and SSH.",
        "packages": ["axon", "ufw", "fail2ban", "openssh", "htop"],
        "default": False,
    },
]

def get_preset_by_id(preset_id: str):
    for p in PRESETS:
        if p["id"] == preset_id:
            return p
    return None

def get_all_preset_ids():
    return [p["id"] for p in PRESETS]
