use std::io::{self, Write};
use std::path::Path;
use std::time::Duration;

const BOUNDS_NS: [u64; 16] = [
    125_000,
    250_000,
    500_000,
    1_000_000,
    2_000_000,
    4_000_000,
    8_000_000,
    16_000_000,
    32_000_000,
    64_000_000,
    128_000_000,
    256_000_000,
    512_000_000,
    1_024_000_000,
    2_048_000_000,
    4_096_000_000,
];

#[derive(Default)]
pub struct Profile {
    scan_calls: u64,
    futures_polled: u64,
    scan_wall_ns: u128,
    timer_wins: u64,
    accept_wins: u64,
    timer_select_wall_ns: u128,
    accept_select_wall_ns: u128,
    timer_max_ns: u128,
    timer_histogram: [u64; 17],
}

impl Profile {
    pub fn scan(&mut self, elapsed: Duration, futures: usize) {
        self.scan_calls = self
            .scan_calls
            .checked_add(1)
            .expect("scan counter overflow");
        self.futures_polled = self
            .futures_polled
            .checked_add(futures as u64)
            .expect("poll counter overflow");
        self.scan_wall_ns += elapsed.as_nanos();
    }

    pub fn selected(&mut self, elapsed: Duration, timer: bool) {
        let ns = elapsed.as_nanos();
        if timer {
            self.timer_wins = self
                .timer_wins
                .checked_add(1)
                .expect("timer counter overflow");
            self.timer_select_wall_ns += ns;
            self.timer_max_ns = self.timer_max_ns.max(ns);
            let bucket = BOUNDS_NS
                .iter()
                .position(|bound| ns <= u128::from(*bound))
                .unwrap_or(16);
            self.timer_histogram[bucket] += 1;
        } else {
            self.accept_wins = self
                .accept_wins
                .checked_add(1)
                .expect("accept counter overflow");
            self.accept_select_wall_ns += ns;
        }
    }

    pub fn json(&self) -> String {
        format!(
            concat!(
                "{{\"schema\":\"nbsr-accept-pump-profile-v1\",",
                "\"scan_calls\":{},\"futures_polled\":{},\"scan_wall_ns\":{},",
                "\"timer_wins\":{},\"accept_wins\":{},\"timer_select_wall_ns\":{},",
                "\"accept_select_wall_ns\":{},\"timer_max_ns\":{},",
                "\"timer_histogram_bounds_ns\":{:?},\"timer_histogram\":{:?}}}\n"
            ),
            self.scan_calls,
            self.futures_polled,
            self.scan_wall_ns,
            self.timer_wins,
            self.accept_wins,
            self.timer_select_wall_ns,
            self.accept_select_wall_ns,
            self.timer_max_ns,
            BOUNDS_NS,
            self.timer_histogram
        )
    }

    pub fn write(&self, path: &Path) -> io::Result<()> {
        let mut file = std::fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(path)?;
        file.write_all(self.json().as_bytes())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    #[test]
    fn profile_never_overwrites_existing_evidence() {
        let unique = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path =
            std::env::temp_dir().join(format!("nbsr-pump-{}-{unique}.json", std::process::id()));
        std::fs::write(&path, b"existing evidence").unwrap();
        assert_eq!(
            Profile::default().write(&path).unwrap_err().kind(),
            io::ErrorKind::AlreadyExists
        );
        assert_eq!(std::fs::read(&path).unwrap(), b"existing evidence");
        std::fs::remove_file(path).unwrap();
    }

    #[test]
    fn scan_and_timer_waits_remain_separate_and_histograms_conserve() {
        let mut profile = Profile::default();
        profile.scan(Duration::from_micros(100), 512);
        profile.selected(Duration::from_millis(16), true);
        profile.selected(Duration::from_millis(2), false);
        let value: serde_json::Value = serde_json::from_str(&profile.json()).unwrap();
        assert_eq!(value["scan_calls"], 1);
        assert_eq!(value["futures_polled"], 512);
        assert_eq!(value["scan_wall_ns"], 100_000);
        assert_eq!(value["timer_wins"], 1);
        assert_eq!(value["accept_wins"], 1);
        assert_eq!(value["timer_select_wall_ns"], 16_000_000);
        assert_eq!(
            value["timer_histogram"]
                .as_array()
                .unwrap()
                .iter()
                .map(|v| v.as_u64().unwrap())
                .sum::<u64>(),
            1
        );
    }
}
