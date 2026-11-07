use crate::disk::DiskDevice;
use crate::hardware::HardwareReport;
use crate::staging::InstallProfile;
use ratatui::{
    layout::{Alignment, Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, BorderType, Borders, Gauge, List, ListItem, Paragraph, Wrap},
    Frame,
};

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WizardStep {
    HardwareAudit,
    DiskSelection,
    ProfileSelection,
    Confirmation,
    Installing,
    Done,
}

pub struct AppState {
    pub current_step: WizardStep,
    pub hardware: HardwareReport,
    pub disks: Vec<DiskDevice>,
    pub selected_disk_idx: usize,
    pub selected_profile: InstallProfile,
    pub progress_percent: u16,
    pub progress_status: String,
    pub install_error: Option<String>,
    pub should_quit: bool,
}

impl AppState {
    pub fn new() -> Self {
        let hardware = HardwareReport::probe();
        let disks = DiskDevice::scan_disks();
        Self {
            current_step: WizardStep::HardwareAudit,
            hardware,
            disks,
            selected_disk_idx: 0,
            selected_profile: InstallProfile::GnomeDesktop,
            progress_percent: 0,
            progress_status: "Ready to install.".into(),
            install_error: None,
            should_quit: false,
        }
    }

    pub fn next_step(&mut self) {
        match self.current_step {
            WizardStep::HardwareAudit => self.current_step = WizardStep::DiskSelection,
            WizardStep::DiskSelection => {
                if !self.disks.is_empty() {
                    self.current_step = WizardStep::ProfileSelection;
                }
            }
            WizardStep::ProfileSelection => self.current_step = WizardStep::Confirmation,
            WizardStep::Confirmation => self.current_step = WizardStep::Installing,
            WizardStep::Installing => self.current_step = WizardStep::Done,
            WizardStep::Done => self.should_quit = true,
        }
    }

    pub fn prev_step(&mut self) {
        match self.current_step {
            WizardStep::HardwareAudit => self.should_quit = true,
            WizardStep::DiskSelection => self.current_step = WizardStep::HardwareAudit,
            WizardStep::ProfileSelection => self.current_step = WizardStep::DiskSelection,
            WizardStep::Confirmation => self.current_step = WizardStep::ProfileSelection,
            WizardStep::Installing => {} // Cannot go back during installation
            WizardStep::Done => self.should_quit = true,
        }
    }
}

pub fn render(frame: &mut Frame, state: &AppState) {
    let mut size = frame.area();
    if size.width < 10 || size.height < 5 {
        size = Rect::new(0, 0, 100, 30);
    }

    // Main layout: Header (3), Body (Remaining), Footer (3)
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(12),
            Constraint::Length(3),
        ])
        .split(size);

    render_header(frame, chunks[0], state);
    render_body(frame, chunks[1], state);
    render_footer(frame, chunks[2], state);
}

fn render_header(frame: &mut Frame, area: Rect, state: &AppState) {
    let step_str = match state.current_step {
        WizardStep::HardwareAudit => "Step 1/5: Hardware Capability Probe",
        WizardStep::DiskSelection => "Step 2/5: Target Storage Device",
        WizardStep::ProfileSelection => "Step 3/5: Installation Profile",
        WizardStep::Confirmation => "Step 4/5: Confirmation & Partition Plan",
        WizardStep::Installing => "Step 5/5: Staging System Assets",
        WizardStep::Done => "Complete: Stage 1 Bootstrap Sealed",
    };

    let title = Line::from(vec![
        Span::styled(" ◈ MyelinOS ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        Span::styled("Bootstrap Installer (Stage 1) ", Style::default().fg(Color::White)),
        Span::styled(format!("│ {} ", step_str), Style::default().fg(Color::Yellow)),
    ]);

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::Cyan));

    let p = Paragraph::new(title).block(block).alignment(Alignment::Left);
    frame.render_widget(p, area);
}

fn render_body(frame: &mut Frame, area: Rect, state: &AppState) {
    match state.current_step {
        WizardStep::HardwareAudit => render_hardware_audit(frame, area, state),
        WizardStep::DiskSelection => render_disk_selection(frame, area, state),
        WizardStep::ProfileSelection => render_profile_selection(frame, area, state),
        WizardStep::Confirmation => render_confirmation(frame, area, state),
        WizardStep::Installing => render_installing(frame, area, state),
        WizardStep::Done => render_done(frame, area, state),
    }
}

