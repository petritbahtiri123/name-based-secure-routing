// Isolated Linux experiment, not a supported general marker backend.
use std::collections::HashSet;
use std::ffi::OsString;
fn names(_: &[u8]) -> Option<HashSet<OsString>> { None }
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
}
