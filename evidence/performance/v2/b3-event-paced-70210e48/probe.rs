// Offline paced marker publication, no QUIC or admission capacity claim.
#[cfg(all(test, target_os = "linux", feature = "benchmark-harness"))]
mod paced_event_probe {
    use super::*;
    use std::sync::{Arc, atomic::{AtomicUsize, Ordering}};

    fn ticks() -> u64 {
        let s=std::fs::read_to_string("/proc/self/stat").unwrap();
        let f:Vec<_>=s[s.rfind(')').unwrap()+2..].split_whitespace().collect();
        f[11].parse::<u64>().unwrap()+f[12].parse::<u64>().unwrap()
    }
    fn percentile(values: &mut [u128], percent: usize) -> u128 {
        values.sort_unstable();
        values[(values.len()*percent).div_ceil(100)-1]
    }
    #[test]
    #[ignore = "offline paced comparison; no QUIC attribution"]
    fn event_monitor_cpu_comparison() {
        let output=std::process::Command::new("getconf").arg("CLK_TCK").output().unwrap();
        assert!(output.status.success());
        let hz=std::str::from_utf8(&output.stdout).unwrap().trim();
        let root=std::env::temp_dir().join(format!("nbsr-paced-monitor-{}",std::process::id()));
        std::fs::create_dir(&root).unwrap();
        let rt=tokio::runtime::Builder::new_current_thread().enable_time().build().unwrap();
        for repeat in 1..=5 {
            let modes=if repeat%2==1 {["monitor","event"]} else {["event","monitor"]};
            for mode in modes {
                let cell=root.join(format!("{repeat}-{mode}"));
                std::fs::create_dir(&cell).unwrap();
                rt.block_on(async {
                    let monitor=(mode=="monitor").then(marker_monitor::MarkerMonitor::new);
                    let event=(mode=="event").then(event_monitor::MarkerMonitor::new);
                    let started=Arc::new(AtomicUsize::new(0));
                    let mut tasks=tokio::task::JoinSet::new();
                    for i in 0..2048 {
                        let path=cell.join(format!("connection-{i}.start"));
                        let started=started.clone();
                        let waiter=monitor.as_ref().map(|m|m.waiter());
                        let event_waiter=event.as_ref().map(|m|m.waiter());
                        tasks.spawn(event_monitor::scope(event_waiter,marker_monitor::scope(waiter,async move {
                            started.fetch_add(1,Ordering::SeqCst);
                            if mode=="event" {
                                event_monitor::wait_if_scoped(&path,Duration::from_secs(120)).await.unwrap().unwrap();
                            } else {
                                wait_for_lifecycle_start(&path,Duration::from_secs(120)).await.unwrap();
                            }
                            (i,std::time::Instant::now())
                        })));
                    }
                    while started.load(Ordering::SeqCst)!=2048 {tokio::task::yield_now().await;}
                    tokio::time::sleep(Duration::from_millis(30)).await;
                    let before=ticks();
                    let start=std::time::Instant::now();
                    let mut published=Vec::with_capacity(2048);
                    let mut lateness=Vec::with_capacity(2048);
                    for i in 0..2048 {
                        let target=start+Duration::from_millis(i*10);
                        tokio::time::sleep_until(tokio::time::Instant::from_std(target)).await;
                        lateness.push(std::time::Instant::now().duration_since(target).as_nanos());
                        // Current-thread runtime: no waiter can run inside this synchronous write.
                        std::fs::write(cell.join(format!("connection-{i}.start")),b"start\n").unwrap();
                        published.push(std::time::Instant::now());
                    }
                    let mut completed=Vec::with_capacity(2048);
                    while let Some(result)=tasks.join_next().await {completed.push(result.unwrap());}
                    let elapsed=start.elapsed().as_nanos();
                    let used=ticks()-before;
                    assert_eq!(completed.len(),2048);
                    let mut seen=vec![false;2048];
                    let mut delays=Vec::with_capacity(2048);
                    for (i,done) in completed {
                        assert!(!seen[i]); seen[i]=true;
                        delays.push(done.checked_duration_since(published[i]).unwrap().as_nanos());
                    }
                    if let Some(m)=monitor {m.shutdown().await;}
                    if let Some(m)=event {m.shutdown().await;}
                    let p50=percentile(&mut delays,50);
                    let p95=percentile(&mut delays,95);
                    let p99=percentile(&mut delays,99);
                    let publish_p99=percentile(&mut lateness,99);
                    println!("PACED_CPU mode={mode} count=2048 completed=2048 offered_per_second=100 repeat={repeat} cpu_ticks={used} hz={hz} elapsed_ns={elapsed} wake_p50_ns={p50} wake_p95_ns={p95} wake_p99_ns={p99} publish_lateness_p99_ns={publish_p99}");
                });
            }
        }
        std::fs::remove_dir_all(root).unwrap();
    }
}
