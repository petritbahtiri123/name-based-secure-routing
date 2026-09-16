//! Benchmark-only local filesystem notification filter; never marker authority.
use std::collections::HashSet;
use std::ffi::OsString;
use std::fs::File;
use std::io::{self, Read};
use std::os::fd::{AsRawFd, FromRawFd};
use std::os::unix::{
    ffi::{OsStrExt, OsStringExt},
    fs::MetadataExt,
};
use std::path::{Path, PathBuf};

#[derive(Default)]
pub(super) struct Notifications {
    watch: Option<Watch>,
    disabled: bool,
}
impl Notifications {
    pub(super) fn observe(&mut self, path: &Path) {
        if self.disabled {
            return;
        }
        if self.watch.is_none() {
            self.watch = path.parent().and_then(|root| Watch::new(root).ok());
        }
        if !self
            .watch
            .as_ref()
            .is_some_and(|watch| path.parent() == Some(watch.root.as_path()))
            || !ordinary_path(path)
        {
            self.disable();
        }
    }
    fn disable(&mut self) {
        self.disabled = true;
        self.watch = None;
    }
    pub(super) fn changed(&mut self) -> Option<HashSet<PathBuf>> {
        if self.disabled {
            return None;
        }
        let selected = self.watch.as_mut().and_then(Watch::changed);
        // A symlink can become a file when its external target changes without
        // an event in this directory. Switch permanently to ordinary polling.
        if selected
            .as_ref()
            .is_none_or(|paths| paths.iter().any(|path| !ordinary_path(path)))
        {
            self.disable();
            return None;
        }
        selected
    }
}

