use crate::digest::Digest;
use crate::id::{EnvironmentId, GenerationId};
use crate::package::{PackageRef, PackageTier};
use serde::{Deserialize, Serialize};

/// An immutable published description of a coherent system or environment state (§5.8, §14.2).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct Generation {
    /// Unique generation ID (e.g. `gen-1`, `gen-2`).
    pub id: GenerationId,
    /// Parent generation ID if this generation was derived from an earlier one.
    pub parent_id: Option<GenerationId>,
    /// Environment profile this generation belongs to (e.g. "system", "project-agent1").
    pub environment: EnvironmentId,
    /// Generation target tier.
    pub tier: PackageTier,
    /// ISO 8601 creation timestamp.
    pub created_at: String,
    /// Exact closure of packages pinned in this generation.
    pub packages: Vec<PackageRef>,
    /// Cryptographic digest of this generation's manifest.
    pub manifest_digest: Digest,
}

impl Generation {
    pub fn compute_manifest_digest(
        id: &GenerationId,
        parent_id: &Option<GenerationId>,
        env: &EnvironmentId,
        tier: &PackageTier,
        packages: &[PackageRef],
    ) -> Digest {
        let serialized = serde_json::to_string(&(id, parent_id, env, tier, packages))
            .unwrap_or_default();
        Digest::from_bytes(serialized.as_bytes())
    }

    pub fn new(
        id: GenerationId,
        parent_id: Option<GenerationId>,
        environment: EnvironmentId,
        tier: PackageTier,
        created_at: String,
        packages: Vec<PackageRef>,
    ) -> Self {
        let manifest_digest = Self::compute_manifest_digest(&id, &parent_id, &environment, &tier, &packages);
        Self {
            id,
            parent_id,
            environment,
            tier,
            created_at,
            packages,
            manifest_digest,
        }
    }
}
