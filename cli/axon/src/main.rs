use clap::{Parser, Subcommand, ValueEnum};
use myelin_package::{
    ArchClient, PackageArchive, PackageBuilder, PackageManager,
};
use myelin_types::{EnvironmentId, GenerationId, PackageManifest, PackageTier};
use std::path::{Path, PathBuf};
use std::process::exit;

#[derive(Parser)]
#[command(
    name = "axon",
    author = "MyelinOS Authors",
    version = "0.1.0",
    about = "Axon — Canonical Package and Generation Manager for MyelinOS with Arch & AUR support"
)]
struct Cli {
    #[arg(long, global = true, help = "Output in JSON format")]
    json: bool,

    #[arg(
        long,
        global = true,
        help = "Target profile/environment [default: 'default']"
    )]
    profile: Option<String>,

    #[arg(long, global = true, help = "Target host system profile directly")]
    system: bool,

    #[arg(
        long,
        global = true,
        help = "Allow mutating the host system profile (§13.2)"
    )]
    allow_host_mutation: bool,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    #[command(about = "Install a package (from Arch repos, AUR, or local .mpkg/.pkg.tar.zst)")]
    Install {
        #[arg(help = "Package name (from Arch/AUR) or local file path (.mpkg, .pkg.tar.zst)")]
        target: String,

        #[arg(long, help = "Install directly from Arch User Repository (AUR)")]
        aur: bool,
    },

    #[command(about = "Search for packages in Arch Linux official repositories and AUR")]
    Search {
        #[arg(help = "Search term")]
        query: String,

        #[arg(long, help = "Also search the Arch User Repository (AUR)")]
        aur: bool,
    },

    #[command(about = "Show detailed information about a package")]
    Info {
        #[arg(help = "Package name")]
        package: String,

        #[arg(long, help = "Query the Arch User Repository (AUR)")]
        aur: bool,
    },

    #[command(about = "Remove a package from the active profile")]
    Remove {
        #[arg(help = "Name of the package to remove")]
        name: String,
    },

    #[command(about = "List installed packages in the active generation")]
    List,

    #[command(about = "Instant atomic rollback to previous profile generation (gen-(N-1))")]
    Rollback,

    #[command(subcommand, about = "Generation inspection, promotion, and switching")]
    Generation(GenerationCommands),

    #[command(subcommand, about = "Package authoring, bundling, and inspection")]
    Package(PackageCommands),

    #[command(subcommand, about = "Content-Addressed Artifact Store operations")]
    Artifact(ArtifactCommands),

    #[command(about = "Garbage collect unreferenced artifacts from the CAS store")]
    Gc {
        #[arg(long, help = "Only show what would be deleted without deleting")]
        dry_run: bool,
    },
}

#[derive(Subcommand)]
enum PackageCommands {
    #[command(about = "Build a .mpkg package from a directory")]
    Build {
        #[arg(help = "Source directory containing package files")]
        source_dir: PathBuf,

        #[arg(short, long, help = "Output .mpkg destination path")]
        output: PathBuf,

        #[arg(long, help = "Package name [default: directory name]")]
        name: Option<String>,

        #[arg(long, default_value = "0.1.0", help = "Package version")]
        version: String,

        #[arg(long, value_enum, default_value_t = CliTier::ProjectOrAgent, help = "Package tier (§13.2)")]
        tier: CliTier,

        #[arg(long, default_value = "", help = "Package description")]
        description: String,
    },

    #[command(about = "Inspect package manifest and contents inside a .mpkg archive")]
    Inspect {
        #[arg(help = "Path to .mpkg package file")]
        path: PathBuf,
    },
}

#[derive(Subcommand)]
enum GenerationCommands {
    #[command(about = "List all published generations for the profile")]
    List,

    #[command(about = "Show current active generation for the profile")]
    Current,

    #[command(about = "Switch to a specific generation ID (e.g. gen-1)")]
    Switch {
        #[arg(help = "Generation ID to switch to")]
        generation_id: String,
    },

