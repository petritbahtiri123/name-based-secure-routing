use std::path::Path;
use std::time::Duration;

pub(crate) fn wait_for_lifecycle_release(
    active: &Path,
    release: &Path,
    timeout: Duration,
) -> Result<(), &'static str> {
    std::fs::write(active, b"active\n").map_err(|_| "cannot publish active marker")?;
    let deadline = std::time::Instant::now() + timeout;
    while !release.is_file() {
        if std::time::Instant::now() >= deadline {
            return Err("lifecycle release marker timeout");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    Ok(())
}

pub(crate) fn wait_for_lifecycle_start(path: &Path, timeout: Duration) -> Result<(), &'static str> {
    let deadline = std::time::Instant::now() + timeout;
    while !path.is_file() {
        if std::time::Instant::now() >= deadline {
            return Err("lifecycle start marker timeout");
        }
        std::thread::sleep(Duration::from_millis(10));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn active_marker_waits_for_explicit_release() {
        let root = std::env::temp_dir().join(format!("nbsr-b3-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir(&root).unwrap();
        let active = root.join("connection-7.active");
        let release = root.join("connection-7.release");
        std::fs::write(&release, b"release\n").unwrap();

        wait_for_lifecycle_release(&active, &release, Duration::from_secs(1)).unwrap();

        assert_eq!(std::fs::read(&active).unwrap(), b"active\n");
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_release_fails_closed() {
        let root = std::env::temp_dir().join(format!("nbsr-b3-missing-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir(&root).unwrap();
        let result = wait_for_lifecycle_release(
            &root.join("active"),
            &root.join("missing"),
            Duration::from_millis(20),
        );
        assert!(result.is_err());
        std::fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn missing_start_fails_closed() {
        let root = std::env::temp_dir().join(format!("nbsr-b3-start-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir(&root).unwrap();
        assert!(
            wait_for_lifecycle_start(&root.join("missing"), Duration::from_millis(20)).is_err()
        );
        std::fs::remove_dir_all(root).unwrap();
    }
}
