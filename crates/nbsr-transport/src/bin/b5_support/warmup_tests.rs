use super::paced_warmup::WarmupPacer;

#[test]
fn aggregate_warmup_budget_is_not_multiplied_by_streams() {
    let mut a = WarmupPacer::new(6000, 1, 2, 0, 3_000_000_000).unwrap();
    let mut b = WarmupPacer::new(6000, 1, 2, 1, 3_000_000_000).unwrap();
    let mut count = 0;
    for tick in 0..300 {
        let now = tick * 10_000_000;
        while a.reserve(now).unwrap() {
            count += 1;
        }
        while b.reserve(now).unwrap() {
            count += 1;
        }
        assert_eq!(count, (tick + 1) * 60);
        assert_eq!(a.next_tick(now), (tick + 1) * 10_000_000);
    }
    assert_eq!(count, 18000);
    assert!(!a.reserve(3_000_000_000).unwrap());
    assert!(!b.reserve(3_000_000_000).unwrap());
}

#[test]
fn delayed_stream_drops_missed_budget_and_never_catches_up() {
    let mut p = WarmupPacer::new(6000, 1, 2, 0, 3_000_000_000).unwrap();
    let mut count = 0;
    while p.reserve(2_500_000_000).unwrap() {
        count += 1;
    }
    assert_eq!(count, 30);
    assert_eq!(p.next_tick(2_999_999_999), 3_000_000_000);
    assert!(!p.reserve(3_000_000_000).unwrap());
}