    #[command(about = "Instant atomic rollback to previous generation (gen-(N-1))")]
    Rollback,
}

#[derive(Subcommand)]
enum ArtifactCommands {
    #[command(about = "List all immutable artifacts stored in CAS")]
    List,

    #[command(about = "Verify cryptographic integrity of stored artifacts")]
    Verify {
        #[arg(help = "Specific artifact digest to verify (optional)")]
        digest: Option<String>,
    },
}

#[derive(Clone, Copy, ValueEnum)]
enum CliTier {
    HostSystem,
    PlatformRuntime,
    ProjectOrAgent,
    PerExecution,
    UserApplication,
}

impl From<CliTier> for PackageTier {
    fn from(t: CliTier) -> Self {
        match t {
            CliTier::HostSystem => PackageTier::HostSystem,
            CliTier::PlatformRuntime => PackageTier::PlatformRuntime,
            CliTier::ProjectOrAgent => PackageTier::ProjectOrAgent,
            CliTier::PerExecution => PackageTier::PerExecution,
            CliTier::UserApplication => PackageTier::UserApplication,
        }
    }
}

fn resolve_environment(cli: &Cli) -> EnvironmentId {
    if cli.system {
        EnvironmentId::system()
    } else if let Some(p) = &cli.profile {
        EnvironmentId::new(p.clone())
    } else {
        EnvironmentId::new("default")
    }
}

