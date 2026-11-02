use crate::profile::ProfileManager;
use myelin_artifact::ArtifactStore;
use myelin_types::{EnvironmentId, Generation, GenerationId, MyelinError, PackageRef, PackageTier, Result};
use std::fs;
use std::os::unix::fs as unix_fs;
use std::path::PathBuf;

/// Manager for immutable published system & environment generations (§5.8, §14.2).
#[derive(Debug, Clone)]
pub struct GenerationManager {
    generations_dir: PathBuf,
    profile_mgr: ProfileManager,
}

impl GenerationManager {
    pub const DEFAULT_DIR: &'static str = "/var/lib/myelin/generations";

    pub fn new(root: impl Into<PathBuf>, profile_mgr: ProfileManager) -> Result<Self> {
        let generations_dir = root.into();
        fs::create_dir_all(&generations_dir)?;
        Ok(Self {
            generations_dir,
            profile_mgr,
        })
    }

    pub fn default_or_env(profile_mgr: ProfileManager) -> Result<Self> {
        if let Ok(dir) = std::env::var("MYELIN_GENERATIONS_DIR") {
            Self::new(dir, profile_mgr)
        } else {
            Self::new(Self::DEFAULT_DIR, profile_mgr)
        }
    }

    pub fn env_generations_dir(&self, env: &EnvironmentId) -> PathBuf {
        self.generations_dir.join(env.as_str())
    }

    pub fn gen_manifest_path(&self, env: &EnvironmentId, gen_id: &GenerationId) -> PathBuf {
        self.env_generations_dir(env).join(format!("{}.json", gen_id))
    }

    pub fn gen_dir(&self, env: &EnvironmentId, gen_id: &GenerationId) -> PathBuf {
        self.env_generations_dir(env).join(gen_id.to_string_id())
    }

    pub fn current_link(&self, env: &EnvironmentId) -> PathBuf {
        self.env_generations_dir(env).join("current")
    }

    /// Lists all generations for a profile in ascending order.
    pub fn list_generations(&self, env: &EnvironmentId) -> Result<Vec<Generation>> {
        let dir = self.env_generations_dir(env);
        if !dir.exists() {
            return Ok(Vec::new());
        }

        let mut gens = Vec::new();
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.extension().map_or(false, |ext| ext == "json") {
                if let Ok(text) = fs::read_to_string(&path) {
                    if let Ok(gen) = serde_json::from_str::<Generation>(&text) {
                        gens.push(gen);
                    }
                }
            }
        }

        gens.sort_by_key(|g| g.id.0);
        Ok(gens)
    }

    /// Gets the current active generation for an environment profile.
    pub fn current_generation(&self, env: &EnvironmentId) -> Result<Option<Generation>> {
        let link = self.current_link(env);
        if !link.exists() {
            return Ok(None);
        }
        let target = fs::read_link(&link)?;
        let gen_str = target
            .file_name()
            .and_then(|n| n.to_str())
            .ok_or_else(|| MyelinError::InvalidInput("Invalid current link target".to_string()))?;
        
        let gen_id = GenerationId::parse(gen_str)
            .ok_or_else(|| MyelinError::InvalidInput(format!("Cannot parse generation ID: {}", gen_str)))?;
        
        let manifest_path = self.gen_manifest_path(env, &gen_id);
        if !manifest_path.exists() {
            return Ok(None);
        }
        let text = fs::read_to_string(manifest_path)?;
        let gen = serde_json::from_str::<Generation>(&text)?;
        Ok(Some(gen))
    }

    /// Publishes a new immutable generation for an environment profile.
    /// Materializes symlink tree and performs atomic promotion (§5.8, INV-18).
    pub fn create_generation(
        &self,
        env: &EnvironmentId,
        tier: PackageTier,
        packages: Vec<PackageRef>,
        store: &ArtifactStore,
    ) -> Result<Generation> {
        let env_dir = self.env_generations_dir(env);
        fs::create_dir_all(&env_dir)?;

        let current = self.current_generation(env)?;
        let next_id = match &current {
            Some(curr) => curr.id.next(),
            None => GenerationId::new(1),
        };
        let parent_id = current.map(|c| c.id);

        let created_at = "2026-11-02T10:00:00Z".to_string();
        let generation = Generation::new(
            next_id.clone(),
            parent_id,
            env.clone(),
            tier,
            created_at,
            packages,
        );

        // 1. Materialize generation directory tree
        let gen_path = self.gen_dir(env, &next_id);
        fs::create_dir_all(&gen_path)?;
        self.profile_mgr
            .materialize_generation_tree(&gen_path, &generation, store)?;

        // 2. Write immutable generation manifest
        let manifest_path = self.gen_manifest_path(env, &next_id);
        let manifest_json = serde_json::to_string_pretty(&generation)?;
        fs::write(&manifest_path, manifest_json)?;

        // 3. Atomically update environment current link
        let tmp_link = env_dir.join(format!(".tmp_current_{}", next_id));
        if tmp_link.exists() || tmp_link.is_symlink() {
            let _ = fs::remove_file(&tmp_link);
        }
        unix_fs::symlink(gen_path.file_name().unwrap(), &tmp_link)?;
        fs::rename(&tmp_link, self.current_link(env))?;

        // 4. Atomically activate profile symlink
        self.profile_mgr.activate_generation(env, &gen_path)?;

        Ok(generation)
    }

    /// Atomically rolls back to the prior generation (gen-(N-1)) (§14.5).
    pub fn rollback(&self, env: &EnvironmentId) -> Result<Generation> {
        let current = self.current_generation(env)?.ok_or_else(|| {
            MyelinError::ObjectNotFound(format!("No active generation found for profile {}", env))
        })?;

        let parent_id = current.parent_id.ok_or_else(|| {
            MyelinError::InvalidTransition(format!(
                "Cannot rollback generation {}: it has no parent generation",
                current.id
            ))
        })?;

        self.switch_generation(env, &parent_id)
    }

    /// Atomically switches the active generation for a profile.
    pub fn switch_generation(&self, env: &EnvironmentId, target_id: &GenerationId) -> Result<Generation> {
        let manifest_path = self.gen_manifest_path(env, target_id);
        if !manifest_path.exists() {
            return Err(MyelinError::ObjectNotFound(format!(
                "Generation {} not found for environment {}",
                target_id, env
            )));
        }

        let text = fs::read_to_string(manifest_path)?;
        let gen = serde_json::from_str::<Generation>(&text)?;

        let gen_path = self.gen_dir(env, target_id);
        if !gen_path.exists() {
            return Err(MyelinError::ObjectNotFound(format!(
                "Generation tree directory {} does not exist",
                gen_path.display()
            )));
        }

        let env_dir = self.env_generations_dir(env);
        let tmp_link = env_dir.join(format!(".tmp_switch_{}", target_id));
        if tmp_link.exists() || tmp_link.is_symlink() {
            let _ = fs::remove_file(&tmp_link);
        }
        unix_fs::symlink(gen_path.file_name().unwrap(), &tmp_link)?;
        fs::rename(&tmp_link, self.current_link(env))?;

        self.profile_mgr.activate_generation(env, &gen_path)?;

        Ok(gen)
    }
}
