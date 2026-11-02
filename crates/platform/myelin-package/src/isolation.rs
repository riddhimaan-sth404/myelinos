use myelin_types::{EnvironmentId, MyelinError, PackageManifest, PackageTier, Result};
use std::path::Path;

/// Host-versus-Project Isolation Policy (§13.2).
///
/// Invariants:
/// - INV-01: One authority per concept.
/// - Project or agent packages MUST NOT mutate the host system profile.
/// - HostSystem packages require explicit authorization or host target profile.
/// - Package file paths must be strictly relative and contain no parent directory (`..`) traversal.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct IsolationPolicy {
    pub allow_host_mutation: bool,
}

impl Default for IsolationPolicy {
    fn default() -> Self {
        Self {
            allow_host_mutation: false,
        }
    }
}

impl IsolationPolicy {
    pub fn new(allow_host_mutation: bool) -> Self {
        Self {
            allow_host_mutation,
        }
    }

    /// Validates whether a package manifest can be installed into a given environment profile.
    pub fn validate_install(
        &self,
        target_env: &EnvironmentId,
        manifest: &PackageManifest,
    ) -> Result<()> {
        let is_host_env = target_env.is_host();

        // 1. Check isolation between host profile and project/agent tiers
        if is_host_env {
            if !self.allow_host_mutation {
                return Err(MyelinError::IsolationViolation(format!(
                    "Cannot install package '{}' into host environment '{}': mutating host requires explicit host authorization",
                    manifest.id, target_env
                )));
            }

            // Project/Agent packages must not be installed directly into the host system profile
            if manifest.tier == PackageTier::ProjectOrAgent {
                return Err(MyelinError::IsolationViolation(format!(
                    "Package '{}' has tier ProjectOrAgent and cannot be installed into HostSystem profile '{}'",
                    manifest.id, target_env
                )));
            }
        } else {
            // Non-host environment (e.g. project or agent profile)
            if manifest.tier == PackageTier::HostSystem && !self.allow_host_mutation {
                return Err(MyelinError::IsolationViolation(format!(
                    "Package '{}' has tier HostSystem but target profile '{}' is non-host",
                    manifest.id, target_env
                )));
            }
        }

        // 2. Validate all file paths in package to ensure no path escapes or absolute paths
        for file in &manifest.files {
            Self::validate_relative_path(&file.relative_path)?;
        }

        Ok(())
    }

    /// Verifies that a path is relative and does not traverse outside root (`..`).
    pub fn validate_relative_path(path_str: &str) -> Result<()> {
        let path = Path::new(path_str);
        if path.is_absolute() {
            return Err(MyelinError::InvalidInput(format!(
                "Absolute paths are forbidden in package archive: '{}'",
                path_str
            )));
        }

        for component in path.components() {
            match component {
                std::path::Component::ParentDir => {
                    return Err(MyelinError::IsolationViolation(format!(
                        "Path traversal attempt detected in package path: '{}'",
                        path_str
                    )));
                }
                std::path::Component::Prefix(_) => {
                    return Err(MyelinError::InvalidInput(format!(
                        "Invalid path prefix in package: '{}'",
                        path_str
                    )));
                }
                _ => {}
            }
        }

        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_project_package_rejected_from_host() {
        let policy = IsolationPolicy::default();
        let env = EnvironmentId::host();
        let manifest = PackageManifest::new("my-tool", "1.0.0", PackageTier::ProjectOrAgent);

        // Disallowed without host mutation flag
        let res = policy.validate_install(&env, &manifest);
        assert!(res.is_err());
        assert!(matches!(res.unwrap_err(), MyelinError::IsolationViolation(_)));

        // Disallowed even with flag because tier is ProjectOrAgent
        let admin_policy = IsolationPolicy::new(true);
        let res2 = admin_policy.validate_install(&env, &manifest);
        assert!(res2.is_err());
        assert!(matches!(res2.unwrap_err(), MyelinError::IsolationViolation(_)));
    }

    #[test]
    fn test_project_package_allowed_in_project_env() {
        let policy = IsolationPolicy::default();
        let env = EnvironmentId::project("data-agent");
        let manifest = PackageManifest::new("my-tool", "1.0.0", PackageTier::ProjectOrAgent);

        let res = policy.validate_install(&env, &manifest);
        assert!(res.is_ok());
    }

    #[test]
    fn test_path_traversal_detection() {
        assert!(IsolationPolicy::validate_relative_path("bin/app").is_ok());
        assert!(IsolationPolicy::validate_relative_path("/etc/passwd").is_err());
        assert!(IsolationPolicy::validate_relative_path("bin/../../etc/passwd").is_err());
    }
}
