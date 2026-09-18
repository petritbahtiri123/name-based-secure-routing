#![cfg(feature = "benchmark-harness")]

use std::time::Instant;

use nbsr_transport::p2a_benchmark::{
    FrameError, OutstandingTracker, decode_frame, decode_measured_frame, encode_frame,
    encode_measured_frame, parse_group_count, parse_group_endpoints, parse_runtime_workers,
    run_current_thread_groups,
};

#[test]
fn frame_round_trip_preserves_literal_sequence_and_payload() {
    let wire = encode_frame(0x0102_0304_0506_0708, &[0x00, 0x7f, 0xff]);
    let decoded = decode_frame(&wire, 0x0102_0304_0506_0708, 3).unwrap();
    assert_eq!(decoded, [0x00, 0x7f, 0xff]);
}

#[test]
fn frame_rejects_wrong_sequence() {
    let wire = encode_frame(7, b"payload");
    assert_eq!(decode_frame(&wire, 8, 7), Err(FrameError::WrongSequence));
}

#[test]
fn frame_rejects_corrupted_payload() {
    let mut wire = encode_frame(9, b"payload");
    wire[12] ^= 0x01;
    assert_eq!(decode_frame(&wire, 9, 7), Err(FrameError::Corrupt));
}

#[test]
fn frame_rejects_wrong_payload_length() {
    let wire = encode_frame(11, b"payload");
    assert_eq!(decode_frame(&wire, 11, 6), Err(FrameError::WrongLength));
}

#[test]
fn measured_frame_preserves_wire_size_without_reusing_full_sha_tag() {
    let payload = vec![0x5a; 16_384];
    let historical = encode_frame(1, &payload);
    let measured = encode_measured_frame(1, &payload);
    assert_eq!(measured.len(), historical.len());
    assert_ne!(
        &measured[measured.len() - 16..],
        &historical[historical.len() - 16..]
    );
    assert_eq!(
        decode_measured_frame(&measured, 1, &payload).unwrap(),
        payload
    );
}

#[test]
fn measured_frame_sample_detects_corruption_away_from_bounded_probes() {
    let payload = vec![0x5a; 16_384];
    let mut measured = encode_measured_frame(1024, &payload);
    measured[12 + 777] ^= 1;
    assert_eq!(
        decode_measured_frame(&measured, 1024, &payload),
        Err(FrameError::Corrupt)
    );
}

#[test]
fn outstanding_tracker_enforces_bound_fifo_and_conservation() {
    let now = Instant::now();
    let mut tracker = OutstandingTracker::new(2).unwrap();
    tracker.issue(10, now).unwrap();
    tracker.issue(11, now).unwrap();
    assert!(tracker.issue(12, now).is_err());
    assert_eq!(tracker.complete(10).unwrap(), now);
    tracker.issue(12, now).unwrap();
    assert!(tracker.complete(12).is_err());
    assert_eq!(tracker.complete(11).unwrap(), now);
    assert_eq!(tracker.complete(12).unwrap(), now);
    assert_eq!(tracker.sent(), 3);
    assert_eq!(tracker.completed(), 3);
    assert_eq!(tracker.in_flight(), 0);
    assert_eq!(tracker.max_in_flight(), 2);
}

#[test]
fn runtime_workers_default_to_one_and_accept_only_scaling_cells() {
    assert_eq!(parse_runtime_workers(["bench"]), Ok(1));
    assert_eq!(
        parse_runtime_workers(["bench", "--p2a-runtime-workers", "2"]),
        Ok(2)
    );
    assert_eq!(
        parse_runtime_workers(["bench", "--p2a-runtime-workers", "4"]),
        Ok(4)
    );
    assert!(parse_runtime_workers(["bench", "--p2a-runtime-workers", "3"]).is_err());
}

#[test]
fn server_scale_runtime_workers_build_and_complete_tasks() {
    use nbsr_transport::p2a_benchmark::build_benchmark_runtime;
    for workers in [8, 16, 32] {
        let count = workers.to_string();
        assert_eq!(
            parse_runtime_workers(["bench", "--p2a-runtime-workers", count.as_str()]),
            Ok(workers)
        );
        let runtime = build_benchmark_runtime(workers).expect("server-scale runtime");
        assert_eq!(runtime.metrics().num_workers(), workers);
        let completed = runtime.block_on(async {
            let tasks: Vec<_> = (0..64)
                .map(|value| tokio::spawn(async move { value }))
                .collect();
            let mut sum = 0;
            for task in tasks {
                sum += task.await.expect("benchmark task joined");
            }
            sum
        });
        assert_eq!(completed, (0..64).sum::<usize>());
    }
    for value in ["0", "3", "6", "64"] {
        assert!(parse_runtime_workers(["bench", "--p2a-runtime-workers", value]).is_err());
    }
}

#[test]
fn group_count_defaults_to_one_and_accepts_only_scaling_cells() {
    assert_eq!(parse_group_count(["bench"]), Ok(1));
    for (value, expected) in [("1", 1), ("2", 2), ("4", 4)] {
        assert_eq!(
            parse_group_count(["bench", "--p2a-groups", value]),
            Ok(expected)
        );
    }
    assert!(parse_group_count(["bench", "--p2a-groups", "3"]).is_err());
}

#[test]
fn group_endpoints_require_one_nonempty_endpoint_per_group() {
    assert_eq!(parse_group_endpoints(["bench"], 2), Ok(None));
    assert_eq!(
        parse_group_endpoints(
            [
                "bench",
                "--p2a-endpoints",
                "127.0.0.1:41001,127.0.0.1:41002"
            ],
            2,
        ),
        Ok(Some(vec![
            "127.0.0.1:41001".to_owned(),
            "127.0.0.1:41002".to_owned(),
        ]))
    );
    assert!(parse_group_endpoints(["bench", "--p2a-endpoints", "127.0.0.1:41001"], 2).is_err());
    assert!(parse_group_endpoints(["bench", "--p2a-endpoints", ","], 2).is_err());
    assert!(
        parse_group_endpoints(
            [
                "bench",
                "--p2a-endpoints",
                "127.0.0.1:41001,,127.0.0.1:41002"
            ],
            2,
        )
        .is_err()
    );
}

#[test]
fn groups_use_distinct_os_threads_and_current_thread_runtimes() {
    let records = run_current_thread_groups(4, |ordinal, barrier| async move {
        barrier.wait();
        (
            ordinal,
            std::thread::current().id(),
            tokio::runtime::Handle::current().runtime_flavor(),
        )
    })
    .unwrap();

    assert_eq!(
        records.iter().map(|record| record.0).collect::<Vec<_>>(),
        [0, 1, 2, 3]
    );
    let unique_threads = records
        .iter()
        .map(|record| record.1)
        .collect::<std::collections::HashSet<_>>();
    assert_eq!(unique_threads.len(), 4);
    assert!(
        records
            .iter()
            .all(|record| record.2 == tokio::runtime::RuntimeFlavor::CurrentThread)
    );
}
