use crate::isolation::IsolationPolicy;
use flate2::read::GzDecoder;
use flate2::write::GzEncoder;
use flate2::Compression;
use myelin_artifact::ArtifactStore;
use myelin_types::{Digest, ExportedFile, MyelinError, PackageManifest, Result};
use std::fs::{self, File};
use std::io::Read;
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use tar::{Archive, Builder, Header};

pub const MANIFEST_FILENAME: &'static str = "manifest.json";

/// Builder for canonical Myelin packages (`.mpkg`).
pub struct PackageBuilder {
    manifest: PackageManifest,
    source_root: PathBuf,
}

impl PackageBuilder {
    pub fn new(source_root: impl Into<PathBuf>, manifest: PackageManifest) -> Self {
        Self {
            source_root: source_root.into(),
            manifest,
        }
    }

    /// Automatically scans the source directory, computes SHA-256 for all files,
    /// and populates the manifest's file list.
    pub fn scan_and_populate_files(&mut self) -> Result<()> {
        let mut files = Vec::new();
        self.collect_files_recursive(&self.source_root.clone(), &PathBuf::new(), &mut files)?;
        self.manifest.files = files;
        Ok(())
    }

    fn collect_files_recursive(
        &self,
        base: &Path,
        rel: &Path,
        files: &mut Vec<ExportedFile>,
    ) -> Result<()> {
        let dir = base.join(rel);
        if !dir.is_dir() {
            return Ok(());
        }

        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            let entry_name = entry.file_name();
            let name_str = entry_name.to_string_lossy();

            // Skip top-level manifest file if present in source
            if rel.as_os_str().is_empty() && name_str == MANIFEST_FILENAME {
                continue;
            }

            let file_rel = rel.join(&entry_name);
            let file_rel_str = file_rel.to_string_lossy().to_string();

            if path.is_dir() {
                self.collect_files_recursive(base, &file_rel, files)?;
            } else if path.is_file() {
                let digest = Digest::from_file(&path)?;
                let meta = path.metadata()?;
                let is_executable = (meta.permissions().mode() & 0o111) != 0;

                files.push(ExportedFile {
                    relative_path: file_rel_str,
                    digest,
                    is_executable,
                    size_bytes: meta.len(),
                });
            }
        }
        Ok(())
    }

    /// Builds and writes the `.mpkg` archive to the target destination.
    pub fn build_to_file(&mut self, output_path: &Path) -> Result<Digest> {
        self.scan_and_populate_files()?;

        let file = File::create(output_path)?;
        let enc = GzEncoder::new(file, Compression::default());
        let mut tar = Builder::new(enc);

        // 1. Write manifest.json at root of archive
        let manifest_bytes = serde_json::to_vec_pretty(&self.manifest)?;
        let mut header = Header::new_gnu();
        header.set_path(MANIFEST_FILENAME).map_err(|e| MyelinError::InvalidInput(e.to_string()))?;
        header.set_size(manifest_bytes.len() as u64);
        header.set_mode(0o644);
        header.set_cksum();
        tar.append(&header, &manifest_bytes[..])?;

        // 2. Append all files
        for exported in &self.manifest.files {
            IsolationPolicy::validate_relative_path(&exported.relative_path)?;
            let src = self.source_root.join(&exported.relative_path);
            let mut f = File::open(&src)?;
            tar.append_file(&exported.relative_path, &mut f)?;
        }

        let encoder = tar.into_inner()?;
        encoder.finish()?;

        // Compute and return SHA-256 of resulting archive
        Ok(Digest::from_file(output_path)?)
    }

    pub fn manifest(&self) -> &PackageManifest {
        &self.manifest
    }
}

/// Helper functions for reading, verifying and extracting `.mpkg` archives.
pub struct PackageArchive;

impl PackageArchive {
    /// Inspects a `.mpkg` archive and reads the embedded `manifest.json`.
    pub fn inspect(archive_path: &Path) -> Result<PackageManifest> {
        let file = File::open(archive_path)?;
        let gz = GzDecoder::new(file);
        let mut tar = Archive::new(gz);

        for entry in tar.entries()? {
            let mut entry = entry?;
            let path = entry.path()?;
            if path == Path::new(MANIFEST_FILENAME) {
                let mut content = String::new();
                entry.read_to_string(&mut content)?;
                let manifest: PackageManifest = serde_json::from_str(&content)?;
                return Ok(manifest);
            }
        }

        Err(MyelinError::InvalidInput(format!(
            "Missing {} in package archive: {}",
            MANIFEST_FILENAME,
            archive_path.display()
        )))
    }

