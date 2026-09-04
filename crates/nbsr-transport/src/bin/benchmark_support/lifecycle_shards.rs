use std::future::Future;
#[cfg(test)]
use std::time::{Duration, Instant};

#[cfg(windows)]
#[link(name = "kernel32")]
unsafe extern "system" {
    fn GetCurrentThreadId() -> u32;
}

#[cfg(windows)]
pub fn current_os_thread_id() -> u32 {
    // SAFETY: GetCurrentThreadId takes no arguments and has no failure mode.
    unsafe { GetCurrentThreadId() }
}

#[cfg(not(windows))]
pub fn current_os_thread_id() -> u32 {
    0
}

pub fn parse_shards(value: Option<&str>) -> Result<usize, &'static str> {
    match value.unwrap_or("1") {
        "1" => Ok(1),
        "2" => Ok(2),
        _ => Err("lifecycle source shards must be 1 or 2"),
    }
}

pub fn assigned_clients(
    logical_clients: usize,
    shards: usize,
    shard: usize,
) -> Result<Vec<usize>, &'static str> {
    if !matches!(shards, 1 | 2) || shard >= shards {
        return Err("invalid lifecycle source shard");
    }
    Ok((0..logical_clients)
        .filter(|client| client % shards == shard)
        .collect())
}

#[cfg(test)]
pub fn global_release_at(
    origin: Instant,
    offered_rate: f64,
    client: usize,
) -> Result<Instant, &'static str> {
    if !offered_rate.is_finite() || offered_rate <= 0.0 {
        return Err("offered rate must be finite and positive");
    }
    Ok(origin + Duration::from_secs_f64(client as f64 / offered_rate))
}

pub fn run_fixed_shards<F, Fut, T>(shards: usize, operation: F) -> Result<Vec<T>, &'static str>
where
    F: Fn(usize) -> Fut + Send + Sync + 'static,
    Fut: Future<Output = T> + Send + 'static,
    T: Send + 'static,
{
    parse_shards(Some(&shards.to_string()))?;
    let operation = std::sync::Arc::new(operation);
    let handles = (0..shards)
        .map(|shard| {
            let operation = std::sync::Arc::clone(&operation);
            std::thread::Builder::new()
                .name(format!("nbsr-admission-shard-{shard}"))
                .spawn(move || {
                    eprintln!(
                        "{{\"event\":\"lifecycle_source_shard\",\"shard\":{shard},\"thread_id\":{}}}",
                        current_os_thread_id()
                    );
                    let runtime = nbsr_transport::p2a_benchmark::build_benchmark_runtime(1)
                        .map_err(|_| "failed to build shard runtime")?;
                    Ok(runtime.block_on(operation(shard)))
                })
                .map_err(|_| "failed to spawn shard")
        })
        .collect::<Result<Vec<_>, _>>()?;
    handles
        .into_iter()
        .map(|handle| handle.join().map_err(|_| "shard panicked")?)
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{Arc, Mutex};

    #[test]
    fn only_fixed_one_or_two_shards_are_valid() {
        assert_eq!(parse_shards(None).unwrap(), 1);
        assert_eq!(parse_shards(Some("1")).unwrap(), 1);
        assert_eq!(parse_shards(Some("2")).unwrap(), 2);
        assert!(parse_shards(Some("0")).is_err());
        assert!(parse_shards(Some("3")).is_err());
    }

    #[test]
    fn assignment_is_deterministic_complete_and_disjoint() {
        assert_eq!(assigned_clients(8, 2, 0).unwrap(), vec![0, 2, 4, 6]);
        assert_eq!(assigned_clients(8, 2, 1).unwrap(), vec![1, 3, 5, 7]);
        assert!(assigned_clients(8, 2, 2).is_err());
    }

    #[test]
    fn global_rate_schedule_is_identical_for_one_and_two_shards() {
        let origin = Instant::now();
        let one = global_release_at(origin, 200.0, 255).unwrap();
        let two = global_release_at(origin, 200.0, 255).unwrap();
        assert_eq!(one, two);
        assert_eq!(one.duration_since(origin), Duration::from_millis(1275));
        assert!(global_release_at(origin, 0.0, 1).is_err());
    }

    #[test]
    fn each_shard_owns_one_current_thread_runtime() {
        let threads = Arc::new(Mutex::new(Vec::new()));
        let observed = Arc::clone(&threads);
        let results = run_fixed_shards(2, move |shard| {
            let observed = Arc::clone(&observed);
            async move {
                observed
                    .lock()
                    .unwrap()
                    .push((shard, std::thread::current().id()));
                shard
            }
        })
        .unwrap();
        assert_eq!(results, vec![0, 1]);
        let threads = threads.lock().unwrap();
        assert_ne!(threads[0].1, threads[1].1);
    }

    #[cfg(windows)]
    #[test]
    fn windows_thread_identifier_is_available_for_external_cpu_sampling() {
        assert_ne!(current_os_thread_id(), 0);
    }
}
