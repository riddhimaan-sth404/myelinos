mod disk;
mod hardware;
mod staging;
mod ui;

use crossterm::{
    event::{self, Event, KeyCode, KeyEventKind},
    execute,
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
};
use ratatui::{backend::CrosstermBackend, Terminal};
use std::io;
use std::sync::mpsc;
use std::time::Duration;
use ui::{AppState, WizardStep};

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let args: Vec<String> = std::env::args().collect();
    let auto_mode = args.iter().any(|a| a == "--auto" || a == "--unattended");

    // Setup terminal
    enable_raw_mode()?;
    let mut stdout = io::stdout();
    execute!(stdout, EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(stdout);
    let mut terminal = Terminal::new(backend)?;

    let mut state = AppState::new();
    if auto_mode && !state.disks.is_empty() {
        state.selected_profile = staging::InstallProfile::GnomeDesktop;
        state.current_step = WizardStep::Installing;
    }

    // Channel for installation progress communication
    let (tx, rx) = mpsc::channel::<(String, u16, Option<String>)>();
    let mut installing_started = false;

    loop {
        // Drain any incoming progress messages
        while let Ok((msg, pct, err)) = rx.try_recv() {
            state.progress_status = msg;
            state.progress_percent = pct;
            if let Some(e) = err {
                state.install_error = Some(e);
            } else if pct >= 100 {
                state.current_step = WizardStep::Done;
                if auto_mode {
                    state.should_quit = true;
                }
            }
        }

        // Draw UI
        terminal.draw(|f| ui::render(f, &state))?;

        if state.should_quit {
            break;
        }

        // Handle Installation Background Execution
        if state.current_step == WizardStep::Installing && !installing_started {
            installing_started = true;
            let tx_clone = tx.clone();
            let disk = state.disks[state.selected_disk_idx].clone();
            let profile = state.selected_profile;

            std::thread::spawn(move || {
                let _ = tx_clone.send(("Partitioning target disk with GPT and ESP...".into(), 10, None));
                
                match disk.partition_and_format() {
                    Ok((esp_dev, root_dev)) => {
                        let _ = tx_clone.send((format!("Formatting complete. ESP: {}, Root: {}", esp_dev, root_dev), 25, None));
                        
                        let tx_prog = tx_clone.clone();
                        let res = staging::stage_installation(&esp_dev, &root_dev, profile, move |step_desc, pct| {
                            let _ = tx_prog.send((step_desc.to_string(), pct, None));
                        });

                        if let Err(e) = res {
                            let _ = tx_clone.send(("Installation failed!".into(), 100, Some(e)));
                        } else {
                            let _ = tx_clone.send(("Installation complete!".into(), 100, None));
                        }
                    }
                    Err(e) => {
                        let _ = tx_clone.send(("Partitioning failed!".into(), 100, Some(e)));
                    }
                }
            });
        }

        // Poll for keyboard events
        if event::poll(Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                if key.kind == KeyEventKind::Press {
                    match key.code {
                        KeyCode::Char('q') => {
                            if state.current_step != WizardStep::Installing {
                                break;
                            }
                        }
                        KeyCode::Esc => {
                            if state.current_step != WizardStep::Installing {
                                state.prev_step();
                            }
                        }
                        KeyCode::Char('b') => {
                            if state.current_step != WizardStep::Installing {
                                state.prev_step();
                            }
                        }
                        KeyCode::Up => {
                            if state.current_step == WizardStep::DiskSelection {
                                if state.selected_disk_idx > 0 {
                                    state.selected_disk_idx -= 1;
                                }
                            } else if state.current_step == WizardStep::ProfileSelection {
                                state.selected_profile = match state.selected_profile {
                                    staging::InstallProfile::DeveloperMinimal => staging::InstallProfile::GnomeDesktop,
                                    staging::InstallProfile::GnomeDesktop => staging::InstallProfile::DeveloperMinimal,
                                };
                            }
                        }
                        KeyCode::Down => {
                            if state.current_step == WizardStep::DiskSelection {
                                if state.selected_disk_idx + 1 < state.disks.len() {
                                    state.selected_disk_idx += 1;
                                }
                            } else if state.current_step == WizardStep::ProfileSelection {
                                state.selected_profile = match state.selected_profile {
                                    staging::InstallProfile::DeveloperMinimal => staging::InstallProfile::GnomeDesktop,
                                    staging::InstallProfile::GnomeDesktop => staging::InstallProfile::DeveloperMinimal,
                                };
                            }
                        }
                        KeyCode::Enter => {
                            if state.current_step == WizardStep::Done {
                                break;
                            } else if state.current_step != WizardStep::Installing {
                                state.next_step();
                            }
                        }
                        _ => {}
                    }
                }
            }
        }
    }

    // Restore terminal
    disable_raw_mode()?;
    execute!(terminal.backend_mut(), LeaveAlternateScreen)?;
    terminal.show_cursor()?;

    println!("[+] Exited MyelinOS Bootstrap Installer.");
    Ok(())
}
