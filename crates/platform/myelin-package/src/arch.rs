use crate::isolation::IsolationPolicy;
use myelin_artifact::ArtifactStore;
use myelin_types::{Digest, ExportedFile, MyelinError, PackageId, PackageManifest, PackageTier, Result};
use serde::{Deserialize, Serialize};
use std::fs::{self, File};
use std::io::{BufReader, Read};
use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use tar::Archive;

pub const DEFAULT_ARCH_MIRROR: &'static str = "https://geo.mirror.pkgbuild.com";
pub const ARCH_API_BASE: &'static str = "https://archlinux.org/packages/search/json";
pub const AUR_API_BASE: &'static str = "https://aur.archlinux.org/rpc/v5";

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArchPackageInfo {
    pub pkgname: String,
    pub pkgver: String,
    pub pkgrel: String,
    pub repo: String,
    pub arch: String,
    pub pkgdesc: String,
    pub filename: String,
    #[serde(default)]
    pub compressed_size: u64,
    #[serde(default)]
    pub installed_size: u64,
    pub url: Option<String>,
    #[serde(default)]
    pub depends: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct ArchSearchResponse {
    pub results: Vec<ArchPackageInfo>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AurPackageInfo {
    #[serde(rename = "Name")]
    pub name: String,
    #[serde(rename = "Version")]
    pub version: String,
    #[serde(rename = "Description")]
    pub description: Option<String>,
    #[serde(rename = "URL")]
    pub url: Option<String>,
    #[serde(rename = "URLPath")]
    pub url_path: Option<String>,
    #[serde(rename = "Depends")]
    pub depends: Option<Vec<String>>,
    #[serde(rename = "MakeDepends")]
    pub make_depends: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct AurRpcResponse {
    pub resultcount: usize,
    pub results: Vec<AurPackageInfo>,
}

pub struct ArchClient;

impl ArchClient {
    /// Searches official Arch Linux repositories via the official packages API.
    pub fn search(query: &str) -> Result<Vec<ArchPackageInfo>> {
        let url = format!("{}?q={}", ARCH_API_BASE, query);
        let resp = ureq::get(&url)
            .timeout(std::time::Duration::from_secs(10))
            .call()
            .map_err(|e| MyelinError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        let search_res: ArchSearchResponse = resp
            .into_json()
            .map_err(|e| MyelinError::InvalidInput(format!("Failed to parse Arch API response: {}", e)))?;

        Ok(search_res.results)
    }

    /// Fetches package info for an exact package name from official Arch repositories.
    pub fn get_package_info(name: &str) -> Result<Option<ArchPackageInfo>> {
        let url = format!("{}?name={}", ARCH_API_BASE, name);
        let resp = ureq::get(&url)
            .timeout(std::time::Duration::from_secs(10))
            .call()
            .map_err(|e| MyelinError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        let search_res: ArchSearchResponse = resp
            .into_json()
            .map_err(|e| MyelinError::InvalidInput(format!("Failed to parse Arch API response: {}", e)))?;

        for item in search_res.results {
            if item.pkgname == name && item.arch == "x86_64" {
                return Ok(Some(item));
            }
        }
        Ok(None)
    }

    /// Searches the Arch User Repository (AUR) via the v5 RPC API.
    pub fn search_aur(query: &str) -> Result<Vec<AurPackageInfo>> {
        let url = format!("{}/search/{}", AUR_API_BASE, query);
        let resp = ureq::get(&url)
            .timeout(std::time::Duration::from_secs(10))
            .call()
            .map_err(|e| MyelinError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        let rpc_res: AurRpcResponse = resp
            .into_json()
            .map_err(|e| MyelinError::InvalidInput(format!("Failed to parse AUR RPC response: {}", e)))?;

        Ok(rpc_res.results)
    }

    /// Fetches package info from the AUR by exact package name.
    pub fn get_aur_info(name: &str) -> Result<Option<AurPackageInfo>> {
        let url = format!("{}/info/{}", AUR_API_BASE, name);
        let resp = ureq::get(&url)
            .timeout(std::time::Duration::from_secs(10))
            .call()
            .map_err(|e| MyelinError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        let rpc_res: AurRpcResponse = resp
            .into_json()
            .map_err(|e| MyelinError::InvalidInput(format!("Failed to parse AUR RPC response: {}", e)))?;

        Ok(rpc_res.results.into_iter().next())
    }

    /// Downloads an official Arch binary package (.pkg.tar.zst) from the mirror.
    pub fn download_package(info: &ArchPackageInfo, dest_path: &Path) -> Result<()> {
        let download_url = format!(
            "{}/{}/os/{}/{}",
            DEFAULT_ARCH_MIRROR, info.repo, info.arch, info.filename
        );

        let resp = ureq::get(&download_url)
            .timeout(std::time::Duration::from_secs(60))
            .call()
            .map_err(|e| MyelinError::Io(std::io::Error::new(std::io::ErrorKind::Other, e.to_string())))?;

        let mut reader = resp.into_reader();
        let mut file = File::create(dest_path)?;
        std::io::copy(&mut reader, &mut file)?;
        file.sync_all()?;

        Ok(())
    }

    /// Ingests an Arch `.pkg.tar.zst` package directly into Myelin's Content-Addressed Store.
    /// Decompresses Zstandard stream, reads `.PKGINFO`, and materializes files into CAS.
    pub fn ingest_arch_package(
        store: &ArtifactStore,
        pkg_path: &Path,
        tier: PackageTier,
    ) -> Result<(PackageManifest, Digest, PathBuf)> {
        // 1. Ingest raw .pkg.tar.zst into CAS store
        let (_art_id, digest) =
            store.ingest_file(pkg_path, "application/x-arch-package", "axon-arch")?;

        let unpacked_dir = store.root().join("unpacked").join(digest.hex());
        if !unpacked_dir.exists() {
            let tmp_unpacked = store.root().join("tmp").join(format!("unpack_arch_{}", digest.hex()));
            if tmp_unpacked.exists() {
                let _ = fs::remove_dir_all(&tmp_unpacked);
            }
            fs::create_dir_all(&tmp_unpacked)?;

            // 2. Unpack zstd tarball
            let file = File::open(pkg_path)?;
            let zstd_dec = zstd::stream::Decoder::new(BufReader::new(file))?;
            let mut tar = Archive::new(zstd_dec);

            let mut pkginfo_content: Option<String> = None;

            for entry in tar.entries()? {
                let mut entry = entry?;
                let path = entry.path()?;
                let path_str = path.to_string_lossy().to_string();

                IsolationPolicy::validate_relative_path(&path_str)?;

                // Save .PKGINFO for metadata
                if path_str == ".PKGINFO" {
                    let mut s = String::new();
                    entry.read_to_string(&mut s)?;
                    pkginfo_content = Some(s);
                    continue;
                }

                // Skip Arch packaging metadata files from filesystem root
                if path_str.starts_with(".BUILDINFO")
                    || path_str.starts_with(".MTREE")
                    || path_str.starts_with(".INSTALL")
                {
                    continue;
                }

                let dest_file = tmp_unpacked.join(&path);
                if let Some(parent) = dest_file.parent() {
                    fs::create_dir_all(parent)?;
                }
                entry.unpack(&dest_file)?;
            }

            // Parse metadata
            let manifest = Self::parse_pkginfo(
                pkginfo_content.as_deref().unwrap_or(""),
                tier,
                &tmp_unpacked,
            )?;
            let _ = fs::write(tmp_unpacked.join(".manifest.json"), serde_json::to_string_pretty(&manifest)?);

            fs::create_dir_all(store.root().join("unpacked"))?;
            fs::rename(&tmp_unpacked, &unpacked_dir)?;

            // Make immutable
            Self::make_tree_readonly(&unpacked_dir)?;

            return Ok((manifest, digest, unpacked_dir));
        }

        // Already unpacked, load cached manifest if present
        let manifest_file = unpacked_dir.join(".manifest.json");
        if manifest_file.exists() {
            if let Ok(text) = fs::read_to_string(manifest_file) {
                if let Ok(m) = serde_json::from_str::<PackageManifest>(&text) {
                    return Ok((m, digest, unpacked_dir));
                }
            }
        }

        let manifest = Self::parse_pkginfo("", tier, &unpacked_dir)?;
        Ok((manifest, digest, unpacked_dir))
    }

    fn parse_pkginfo(
        content: &str,
        tier: PackageTier,
        unpacked_root: &Path,
    ) -> Result<PackageManifest> {
        let mut name = "arch-package".to_string();
        let mut ver = "1.0.0".to_string();
        let mut desc = String::new();
        let mut license = "Unknown".to_string();
        let mut depends = Vec::new();

        for line in content.lines() {
            let line = line.trim();
            if let Some((k, v)) = line.split_once('=') {
                let key = k.trim();
                let val = v.trim();
                match key {
                    "pkgname" => name = val.to_string(),
                    "pkgver" => ver = val.to_string(),
                    "pkgdesc" => desc = val.to_string(),
                    "license" => license = val.to_string(),
                    "depend" => depends.push(PackageId::new(val, "latest")),
                    _ => {}
                }
            }
        }

        let mut manifest = PackageManifest::new(name, ver, tier);
        manifest.description = desc;
        manifest.license = license;
        manifest.dependencies = depends;

        // Collect exported files
        let mut files = Vec::new();
        Self::collect_exported_files(unpacked_root, Path::new(""), &mut files)?;
        manifest.files = files;

        Ok(manifest)
    }

    fn collect_exported_files(
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
            let file_rel = rel.join(&entry_name);

            if path.is_dir() {
                Self::collect_exported_files(base, &file_rel, files)?;
            } else if path.is_file() {
                let digest = Digest::from_file(&path)?;
                let meta = path.metadata()?;
                let is_exec = (meta.permissions().mode() & 0o111) != 0;

                files.push(ExportedFile {
                    relative_path: file_rel.to_string_lossy().to_string(),
                    digest,
                    is_executable: is_exec,
                    size_bytes: meta.len(),
                });
            }
        }
        Ok(())
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
