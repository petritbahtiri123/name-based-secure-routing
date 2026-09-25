use std::fs::OpenOptions;
use std::io::Write;
use std::path::Path;

pub fn enabled(value: Option<&str>, concurrent_sessions: bool) -> Result<bool, &'static str> {
    match value {
        None => Ok(false),
        Some("1") if !concurrent_sessions => Ok(true),
        _ => Err("B3 completion markers require one sequential source and value 1"),
    }
}

pub fn publish(root: &Path, ordinal: u64) -> std::io::Result<()> {
    // Publish a complete file atomically without overwriting an earlier cycle.
    let temporary = root.join(format!(".destination-{ordinal}.complete.tmp"));
    let final_path = root.join(format!("destination-{ordinal}.complete"));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temporary)?;
    let result = (|| {
        file.write_all(b"complete\n")?;
        drop(file);
        std::fs::hard_link(&temporary, &final_path)
    })();
    let cleanup = std::fs::remove_file(&temporary);
    result.and(cleanup)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn only_explicit_sequential_mode_enables_completion() {
        assert_eq!(enabled(None, false), Ok(false));
        assert_eq!(enabled(None, true), Ok(false));
        assert_eq!(enabled(Some("1"), false), Ok(true));
        assert!(enabled(Some("1"), true).is_err());
        assert!(enabled(Some("0"), false).is_err());
    }
    #[test]
    fn publication_is_exact_and_cannot_replace_a_stale_marker() {
        let root = std::env::temp_dir().join(format!("nbsr-b3-completion-{}", std::process::id()));
        std::fs::create_dir(&root).unwrap();
        publish(&root, 7).unwrap();
        assert_eq!(
            std::fs::read(root.join("destination-7.complete")).unwrap(),
            b"complete\n"
        );
        assert!(publish(&root, 7).is_err());
        std::fs::remove_file(root.join("destination-7.complete")).unwrap();
        std::fs::remove_dir(root).unwrap();
    }
}