    /// Unpacks the archive into a destination directory, enforcing path isolation.
    pub fn unpack_to(archive_path: &Path, dest_dir: &Path) -> Result<PackageManifest> {
        let file = File::open(archive_path)?;
        let gz = GzDecoder::new(file);
        let mut tar = Archive::new(gz);

        fs::create_dir_all(dest_dir)?;
        let mut manifest: Option<PackageManifest> = None;

        for entry in tar.entries()? {
            let mut entry = entry?;
            let path = entry.path()?;
            let path_str = path.to_string_lossy().to_string();

            // Validate against path traversal
            IsolationPolicy::validate_relative_path(&path_str)?;

            if path == Path::new(MANIFEST_FILENAME) {
                let mut content = String::new();
                entry.read_to_string(&mut content)?;
                manifest = Some(serde_json::from_str(&content)?);
                continue;
            }

            let dest_file = dest_dir.join(&path);
            if let Some(parent) = dest_file.parent() {
                fs::create_dir_all(parent)?;
            }

            entry.unpack(&dest_file)?;
        }

        manifest.ok_or_else(|| {
            MyelinError::InvalidInput(format!(
                "Archive missing {} manifest",
                MANIFEST_FILENAME
            ))
        })
    }

    /// Ingests a `.mpkg` package into the CAS ArtifactStore.
    /// Stores the archive file itself and unpacks the content tree into an immutable store directory.
    pub fn ingest_into_store(
        store: &ArtifactStore,
        archive_path: &Path,
    ) -> Result<(PackageManifest, Digest, PathBuf)> {
        let manifest = Self::inspect(archive_path)?;
        
        // 1. Ingest raw .mpkg archive into CAS
        let (_art_id, digest) = store.ingest_file(archive_path, "application/x-myelin-package", "myelin-pkg")?;

        // 2. Unpack into immutable CAS directory
        let unpacked_dir = store.root().join("unpacked").join(digest.hex());
        if !unpacked_dir.exists() {
            let tmp_unpacked = store.root().join("tmp").join(format!("unpack_{}", digest.hex()));
            if tmp_unpacked.exists() {
                let _ = fs::remove_dir_all(&tmp_unpacked);
            }
            fs::create_dir_all(&tmp_unpacked)?;

            Self::unpack_to(archive_path, &tmp_unpacked)?;

            fs::create_dir_all(store.root().join("unpacked"))?;
            fs::rename(&tmp_unpacked, &unpacked_dir)?;

            // Make files read-only (0444) / dirs (0555) to enforce INV-18
            Self::make_tree_readonly(&unpacked_dir)?;
        }

        Ok((manifest, digest, unpacked_dir))
    }

    fn make_tree_readonly(dir: &Path) -> Result<()> {
        for entry in fs::read_dir(dir)? {
            let entry = entry?;
            let path = entry.path();
            if path.is_dir() {
                Self::make_tree_readonly(&path)?;
                let mut perms = fs::metadata(&path)?.permissions();
                perms.set_mode(0o555);
                let _ = fs::set_permissions(&path, perms);
            } else {
                let mut perms = fs::metadata(&path)?.permissions();
                let is_exec = (perms.mode() & 0o111) != 0;
                perms.set_mode(if is_exec { 0o555 } else { 0o444 });
                let _ = fs::set_permissions(&path, perms);
            }
        }
        let mut dir_perms = fs::metadata(dir)?.permissions();
        dir_perms.set_mode(0o555);
        let _ = fs::set_permissions(dir, dir_perms);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use myelin_types::PackageTier;

    #[test]
    fn test_package_builder_and_inspection() {
        let tmp = tempfile::tempdir().unwrap();
        let src = tmp.path().join("src");
        fs::create_dir_all(src.join("bin")).unwrap();
        let app_file = src.join("bin/hello");
        fs::write(&app_file, b"#!/bin/sh\necho hello").unwrap();
        let mut perms = fs::metadata(&app_file).unwrap().permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&app_file, perms).unwrap();

        let manifest = PackageManifest::new("hello-app", "1.0.0", PackageTier::ProjectOrAgent);
        let mut builder = PackageBuilder::new(&src, manifest);

        let out_pkg = tmp.path().join("hello-app-1.0.0.mpkg");
        let digest = builder.build_to_file(&out_pkg).unwrap();
        assert!(out_pkg.exists());
        assert!(digest.hex().len() == 64);

        let inspected = PackageArchive::inspect(&out_pkg).unwrap();
        assert_eq!(inspected.id.name, "hello-app");
        assert_eq!(inspected.id.version, "1.0.0");
        assert_eq!(inspected.files.len(), 1);
        assert_eq!(inspected.files[0].relative_path, "bin/hello");
        assert!(inspected.files[0].is_executable);
    }
}
