pub fn valid_client_count(count: usize, live_bundles: bool) -> bool {
    let maximum_clients = if live_bundles { 8192 } else { 1024 };
    (1..=maximum_clients).contains(&count)
}

#[cfg(test)]
mod tests {
    use super::valid_client_count;

    #[test]
    fn live_count_accepts_8192_but_not_more() {
        assert!(valid_client_count(8192, true));
        assert!(!valid_client_count(8193, true));
        assert!(!valid_client_count(0, true));
    }

    #[test]
    fn idle_limit_and_existing_live_counts_are_unchanged() {
        assert!(valid_client_count(1024, false));
        assert!(!valid_client_count(1025, false));
        assert!(!valid_client_count(8192, false));
        assert!(!valid_client_count(0, false));
        assert!(valid_client_count(4096, true));
    }
}
