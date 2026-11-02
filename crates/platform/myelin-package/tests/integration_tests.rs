use myelin_artifact::ArtifactStore;
use myelin_generation::{GenerationManager, ProfileManager};
use myelin_package::{IsolationPolicy, PackageBuilder, PackageManager};
use myelin_types::{EnvironmentId, GenerationId, MyelinError, PackageManifest, PackageTier};
use std::fs;
use std::os::unix::fs::PermissionsExt;
use std::path::Path;
use tempfile::tempdir;

fn build_dummy_package(
    dir: &Path,
    name: &str,
    version: &str,
    tier: PackageTier,
    content: &str,
) -> std::path::PathBuf {
    let src = dir.join(format!("{}-src", name));
    fs::create_dir_all(src.join("bin")).unwrap();
    let bin_path = src.join("bin").join(name);
    fs::write(&bin_path, content.as_bytes()).unwrap();

    let mut perms = fs::metadata(&bin_path).unwrap().permissions();
    perms.set_mode(0o755);
    fs::set_permissions(&bin_path, perms).unwrap();

    let manifest = PackageManifest::new(name, version, tier);
    let mut builder = PackageBuilder::new(&src, manifest);

    let pkg_file = dir.join(format!("{}-{}.mpkg", name, version));
    builder.build_to_file(&pkg_file).unwrap();
    pkg_file
}

#[test]
fn test_package_lifecycle_install_rollback_and_gc() {
    let tmp = tempdir().unwrap();
    let store_dir = tmp.path().join("store");
    let prof_dir = tmp.path().join("profiles");
    let gen_dir = tmp.path().join("generations");

    let store = ArtifactStore::new(&store_dir).unwrap();
    let prof_mgr = ProfileManager::new(&prof_dir).unwrap();
    let gen_mgr = GenerationManager::new(&gen_dir, prof_mgr.clone()).unwrap();
    let isolation = IsolationPolicy::default();

    let pkg_mgr = PackageManager::new(store.clone(), gen_mgr.clone(), prof_mgr.clone(), isolation);

    // 1. Create a project package
    let pkg1 = build_dummy_package(
        tmp.path(),
        "my-agent-cli",
        "1.0.0",
        PackageTier::ProjectOrAgent,
        "#!/bin/sh\necho agent v1",
    );

    let env = EnvironmentId::project("research-agent");

    // 2. Install package
    let (gen1, _pkg_ref) = pkg_mgr.install_package(&pkg1, &env).unwrap();
    assert_eq!(gen1.id.to_string_id(), "gen-1");
    assert_eq!(gen1.packages.len(), 1);
    assert_eq!(gen1.packages[0].id.name, "my-agent-cli");

    // Check profile symlink exists and points to generation
    let profile_link = prof_mgr.profile_link_path(&env);
    assert!(profile_link.exists());
    assert!(profile_link.join("bin/my-agent-cli").exists());
    assert!(profile_link.join("env.sh").exists());

    // 3. Install a second package (creates gen-2)
    let pkg2 = build_dummy_package(
        tmp.path(),
        "helper-lib",
        "0.2.0",
        PackageTier::ProjectOrAgent,
        "#!/bin/sh\necho helper",
    );
    let (gen2, _) = pkg_mgr.install_package(&pkg2, &env).unwrap();
    assert_eq!(gen2.id.to_string_id(), "gen-2");
    assert_eq!(gen2.packages.len(), 2);
    assert!(profile_link.join("bin/helper-lib").exists());

    // 4. Test atomic rollback to gen-1
    let rolled_back_gen = pkg_mgr.rollback(&env).unwrap();
    assert_eq!(rolled_back_gen.id.to_string_id(), "gen-1");
    assert_eq!(rolled_back_gen.packages.len(), 1);
    // helper-lib should no longer be in profile
    assert!(!profile_link.join("bin/helper-lib").exists());
    assert!(profile_link.join("bin/my-agent-cli").exists());

    // 5. Test switch back to gen-2
    let switched = pkg_mgr.switch_generation(&env, &GenerationId::new(2)).unwrap();
    assert_eq!(switched.id.to_string_id(), "gen-2");
    assert!(profile_link.join("bin/helper-lib").exists());

    // 6. Test artifact verification
    let report = pkg_mgr.verify_store().unwrap();
    assert_eq!(report.corrupted_count, 0);
    assert!(report.verified_count >= 2);

    // 7. Test Garbage Collection
    // Since gen-1 and gen-2 reference both packages, GC should delete 0 objects
    let gc_report = pkg_mgr.garbage_collect(false).unwrap();
    assert_eq!(gc_report.deleted_objects, 0);
}

#[test]
fn test_isolation_invariant_project_cannot_mutate_host() {
    let tmp = tempdir().unwrap();
    let store = ArtifactStore::new(tmp.path().join("store")).unwrap();
    let prof_mgr = ProfileManager::new(tmp.path().join("profiles")).unwrap();
    let gen_mgr = GenerationManager::new(tmp.path().join("generations"), prof_mgr.clone()).unwrap();

    // Default isolation policy without allow_host_mutation
    let isolation = IsolationPolicy::default();
    let pkg_mgr = PackageManager::new(store, gen_mgr, prof_mgr, isolation);

    let pkg = build_dummy_package(
        tmp.path(),
        "rogue-agent-pkg",
        "1.0.0",
        PackageTier::ProjectOrAgent,
        "#!/bin/sh\necho attack",
    );

    let host_env = EnvironmentId::host();

    // Attempting to install into host profile MUST FAIL with IsolationViolation
    let res = pkg_mgr.install_package(&pkg, &host_env);
    assert!(res.is_err());
    match res.unwrap_err() {
        MyelinError::IsolationViolation(msg) => {
            assert!(msg.contains("mutating host requires explicit host authorization"));
        }
        other => panic!("Expected IsolationViolation, got {:?}", other),
    }
}

#[test]
fn test_artifact_tamper_detection() {
    let tmp = tempdir().unwrap();
    let store_dir = tmp.path().join("store");
    let store = ArtifactStore::new(&store_dir).unwrap();
    let prof_mgr = ProfileManager::new(tmp.path().join("profiles")).unwrap();
    let gen_mgr = GenerationManager::new(tmp.path().join("generations"), prof_mgr.clone()).unwrap();
    let isolation = IsolationPolicy::default();
    let pkg_mgr = PackageManager::new(store.clone(), gen_mgr, prof_mgr, isolation);

    let (_art_id, digest) = store.ingest_bytes(b"original content", "text/plain", "test").unwrap();
    assert!(store.verify(&digest).unwrap());

    // Tamper with the file (temporarily change permissions to write)
    let art_path = store.artifact_path(&digest);
    let mut perms = fs::metadata(&art_path).unwrap().permissions();
    perms.set_mode(0o644);
    fs::set_permissions(&art_path, perms.clone()).unwrap();
    fs::write(&art_path, b"corrupted bytes").unwrap();

    // Verification must now fail
    let verify_res = store.verify(&digest);
    assert!(verify_res.is_err());
    assert!(matches!(verify_res.unwrap_err(), MyelinError::ArtifactIntegrityFailed(_)));

    let rep = pkg_mgr.verify_store().unwrap();
    assert_eq!(rep.corrupted_count, 1);
}
