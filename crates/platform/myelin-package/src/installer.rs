use crate::archive::PackageArchive;
use crate::isolation::IsolationPolicy;
use myelin_artifact::ArtifactStore;
use myelin_generation::{GenerationManager, ProfileManager};
use myelin_types::{
    ArtifactId, EnvironmentId, Generation, GenerationId, MyelinError,
    PackageRef, PackageTier, Result,
};
use serde::{Deserialize, Serialize};
use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StoreVerificationReport {
    pub total_artifacts: usize,
    pub verified_count: usize,
    pub corrupted_count: usize,
    pub corrupted: Vec<(String, String)>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GcReport {
    pub total_objects_scanned: usize,
    pub retained_objects: usize,
    pub deleted_objects: usize,
    pub bytes_freed: u64,
    pub dry_run: bool,
}

/// Central coordinator for the Myelin Package Subsystem (§5.4, §13, §14).
#[derive(Debug, Clone)]
pub struct PackageManager {
    store: ArtifactStore,
    gen_mgr: GenerationManager,
    profile_mgr: ProfileManager,
    isolation: IsolationPolicy,
}

impl PackageManager {
    pub fn new(
        store: ArtifactStore,
        gen_mgr: GenerationManager,
        profile_mgr: ProfileManager,
        isolation: IsolationPolicy,
    ) -> Self {
        Self {
            store,
            gen_mgr,
            profile_mgr,
            isolation,
        }
    }

    /// Initializes PackageManager from environment variables or canonical system directories.
    pub fn default_or_env(allow_host_mutation: bool) -> Result<Self> {
        let is_root = unsafe { libc::geteuid() } == 0;
        let base_dir = if let Ok(dir) = std::env::var("MYELIN_HOME") {
            PathBuf::from(dir)
        } else if is_root {
            PathBuf::from("/var/lib/myelin")
        } else if let Ok(home) = std::env::var("HOME") {
            PathBuf::from(home).join(".local/share/myelin")
        } else {
            PathBuf::from("/var/lib/myelin")
        };

        let store_dir = std::env::var("MYELIN_STORE_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| base_dir.join("store"));
        let store = ArtifactStore::new(store_dir)?;

        let profiles_dir = std::env::var("MYELIN_PROFILES_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| base_dir.join("profiles"));
        let profile_mgr = ProfileManager::new(profiles_dir)?;

        let gen_dir = std::env::var("MYELIN_GENERATIONS_DIR")
            .map(PathBuf::from)
            .unwrap_or_else(|_| base_dir.join("generations"));
        let gen_mgr = GenerationManager::new(gen_dir, profile_mgr.clone())?;

        let isolation = IsolationPolicy::new(allow_host_mutation);

        Ok(Self::new(store, gen_mgr, profile_mgr, isolation))
    }

    pub fn store(&self) -> &ArtifactStore {
        &self.store
    }

    pub fn gen_mgr(&self) -> &GenerationManager {
        &self.gen_mgr
    }

    pub fn profile_mgr(&self) -> &ProfileManager {
        &self.profile_mgr
    }

    pub fn isolation(&self) -> &IsolationPolicy {
        &self.isolation
    }

    /// Installs a package archive into an environment profile.
    /// Invariants:
    /// - Isolation validated (§13.2)
    /// - Ingested into CAS store (INV-18)
    /// - New generation materialized and atomically promoted.
    pub fn install_package(
        &self,
        archive_path: &Path,
        env: &EnvironmentId,
    ) -> Result<(Generation, PackageRef)> {
        // 1. Inspect package manifest
        let manifest = PackageArchive::inspect(archive_path)?;

        // 2. Validate isolation constraints
        self.isolation.validate_install(env, &manifest)?;

        // 3. Ingest into CAS store
        let (manifest, archive_digest, _unpacked_dir) =
            PackageArchive::ingest_into_store(&self.store, archive_path)?;

        let pkg_ref = PackageRef {
            id: manifest.id.clone(),
            tier: manifest.tier,
            artifact_id: ArtifactId::new(format!("art-{}", &archive_digest.hex()[..16])),
            digest: archive_digest,
            description: manifest.description.clone(),
        };

        // 4. Determine package set for the next generation
        let current_gen = self.gen_mgr.current_generation(env)?;
        let mut packages = match &current_gen {
            Some(g) => g.packages.clone(),
            None => Vec::new(),
        };

        // Replace if already present with same package name, else append
        if let Some(pos) = packages.iter().position(|p| p.id.name == pkg_ref.id.name) {
            packages[pos] = pkg_ref.clone();
        } else {
            packages.push(pkg_ref.clone());
        }

        // Tier matches environment type or highest tier present
        let env_tier = if env.is_host() {
            PackageTier::HostSystem
        } else {
            manifest.tier
        };

        // 5. Create immutable generation & atomically switch profile
        let new_gen = self
            .gen_mgr
            .create_generation(env, env_tier, packages, &self.store)?;

        Ok((new_gen, pkg_ref))
    }

    /// Fetches an official Arch Linux binary package (.pkg.tar.zst) from cache or mirrors,
    /// ingests it into CAS, and publishes a new profile generation.
    pub fn install_arch_package(
        &self,
        name: &str,
        env: &EnvironmentId,
    ) -> Result<(Generation, PackageRef)> {
        // 1. Determine tier
        let tier = if env.is_host() {
            PackageTier::HostSystem
        } else {
            PackageTier::UserApplication
        };

        // 2. Check local package caches first
        let cache_dirs = [
            PathBuf::from("/var/cache/myelin/packages"),
            PathBuf::from("/usr/share/myelin/packages"),
            PathBuf::from("build/packages/cache"),
            self.store.root().join("cache"),
            PathBuf::from("/tmp/packages"),
        ];

        let mut cached_pkg: Option<PathBuf> = None;
        for cdir in &cache_dirs {
            if cdir.exists() {
                if let Ok(entries) = fs::read_dir(cdir) {
                    for entry in entries.flatten() {
                        let path = entry.path();
                        if let Some(fname) = path.file_name().and_then(|n| n.to_str()) {
                            let prefix = format!("{}-", name);
                            if (fname.starts_with(&prefix) || fname == format!("{}.pkg.tar.zst", name))
                                && fname.ends_with(".pkg.tar.zst")
                            {
                                cached_pkg = Some(path);
                                break;
                            }
                        }
                    }
                }
            }
            if cached_pkg.is_some() {
                break;
            }
        }

        let (manifest, digest, _unpacked) = if let Some(pkg_file) = cached_pkg {
            crate::arch::ArchClient::ingest_arch_package(&self.store, &pkg_file, tier)?
        } else {
            // Fetch info from official Arch repos
            let pkg_info = crate::arch::ArchClient::get_package_info(name)?
                .ok_or_else(|| MyelinError::ObjectNotFound(format!("Arch package '{}' not found in official repositories or local cache", name)))?;

            // Download into temporary directory
            let tmp_dir = self.store.root().join("tmp");
            fs::create_dir_all(&tmp_dir)?;
            let pkg_file = tmp_dir.join(&pkg_info.filename);
            crate::arch::ArchClient::download_package(&pkg_info, &pkg_file)?;

            let res = crate::arch::ArchClient::ingest_arch_package(&self.store, &pkg_file, tier)?;

            // Cache for future offline use
            let cache_target_dir = PathBuf::from("/var/cache/myelin/packages");
            if fs::create_dir_all(&cache_target_dir).is_ok() {
                let _ = fs::copy(&pkg_file, cache_target_dir.join(&pkg_info.filename));
            }

            let _ = fs::remove_file(pkg_file);
            res
        };

        let pkg_ref = PackageRef {
            id: manifest.id.clone(),
            tier: manifest.tier,
            artifact_id: ArtifactId::new(format!("art-{}", &digest.hex()[..16])),
            digest,
            description: manifest.description.clone(),
        };

        // 3. Update generation package set
        let current_gen = self.gen_mgr.current_generation(env)?;
        let mut packages = match &current_gen {
            Some(g) => g.packages.clone(),
            None => Vec::new(),
        };

        if let Some(pos) = packages.iter().position(|p| p.id.name == pkg_ref.id.name) {
            packages[pos] = pkg_ref.clone();
        } else {
            packages.push(pkg_ref.clone());
        }

        let new_gen = self.gen_mgr.create_generation(env, tier, packages, &self.store)?;

        // 4. Link binaries into system PATH if host/system profile
        if env.is_host() {
            let usr_local_bin = PathBuf::from("/usr/local/bin");
            if fs::create_dir_all(&usr_local_bin).is_ok() {
                let gen_bin = self.gen_mgr.gen_dir(env, &new_gen.id).join("bin");
                if gen_bin.exists() {
                    if let Ok(entries) = fs::read_dir(gen_bin) {
                        for entry in entries.flatten() {
                            let bin_path = entry.path();
                            if let Some(bin_name) = bin_path.file_name() {
                                let link_path = usr_local_bin.join(bin_name);
                                let _ = fs::remove_file(&link_path);
                                let _ = std::os::unix::fs::symlink(&bin_path, &link_path);
                            }
                        }
                    }
                }
            }
        }

        Ok((new_gen, pkg_ref))
    }

    /// Removes a package from an environment profile, creating a new generation.
    pub fn remove_package(
        &self,
        package_name: &str,
        env: &EnvironmentId,
    ) -> Result<Generation> {
        let current_gen = self.gen_mgr.current_generation(env)?.ok_or_else(|| {
            MyelinError::ObjectNotFound(format!("No active generation found for profile '{}'", env))
        })?;

        let mut packages = current_gen.packages.clone();
        let initial_len = packages.len();
        packages.retain(|p| p.id.name != package_name);

        if packages.len() == initial_len {
            return Err(MyelinError::ObjectNotFound(format!(
                "Package '{}' is not installed in profile '{}'",
                package_name, env
            )));
        }

        let new_gen = self.gen_mgr.create_generation(
            env,
            current_gen.tier,
            packages,
            &self.store,
        )?;

        Ok(new_gen)
    }

    /// Lists packages installed in the active generation of an environment profile.
    pub fn list_installed(&self, env: &EnvironmentId) -> Result<Vec<PackageRef>> {
        let current = self.gen_mgr.current_generation(env)?;
        Ok(current.map(|g| g.packages).unwrap_or_default())
    }

    /// Lists all generations published for an environment profile.
    pub fn list_generations(&self, env: &EnvironmentId) -> Result<Vec<Generation>> {
        self.gen_mgr.list_generations(env)
    }

    /// Gets current active generation for an environment profile.
    pub fn current_generation(&self, env: &EnvironmentId) -> Result<Option<Generation>> {
        self.gen_mgr.current_generation(env)
    }

    /// Rolls back the profile to its previous generation.
    pub fn rollback(&self, env: &EnvironmentId) -> Result<Generation> {
        self.gen_mgr.rollback(env)
    }

    /// Switches the profile to a specific generation.
    pub fn switch_generation(&self, env: &EnvironmentId, gen_id: &GenerationId) -> Result<Generation> {
        self.gen_mgr.switch_generation(env, gen_id)
    }

    /// Cryptographically verifies all artifacts in the CAS store (§5.7).
    pub fn verify_store(&self) -> Result<StoreVerificationReport> {
        let all_meta = self.store.list_artifacts()?;
        let mut corrupted = Vec::new();
        let mut verified_count = 0;

        for meta in &all_meta {
            match self.store.verify(&meta.digest) {
                Ok(true) => verified_count += 1,
                Ok(false) => corrupted.push((meta.digest.to_string(), "Verification returned false".to_string())),
                Err(e) => corrupted.push((meta.digest.to_string(), e.to_string())),
            }
        }

        Ok(StoreVerificationReport {
            total_artifacts: all_meta.len(),
            verified_count,
            corrupted_count: corrupted.len(),
            corrupted,
        })
    }

    /// Performs Garbage Collection (GC) across the ArtifactStore (§31, §36.3).
    /// Gathers all live references from all generations across all environments,
    /// and purges unreferenced objects.
    pub fn garbage_collect(&self, dry_run: bool) -> Result<GcReport> {
        let mut live_digests: HashSet<String> = HashSet::new();

        // 1. Scan all environments in generations directory
        let gen_root = self.gen_mgr.env_generations_dir(&EnvironmentId::new(".."));
        let gen_base = gen_root.parent().unwrap_or(&gen_root);

        if gen_base.exists() {
            for env_entry in fs::read_dir(gen_base)? {
                let env_entry = env_entry?;
                if env_entry.file_type()?.is_dir() {
                    let env_name = env_entry.file_name().to_string_lossy().to_string();
                    let env_id = EnvironmentId::new(env_name);
                    if let Ok(gens) = self.gen_mgr.list_generations(&env_id) {
                        for g in gens {
                            for pkg in g.packages {
                                live_digests.insert(pkg.digest.hex().to_string());
                            }
                        }
                    }
                }
            }
        }

        // 2. Scan store objects and identify unreferenced artifacts
        let all_artifacts = self.store.list_artifacts()?;
        let mut retained = 0;
        let mut deleted = 0;
        let mut bytes_freed = 0u64;

        for meta in all_artifacts {
            let hex = meta.digest.hex();
            if live_digests.contains(hex) {
                retained += 1;
            } else {
                deleted += 1;
                bytes_freed += meta.size_bytes;

                if !dry_run {
                    let obj_path = self.store.artifact_path(&meta.digest);
                    let meta_path = self.store.meta_path(&meta.digest);
                    let unpacked_path = self.store.root().join("unpacked").join(hex);

                    let _ = fs::remove_file(obj_path);
                    let _ = fs::remove_file(meta_path);
                    if unpacked_path.exists() {
                        let _ = fs::remove_dir_all(unpacked_path);
                    }
                }
            }
        }

        Ok(GcReport {
            total_objects_scanned: retained + deleted,
            retained_objects: retained,
            deleted_objects: deleted,
            bytes_freed,
            dry_run,
        })
    }
}