fn render_hardware_audit(frame: &mut Frame, area: Rect, state: &AppState) {
    let hw = &state.hardware;

    let mut lines = Vec::new();
    lines.push(Line::from(vec![
        Span::styled("Hardware Platform Capability & Integrity Report (Canonical Arch §36.4, §36.5)", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
    ]));
    lines.push(Line::from(""));

    // CPU
    let virt_status = if hw.has_virtualization {
        Span::styled("Supported [VMX/SVM Enabled]", Style::default().fg(Color::Green))
    } else {
        Span::styled("Not Detected", Style::default().fg(Color::Yellow))
    };
    lines.push(Line::from(vec![
        Span::raw(" • CPU Model:          "),
        Span::styled(&hw.cpu_model, Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
        Span::raw(format!(" ({} Cores)", hw.cpu_cores)),
    ]));
    lines.push(Line::from(vec![
        Span::raw(" • Hardware Virt:       "),
        virt_status,
    ]));

    // RAM
    let ram_status = if hw.total_ram_mb >= 3800 {
        Span::styled(format!("{} MB [Optimal for GNOME Desktop]", hw.total_ram_mb), Style::default().fg(Color::Green))
    } else if hw.total_ram_mb >= 1800 {
        Span::styled(format!("{} MB [Adequate for Minimal]", hw.total_ram_mb), Style::default().fg(Color::Yellow))
    } else {
        Span::styled(format!("{} MB [Under Requirements]", hw.total_ram_mb), Style::default().fg(Color::Red))
    };
    lines.push(Line::from(vec![
        Span::raw(" • System Memory:       "),
        ram_status,
    ]));

    // Firmware & Boot Mode
    let uefi_status = if hw.is_uefi {
        Span::styled("UEFI Mode (GPT / ESP Capable)", Style::default().fg(Color::Green))
    } else {
        Span::styled("Legacy BIOS (Degraded - GPT Recommended)", Style::default().fg(Color::Red))
    };
    lines.push(Line::from(vec![
        Span::raw(" • Firmware Interface:  "),
        uefi_status,
    ]));

    // Secure Boot
    let secboot_status = if hw.secure_boot {
        Span::styled("Enabled (Verified Boot Chain Active)", Style::default().fg(Color::Green))
    } else {
        Span::styled("Disabled / Standard Mode", Style::default().fg(Color::Yellow))
    };
    lines.push(Line::from(vec![
        Span::raw(" • UEFI Secure Boot:    "),
        secboot_status,
    ]));

    // TPM 2.0
    let tpm_status = if hw.has_tpm2 {
        Span::styled("Present (/dev/tpm0) - Measured Boot Ready", Style::default().fg(Color::Green))
    } else {
        Span::styled("Not Present - Boot Integrity Protection Unavailable", Style::default().fg(Color::Yellow))
    };
    lines.push(Line::from(vec![
        Span::raw(" • TPM 2.0 Security:    "),
        tpm_status,
    ]));

    // Disks
    lines.push(Line::from(vec![
        Span::raw(" • Storage Devices:     "),
        Span::styled(format!("{} block device(s) found", hw.storage_devices_found), Style::default().fg(Color::White)),
    ]));

    // Warnings if any
    if !hw.warnings.is_empty() {
        lines.push(Line::from(""));
        lines.push(Line::from(Span::styled("Platform Advisories:", Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD))));
        for w in &hw.warnings {
            lines.push(Line::from(vec![
                Span::styled("   ⚠ ", Style::default().fg(Color::Yellow)),
                Span::raw(w),
            ]));
        }
    }

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" System Compatibility Audit ")
        .border_style(Style::default().fg(Color::Blue));

    let p = Paragraph::new(lines).block(block).wrap(Wrap { trim: true });
    frame.render_widget(p, area);
}

fn render_disk_selection(frame: &mut Frame, area: Rect, state: &AppState) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" Select Target Installation Hard Disk ")
        .border_style(Style::default().fg(Color::Blue));

    if state.disks.is_empty() {
        let p = Paragraph::new(vec![
            Line::from(Span::styled("No writable storage drives detected!", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD))),
            Line::from("Please attach a hard disk or virtual drive and restart the installer."),
        ]).block(block);
        frame.render_widget(p, area);
        return;
    }

    let items: Vec<ListItem> = state.disks.iter().enumerate().map(|(idx, d)| {
        let is_selected = idx == state.selected_disk_idx;
        let prefix = if is_selected { " ▶ " } else { "   " };
        let style = if is_selected {
            Style::default().fg(Color::Black).bg(Color::Cyan).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::White)
        };

        let rot = if d.is_rotational { "HDD" } else { "SSD/NVMe" };
        let text = format!("{}{} ({} GB, {}) - {}", prefix, d.device_path.display(), d.size_gb as u64, rot, d.model);
        ListItem::new(text).style(style)
    }).collect();

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Min(4), Constraint::Length(4)])
        .split(area);

    let list = List::new(items).block(block);
    frame.render_widget(list, chunks[0]);

    let warning_block = Block::default()
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Red))
        .title(" Data Caution ");
    let warning_text = Paragraph::new(vec![
        Line::from(vec![
            Span::styled("CAUTION: ", Style::default().fg(Color::Red).add_modifier(Modifier::BOLD)),
            Span::raw("Installing will wipe the selected disk, initialize GPT, create ESP (512MB), and format root with Btrfs (COW enabled)."),
        ]),
        Line::from("Use [Up/Down] arrows to choose drive, [Enter] to proceed."),
    ]).block(warning_block);
    frame.render_widget(warning_text, chunks[1]);
}

