use myelin_artifact::ArtifactStore;
use myelin_types::{EnvironmentId, Generation, MyelinError, Result};
use std::fs;
use std::os::unix::fs as unix_fs;
use std::path::{Path, PathBuf};

/// Environment Profile materialization and atomic generation promotion (§5.8, §13.2).
#[derive(Debug, Clone)]
pub struct ProfileManager {
    profiles_dir: PathBuf,
}

impl ProfileManager {
    pub const DEFAULT_DIR: &'static str = "/var/lib/myelin/profiles";

    pub fn new(root: impl Into<PathBuf>) -> Result<Self> {
        let profiles_dir = root.into();
        fs::create_dir_all(&profiles_dir)?;
        Ok(Self { profiles_dir })
    }

    pub fn profiles_dir(&self) -> &Path {
        &self.profiles_dir
    }

    pub fn profile_link_path(&self, env: &EnvironmentId) -> PathBuf {
        self.profiles_dir.join(env.as_str())
    }

    /// Materializes the generation tree (bin, lib, share) linking into CAS store.
    pub fn materialize_generation_tree(
        &self,
        gen_dir: &Path,
        generation: &Generation,
        store: &ArtifactStore,
    ) -> Result<()> {
        let bin_dir = gen_dir.join("bin");
        let lib_dir = gen_dir.join("lib");
        let share_dir = gen_dir.join("share");
        let etc_dir = gen_dir.join("etc");

        fs::create_dir_all(&bin_dir)?;
        fs::create_dir_all(&lib_dir)?;
        fs::create_dir_all(&share_dir)?;
        fs::create_dir_all(&etc_dir)?;

        for pkg in &generation.packages {
            let unpacked_path = store.root().join("unpacked").join(pkg.digest.hex());
            let artifact_path = if unpacked_path.is_dir() {
                unpacked_path
            } else {
                store.artifact_path(&pkg.digest)
            };

            if !artifact_path.exists() {
                return Err(MyelinError::ArtifactIntegrityFailed(format!(
                    "Package artifact {} missing in store: {}",
                    pkg.id,
                    artifact_path.display()
                )));
            }

            // If the artifact is a directory or unpacked tree
            if artifact_path.is_dir() {
                // If package hierarchy is prefixed with usr/ (e.g. Arch packages), link usr/ subtrees directly
                let usr_dir = artifact_path.join("usr");
                if usr_dir.is_dir() {
                    Self::symlink_tree(&usr_dir, gen_dir)?;
                }
                Self::symlink_tree(&artifact_path, gen_dir)?;
            } else {
                // By default link binary by package name if marked
                let dest_bin = bin_dir.join(&pkg.id.name);
                if !dest_bin.exists() {
                    let _ = unix_fs::symlink(&artifact_path, &dest_bin);
                }
            }
        }

        // Generate environment activation script
        let env_script = format!(
            r#"# Myelin Profile Environment: {} ({})
export MYELIN_PROFILE="{}"
export MYELIN_GENERATION="{}"
export PATH="{}/bin:{}/usr/bin:$PATH"
export LD_LIBRARY_PATH="{}/lib:{}/usr/lib:${{LD_LIBRARY_PATH:-}}"
"#,
            generation.environment,
            generation.id,
            generation.environment,
            generation.id,
            gen_dir.display(),
            gen_dir.display(),
            gen_dir.display(),
            gen_dir.display()
        );
        fs::write(gen_dir.join("env.sh"), env_script)?;

        Ok(())
    }

    fn symlink_tree(src: &Path, dest: &Path) -> Result<()> {
        for entry in fs::read_dir(src)? {
            let entry = entry?;
            let rel = entry.file_name();
            let src_item = entry.path();
            let dest_item = dest.join(&rel);

            if src_item.is_dir() {
                fs::create_dir_all(&dest_item)?;
                Self::symlink_tree(&src_item, &dest_item)?;
            } else {
                if dest_item.exists() || dest_item.is_symlink() {
                    let _ = fs::remove_file(&dest_item);
                }
                unix_fs::symlink(&src_item, &dest_item)?;
            }
        }
        Ok(())
    }

    /// Atomically swaps the active profile symlink to point to the new generation directory.
    /// Uses POSIX atomic rename (renameat).
    pub fn activate_generation(&self, env: &EnvironmentId, gen_dir: &Path) -> Result<()> {
        let profile_link = self.profile_link_path(env);
        let tmp_link = self.profiles_dir.join(format!(".tmp_{}", env));

        if tmp_link.exists() || tmp_link.is_symlink() {
            let _ = fs::remove_file(&tmp_link);
        }

        unix_fs::symlink(gen_dir, &tmp_link)?;
        fs::rename(&tmp_link, &profile_link)?;

        Ok(())
    }
}
