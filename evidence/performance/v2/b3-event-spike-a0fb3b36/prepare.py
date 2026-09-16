from pathlib import Path
root=Path(__file__).resolve().parent
source=(root/'marker_monitor.rs').read_text()
source=source.replace('//! Runtime-owned benchmark marker waiting; never protocol or admission authority.',
    '//! THROWAWAY local regular-file notification experiment; not integrated.\n#[path = "gate.rs"]\nmod gate;')
source=source.replace('let mut pending = Vec::new();\n    loop {',
    'let mut pending = Vec::new();\n    let mut gate: Option<gate::Gate> = None;\n    let mut initialized = false;\n    loop {\n        let mut added = false;')
source=source.replace('Some(request) => pending.push(request),', 'Some(request) => { pending.push(request); added = true; },')
source=source.replace('pending.push(request);\n        }\n        poll_pending(&mut pending);',
    '''pending.push(request);
            added = true;
        }
        if !initialized {
            gate = pending.first().and_then(|r|r.path.parent()).and_then(|p|gate::Gate::new(p).ok());
            initialized = true;
        }
        // Prototype contract: one fixed native directory, regular marker paths.
        // Watch is installed before first registration scan.
        let changed = gate.as_mut().is_none_or(|g|g.changed());
        if added || changed { poll_pending(&mut pending); }
        else { pending.retain(|r|!r.ready.is_closed()); }''')
# The integration-specific task-local test references the original module;
# retain it in baseline, omit it from the isolated prototype copy.
start=source.index('    #[tokio::test(flavor = "current_thread")]\n    async fn scoped_release_')
source=source[:start]+'}\n'
(root/'event_monitor.rs').write_text(source)
probe=Path('C:/NBSR-build/b3-marker-monitor-cpu-0288122d/probe.rs').read_text()
probe=probe.replace('actual_monitor_cpu_comparison','event_monitor_cpu_comparison')
probe=probe.replace('["current","monitor","pending"]','["monitor","event","pending"]')
probe=probe.replace('["pending","monitor","current"]','["pending","event","monitor"]')
probe=probe.replace('let started=Arc::new', 'let event=(mode=="event").then(event_monitor::MarkerMonitor::new);\n                        let started=Arc::new')
probe=probe.replace('let waiter=monitor.as_ref().map(|m|m.waiter());','let waiter=monitor.as_ref().map(|m|m.waiter());\n                            let event_waiter=event.as_ref().map(|m|m.waiter());')
probe=probe.replace('tasks.spawn(marker_monitor::scope(waiter, async move {','tasks.spawn(event_monitor::scope(event_waiter, marker_monitor::scope(waiter, async move {')
probe=probe.replace('else {wait_for_lifecycle_start', 'else if mode=="event" { event_monitor::wait_if_scoped(&path,Duration::from_secs(120)).await.unwrap().unwrap(); }\n                                else {wait_for_lifecycle_start')
probe=probe.replace('}));','})));')
probe=probe.replace('let elapsed=start.elapsed()', 'let elapsed=start.elapsed()')
probe=probe.replace('Duration::from_secs(2)', 'Duration::from_secs(4)')
probe=probe.replace('if let Some(monitor)=monitor {monitor.shutdown().await;}',
    'if let Some(monitor)=monitor {monitor.shutdown().await;}\n                        if let Some(event)=event {event.shutdown().await;}')
(root/'probe.rs').write_text(probe)
