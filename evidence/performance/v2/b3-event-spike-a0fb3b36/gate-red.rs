// Throwaway Linux-local-filesystem experiment, not a production backend.
use std::path::Path;
pub struct Gate;
impl Gate {
    pub fn new(_: &Path) -> std::io::Result<Self> { Ok(Self) }
    pub fn changed(&mut self) -> bool { true }
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn idle_directory_does_not_request_full_scan_and_creation_does() {
        let root=std::env::temp_dir().join(format!("event-gate-test-{}",std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let mut gate=Gate::new(&root).unwrap();
        assert!(!gate.changed(), "unchanged directory must suppress file polling");
        std::fs::write(root.join("marker"),b"ready").unwrap();
        assert!(gate.changed());
        assert!(!gate.changed());
        std::fs::remove_dir_all(root).unwrap();
    }
}