fn ordinary_path(path: &Path) -> bool {
    match std::fs::symlink_metadata(path) {
        Ok(metadata) => !metadata.file_type().is_symlink(),
        Err(error) => error.kind() == io::ErrorKind::NotFound,
    }
}
fn supported_filesystem(kind: impl Into<i128>) -> bool {
    [
        i128::from(libc::EXT4_SUPER_MAGIC),
        i128::from(libc::TMPFS_MAGIC),
        i128::from(libc::OVERLAYFS_SUPER_MAGIC),
    ]
    .contains(&kind.into())
}
struct Watch {
    file: File,
    root: PathBuf,
    identity: (u64, u64),
    descriptor: i32,
}
impl Watch {
    fn new(root: &Path) -> io::Result<Self> {
        if !root.is_absolute() || std::fs::canonicalize(root)? != root {
            return Err(io::Error::other("noncanonical marker directory"));
        }
        let directory = File::open(root)?;
        let metadata = directory.metadata()?;
        let mut info = std::mem::MaybeUninit::<libc::statfs>::uninit();
        // SAFETY: directory owns a live fd; statfs writes one correctly sized struct.
        if unsafe { libc::fstatfs(directory.as_raw_fd(), info.as_mut_ptr()) } != 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: successful fstatfs initialized info.
        if !supported_filesystem(unsafe { info.assume_init() }.f_type) {
            return Err(io::Error::other("unsupported marker filesystem"));
        }
        let root_c = std::ffi::CString::new(root.as_os_str().as_bytes())?;
        // SAFETY: valid Linux flags, no borrowed pointers.
        let fd = unsafe { libc::inotify_init1(libc::IN_NONBLOCK | libc::IN_CLOEXEC) };
        if fd < 0 {
            return Err(io::Error::last_os_error());
        }
        // SAFETY: init1 returned a new owned fd, transferred exactly once.
        let file = unsafe { File::from_raw_fd(fd) };
        // SAFETY: fd is live and root_c is a valid nul-terminated path.
        let descriptor = unsafe {
            libc::inotify_add_watch(
                file.as_raw_fd(),
                root_c.as_ptr(),
                libc::IN_CREATE
                    | libc::IN_MOVED_TO
                    | libc::IN_MOVED_FROM
                    | libc::IN_DELETE
                    | libc::IN_ATTRIB
                    | libc::IN_CLOSE_WRITE
                    | libc::IN_DELETE_SELF
                    | libc::IN_MOVE_SELF
                    | libc::IN_ONLYDIR
                    | libc::IN_DONT_FOLLOW,
            )
        };
        if descriptor < 0 {
            return Err(io::Error::last_os_error());
        }
        let watch = Self {
            file,
            root: root.to_owned(),
            identity: (metadata.dev(), metadata.ino()),
            descriptor,
        };
        if !watch.same_root() {
            return Err(io::Error::other(
                "marker directory changed during watch creation",
            ));
        }
        Ok(watch)
    }
    fn same_root(&self) -> bool {
        std::fs::symlink_metadata(&self.root)
            .is_ok_and(|m| m.is_dir() && (m.dev(), m.ino()) == self.identity)
    }
    fn changed(&mut self) -> Option<HashSet<PathBuf>> {
        if !self.same_root() {
            return None;
        }
        let mut bytes = [0u8; 8192];
        match self.file.read(&mut bytes) {
            Err(error) if error.kind() == io::ErrorKind::WouldBlock => Some(HashSet::new()),
            Err(_) | Ok(0) => None,
            Ok(length) => {
                let names = decode(&bytes[..length], self.descriptor)?;
                // Do not defer a large event backlog across many 10ms ticks.
                // A second nonempty batch conservatively restores full polling.
                match self.file.read(&mut bytes) {
                    Err(error) if error.kind() == io::ErrorKind::WouldBlock => {
                        Some(names.into_iter().map(|name| self.root.join(name)).collect())
                    }
                    _ => None,
                }
            }
        }
    }
}
fn decode(bytes: &[u8], descriptor: i32) -> Option<HashSet<OsString>> {
    let mut names = HashSet::new();
    let mut offset = 0usize;
    while offset < bytes.len() {
        let header_end = offset.checked_add(16)?;
        let header = bytes.get(offset..header_end)?;
        let wd = i32::from_ne_bytes(header[..4].try_into().ok()?);
        let mask = u32::from_ne_bytes(header[4..8].try_into().ok()?);
        let length = u32::from_ne_bytes(header[12..16].try_into().ok()?) as usize;
        if wd != descriptor
            || mask
                & (libc::IN_Q_OVERFLOW
                    | libc::IN_IGNORED
                    | libc::IN_DELETE_SELF
                    | libc::IN_MOVE_SELF
                    | libc::IN_UNMOUNT)
                != 0
        {
            return None;
        }
        let end = header_end.checked_add(length)?;
        let name = bytes.get(header_end..end)?;
        let nul = name.iter().position(|b| *b == 0)?;
        if nul == 0 || name[..nul].contains(&b'/') || &name[..nul] == b"." || &name[..nul] == b".."
        {
            return None;
        }
        names.insert(OsString::from_vec(name[..nul].to_vec()));
        offset = end;
    }
    Some(names)
}

