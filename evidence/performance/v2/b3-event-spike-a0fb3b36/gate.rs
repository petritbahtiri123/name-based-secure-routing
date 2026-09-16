// Throwaway Linux-local-filesystem experiment, not a production backend.
use std::path::{Path, PathBuf};
use std::io::Read;
use std::os::fd::{FromRawFd, AsRawFd};
use std::os::unix::{ffi::OsStrExt, fs::MetadataExt};
unsafe extern "C" {
    fn inotify_init1(flags: i32) -> i32;
    fn inotify_add_watch(fd: i32, path: *const std::ffi::c_char, mask: u32) -> i32;
}
pub struct Gate { file: std::fs::File, root: PathBuf, identity: (u64,u64), fallback: bool }
impl Gate {
    pub fn new(root: &Path) -> std::io::Result<Self> {
        let path=std::ffi::CString::new(root.as_os_str().as_bytes())?;
        let metadata=std::fs::metadata(root)?;
        // Linux O_NONBLOCK | O_CLOEXEC. This prototype runs only on Linux.
        let fd=unsafe { inotify_init1(0x800 | 0x80000) };
        if fd<0 { return Err(std::io::Error::last_os_error()); }
        let file=unsafe { std::fs::File::from_raw_fd(fd) };
        let wd=unsafe { inotify_add_watch(file.as_raw_fd(),path.as_ptr(),0xfff | 0x01000000 | 0x02000000) };
        if wd<0 { return Err(std::io::Error::last_os_error()); }
        Ok(Self { file, root:root.to_owned(), identity:(metadata.dev(),metadata.ino()), fallback:false })
    }
    pub fn changed(&mut self) -> bool {
        if self.fallback { return true; }
        if !std::fs::metadata(&self.root).is_ok_and(|m|(m.dev(),m.ino())==self.identity) {
            self.fallback=true; return true;
        }
        let mut buffer=[0u8;8192];
        match self.file.read(&mut buffer) {
            Err(e) if e.kind()==std::io::ErrorKind::WouldBlock => false,
            Err(_) | Ok(0) => { self.fallback=true; true },
            Ok(n) => {
                let mut offset=0;
                while offset<n {
                    if offset+16>n { self.fallback=true; break; }
                    let mask=u32::from_ne_bytes(buffer[offset+4..offset+8].try_into().unwrap());
                    let len=u32::from_ne_bytes(buffer[offset+12..offset+16].try_into().unwrap()) as usize;
                    if mask & (0x400 | 0x800 | 0x4000 | 0x8000) != 0 { self.fallback=true; }
                    offset+=16+len;
                    if offset>n { self.fallback=true; }
                }
                true
            }
        }
    }
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
    #[test]
    fn replaced_root_falls_back_to_scanning() {
        let root=std::env::temp_dir().join(format!("event-gate-replace-{}",std::process::id()));
        let moved=root.with_extension("moved");
        std::fs::create_dir(&root).unwrap();
        let mut gate=Gate::new(&root).unwrap();
        std::fs::rename(&root,&moved).unwrap();
        std::fs::create_dir(&root).unwrap();
        assert!(gate.changed());
        assert!(gate.changed());
        std::fs::remove_dir(root).unwrap();
        std::fs::remove_dir(moved).unwrap();
    }
}
