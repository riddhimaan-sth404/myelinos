use myelin_types::{ArtifactId, Digest};
use serde::{Deserialize, Serialize};

/// Metadata associated with an immutable artifact in the content-addressed store (§5.7, §13.1).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ArtifactMetadata {
    pub id: ArtifactId,
    pub digest: Digest,
    pub size_bytes: u64,
    pub created_at: String,
    pub content_type: String,
    pub producer: String,
    pub provenance: String,
    pub retention_policy: String,
}

impl ArtifactMetadata {
    pub fn new(
        id: ArtifactId,
        digest: Digest,
        size_bytes: u64,
        content_type: impl Into<String>,
        producer: impl Into<String>,
    ) -> Self {
        Self {
            id,
            digest,
            size_bytes,
            created_at: "2026-11-02T10:00:00Z".to_string(),
            content_type: content_type.into(),
            producer: producer.into(),
            provenance: "platform-verified".to_string(),
            retention_policy: "keep-referenced".to_string(),
        }
    }
}
