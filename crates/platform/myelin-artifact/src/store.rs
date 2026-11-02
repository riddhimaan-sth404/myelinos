use crate::metadata::ArtifactMetadata;
use myelin_types::{ArtifactId, Digest, MyelinError, Result};
use std::fs::{self, File};
use std::io::Read;
use std::io::Write;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};

/// Content-Addressed Storage (CAS) for immutable software artifacts (§13.1).
#[derive(Debug, Clone)]
pub struct ArtifactStore {
    root_dir: PathBuf,
}

impl ArtifactStore {
    pub const DEFAULT_DIR: &'static str = "/var/lib/myelin/store";

    pub fn new(root: impl Into<PathBuf>) -> Result<Self> {
        let root_dir = root.into();
        fs::create_dir_all(root_dir.join("objects"))?;
        fs::create_dir_all(root_dir.join("meta"))?;
        fs::create_dir_all(root_dir.join("tmp"))?;
        fs::create_dir_all(root_dir.join("unpacked"))?;
        Ok(Self { root_dir })
    }

    pub fn default_or_env() -> Result<Self> {
        if let Ok(dir) = std::env::var("MYELIN_STORE_DIR") {
            Self::new(dir)
        } else {
            Self::new(Self::DEFAULT_DIR)
        }
    }

    pub fn root(&self) -> &Path {
        &self.root_dir
    }

    pub fn objects_dir(&self) -> PathBuf {
        self.root_dir.join("objects")
    }

    pub fn meta_dir(&self) -> PathBuf {
        self.root_dir.join("meta")
    }

    pub fn artifact_path(&self, digest: &Digest) -> PathBuf {
        self.objects_dir().join(digest.hex())
    }

    pub fn meta_path(&self, digest: &Digest) -> PathBuf {
        self.meta_dir().join(format!("{}.json", digest.hex()))
    }

    /// Ingests arbitrary bytes into the content-addressed store.
    /// Sets permissions to read-only (0444) to guarantee immutability (INV-18).
    pub fn ingest_bytes(
        &self,
        bytes: &[u8],
        content_type: &str,
        producer: &str,
    ) -> Result<(ArtifactId, Digest)> {
        let digest = Digest::from_bytes(bytes);
        let target_path = self.artifact_path(&digest);
        let meta_path = self.meta_path(&digest);

        if !target_path.exists() {
            let tmp_path = self.root_dir.join("tmp").join(format!("ingest_{}", digest.hex()));
            let mut file = File::create(&tmp_path)?;
            file.write_all(bytes)?;
            file.sync_all()?;

            // Set immutable read-only permissions
            let mut perms = file.metadata()?.permissions();
            perms.set_mode(0o444);
            fs::set_permissions(&tmp_path, perms)?;

            // Atomic rename into CAS store
            fs::rename(&tmp_path, &target_path)?;
        }

        let artifact_id = ArtifactId::new(format!("art-{}", &digest.hex()[..16]));
        let meta = ArtifactMetadata::new(
            artifact_id.clone(),
            digest.clone(),
            bytes.len() as u64,
            content_type,
            producer,
        );

        let meta_json = serde_json::to_string_pretty(&meta)?;
        fs::write(meta_path, meta_json)?;

        Ok((artifact_id, digest))
    }

    /// Ingests a file from disk into the content-addressed store.
    pub fn ingest_file(
        &self,
        path: &Path,
        content_type: &str,
        producer: &str,
    ) -> Result<(ArtifactId, Digest)> {
        let mut file = File::open(path)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        self.ingest_bytes(&bytes, content_type, producer)
    }

    /// Cryptographically verifies that an artifact matches its declared digest.
    pub fn verify(&self, digest: &Digest) -> Result<bool> {
        let path = self.artifact_path(digest);
        if !path.exists() {
            return Err(MyelinError::ObjectNotFound(format!(
                "Artifact {} not found in store",
                digest
            )));
        }

        let actual_digest = Digest::from_file(&path)?;
        if actual_digest.hex() != digest.hex() {
            return Err(MyelinError::ArtifactIntegrityFailed(format!(
                "Digest mismatch for artifact {}: expected {}, found {}",
                path.display(),
                digest,
                actual_digest
            )));
        }

        Ok(true)
    }

    /// Retrieves metadata for an artifact.
    pub fn get_metadata(&self, digest: &Digest) -> Result<ArtifactMetadata> {
        let path = self.meta_path(digest);
        if !path.exists() {
            return Err(MyelinError::ObjectNotFound(format!(
                "Metadata for artifact {} not found",
                digest
            )));
        }
        let text = fs::read_to_string(path)?;
        let meta = serde_json::from_str(&text)?;
        Ok(meta)
    }

    /// Lists all artifacts currently stored in the CAS repository.
    pub fn list_artifacts(&self) -> Result<Vec<ArtifactMetadata>> {
        let mut list = Vec::new();
        if !self.meta_dir().exists() {
            return Ok(list);
        }
        for entry in fs::read_dir(self.meta_dir())? {
            let entry = entry?;
            if entry.path().extension().map_or(false, |ext| ext == "json") {
                let text = fs::read_to_string(entry.path())?;
                if let Ok(meta) = serde_json::from_str::<ArtifactMetadata>(&text) {
                    list.push(meta);
                }
            }
        }
        list.sort_by(|a, b| a.created_at.cmp(&b.created_at));
        Ok(list)
    }
}
