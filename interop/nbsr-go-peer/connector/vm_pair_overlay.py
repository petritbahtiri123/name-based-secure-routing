"""Pinned, test-only two-VM overlay. Importing never writes or starts processes.
Derived from the retained SPHERE test_overlay.py; only the positive case is exposed.
"""

import hashlib
import subprocess

BASE = "38f485cf332480e919b38f26abe9901a800e7a80"
GO = "interop/nbsr-go-peer/connector/loopback_test.go"
RUST = "crates/nbsr-transport/tests/support/connector_loopback.rs"


def pinned_sources(repo):
    return tuple(
        subprocess.check_output(["git", "-c", "gc.auto=0", "-c", "maintenance.auto=false", "show", BASE + ":" + path], cwd=repo)
        .decode()
        .replace("\r\n", "\n")
        for path in (GO, RUST)
    )


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def swap(s, a, b):
    if s.count(a) != 1:
        raise ValueError("overlay source mismatch")
    return s.replace(a, b)


def overlay(gs, rs):
    gs = swap(gs, 'if host != "127.0.0.1" {', 'if host != "10.77.0.1" {')
    gs = swap(
        gs,
        "func loopDial(c loopConfig) (*loopPeer, error) {",
        'func loopDial(c loopConfig) (*loopPeer, error) {\n\tif c.Case != "positive" || os.Getenv("NBSR_CONNECTOR_DOCKER_ENDPOINT") != "" { return nil, ErrInvalid }',
    )
    gs = swap(gs, "local := net.IPv4(127, 0, 0, 1)", "local := net.IPv4(10, 77, 0, 2)")
    rs = swap(rs, 'endpoint_at(p, "127.0.0.1:0".parse().unwrap())', 'endpoint_at(p, "10.77.0.1:0".parse().unwrap())')
    start = rs.index('    let binary = std::env::var("NBSR_CONNECTOR_GO_TEST")')
    end = rs.index("    let p = pki();", start)
    rs = (
        rs[:start]
        + """    timeout(Duration::from_secs(20), run_case("positive"))
            .await.expect("cross VM deadline");
        println!("SPHERE_CONNECTOR_PASS synthetic_authority=true");
    }
    async fn run_case(case: &str) {
    """
        + rs[end:]
    )
    start = rs.index("    let mut command = Command::new(binary);")
    end = rs.index("    let incoming = timeout(LIMIT, ep.accept())", start)
    rs = (
        rs[:start]
        + """    use std::io::Write;
        println!("SPHERE_HANDOFF {}", serde_json::to_string(&input).unwrap());
        std::io::stdout().flush().unwrap();
    """
        + rs[end:]
    )
    rs = swap(
        rs,
        "    let handshake = timeout(LIMIT, incoming).await.unwrap();",
        """    assert_eq!(incoming.remote_address().ip(), "10.77.0.2".parse::<std::net::IpAddr>().unwrap());
        println!("SPHERE_PEER {} -> {}", incoming.remote_address(), port);
        let handshake = timeout(LIMIT, incoming).await.unwrap();""",
    )
    start = rs.index("    let status = timeout(LIMIT, async {")
    end = rs.index("    // Closing the endpoint", start)
    rs = (
        rs[:start]
        + """    let mut receipt = String::new();
        std::io::stdin().read_line(&mut receipt).unwrap();
        assert_eq!(receipt.trim(), "CONNECTOR_EXIT_0_SOCKET_RELEASED");
    """
        + rs[end:]
    )
    start = rs.index('    println!(\n        "loopback_reaped')
    rs = (
        rs[:start]
        + """    println!("SPHERE_GATEWAY_CLEANUP gateway_socket_released=true owner_count=0");
    }
    """
    )

    rs = swap(rs, 'std::path::Path::new(env!("CARGO_MANIFEST_DIR"))', 'std::path::Path::new("crates/nbsr-transport")')
    return gs, rs