fn render_profile_selection(frame: &mut Frame, area: Rect, state: &AppState) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" Select Target Installation Profile ")
        .border_style(Style::default().fg(Color::Blue));

    let profiles = [InstallProfile::GnomeDesktop, InstallProfile::DeveloperMinimal];

    let items: Vec<ListItem> = profiles.iter().map(|p| {
        let is_selected = *p == state.selected_profile;
        let prefix = if is_selected { " ▶ [●] " } else { "   [ ] " };
        let style = if is_selected {
            Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)
        } else {
            Style::default().fg(Color::White)
        };

        let lines = vec![
            Line::from(Span::styled(format!("{}{}", prefix, p.name()), style)),
            Line::from(Span::styled(format!("       {}", p.description()), Style::default().fg(Color::DarkGray))),
            Line::from(""),
        ];
        ListItem::new(lines)
    }).collect();

    let list = List::new(items).block(block);
    frame.render_widget(list, area);
}

fn render_confirmation(frame: &mut Frame, area: Rect, state: &AppState) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" Installation Summary & Confirmation ")
        .border_style(Style::default().fg(Color::Yellow));

    let selected_disk = &state.disks[state.selected_disk_idx];

    let lines = vec![
        Line::from(Span::styled("Ready to initialize MyelinOS Stage 1 Bootstrap:", Style::default().fg(Color::Yellow).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from(vec![
            Span::raw(" • Target Disk:       "),
            Span::styled(format!("{} ({} GB)", selected_disk.device_path.display(), selected_disk.size_gb as u64), Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::raw(" • Partition Table:   "),
            Span::styled("GPT (GUID Partition Table)", Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::raw(" • EFI System Part:   "),
            Span::styled("512 MB FAT32 (/boot/efi)", Style::default().fg(Color::White)),
        ]),
        Line::from(vec![
            Span::raw(" • Root Filesystem:   "),
            Span::styled("Remainder Btrfs (Label: MYELINOS_ROOT, COW Enabled)", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::raw(" • OS Profile:        "),
            Span::styled(state.selected_profile.name(), Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
        ]),
        Line::from(vec![
            Span::raw(" • Stage 2 Target:    "),
            Span::styled("Staged Graphical Installer on Target Disk", Style::default().fg(Color::Cyan)),
        ]),
        Line::from(""),
        Line::from(Span::styled("Press [Enter] to partition disk and begin staging assets.", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("Press [Esc] or [b] to go back and adjust selections.", Style::default().fg(Color::DarkGray))),
    ];

    let p = Paragraph::new(lines).block(block);
    frame.render_widget(p, area);
}

fn render_installing(frame: &mut Frame, area: Rect, state: &AppState) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" Staging Operating System Assets ")
        .border_style(Style::default().fg(Color::Cyan));

    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(5),
            Constraint::Length(3),
            Constraint::Min(6),
        ])
        .split(area);

    let info_text = Paragraph::new(vec![
        Line::from(Span::styled("Staging Stage 2 Graphical Installer to Target Disk...", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from(vec![
            Span::styled("Status: ", Style::default().fg(Color::White).add_modifier(Modifier::BOLD)),
            Span::styled(&state.progress_status, Style::default().fg(Color::Yellow)),
        ]),
    ]).block(block);
    frame.render_widget(info_text, chunks[0]);

    let gauge = Gauge::default()
        .block(Block::default().borders(Borders::ALL).border_type(BorderType::Rounded).title(" Progress "))
        .gauge_style(Style::default().fg(Color::Cyan).bg(Color::DarkGray))
        .percent(state.progress_percent)
        .label(format!("{}%", state.progress_percent));
    frame.render_widget(gauge, chunks[1]);

    if let Some(err) = &state.install_error {
        let err_block = Block::default().borders(Borders::ALL).border_style(Style::default().fg(Color::Red)).title(" Error Encountered ");
        let err_p = Paragraph::new(err.as_str()).block(err_block).style(Style::default().fg(Color::Red));
        frame.render_widget(err_p, chunks[2]);
    } else {
        let details_block = Block::default()
            .borders(Borders::ALL)
            .border_type(BorderType::Rounded)
            .title(" Staging Pipeline Details ")
            .border_style(Style::default().fg(Color::DarkGray));
        
        let p_pct = state.progress_percent;
        let s1 = if p_pct >= 10 { "✔" } else { "⏳" };
        let s2 = if p_pct >= 25 { "✔" } else { "⏳" };
        let s3 = if p_pct >= 70 { "✔" } else { "⏳" };
        let s4 = if p_pct >= 85 { "✔" } else { "⏳" };
        let s5 = if p_pct >= 95 { "✔" } else { "⏳" };

        let details_lines = vec![
            Line::from(vec![Span::styled(format!(" [{}] ", s1), Style::default().fg(if p_pct >= 10 { Color::Green } else { Color::Yellow })), Span::raw("Wipe and partition target drive with GPT, ESP (512MB), and Btrfs root")]),
            Line::from(vec![Span::styled(format!(" [{}] ", s2), Style::default().fg(if p_pct >= 25 { Color::Green } else { Color::Yellow })), Span::raw("Mount Btrfs root filesystem and stage base operating system payload")]),
            Line::from(vec![Span::styled(format!(" [{}] ", s3), Style::default().fg(if p_pct >= 70 { Color::Green } else { Color::Yellow })), Span::raw("Install UEFI GRUB 2 bootloader (BOOTX64.EFI) and Linux 7.2 kernel")]),
            Line::from(vec![Span::styled(format!(" [{}] ", s4), Style::default().fg(if p_pct >= 85 { Color::Green } else { Color::Yellow })), Span::raw("Deploy Stage 2 Graphical Installer and Axon package cache")]),
            Line::from(vec![Span::styled(format!(" [{}] ", s5), Style::default().fg(if p_pct >= 95 { Color::Green } else { Color::Yellow })), Span::raw("Flush disk caches, seal Stage 1 bootstrap, and unmount partitions")]),
        ];
        let details_p = Paragraph::new(details_lines).block(details_block);
        frame.render_widget(details_p, chunks[2]);
    }
}

fn render_done(frame: &mut Frame, area: Rect, state: &AppState) {
    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .title(" Bootstrap Staging Complete! ")
        .border_style(Style::default().fg(Color::Green));

    let selected_disk = &state.disks[state.selected_disk_idx];

    let lines = vec![
        Line::from(Span::styled("✔ Stage 1 Bootstrap Successfully Completed!", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD))),
        Line::from(""),
        Line::from(format!("• Target disk {} has been partitioned with UEFI GPT + ESP.", selected_disk.device_path.display())),
        Line::from("• Stage 2 Graphical Installer and base OS payload are sealed on the Btrfs drive."),
        Line::from(""),
        Line::from(Span::styled("Next Steps:", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD))),
        Line::from(" 1. Remove the Bootstrap ISO / installation medium if booted from USB."),
        Line::from(" 2. Reboot the system into the target hard drive."),
        Line::from(" 3. The Stage 2 Graphical Installer will launch directly into the GNOME session."),
        Line::from(""),
        Line::from(Span::styled("▶ Press [Enter] to REBOOT IMMEDIATELY into MyelinOS.", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD))),
        Line::from(Span::styled("▶ Press [q] or [Esc] to exit to rescue shell.", Style::default().fg(Color::DarkGray))),
    ];

    let p = Paragraph::new(lines).block(block).wrap(Wrap { trim: true });
    frame.render_widget(p, area);
}

fn render_footer(frame: &mut Frame, area: Rect, state: &AppState) {
    let help_spans = match state.current_step {
        WizardStep::HardwareAudit => vec![
            Span::styled("[Enter] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Continue to Disk Selection  │  "),
            Span::styled("[q/Esc] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Exit to Shell"),
        ],
        WizardStep::DiskSelection => vec![
            Span::styled("[↑/↓] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Select Disk  │  "),
            Span::styled("[Enter] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Confirm Drive  │  "),
            Span::styled("[Esc/b] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Back"),
        ],
        WizardStep::ProfileSelection => vec![
            Span::styled("[↑/↓] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Toggle Profile  │  "),
            Span::styled("[Enter] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Confirm Profile  │  "),
            Span::styled("[Esc/b] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Back"),
        ],
        WizardStep::Confirmation => vec![
            Span::styled("[Enter] ", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::raw("START INSTALLATION  │  "),
            Span::styled("[Esc/b] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Back to Profile"),
        ],
        WizardStep::Installing => vec![
            Span::raw("Partitioning & Staging in progress... Please wait."),
        ],
        WizardStep::Done => vec![
            Span::styled("[Enter] ", Style::default().fg(Color::Green).add_modifier(Modifier::BOLD)),
            Span::raw("Reboot System  │  "),
            Span::styled("[q] ", Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)),
            Span::raw("Exit to Shell"),
        ],
    };

    let block = Block::default()
        .borders(Borders::ALL)
        .border_type(BorderType::Rounded)
        .border_style(Style::default().fg(Color::DarkGray));

    let p = Paragraph::new(Line::from(help_spans)).block(block).alignment(Alignment::Center);
    frame.render_widget(p, area);
}
