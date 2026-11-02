use thiserror::Error;

/// Canonical error classes (§Appendix C).
#[derive(Debug, Error)]
pub enum MyelinError {
    #[error("Unauthenticated caller: {0}")]
    Unauthenticated(String),

    #[error("Unauthorized operation: {0}")]
    Unauthorized(String),

    #[error("Isolation violation (§13.2): {0}")]
    IsolationViolation(String),

    #[error("Capability missing: {0}")]
    CapabilityMissing(String),

    #[error("Object not found: {0}")]
    ObjectNotFound(String),

    #[error("Object conflict: {0}")]
    ObjectConflict(String),

    #[error("Invalid state transition: {0}")]
    InvalidTransition(String),

    #[error("Generation mismatch: {0}")]
    GenerationMismatch(String),

    #[error("Artifact integrity failed: {0}")]
    ArtifactIntegrityFailed(String),

    #[error("Invalid input or manifest: {0}")]
    InvalidInput(String),

    #[error("Verification failed: {0}")]
    VerificationFailed(String),

    #[error("I/O error: {0}")]
    Io(#[from] std::io::Error),

    #[error("Serialization error: {0}")]
    Serialization(#[from] serde_json::Error),
}

pub type Result<T> = std::result::Result<T, MyelinError>;
