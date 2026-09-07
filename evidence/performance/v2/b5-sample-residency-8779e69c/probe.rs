use std::ffi::{c_int, c_void};
unsafe extern "C" {
    fn mincore(addr: *mut c_void, length: usize, vector: *mut u8) -> c_int;
    fn getpagesize() -> c_int;
}
fn resident(buffer: &Vec<u64>) -> (usize, usize) {
    // The allocated capacity covers the rounded pages; mincore queries mapping
    // metadata without reading uninitialized sample storage.
    let page = unsafe { getpagesize() } as usize;
    let start = buffer.as_ptr() as usize;
    let base = start / page * page;
    let bytes = start - base + buffer.capacity() * size_of::<u64>();
    let pages = bytes.div_ceil(page);
    let mut flags = vec![0_u8; pages];
    assert_eq!(unsafe { mincore(base as *mut c_void, pages * page, flags.as_mut_ptr()) }, 0);
    (flags.iter().filter(|value| **value & 1 != 0).count(), pages)
}
fn main() {
    let pretouch = std::env::args().nth(1).as_deref() == Some("pretouch");
    let mut samples = Vec::<u64>::new();
    samples.try_reserve_exact(24347).unwrap();
    if pretouch {
        samples.resize(24347, u64::MAX);
        std::hint::black_box(samples.as_slice());
        samples.clear();
    }
    let (before, pages) = resident(&samples);
    for value in 0..12067 { samples.push(value); }
    std::hint::black_box(samples.as_slice());
    let (after, _) = resident(&samples);
    println!("{{\"pretouch\":{pretouch},\"capacity\":{},\"samples\":{},\"pages\":{pages},\"resident_before\":{before},\"resident_after\":{after}}}", samples.capacity(), samples.len());
}