fn main() {
    let cli = Cli::parse();

    // Commands that operate locally without requiring a store instance
    if let Commands::Package(pkg_cmd) = &cli.command {
        match pkg_cmd {
            PackageCommands::Build {
                source_dir,
                output,
                name,
                version,
                tier,
                description,
            } => {
                let pkg_name = name.clone().unwrap_or_else(|| {
                    source_dir
                        .canonicalize()
                        .ok()
                        .and_then(|p| p.file_name().map(|n| n.to_string_lossy().to_string()))
                        .unwrap_or_else(|| "unnamed-package".to_string())
                });

                let mut manifest = PackageManifest::new(pkg_name, version, (*tier).into());
                manifest.description = description.clone();

                let mut builder = PackageBuilder::new(source_dir, manifest);
                match builder.build_to_file(output) {
                    Ok(digest) => {
                        if cli.json {
                            println!(
                                "{}",
                                serde_json::json!({
                                    "status": "success",
                                    "package": builder.manifest().id.name,
                                    "version": builder.manifest().id.version,
                                    "digest": digest.to_string(),
                                    "output": output.display().to_string()
                                })
                            );
                        } else {
                            println!("✓ Successfully built package {}", output.display());
                            println!("  Name:    {}", builder.manifest().id.name);
                            println!("  Version: {}", builder.manifest().id.version);
                            println!("  Digest:  {}", digest);
                            println!("  Files:   {}", builder.manifest().files.len());
                        }
                    }
                    Err(e) => {
                        eprintln!("Error building package: {}", e);
                        exit(1);
                    }
                }
                return;
            }
            PackageCommands::Inspect { path } => {
                match PackageArchive::inspect(path) {
                    Ok(manifest) => {
                        if cli.json {
                            println!("{}", serde_json::to_string_pretty(&manifest).unwrap());
                        } else {
                            println!("Package Manifest: {} v{}", manifest.id.name, manifest.id.version);
                            println!("  Tier:        {:?}", manifest.tier);
                            println!("  License:     {}", manifest.license);
                            println!("  Description: {}", manifest.description);
                            println!("  Files ({}):", manifest.files.len());
                            for f in &manifest.files {
                                let exec_flag = if f.is_executable { " [exec]" } else { "" };
                                println!("    - {} ({} bytes, {}){}", f.relative_path, f.size_bytes, f.digest, exec_flag);
                            }
                        }
                    }
                    Err(e) => {
                        eprintln!("Error inspecting package: {}", e);
                        exit(1);
                    }
                }
                return;
            }
        }
    }

    // Commands that query search/info over network
    if let Commands::Search { query, aur } = &cli.command {
        println!("Searching Arch official repositories for '{}'...", query);
        match ArchClient::search(query) {
            Ok(results) => {
                if cli.json {
                    println!("{}", serde_json::to_string_pretty(&results).unwrap());
                } else {
                    println!("Arch Linux Official Repositories ({} matches):", results.len());
                    for pkg in results.iter().take(25) {
                        println!("  • {}/{} v{} - {}", pkg.repo, pkg.pkgname, pkg.pkgver, pkg.pkgdesc);
                    }
                }
            }
            Err(e) => {
                eprintln!("Error querying Arch repositories: {}", e);
            }
        }

        if *aur {
            println!("\nSearching Arch User Repository (AUR) for '{}'...", query);
            match ArchClient::search_aur(query) {
                Ok(results) => {
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&results).unwrap());
                    } else {
                        println!("Arch User Repository (AUR) ({} matches):", results.len());
                        for pkg in results.iter().take(25) {
                            let desc = pkg.description.as_deref().unwrap_or("No description");
                            println!("  • aur/{} v{} - {}", pkg.name, pkg.version, desc);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error querying AUR: {}", e);
                }
            }
        }
        return;
    }

    if let Commands::Info { package, aur } = &cli.command {
        if *aur {
            match ArchClient::get_aur_info(package) {
                Ok(Some(pkg)) => {
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&pkg).unwrap());
                    } else {
                        println!("AUR Package: {}", pkg.name);
                        println!("  Version:      {}", pkg.version);
                        println!("  Description:  {}", pkg.description.as_deref().unwrap_or(""));
                        println!("  URL:          {}", pkg.url.as_deref().unwrap_or(""));
                        if let Some(deps) = &pkg.depends {
                            println!("  Dependencies: {}", deps.join(", "));
                        }
                    }
                }
                Ok(None) => {
                    eprintln!("Package '{}' not found in AUR.", package);
                    exit(1);
                }
                Err(e) => {
                    eprintln!("Error fetching AUR info: {}", e);
                    exit(1);
                }
            }
        } else {
            match ArchClient::get_package_info(package) {
                Ok(Some(pkg)) => {
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&pkg).unwrap());
                    } else {
                        println!("Arch Package: {}/{}", pkg.repo, pkg.pkgname);
                        println!("  Version:         {}-{}", pkg.pkgver, pkg.pkgrel);
                        println!("  Architecture:    {}", pkg.arch);
                        println!("  Description:     {}", pkg.pkgdesc);
                        println!("  URL:             {}", pkg.url.as_deref().unwrap_or(""));
                        println!("  Compressed Size: {} KB", pkg.compressed_size / 1024);
                        println!("  Installed Size:  {} KB", pkg.installed_size / 1024);
                        if !pkg.depends.is_empty() {
                            println!("  Dependencies:    {}", pkg.depends.join(", "));
                        }
                    }
                }
                Ok(None) => {
                    eprintln!("Package '{}' not found in official Arch repositories. Try '--aur' to search AUR.", package);
                    exit(1);
                }
                Err(e) => {
                    eprintln!("Error fetching package info: {}", e);
                    exit(1);
                }
            }
        }
        return;
    }

    let env = resolve_environment(&cli);
    let allow_host = cli.allow_host_mutation || cli.system;

    let pkg_mgr = match PackageManager::default_or_env(allow_host) {
        Ok(mgr) => mgr,
        Err(e) => {
            eprintln!("Error initializing package manager: {}", e);
            exit(1);
        }
    };

    match &cli.command {
        Commands::Package(_) | Commands::Search { .. } | Commands::Info { .. } => unreachable!(),

        Commands::Install { target, aur } => {
            let path = Path::new(target);
            if path.exists() {
                // Local archive installation (.mpkg or .pkg.tar.zst)
                if target.ends_with(".mpkg") {
                    match pkg_mgr.install_package(path, &env) {
                        Ok((gen, pkg_ref)) => {
                            report_install_success(&cli, &env, &gen.id, &pkg_ref.id.name, &pkg_ref.id.version, &pkg_ref.digest.to_string(), &pkg_mgr);
                        }
                        Err(e) => {
                            eprintln!("Error installing package: {}", e);
                            exit(1);
                        }
                    }
                } else if target.ends_with(".pkg.tar.zst") {
                    let tier = if env.is_host() { PackageTier::HostSystem } else { PackageTier::UserApplication };
                    match ArchClient::ingest_arch_package(pkg_mgr.store(), path, tier) {
                        Ok((manifest, digest, _)) => {
                            let pkg_ref = myelin_types::PackageRef {
                                id: manifest.id.clone(),
                                tier: manifest.tier,
                                artifact_id: myelin_types::ArtifactId::new(format!("art-{}", &digest.hex()[..16])),
                                digest: digest.clone(),
                                description: manifest.description.clone(),
                            };
                            let current_gen = pkg_mgr.gen_mgr().current_generation(&env).unwrap_or(None);
                            let mut packages = current_gen.map(|g| g.packages).unwrap_or_default();
                            packages.push(pkg_ref.clone());
                            let gen = pkg_mgr.gen_mgr().create_generation(&env, tier, packages, pkg_mgr.store()).unwrap();
                            report_install_success(&cli, &env, &gen.id, &manifest.id.name, &manifest.id.version, &digest.to_string(), &pkg_mgr);
                        }
                        Err(e) => {
                            eprintln!("Error ingesting Arch package: {}", e);
                            exit(1);
                        }
                    }
                } else {
                    eprintln!("Unsupported package file format: '{}'. Expected .mpkg or .pkg.tar.zst", target);
                    exit(1);
                }
            } else {
                // Fetch from official Arch Linux repositories or AUR
                println!("Resolving '{}' from Arch Linux repositories...", target);
                match pkg_mgr.install_arch_package(target, &env) {
                    Ok((gen, pkg_ref)) => {
                        report_install_success(&cli, &env, &gen.id, &pkg_ref.id.name, &pkg_ref.id.version, &pkg_ref.digest.to_string(), &pkg_mgr);
                    }
                    Err(e) => {
                        if *aur {
                            println!("Package '{}' not in official repos; querying AUR...", target);
                            match ArchClient::get_aur_info(target) {
                                Ok(Some(aur_info)) => {
                                    println!("Found '{}' v{} in AUR. Note: Native binary ingestion supported.", aur_info.name, aur_info.version);
                                    eprintln!("AUR build engine: package '{}' requires makepkg build.", target);
                                    exit(1);
                                }
                                Ok(None) => {
                                    eprintln!("Package '{}' not found in Arch repos or AUR.", target);
                                    exit(1);
                                }
                                Err(err) => {
                                    eprintln!("AUR error: {}", err);
                                    exit(1);
                                }
                            }
                        } else {
                            eprintln!("Error: {}", e);
                            eprintln!("Tip: pass '--aur' to search and install from the Arch User Repository.");
                            exit(1);
                        }
                    }
                }
            }
        }

        Commands::Remove { name } => match pkg_mgr.remove_package(name, &env) {
            Ok(gen) => {
                if cli.json {
                    println!(
                        "{}",
                        serde_json::json!({
                            "status": "removed",
                            "environment": env.to_string(),
                            "generation": gen.id.to_string(),
                            "package": name
                        })
                    );
                } else {
                    println!("✓ Successfully removed package '{}' from profile '{}'", name, env);
                    println!("  Active Generation: {}", gen.id);
                }
            }
            Err(e) => {
                eprintln!("Error removing package: {}", e);
                exit(1);
            }
        },

        Commands::List => match pkg_mgr.list_installed(&env) {
            Ok(packages) => {
                if cli.json {
                    println!("{}", serde_json::to_string_pretty(&packages).unwrap());
                } else {
                    println!("Profile '{}' Installed Packages ({}):", env, packages.len());
                    if packages.is_empty() {
                        println!("  (no packages installed in active generation)");
                    } else {
                        for p in &packages {
                            println!("  • {} v{} [{:?}] - {}", p.id.name, p.id.version, p.tier, p.digest);
                        }
                    }
                }
            }
            Err(e) => {
                eprintln!("Error listing packages: {}", e);
                exit(1);
            }
        },

        Commands::Rollback => match pkg_mgr.rollback(&env) {
            Ok(gen) => {
                if cli.json {
                    println!(
                        "{}",
                        serde_json::json!({
                            "status": "rolled_back",
                            "environment": env.to_string(),
                            "generation": gen.id.to_string()
                        })
                    );
                } else {
                    println!("✓ Atomically rolled back profile '{}' to {}", env, gen.id);
                }
            }
            Err(e) => {
                eprintln!("Error rolling back generation: {}", e);
                exit(1);
            }
        },

        Commands::Generation(gen_cmd) => match gen_cmd {
            GenerationCommands::List => match pkg_mgr.list_generations(&env) {
                Ok(gens) => {
                    let curr = pkg_mgr.current_generation(&env).ok().flatten();
                    let curr_id = curr.map(|g| g.id);

                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&gens).unwrap());
                    } else {
                        println!("Generations for profile '{}' ({}):", env, gens.len());
                        for g in &gens {
                            let marker = if Some(&g.id) == curr_id.as_ref() { " (current)" } else { "" };
                            println!("  [{}] packages: {}, created: {}{}", g.id, g.packages.len(), g.created_at, marker);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error listing generations: {}", e);
                    exit(1);
                }
            },
            GenerationCommands::Current => match pkg_mgr.current_generation(&env) {
                Ok(Some(curr)) => {
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&curr).unwrap());
                    } else {
                        println!("Current Generation for profile '{}': {}", env, curr.id);
                        println!("  Manifest Digest: {}", curr.manifest_digest);
                        println!("  Created At:      {}", curr.created_at);
                        println!("  Tier:            {:?}", curr.tier);
                        println!("  Packages ({}):", curr.packages.len());
                        for p in &curr.packages {
                            println!("    - {} v{}", p.id.name, p.id.version);
                        }
                    }
                }
                Ok(None) => {
                    if cli.json {
                        println!("null");
                    } else {
                        println!("Profile '{}' has no active generation published.", env);
                    }
                }
                Err(e) => {
                    eprintln!("Error getting current generation: {}", e);
                    exit(1);
                }
            },
            GenerationCommands::Switch { generation_id } => {
                let target_id = match GenerationId::parse(generation_id) {
                    Some(id) => id,
                    None => {
                        eprintln!("Invalid generation ID format: '{}'. Expected 'gen-<N>'.", generation_id);
                        exit(1);
                    }
                };
                match pkg_mgr.switch_generation(&env, &target_id) {
                    Ok(gen) => {
                        if cli.json {
                            println!(
                                "{}",
                                serde_json::json!({
                                    "status": "switched",
                                    "environment": env.to_string(),
                                    "generation": gen.id.to_string()
                                })
                            );
                        } else {
                            println!("✓ Successfully switched profile '{}' to {}", env, gen.id);
                        }
                    }
                    Err(e) => {
                        eprintln!("Error switching generation: {}", e);
                        exit(1);
                    }
                }
            }
            GenerationCommands::Rollback => match pkg_mgr.rollback(&env) {
                Ok(gen) => {
                    if cli.json {
                        println!(
                            "{}",
                            serde_json::json!({
                                "status": "rolled_back",
                                "environment": env.to_string(),
                                "generation": gen.id.to_string()
                            })
                        );
                    } else {
                        println!("✓ Atomically rolled back profile '{}' to {}", env, gen.id);
                    }
                }
                Err(e) => {
                    eprintln!("Error rolling back generation: {}", e);
                    exit(1);
                }
            },
        },

        Commands::Artifact(art_cmd) => match art_cmd {
            ArtifactCommands::List => match pkg_mgr.store().list_artifacts() {
                Ok(artifacts) => {
                    if cli.json {
                        println!("{}", serde_json::to_string_pretty(&artifacts).unwrap());
                    } else {
                        println!("Content-Addressed Artifacts ({}):", artifacts.len());
                        for a in &artifacts {
                            println!("  • {} [{} bytes, {}] - {}", a.id, a.size_bytes, a.content_type, a.digest);
                        }
                    }
                }
                Err(e) => {
                    eprintln!("Error listing artifacts: {}", e);
                    exit(1);
                }
            },
            ArtifactCommands::Verify { digest } => {
                if let Some(d_str) = digest {
                    let d = match myelin_types::Digest::parse(d_str) {
                        Some(d) => d,
                        None => {
                            eprintln!("Invalid digest format: '{}'. Expected 'sha256:<hex>'", d_str);
                            exit(1);
                        }
                    };
                    match pkg_mgr.store().verify(&d) {
                        Ok(true) => {
                            println!("✓ Artifact {} verified successfully.", d);
                        }
                        Ok(false) => {
                            eprintln!("✗ Artifact {} verification returned false", d);
                            exit(1);
                        }
                        Err(e) => {
                            eprintln!("✗ Artifact {} verification failed: {}", d, e);
                            exit(1);
                        }
                    }
                } else {
                    match pkg_mgr.verify_store() {
                        Ok(report) => {
                            if cli.json {
                                println!("{}", serde_json::to_string_pretty(&report).unwrap());
                            } else {
                                println!("Store Verification Report:");
                                println!("  Total artifacts: {}", report.total_artifacts);
                                println!("  Verified:        {}", report.verified_count);
                                println!("  Corrupted:       {}", report.corrupted_count);
                                if !report.corrupted.is_empty() {
                                    println!("\nCorrupted artifacts:");
                                    for (d, err) in &report.corrupted {
                                        println!("  ✗ {}: {}", d, err);
                                    }
                                }
                            }
                        }
                        Err(e) => {
                            eprintln!("Error verifying artifacts: {}", e);
                            exit(1);
                        }
                    }
                }
            }
        },

        Commands::Gc { dry_run } => match pkg_mgr.garbage_collect(*dry_run) {
            Ok(report) => {
                if cli.json {
                    println!("{}", serde_json::to_string_pretty(&report).unwrap());
                } else {
                    let mode = if report.dry_run { " (dry run)" } else { "" };
                    println!("Garbage Collection Complete{}:", mode);
                    println!("  Scanned objects:  {}", report.total_objects_scanned);
                    println!("  Retained objects: {}", report.retained_objects);
                    println!("  Deleted objects:  {}", report.deleted_objects);
                    println!("  Bytes freed:      {} bytes", report.bytes_freed);
                }
            }
            Err(e) => {
                eprintln!("Error during garbage collection: {}", e);
                exit(1);
            }
        },
    }
}

fn report_install_success(
    cli: &Cli,
    env: &EnvironmentId,
    gen_id: &GenerationId,
    pkg_name: &str,
    pkg_ver: &str,
    digest: &str,
    pkg_mgr: &PackageManager,
) {
    if cli.json {
        println!(
            "{}",
            serde_json::json!({
                "status": "installed",
                "environment": env.to_string(),
                "generation": gen_id.to_string(),
                "package": pkg_name,
                "version": pkg_ver,
                "digest": digest,
            })
        );
    } else {
        println!("✓ Successfully installed {} v{} into profile '{}'", pkg_name, pkg_ver, env);
        println!("  Active Generation: {}", gen_id);
        println!("  Artifact Digest:   {}", digest);
        println!("  Profile Path:      {}", pkg_mgr.profile_mgr().profile_link_path(env).display());
    }
}
