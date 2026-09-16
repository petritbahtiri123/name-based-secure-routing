// Isolated Linux experiment, not a supported general marker backend.
use std::collections::HashSet;
use std::ffi::OsString;
use std::path::{Path,PathBuf};
use std::io::Read;
use std::os::fd::{AsRawFd,FromRawFd};
use std::os::unix::{ffi::{OsStrExt,OsStringExt},fs::MetadataExt};
fn names(bytes: &[u8]) -> Option<HashSet<OsString>> {
    let mut selected=HashSet::new();
    let mut offset=0;
    while offset<bytes.len() {
        let header=bytes.get(offset..offset+16)?;
        let wd=i32::from_ne_bytes(header[..4].try_into().ok()?);
        let mask=u32::from_ne_bytes(header[4..8].try_into().ok()?);
        let len=u32::from_ne_bytes(header[12..16].try_into().ok()?) as usize;
        if wd<0 || mask & (0x4000|0x8000|0x400|0x800)!=0 { return None; }
        let end=(offset+16).checked_add(len)?;
        let name=bytes.get(offset+16..end)?;
        let nul=name.iter().position(|b|*b==0)?;
        if nul==0 || name[..nul].contains(&b'/') || &name[..nul]==b"." || &name[..nul]==b".." {return None;}
        selected.insert(OsString::from_vec(name[..nul].to_vec()));
        offset=end;
    }
    Some(selected)
}
unsafe extern "C" {
    fn inotify_init1(flags:i32)->i32;
    fn inotify_add_watch(fd:i32,path:*const std::ffi::c_char,mask:u32)->i32;
}
pub struct Gate {file:std::fs::File,root:PathBuf,identity:(u64,u64),fallback:bool}
impl Gate {
    pub fn new(root:&Path)->std::io::Result<Self> {
        let path=std::ffi::CString::new(root.as_os_str().as_bytes())?;
        let metadata=std::fs::metadata(root)?;
        let fd=unsafe {inotify_init1(0x800|0x80000)};
        if fd<0 {return Err(std::io::Error::last_os_error());}
        let file=unsafe {std::fs::File::from_raw_fd(fd)};
        if unsafe {inotify_add_watch(file.as_raw_fd(),path.as_ptr(),0xfff|0x01000000|0x02000000)}<0 {
            return Err(std::io::Error::last_os_error());
        }
        Ok(Self {file,root:root.to_owned(),identity:(metadata.dev(),metadata.ino()),fallback:false})
    }
    // None means every path must be checked; Some(empty) means no named changes.
    pub fn changes(&mut self)->Option<HashSet<PathBuf>> {
        if self.fallback {return None;}
        if !std::fs::metadata(&self.root).is_ok_and(|m|(m.dev(),m.ino())==self.identity) {
            self.fallback=true;return None;
        }
        let mut buffer=[0u8;8192];
        let selected=match self.file.read(&mut buffer) {
            Err(e) if e.kind()==std::io::ErrorKind::WouldBlock=>Some(HashSet::new()),
            Err(_)|Ok(0)=>None,
            Ok(n)=>names(&buffer[..n]),
        };
        if selected.is_none() {self.fallback=true;}
        selected.map(|names|names.into_iter().map(|n|self.root.join(n)).collect())
    }
}
#[cfg(test)]
mod tests {
    use super::*;
    fn event(mask:u32,name:&[u8]) -> Vec<u8> {
        let mut bytes=Vec::new();
        bytes.extend_from_slice(&1i32.to_ne_bytes());
        bytes.extend_from_slice(&mask.to_ne_bytes());
        bytes.extend_from_slice(&0u32.to_ne_bytes());
        bytes.extend_from_slice(&(name.len() as u32).to_ne_bytes());
        bytes.extend_from_slice(name);
        bytes
    }
    #[test]
    fn selects_only_published_names_and_coalesces_duplicates() {
        let mut bytes=event(0x100,b"connection-3.start\0");
        bytes.extend(event(0x8,b"connection-3.start\0"));
        let selected=names(&bytes).expect("normal named events must be selective");
        assert_eq!(selected.len(),1);
        assert!(selected.contains(&OsString::from("connection-3.start")));
        assert!(!selected.contains(&OsString::from("connection-4.start")));
    }
    #[test]
    fn overflow_and_watch_loss_require_full_scan() {
        for mask in [0x4000,0x8000,0x400,0x800] { assert!(names(&event(mask,b"\0")).is_none()); }
    }
    #[test]
    fn malformed_or_nonlocal_names_require_full_scan() {
        assert!(names(&[0u8;15]).is_none());
        for name in [b"../x\0".as_slice(),b"x/y\0",b"missing-nul",b"\0"] {
            assert!(names(&event(0x100,name)).is_none());
        }
        let mut truncated=event(0x100,b"marker\0");
        truncated.pop();
        assert!(names(&truncated).is_none());
    }
    #[test]
    fn native_create_and_rename_are_named() {
        let root=std::env::temp_dir().join(format!("selective-create-{}",std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let mut gate=Gate::new(&root).unwrap();
        assert!(gate.changes().unwrap().is_empty());
        let old=root.join("temporary"); let new=root.join("marker");
        std::fs::write(&old,b"ready").unwrap();
        std::fs::rename(&old,&new).unwrap();
        assert!(gate.changes().unwrap().contains(&new));
        assert!(gate.changes().unwrap().is_empty());
        std::fs::remove_dir_all(root).unwrap();
        assert!(gate.changes().is_none());
        assert!(gate.changes().is_none());
    }
    #[test]
    fn root_replacement_requires_permanent_full_scan() {
        let root=std::env::temp_dir().join(format!("selective-replace-{}",std::process::id()));
        let moved=root.with_extension("moved");
        std::fs::create_dir(&root).unwrap();
        let mut gate=Gate::new(&root).unwrap();
        std::fs::rename(&root,&moved).unwrap();
        std::fs::create_dir(&root).unwrap();
        assert!(gate.changes().is_none()); assert!(gate.changes().is_none());
        std::fs::remove_dir(root).unwrap(); std::fs::remove_dir(moved).unwrap();
    }
}