#[cfg(test)]
mod tests {
    use super::*;
    struct Fixture(PathBuf);
    impl Fixture {
        fn new() -> Self {
            let root = std::env::temp_dir().join(format!(
                "nbsr-notices-{}-{}",
                std::process::id(),
                std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            std::fs::create_dir(&root).unwrap();
            Self(std::fs::canonicalize(root).unwrap())
        }
    }
    impl Drop for Fixture {
        fn drop(&mut self) {
            std::fs::remove_dir_all(&self.0).unwrap();
        }
    }
    #[test]
    fn overflow_malformed_and_unknown_watch_reject_selection() {
        fn event(wd: i32, mask: u32, name: &[u8]) -> Vec<u8> {
            [
                wd.to_ne_bytes().as_slice(),
                mask.to_ne_bytes().as_slice(),
                0u32.to_ne_bytes().as_slice(),
                (name.len() as u32).to_ne_bytes().as_slice(),
                name,
            ]
            .concat()
        }
        assert_eq!(
            decode(&event(1, libc::IN_CREATE, b"a\0"), 1),
            Some(HashSet::from([OsString::from("a")]))
        );
        for mask in [
            libc::IN_Q_OVERFLOW,
            libc::IN_IGNORED,
            libc::IN_DELETE_SELF,
            libc::IN_MOVE_SELF,
            libc::IN_UNMOUNT,
        ] {
            assert!(decode(&event(1, mask, b"a\0"), 1).is_none());
        }
        assert!(decode(&event(2, libc::IN_CREATE, b"a\0"), 1).is_none());
        assert!(decode(&[0; 15], 1).is_none());
        for name in [b"a/b\0".as_slice(), b"..\0", b".\0", b"\0", b"no-nul"] {
            assert!(decode(&event(1, libc::IN_CREATE, name), 1).is_none());
        }
    }
    #[test]
    fn unsupported_filesystems_and_relative_roots_use_polling() {
        assert!(supported_filesystem(libc::EXT4_SUPER_MAGIC));
        assert!(supported_filesystem(libc::TMPFS_MAGIC));
        assert!(supported_filesystem(libc::OVERLAYFS_SUPER_MAGIC));
        assert!(!supported_filesystem(libc::NFS_SUPER_MAGIC));
        assert!(!supported_filesystem(libc::PROC_SUPER_MAGIC));
        let mut notices = Notifications::default();
        notices.observe(Path::new("relative/marker"));
        assert!(notices.changed().is_none());
        let mut notices = Notifications::default();
        notices.observe(Path::new("/proc/nonexistent-marker"));
        assert!(notices.changed().is_none());
    }
    #[test]
    fn event_backlog_falls_back_and_releases_watch() {
        let root = Fixture::new();
        let mut notices = Notifications::default();
        notices.observe(&root.0.join("marker"));
        assert!(notices.watch.is_some());
        for i in 0..512 {
            std::fs::write(root.0.join(format!("other-{i}")), b"x").unwrap();
        }
        assert!(notices.changed().is_none());
        assert!(notices.watch.is_none());
        assert!(notices.disabled);
    }
    #[test]
    fn select_named_creation_without_scanning_unchanged_paths() {
        let root = Fixture::new();
        let path = root.0.join("marker");
        let mut notices = Notifications::default();
        notices.observe(&path);
        assert_eq!(notices.changed(), Some(HashSet::new()));
        std::fs::write(&path, b"ready").unwrap();
        assert!(notices.changed().unwrap().contains(&path));
        assert_eq!(notices.changed(), Some(HashSet::new()));
    }
    #[test]
    fn mixed_roots_and_existing_symlink_fall_back() {
        let a = Fixture::new();
        let b = Fixture::new();
        let mut notices = Notifications::default();
        notices.observe(&a.0.join("marker"));
        notices.observe(&b.0.join("marker"));
        assert!(notices.changed().is_none());
        let link = a.0.join("link");
        std::os::unix::fs::symlink(b.0.join("absent"), &link).unwrap();
        let mut notices = Notifications::default();
        notices.observe(&link);
        assert!(notices.changed().is_none());
    }
    #[test]
    fn late_symlink_and_root_replacement_fall_back_permanently() {
        let a = Fixture::new();
        let b = Fixture::new();
        let path = a.0.join("marker");
        let mut notices = Notifications::default();
        notices.observe(&path);
        std::os::unix::fs::symlink(b.0.join("absent"), &path).unwrap();
        assert!(notices.changed().is_none());
        assert!(notices.changed().is_none());
        let mut notices = Notifications::default();
        notices.observe(&b.0.join("marker"));
        let moved = b.0.with_extension("moved");
        std::fs::rename(&b.0, &moved).unwrap();
        std::fs::create_dir(&b.0).unwrap();
        assert!(notices.changed().is_none());
        std::fs::remove_dir(&moved).unwrap();
    }
}
