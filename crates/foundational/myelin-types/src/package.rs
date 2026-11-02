use crate::digest::Digest;
use crate::id::{ArtifactId, PackageId};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Package & environment boundary tiers defined in Canonical Architecture §13.2.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize, Deserialize)]
pub enum PackageTier {
    /// Host/system packages required to boot and operate the base OS.
    HostSystem,
    /// Myelin platform/runtime environment services.
    PlatformRuntime,
    /// Project or agent environment dependencies (isolated from host).
    ProjectOrAgent,
    /// Per-execution temporary dependencies (ephemeral).
    PerExecution,
    /// User-installed applications and user data.
    UserApplication,
}

impl PackageTier {
    pub fn is_host(&self) -> bool {
        matches!(self, PackageTier::HostSystem)
    }

    pub fn can_mutate_host(&self) -> bool {
        matches!(self, PackageTier::HostSystem)
    }
}

/// A pinned reference to a package in a generation.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PackageRef {
    pub id: PackageId,
    pub tier: PackageTier,
    pub artifact_id: ArtifactId,
    pub digest: Digest,
    pub description: String,
}

/// Exported file or symlink inside a package.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ExportedFile {
    pub relative_path: String,
    pub digest: Digest,
    pub is_executable: bool,
    pub size_bytes: u64,
}

/// Declarative package manifest (`myelin-pkg.toml` or embedded `manifest.json`).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PackageManifest {
    pub id: PackageId,
    pub description: String,
    pub license: String,
    pub tier: PackageTier,
    pub dependencies: Vec<PackageId>,
    pub exported_binaries: Vec<String>,
    pub exported_libraries: Vec<String>,
    pub environment_variables: HashMap<String, String>,
    pub files: Vec<ExportedFile>,
}

impl PackageManifest {
    pub fn new(
        name: impl Into<String>,
        version: impl Into<String>,
        tier: PackageTier,
    ) -> Self {
        Self {
            id: PackageId::new(name, version),
            description: String::new(),
            license: "Apache-2.0 OR MIT".to_string(),
            tier,
            dependencies: Vec::new(),
            exported_binaries: Vec::new(),
            exported_libraries: Vec::new(),
            environment_variables: HashMap::new(),
            files: Vec::new(),
        }
    }
}
