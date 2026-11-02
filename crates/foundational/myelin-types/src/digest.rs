use serde::{Deserialize, Serialize};
use sha2::{Digest as Sha2Digest, Sha256};
use std::fmt;
use std::fs::File;
use std::io::{self, Read};
use std::path::Path;

/// Cryptographic content digest (format: "sha256:<64-hex>").
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct Digest(pub String);

impl Digest {
    pub fn new(raw: impl Into<String>) -> Self {
        let s = raw.into();
        if s.starts_with("sha256:") {
            Self(s)
        } else {
            Self(format!("sha256:{}", s))
        }
    }

    pub fn parse(s: &str) -> Option<Self> {
        let hex_part = s.strip_prefix("sha256:").unwrap_or(s);
        if hex_part.len() == 64 && hex_part.chars().all(|c| c.is_ascii_hexdigit()) {
            Some(Self(format!("sha256:{}", hex_part.to_ascii_lowercase())))
        } else {
            None
        }
    }

    pub fn hex(&self) -> &str {
        self.0.strip_prefix("sha256:").unwrap_or(&self.0)
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn from_bytes(bytes: &[u8]) -> Self {
        let mut hasher = Sha256::new();
        hasher.update(bytes);
        let result = hasher.finalize();
        Self::new(hex::encode(result))
    }

    pub fn from_reader<R: Read>(mut reader: R) -> io::Result<Self> {
        let mut hasher = Sha256::new();
        let mut buffer = [0u8; 65536];
        loop {
            let bytes_read = reader.read(&mut buffer)?;
            if bytes_read == 0 {
                break;
            }
            hasher.update(&buffer[..bytes_read]);
        }
        let result = hasher.finalize();
        Ok(Self::new(hex::encode(result)))
    }

    pub fn from_file<P: AsRef<Path>>(path: P) -> io::Result<Self> {
        let file = File::open(path)?;
        Self::from_reader(file)
    }

    pub fn matches(&self, other_bytes: &[u8]) -> bool {
        let computed = Self::from_bytes(other_bytes);
        self.hex().eq_ignore_ascii_case(computed.hex())
    }
}

impl fmt::Display for Digest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}
