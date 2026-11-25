//! Bounded synthetic sessions on one retained Gateway and UDP endpoint.
//! Fixture bytes go only to a private supervisor pipe, never Docker logs.
use super::*;
use std::io::{BufRead, BufReader};

pub async fn run() {
    let first_stop =
        std::env::var("NBSR_CONNECTOR_DOCKER_FIRST_STOP").unwrap_or_else(|_| "term".into());
    assert!(["term", "kill", "network", "auto-network"].contains(&first_stop.as_str()));
    let automatic = first_stop == "auto-network";
    let cycles: u64 = std::env::var("NBSR_CONNECTOR_DOCKER_CYCLES")
        .unwrap_or_else(|_| "1".into())
        .parse()
        .expect("integer cycle count");
    assert!((1..=5).contains(&cycles) && (automatic || cycles == 1));
    let fail_cleanup =
        std::env::var("NBSR_CONNECTOR_DOCKER_FAIL_CLEANUP").unwrap_or_default() == "1";
    assert!(!fail_cleanup || (automatic && cycles == 1));
    let sessions = if automatic { cycles + 1 } else { 2 };
    let address: std::net::SocketAddrV4 = std::env::var("NBSR_CONNECTOR_DOCKER_GATEWAY")
        .expect("explicit Docker endpoint")
        .parse()
        .expect("literal IPv4 endpoint");
    assert!(address.ip().is_private() && address.port() != 0);
    let p = pki();
    let ep = endpoint_at(&p, address.into());
    let vector = std::fs::read(
        std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../vectors/connector-registration-development-v1/request.cbor"),
    )
    .unwrap();
    let mut envelope = map(&codec::decode(codec::ALPN, &vector).unwrap())
        .unwrap()
        .clone();
    let mut body = map(get(&envelope, 5).unwrap()).unwrap().clone();
    let peer: [u8; 32] = Sha256::digest(&p.client_public).into();
    body.insert(8, V::Bytes(peer.to_vec()));
    body.insert(14, V::Uint(100));
    let policy = V::Map(body);
    envelope.insert(5, policy.clone());
    let mut gateway = Gateway::new(policy.clone(), [42; 16], 0).unwrap();
    let mut input = BufReader::new(std::io::stdin());
    let mut prior_registration = None;
    for attempt in 1..=sessions {
        let session = [b's' + attempt as u8; 16];
        envelope.insert(3, V::Bytes(session.to_vec()));
        let mut rid = session[..8].to_vec();
        rid.extend(1u64.to_be_bytes());
        envelope.insert(2, V::Bytes(rid));
        envelope.insert(4, V::Uint(1));
        // stdout is attached with Docker logging disabled. The supervisor must
        // intercept this one line and forward it in memory to Connector stdin.
        let mut fixture = serde_json::json!({"Endpoint":address.to_string(),"Case":"docker_hold",
            "CA":p.ca.as_ref(),"Cert":p.client.as_ref(),"Key":p.client_key,
            "ServerKey":p.server_public,"Request":codec::encode(&V::Map(envelope.clone()))});
        if automatic && attempt > 1 {
            // Parent-only fixture receipt: produced only after the previous
            // exact cleanup ticket was applied, never a wire authority claim.
            fixture["PreviousCleanupSession"] =
                serde_json::json!(vec![b's' + (attempt - 1) as u8; 16]);
        }
        println!("NBSR_PRIVATE_FIXTURE {fixture}");
        std::io::stdout().flush().unwrap();
        let incoming = timeout(Duration::from_secs(15), ep.accept())
            .await
            .unwrap()
            .unwrap();
        let conn = timeout(LIMIT, incoming).await.unwrap().expect("mutual TLS");
        let certs = conn
            .peer_identity()
            .unwrap()
            .downcast::<Vec<CertificateDer<'static>>>()
            .unwrap();
        assert_eq!(certs[0], p.client);
        let handshake = conn
            .handshake_data()
            .unwrap()
            .downcast::<quinn::crypto::rustls::HandshakeData>()
            .unwrap();
        assert_eq!(handshake.protocol.as_deref(), Some(codec::ALPN.as_bytes()));
        gateway.attach(attempt, session, peer, 100).unwrap();
        let mut authority = SyntheticAuthority {
            connection: attempt,
            session,
            template: policy.clone(),
            peer,
            revision: 1,
            stale: false,
            calls: 0,
        };
        let mut transport = LiveTransport(conn.clone());
        let (mut send, mut recv) = timeout(LIMIT, conn.accept_bi()).await.unwrap().unwrap();
        assert_eq!(u64::from(send.id()), 0);
        for _ in 0..2 {
            let raw = timeout(LIMIT, read_frame(&mut recv))
                .await
                .unwrap()
                .unwrap();
            let response = gateway
                .handle(attempt, &raw, 100, Some(&mut authority), &mut transport)
                .unwrap()
                .unwrap();
            send_frame(&mut send, &response).await;
        }
        let owner = gateway.owner.as_ref().unwrap();
        assert!(owner.eligible);
        assert_eq!(owner.generation, attempt);
        assert_ne!(Some(owner.registration), prior_registration);
        prior_registration = Some(owner.registration);
        println!(
            "NBSR_GATEWAY_ACCEPTED attempt={attempt} generation={attempt} synthetic_authority=true"
        );
        // A remote close alone is not enough to declare the remote process reaped.
        let close_reason = timeout(Duration::from_secs(15), conn.closed())
            .await
            .expect("Connector close deadline");
        let killed = attempt == 1 && first_stop == "kill";
        let network_lost =
            (attempt == 1 && first_stop == "network") || (automatic && attempt < sessions);
        if killed || network_lost {
            assert!(matches!(close_reason, quinn::ConnectionError::TimedOut));
        }
        println!("NBSR_TRANSPORT_CLOSED attempt={attempt} reason={close_reason:?}");
        let mut ticket = gateway.begin_cleanup(attempt).unwrap();
        assert!(gateway.finish_cleanup(&ticket).is_err());
        assert!(!gateway.owner.as_ref().unwrap().eligible);
        println!("NBSR_OWNER_RETAINED attempt={attempt} owner_count=1 eligible=false");
        recv.stop(VarInt::from_u32(0)).ok();
        send.reset(VarInt::from_u32(0)).ok();
        drop((recv, send, transport, conn));
        timeout(LIMIT, ep.wait_idle())
            .await
            .expect("Gateway connection drained");
        // Graceful: host confirms exit=0 and Go socket/owner cleanup marker.
        // Killed: host confirms SIGKILL, exit=137, PID=0, no graceful marker and
        // Docker network endpoint removal. No Go cleanup callback is invented.
        // This is explicit test orchestration evidence, not authenticated authority.
        let mut confirmation = String::new();
        input.read_line(&mut confirmation).unwrap();
        if network_lost {
            assert_eq!(confirmation.trim(), format!("CHECK_RETAINED {attempt}"));
            assert!(gateway.finish_cleanup(&ticket).is_err());
            let retained = gateway.owner.clone().unwrap();
            assert!(!retained.eligible && retained.generation == attempt);
            // Observe restoration with the original Connector still running.
            // Bounded absence is not a claim about all future reconnect behavior.
            assert!(timeout(Duration::from_secs(2), ep.accept()).await.is_err());
            assert_eq!(gateway.owner.as_ref(), Some(&retained));
            assert!(gateway.finish_cleanup(&ticket).is_err());
            println!(
                "NBSR_NETWORK_RESTORED_NO_RECONNECT attempt={attempt} window_ms=2000 owner_count=1 eligible=false"
            );
            std::io::stdout().flush().unwrap();
            confirmation.clear();
            input.read_line(&mut confirmation).unwrap();
        }
        if fail_cleanup && attempt == 1 {
            assert_eq!(confirmation.trim(), format!("FAIL_CLEANUP {attempt}"));
            let retained = gateway.owner.clone().unwrap();
            ticket.complete(Err("injected cleanup failure"));
            assert_eq!(
                gateway.finish_cleanup(&ticket),
                Err("injected cleanup failure")
            );
            // A later success cannot overwrite the first failed callback.
            ticket.complete(Ok(()));
            assert_eq!(
                gateway.finish_cleanup(&ticket),
                Err("injected cleanup failure")
            );
            assert!(timeout(Duration::from_secs(2), ep.accept()).await.is_err());
            assert_eq!(gateway.owner.as_ref(), Some(&retained));
            println!(
                "NBSR_CLEANUP_FAILED_BLOCKED attempt={attempt} owner_count=1 eligible=false window_ms=2000"
            );
            std::io::stdout().flush().unwrap();
            confirmation.clear();
            input.read_line(&mut confirmation).unwrap();
            assert_eq!(confirmation.trim(), format!("RETRY_CLEANUP {attempt}"));
            let old_ticket = ticket;
            ticket = gateway.retry_cleanup(&old_ticket).unwrap();
            old_ticket.complete(Ok(()));
            assert_eq!(
                gateway.finish_cleanup(&old_ticket),
                Err("stale cleanup owner/attempt")
            );
            assert_eq!(gateway.finish_cleanup(&ticket), Err("cleanup pending"));
            assert!(timeout(Duration::from_secs(2), ep.accept()).await.is_err());
            assert_eq!(gateway.owner.as_ref(), Some(&retained));
            assert_eq!(gateway.finish_cleanup(&ticket), Err("cleanup pending"));
            println!(
                "NBSR_CLEANUP_RETRY_BLOCKED attempt={attempt} owner_count=1 eligible=false stale_ticket_rejected=true window_ms=2000"
            );
            std::io::stdout().flush().unwrap();
            confirmation.clear();
            input.read_line(&mut confirmation).unwrap();
        }
        let expected = if automatic && attempt < sessions {
            "CONFIRM_RECONNECT_CLEANUP"
        } else if killed {
            "CONFIRM_KILL"
        } else {
            "CONFIRM_STOP"
        };
        assert_eq!(confirmation.trim(), format!("{expected} {attempt}"));
        ticket.complete(Ok(()));
        gateway.finish_cleanup(&ticket).unwrap();
        assert!(gateway.owner.is_none());
        println!("NBSR_OWNER_RELEASED attempt={attempt} owner_count=0");
        std::io::stdout().flush().unwrap();
    }
    ep.close(VarInt::from_u32(0), b"");
    timeout(LIMIT, ep.wait_idle()).await.unwrap();
    drop(ep);
    // Quinn's endpoint driver releases the socket asynchronously after Drop.
    // Match the existing loopback harness: require an actual successful rebind.
    timeout(LIMIT, async {
        loop {
            match std::net::UdpSocket::bind(address) {
                Ok(probe) => {
                    drop(probe);
                    break;
                }
                Err(_) => tokio::time::sleep(Duration::from_millis(10)).await,
            }
        }
    })
    .await
    .expect("Gateway UDP released");
    println!("NBSR_DOCKER_COMPLETE sessions={sessions} owner_count=0 gateway_socket_released=true");
}
