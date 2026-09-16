
// Offline before/after CPU test using the actual scoped marker implementation.
#[cfg(all(test, target_os = "linux", feature = "benchmark-harness"))]
mod monitor_cpu_probe {
    use super::*;
    use std::sync::{Arc, atomic::{AtomicUsize, Ordering}};

    fn ticks() -> u64 {
        let s=std::fs::read_to_string("/proc/self/stat").unwrap();
        let f:Vec<_>=s[s.rfind(')').unwrap()+2..].split_whitespace().collect();
        f[11].parse::<u64>().unwrap()+f[12].parse::<u64>().unwrap()
    }

    #[test]
    #[ignore = "offline CPU comparison; no QUIC attribution"]
    fn event_monitor_cpu_comparison() {
        let hz=std::process::Command::new("getconf").arg("CLK_TCK").output().unwrap();
        assert!(hz.status.success());
        let hz=std::str::from_utf8(&hz.stdout).unwrap().trim();
        let root=std::env::temp_dir().join(format!("nbsr-actual-monitor-cpu-{}",std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let rt=tokio::runtime::Builder::new_current_thread().enable_time().build().unwrap();
        for unrelated in [0,8192] {
            for i in 0..unrelated {std::fs::write(root.join(format!("other-{i}.active")), b"active\n").unwrap();}
            for repeat in 1..=5 {
                let modes=if repeat%2==1 {["monitor","event","pending"]} else {["pending","event","monitor"]};
                for mode in modes {
                    rt.block_on(async {
                        let monitor=(mode=="monitor").then(marker_monitor::MarkerMonitor::new);
                        let event=(mode=="event").then(event_monitor::MarkerMonitor::new);
                        let started=Arc::new(AtomicUsize::new(0));
                        let mut tasks=tokio::task::JoinSet::new();
                        for i in 0..2048 {
                            let path=root.join(format!("connection-{i}.start"));
                            let started=started.clone();
                            let waiter=monitor.as_ref().map(|m|m.waiter());
                            let event_waiter=event.as_ref().map(|m|m.waiter());
                            tasks.spawn(event_monitor::scope(event_waiter, marker_monitor::scope(waiter, async move {
                                started.fetch_add(1,Ordering::SeqCst);
                                if mode=="pending" {std::future::pending::<()>().await;}
                                else if mode=="event" { event_monitor::wait_if_scoped(&path,Duration::from_secs(120)).await.unwrap().unwrap(); }
                                else {wait_for_lifecycle_start(&path,Duration::from_secs(120)).await.unwrap();}
                            })));
                        }
                        while started.load(Ordering::SeqCst)!=2048 {tokio::task::yield_now().await;}
                        // Let the scanner consume registrations before measurement.
                        tokio::time::sleep(Duration::from_millis(30)).await;
                        let before=ticks();let start=std::time::Instant::now();
                        tokio::time::sleep(Duration::from_secs(4)).await;
                        let elapsed=start.elapsed().as_nanos();let used=ticks()-before;
                        tasks.abort_all();while tasks.join_next().await.is_some() {}
                        if let Some(monitor)=monitor {monitor.shutdown().await;}
                        if let Some(event)=event {event.shutdown().await;}
                        println!("MONITOR_CPU mode={mode} count=2048 unrelated={unrelated} repeat={repeat} cpu_ticks={used} hz={hz} elapsed_ns={elapsed}");
                    });
                }
            }
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}
