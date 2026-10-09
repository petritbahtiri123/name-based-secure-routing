use nbsr_transport::{AuthenticatedConnection, TransportError};

pub async fn finish(
    connection: AuthenticatedConnection,
    hold_for_release: bool,
) -> Result<(), TransportError> {
    if hold_for_release {
        #[cfg(feature = "benchmark-harness")]
        {
            // Receiving the echo does not prove the destination received its ACK.
            // Retain the endpoint and its worker runtime until destination close.
            let completed = connection.benchmark_wait_for_peer_close().await;
            let drained = connection.close().await;
            completed.and(drained)
        }
        #[cfg(not(feature = "benchmark-harness"))]
        {
            drop(connection);
            Ok(())
        }
    } else {
        connection.close().await
    }
}
