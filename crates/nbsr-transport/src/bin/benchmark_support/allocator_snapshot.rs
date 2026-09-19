//! Opt-in benchmark observation; never changes allocator policy.

use std::path::Path;

pub(crate) fn ensure_supported() -> std::io::Result<()> {
    if cfg!(all(target_os = "linux", target_env = "gnu")) {
        Ok(())
    } else {
        Err(std::io::Error::other(
            "allocator snapshots require Linux/glibc",
        ))
    }
}

pub(crate) fn snapshot(directory: &Path, ordinal: u64) -> std::io::Result<()> {
    ensure_supported()?;
    if ordinal > 100 {
        return Err(std::io::Error::other(
            "allocator snapshot ordinal exceeds bound",
        ));
    }
    #[cfg(all(target_os = "linux", target_env = "gnu"))]
    {
        use std::os::fd::IntoRawFd;
        let path = directory.join(format!("allocator-{ordinal}.xml"));
        let file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&path)?;
        let fd = file.into_raw_fd();
        // SAFETY: fd is exclusively owned here; fdopen transfers it to FILE on
        // success. Every branch closes the owned descriptor exactly once.
        let stream = unsafe { libc::fdopen(fd, c"w".as_ptr()) };
        if stream.is_null() {
            let error = std::io::Error::last_os_error();
            unsafe { libc::close(fd) };
            return Err(error);
        }
        // SAFETY: stream remains valid until fclose; zero is the supported option.
        // This observes allocator state without changing tuning or freeing memory.
        let result = unsafe { libc::malloc_info(0, stream) };
        let write_error = unsafe { libc::ferror(stream) };
        let closed = unsafe { libc::fclose(stream) };
        if result != 0 || write_error != 0 || closed != 0 {
            return Err(std::io::Error::other("allocator snapshot write failed"));
        }
        if std::fs::metadata(path)?.len() > 1024 * 1024 {
            return Err(std::io::Error::other(
                "allocator snapshot exceeds XML bound",
            ));
        }
    }
    #[cfg(not(all(target_os = "linux", target_env = "gnu")))]
    let _ = directory;
    Ok(())
}

#[cfg(all(test, target_os = "linux", target_env = "gnu"))]
mod tests {
    use super::*;

    #[test]
    fn snapshot_retains_glibc_xml_and_refuses_overwrite() {
        let root = std::env::temp_dir().join(format!("nbsr-allocator-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        snapshot(&root, 0).unwrap();
        let path = root.join("allocator-0.xml");
        let raw = std::fs::read_to_string(&path).unwrap();
        assert!(raw.starts_with("<malloc version=\"1\">"));
        assert!(raw.contains("<heap nr=\"0\">"));
        assert!(raw.ends_with("</malloc>\n"));
        assert!(snapshot(&root, 0).is_err());
        assert_eq!(std::fs::read_to_string(&path).unwrap(), raw);
        std::fs::remove_file(path).unwrap();
        std::fs::remove_dir(root).unwrap();
    }

    #[test]
    fn snapshot_does_not_create_unknown_parent() {
        let absent =
            std::env::temp_dir().join(format!("nbsr-allocator-absent-{}", std::process::id()));
        assert!(!absent.exists());
        assert!(snapshot(&absent, 0).is_err());
        assert!(!absent.exists());
    }
}
