//! Independently bounded application streams for active Service Channels.

use std::collections::{HashMap, HashSet};

use crate::stream_gate::StreamGate;
use crate::{ActiveChannel, CoreV02Envelope, StreamReject};

const MAX_STREAMS_PER_CHANNEL: usize = 64;
const MAX_BUFFERED_PER_STREAM: usize = 1_048_576;
const MAX_BUFFERED_PER_CHANNEL: usize = 8_388_608;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ReplayHistoryLimit(u32);

impl ReplayHistoryLimit {
    pub const MAX: Self = Self(u32::MAX);

    #[must_use]
    pub const fn get(self) -> usize {
        self.0 as usize
    }
}

impl TryFrom<usize> for ReplayHistoryLimit {
    type Error = ReplayHistoryLimitError;

    fn try_from(value: usize) -> Result<Self, Self::Error> {
        let value = u32::try_from(value).map_err(|_| ReplayHistoryLimitError)?;
        if value == 0 {
            return Err(ReplayHistoryLimitError);
        }
        Ok(Self(value))
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct ReplayHistoryLimitError;

pub(crate) struct ChannelStreams {
    channels: HashMap<[u8; 16], ChannelStreamState>,
    used_stream_ids: HashSet<u64>,
    replay_history_limit: ReplayHistoryLimit,
}

struct ChannelStreamState {
    buffered: usize,
    streams: HashMap<u64, StreamEntry>,
}

struct StreamEntry {
    buffered: usize,
    credited: bool,
    gate: StreamGate,
}

pub(crate) struct PreparedStreamOpen {
    channel_id: [u8; 16],
    stream_id: u64,
    credited: bool,
    gate: StreamGate,
}

pub(crate) struct PreparedStreamTransition {
    channel_id: [u8; 16],
    stream_id: u64,
    gate: StreamGate,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum CreditedStreamReject {
    InvalidStream,
    DuplicateStream,
    OverCapacity,
    ReplayCapacity,
}

impl ChannelStreams {
    pub(crate) fn new(replay_history_limit: ReplayHistoryLimit) -> Self {
        Self {
            channels: HashMap::new(),
            used_stream_ids: HashSet::new(),
            replay_history_limit,
        }
    }

    pub(crate) fn replay_entries(&self) -> usize {
        self.used_stream_ids.len()
    }

    pub(crate) fn replay_limit(&self) -> usize {
        self.replay_history_limit.get()
    }

    pub(crate) fn prepare_open(
        &self,
        channel: &ActiveChannel,
        envelope: &CoreV02Envelope,
    ) -> Result<PreparedStreamOpen, StreamReject> {
        let request = envelope
            .stream_open_request()
            .map_err(|_| StreamReject::ControlRejected)?;
        if self.used_stream_ids.contains(&request.quic_stream_id) {
            return Err(StreamReject::DuplicateStream);
        }
        if self
            .channels
            .get(&channel.channel_id)
            .map_or(0, |state| state.streams.len())
            >= MAX_STREAMS_PER_CHANNEL
        {
            return Err(StreamReject::OverCapacity);
        }
        let mut gate = StreamGate::new(channel.clone());
        gate.authorize_open(envelope)?;
        if self.used_stream_ids.len() >= self.replay_history_limit.get() {
            return Err(StreamReject::OverCapacity);
        }
        Ok(PreparedStreamOpen {
            channel_id: channel.channel_id,
            stream_id: request.quic_stream_id,
            credited: false,
            gate,
        })
    }

    pub(crate) fn prepare_credited(
        &self,
        channel: &ActiveChannel,
        stream_id: u64,
    ) -> Result<PreparedStreamOpen, CreditedStreamReject> {
        if stream_id < 4 || !stream_id.is_multiple_of(4) || stream_id > 4_611_686_018_427_387_903 {
            return Err(CreditedStreamReject::InvalidStream);
        }
        if self.used_stream_ids.contains(&stream_id) {
            return Err(CreditedStreamReject::DuplicateStream);
        }
        if self
            .channels
            .get(&channel.channel_id)
            .map_or(0, |state| state.streams.len())
            >= MAX_STREAMS_PER_CHANNEL
        {
            return Err(CreditedStreamReject::OverCapacity);
        }
        if self.used_stream_ids.len() >= self.replay_history_limit.get() {
            return Err(CreditedStreamReject::ReplayCapacity);
        }
        Ok(PreparedStreamOpen {
            channel_id: channel.channel_id,
            stream_id,
            credited: true,
            gate: StreamGate::new(channel.clone()),
        })
    }

    pub(crate) fn commit_open(&mut self, prepared: PreparedStreamOpen) {
        self.used_stream_ids.insert(prepared.stream_id);
        self.channels
            .entry(prepared.channel_id)
            .or_insert_with(|| ChannelStreamState {
                buffered: 0,
                streams: HashMap::new(),
            })
            .streams
            .insert(
                prepared.stream_id,
                StreamEntry {
                    buffered: 0,
                    credited: prepared.credited,
                    gate: prepared.gate,
                },
            );
        crate::diagnostics::global()
            .created(crate::diagnostics::DiagnosticOwner::ApplicationStream);
        self.observe_diagnostics();
    }

    pub(crate) fn prepare_accept(
        &self,
        channel_id: &[u8; 16],
        envelope: &CoreV02Envelope,
    ) -> Result<PreparedStreamTransition, StreamReject> {
        let (stream_id, _, _) = envelope
            .stream_accept_binding()
            .map_err(|_| StreamReject::ControlRejected)?;
        let mut gate = self.entry(channel_id, stream_id)?.gate.clone();
        gate.accept(envelope)?;
        Ok(PreparedStreamTransition {
            channel_id: *channel_id,
            stream_id,
            gate,
        })
    }

    pub(crate) fn prepare_application_stream(
        &self,
        channel_id: &[u8; 16],
        stream_id: u64,
    ) -> Result<PreparedStreamTransition, StreamReject> {
        let mut gate = self.entry(channel_id, stream_id)?.gate.clone();
        gate.authorize_application_stream(stream_id)?;
        Ok(PreparedStreamTransition {
            channel_id: *channel_id,
            stream_id,
            gate,
        })
    }

    pub(crate) fn commit_transition(&mut self, prepared: PreparedStreamTransition) {
        if let Some(entry) = self
            .channels
            .get_mut(&prepared.channel_id)
            .and_then(|channel| channel.streams.get_mut(&prepared.stream_id))
        {
            entry.gate = prepared.gate;
        }
    }

    pub(crate) fn validate_application_stream(
        &self,
        channel_id: &[u8; 16],
        stream_id: u64,
    ) -> Result<(), StreamReject> {
        let entry = self.entry(channel_id, stream_id)?;
        if entry.credited || entry.gate.is_accepted() || entry.gate.is_opened() {
            Ok(())
        } else {
            Err(StreamReject::ControlRejected)
        }
    }

    pub(crate) fn revoke_channel(&mut self, channel_id: &[u8; 16]) {
        if let Some(channel) = self.channels.remove(channel_id) {
            for _ in 0..channel.streams.len() {
                crate::diagnostics::global()
                    .failed(crate::diagnostics::DiagnosticOwner::ApplicationStream);
            }
        }
        self.observe_diagnostics();
    }

    pub(crate) fn revoke_all(&mut self) {
        let live = self
            .channels
            .values()
            .map(|channel| channel.streams.len())
            .sum::<usize>();
        self.channels.clear();
        for _ in 0..live {
            crate::diagnostics::global()
                .failed(crate::diagnostics::DiagnosticOwner::ApplicationStream);
        }
        self.observe_diagnostics();
    }

    pub(crate) fn reserve_bytes(
        &mut self,
        channel_id: &[u8; 16],
        stream_id: u64,
        bytes: usize,
    ) -> Result<(), StreamReject> {
        let channel = self
            .channels
            .get_mut(channel_id)
            .ok_or(StreamReject::ControlRejected)?;
        let entry = channel
            .streams
            .get_mut(&stream_id)
            .ok_or(StreamReject::ControlRejected)?;
        if !entry.credited && !entry.gate.is_opened() {
            return Err(StreamReject::ControlRejected);
        }
        let stream_buffered = entry
            .buffered
            .checked_add(bytes)
            .ok_or(StreamReject::OverCapacity)?;
        let channel_buffered = channel
            .buffered
            .checked_add(bytes)
            .ok_or(StreamReject::OverCapacity)?;
        if stream_buffered > MAX_BUFFERED_PER_STREAM || channel_buffered > MAX_BUFFERED_PER_CHANNEL
        {
            return Err(StreamReject::OverCapacity);
        }
        entry.buffered = stream_buffered;
        channel.buffered = channel_buffered;
        Ok(())
    }

    pub(crate) fn release_bytes(
        &mut self,
        channel_id: &[u8; 16],
        stream_id: u64,
        bytes: usize,
    ) -> Result<(), StreamReject> {
        let channel = self
            .channels
            .get_mut(channel_id)
            .ok_or(StreamReject::ControlRejected)?;
        let entry = channel
            .streams
            .get_mut(&stream_id)
            .ok_or(StreamReject::ControlRejected)?;
        let stream_buffered = entry
            .buffered
            .checked_sub(bytes)
            .ok_or(StreamReject::ControlRejected)?;
        let channel_buffered = channel
            .buffered
            .checked_sub(bytes)
            .ok_or(StreamReject::ControlRejected)?;
        entry.buffered = stream_buffered;
        channel.buffered = channel_buffered;
        Ok(())
    }

    pub(crate) fn release_stream(
        &mut self,
        channel_id: &[u8; 16],
        stream_id: u64,
    ) -> Result<(), StreamReject> {
        let channel = self
            .channels
            .get_mut(channel_id)
            .ok_or(StreamReject::ControlRejected)?;
        let entry = channel
            .streams
            .remove(&stream_id)
            .ok_or(StreamReject::ControlRejected)?;
        channel.buffered = channel
            .buffered
            .checked_sub(entry.buffered)
            .ok_or(StreamReject::ControlRejected)?;
        crate::diagnostics::global()
            .completed(crate::diagnostics::DiagnosticOwner::ApplicationStream);
        self.observe_diagnostics();
        Ok(())
    }

    fn observe_diagnostics(&self) {
        let entries = self
            .channels
            .values()
            .map(|channel| channel.streams.len())
            .sum::<usize>();
        let capacity = self.channels.capacity()
            + self
                .channels
                .values()
                .map(|channel| channel.streams.capacity())
                .sum::<usize>();
        crate::diagnostics::global().observe_collection(
            crate::diagnostics::DiagnosticOwner::StreamRegistry,
            entries,
            capacity,
        );
        crate::diagnostics::global().observe_collection(
            crate::diagnostics::DiagnosticOwner::ReplayState,
            self.used_stream_ids.len(),
            self.used_stream_ids.capacity(),
        );
    }

    fn entry(&self, channel_id: &[u8; 16], stream_id: u64) -> Result<&StreamEntry, StreamReject> {
        self.channels
            .get(channel_id)
            .and_then(|channel| channel.streams.get(&stream_id))
            .ok_or(StreamReject::ControlRejected)
    }
}

impl Drop for ChannelStreams {
    fn drop(&mut self) {
        let live = self
            .channels
            .values()
            .map(|channel| channel.streams.len())
            .sum::<usize>();
        for _ in 0..live {
            crate::diagnostics::global()
                .failed(crate::diagnostics::DiagnosticOwner::ApplicationStream);
        }
        crate::diagnostics::global().observe_collection(
            crate::diagnostics::DiagnosticOwner::StreamRegistry,
            0,
            0,
        );
        crate::diagnostics::global().observe_collection(
            crate::diagnostics::DiagnosticOwner::ReplayState,
            0,
            0,
        );
    }
}

#[cfg(test)]
mod tests {
    use std::time::{Duration, Instant};

    use super::{ChannelStreams, CreditedStreamReject, ReplayHistoryLimit};
    use crate::{
        ActiveChannel, CoreV02Envelope, CoreV02Limits, StreamReject, decode_control_envelope,
    };

    const SESSION_ID: [u8; 16] = [0x10; 16];

    fn channel(id: u8) -> ActiveChannel {
        ActiveChannel {
            channel_id: [id; 16],
            route_id: [id.wrapping_add(0x40); 16],
            service_id: format!("service-{id}"),
            route_grant_digest: [id.wrapping_add(0x80); 32],
            transport: "tcp".into(),
            port: 8443,
        }
    }

    fn open(channel: &ActiveChannel, stream_id: u64) -> CoreV02Envelope {
        let mut body = Vec::new();
        map(&mut body, 7);
        field_uint(&mut body, 0, 1);
        field_uint(&mut body, 1, stream_id);
        field_bytes(&mut body, 2, &channel.channel_id);
        field_bytes(&mut body, 3, &channel.route_id);
        field_bytes(&mut body, 4, &channel.route_grant_digest);
        field_text(&mut body, 5, &channel.transport);
        field_uint(&mut body, 6, u64::from(channel.port));
        envelope(6, [stream_id as u8; 16], 5, body)
    }

    fn accept(channel: &ActiveChannel, stream_id: u64) -> CoreV02Envelope {
        let mut body = Vec::new();
        map(&mut body, 5);
        field_uint(&mut body, 0, 1);
        field_uint(&mut body, 1, stream_id);
        field_bytes(&mut body, 2, &channel.channel_id);
        field_bytes(&mut body, 3, &channel.route_id);
        field_uint(&mut body, 4, 1_893_456_000);
        envelope(7, [stream_id as u8; 16], 6, body)
    }

    fn authorize(streams: &mut ChannelStreams, channel: &ActiveChannel, stream_id: u64) {
        let prepared = streams
            .prepare_open(channel, &open(channel, stream_id))
            .expect("open authorized");
        streams.commit_open(prepared);
        let prepared = streams
            .prepare_accept(&channel.channel_id, &accept(channel, stream_id))
            .expect("accept confirmed");
        streams.commit_transition(prepared);
        let prepared = streams
            .prepare_application_stream(&channel.channel_id, stream_id)
            .expect("actual stream confirmed");
        streams.commit_transition(prepared);
    }

    fn authorize_open(
        streams: &mut ChannelStreams,
        channel: &ActiveChannel,
        stream_id: u64,
    ) -> Result<(), StreamReject> {
        let prepared = streams.prepare_open(channel, &open(channel, stream_id))?;
        streams.commit_open(prepared);
        Ok(())
    }

    fn bounded(limit: usize) -> ChannelStreams {
        ChannelStreams::new(ReplayHistoryLimit::try_from(limit).expect("valid test limit"))
    }

    #[test]
    fn replay_history_limit_rejects_zero_and_values_above_the_operational_bound() {
        assert!(ReplayHistoryLimit::try_from(0).is_err());
        assert!(ReplayHistoryLimit::try_from(usize::MAX).is_err());
    }

    #[test]
    fn exact_replay_history_boundary_is_fail_closed_without_mutation() {
        let active = channel(1);
        let mut streams = bounded(2);
        authorize_open(&mut streams, &active, 4).expect("N-1 succeeds");
        authorize_open(&mut streams, &active, 8).expect("Nth succeeds");
        assert_eq!(streams.used_stream_ids.len(), 2);
        assert_eq!(
            streams.prepare_open(&active, &open(&active, 12)).err(),
            Some(StreamReject::OverCapacity)
        );
        assert_eq!(streams.used_stream_ids.len(), 2);
    }

    #[test]
    fn full_history_preserves_duplicate_and_authorization_precedence() {
        let active = channel(1);
        let mut streams = bounded(1);
        authorize_open(&mut streams, &active, 4).expect("exact limit succeeds");
        assert_eq!(
            streams.prepare_open(&active, &open(&active, 4)).err(),
            Some(StreamReject::DuplicateStream)
        );
        let wrong_channel = channel(2);
        assert_eq!(
            streams
                .prepare_open(&active, &open(&wrong_channel, 8))
                .err(),
            Some(StreamReject::ChannelMismatch)
        );
        assert_eq!(streams.used_stream_ids.len(), 1);
    }

    #[test]
    fn rejected_and_uncommitted_opens_do_not_consume_shared_session_capacity() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = bounded(2);
        let prepared = streams
            .prepare_open(&first, &open(&first, 4))
            .expect("prepared but not committed");
        assert_eq!(streams.used_stream_ids.len(), 0);
        drop(prepared);
        authorize_open(&mut streams, &first, 4).expect("retry remains valid");
        authorize_open(&mut streams, &sibling, 8).expect("sibling shares remaining budget");
        streams.revoke_channel(&first.channel_id);
        assert_eq!(
            streams.prepare_open(&first, &open(&first, 12)).err(),
            Some(StreamReject::OverCapacity)
        );
        assert_eq!(streams.used_stream_ids.len(), 2);
    }

    #[test]
    fn credited_prepare_is_atomic_with_replay_capacity_and_creates_an_open_gate() {
        let active = channel(1);
        let mut streams = bounded(1);
        assert_eq!(
            streams.prepare_credited(&active, 0).err(),
            Some(CreditedStreamReject::InvalidStream)
        );
        let prepared = streams
            .prepare_credited(&active, 4)
            .expect("credited stream prepares");
        assert_eq!(streams.used_stream_ids.len(), 0);
        assert!(streams.channels.is_empty());
        streams.commit_open(prepared);
        assert_eq!(streams.used_stream_ids.len(), 1);
        streams
            .validate_application_stream(&active.channel_id, 4)
            .expect("credited gate is ordinary and opened");
        assert_eq!(
            streams.prepare_credited(&active, 4).err(),
            Some(CreditedStreamReject::DuplicateStream)
        );
        assert_eq!(
            streams.prepare_credited(&active, 8).err(),
            Some(CreditedStreamReject::ReplayCapacity)
        );
        assert_eq!(streams.used_stream_ids.len(), 1);
    }

    #[test]
    fn credited_capacity_and_sibling_isolation_match_legacy_streams() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        for stream_id in (4..=256).step_by(4) {
            let prepared = streams.prepare_credited(&first, stream_id).unwrap();
            streams.commit_open(prepared);
        }
        assert_eq!(
            streams.prepare_credited(&first, 260).err(),
            Some(CreditedStreamReject::OverCapacity)
        );
        let sibling_prepared = streams.prepare_credited(&sibling, 264).unwrap();
        streams.commit_open(sibling_prepared);
        streams.revoke_channel(&first.channel_id);
        streams
            .validate_application_stream(&sibling.channel_id, 264)
            .expect("sibling survives cleanup");
        assert_eq!(streams.used_stream_ids.len(), 65);
    }

    #[test]
    fn adversarial_unique_attempts_never_grow_history_past_ten_thousand() {
        let active = channel(1);
        let mut streams = bounded(10_000);
        for ordinal in 1..=10_000_u64 {
            let stream_id = ordinal * 4;
            let prepared = streams
                .prepare_open(&active, &open(&active, stream_id))
                .expect("within limit");
            streams.commit_open(prepared);
            streams
                .release_stream(&active.channel_id, stream_id)
                .expect("release active slot without erasing replay");
        }
        for ordinal in 10_001..=25_000_u64 {
            let stream_id = ordinal * 4;
            assert_eq!(
                streams
                    .prepare_open(&active, &open(&active, stream_id))
                    .err(),
                Some(StreamReject::OverCapacity)
            );
        }
        assert_eq!(streams.used_stream_ids.len(), 10_000);
        assert_eq!(
            streams.prepare_open(&active, &open(&active, 4)).err(),
            Some(StreamReject::DuplicateStream)
        );
    }

    #[test]
    #[ignore = "P1F evidence-only ten-minute bounded-memory soak"]
    fn adversarial_soak_holds_replay_history_at_ten_thousand() {
        let active = channel(1);
        let mut streams = bounded(10_000);
        for ordinal in 1..=10_000_u64 {
            let stream_id = ordinal * 4;
            let prepared = streams
                .prepare_open(&active, &open(&active, stream_id))
                .expect("within limit");
            streams.commit_open(prepared);
            streams
                .release_stream(&active.channel_id, stream_id)
                .expect("release active slot");
        }
        let started = Instant::now();
        let duration = Duration::from_secs(
            std::env::var("NBSR_P1F_SOAK_SECONDS")
                .ok()
                .and_then(|value| value.parse().ok())
                .unwrap_or(600),
        );
        let mut attempts = 0_u64;
        let mut next_report = Duration::ZERO;
        while started.elapsed() < duration {
            attempts += 1;
            let stream_id = 40_000_u64.saturating_add(attempts.saturating_mul(4));
            assert_eq!(
                streams
                    .prepare_open(&active, &open(&active, stream_id))
                    .err(),
                Some(StreamReject::OverCapacity)
            );
            if started.elapsed() >= next_report {
                eprintln!(
                    "P1F_SOAK elapsed_ms={} attempts={} entries={} capacity={}",
                    started.elapsed().as_millis(),
                    attempts,
                    streams.used_stream_ids.len(),
                    streams.used_stream_ids.capacity()
                );
                next_report += Duration::from_secs(1);
            }
        }
        assert_eq!(streams.used_stream_ids.len(), 10_000);
        assert_eq!(
            streams.prepare_open(&active, &open(&active, 4)).err(),
            Some(StreamReject::DuplicateStream)
        );
    }

    #[test]
    fn duplicate_stream_ids_fail_across_channels_and_after_release() {
        let first = channel(1);
        let second = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        authorize(&mut streams, &first, 4);
        assert_eq!(
            streams.prepare_open(&second, &open(&second, 4)).err(),
            Some(StreamReject::DuplicateStream)
        );
        streams
            .release_stream(&first.channel_id, 4)
            .expect("release first stream");
        assert_eq!(
            streams.prepare_open(&second, &open(&second, 4)).err(),
            Some(StreamReject::DuplicateStream)
        );
    }

    #[test]
    fn sixty_four_streams_are_allowed_but_the_sixty_fifth_is_scoped() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        for stream_id in (4..=256).step_by(4) {
            authorize_open(&mut streams, &first, stream_id).expect("first 64 streams");
        }
        assert_eq!(
            streams.prepare_open(&first, &open(&first, 260)).err(),
            Some(StreamReject::OverCapacity)
        );
        streams
            .release_stream(&first.channel_id, 4)
            .expect("release one active slot");
        authorize_open(&mut streams, &first, 268)
            .expect("released slot is available to a fresh stream ID");
        authorize_open(&mut streams, &sibling, 264).expect("sibling remains independent");
    }

    #[test]
    fn byte_limits_are_exact_and_failed_reservations_do_not_mutate_counts() {
        let active = channel(1);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        for stream_id in (4..=32).step_by(4) {
            authorize(&mut streams, &active, stream_id);
            streams
                .reserve_bytes(&active.channel_id, stream_id, 1_048_576)
                .expect("exact one MiB per stream");
        }
        assert_eq!(
            streams.reserve_bytes(&active.channel_id, 4, 1),
            Err(StreamReject::OverCapacity)
        );

        authorize(&mut streams, &active, 36);
        assert_eq!(
            streams.reserve_bytes(&active.channel_id, 36, 1),
            Err(StreamReject::OverCapacity)
        );
        streams
            .release_bytes(&active.channel_id, 4, 1)
            .expect("release one accounted byte");
        streams
            .reserve_bytes(&active.channel_id, 36, 1)
            .expect("failed reservation left channel count unchanged");
        assert_eq!(
            streams.reserve_bytes(&active.channel_id, 36, usize::MAX),
            Err(StreamReject::OverCapacity)
        );
        streams
            .release_bytes(&active.channel_id, 36, 1)
            .expect("overflow attempt left stream count unchanged");
    }

    #[test]
    fn releasing_a_stream_frees_all_bytes_without_mutating_a_sibling() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        authorize(&mut streams, &first, 4);
        authorize(&mut streams, &sibling, 8);
        streams
            .reserve_bytes(&first.channel_id, 4, 1_048_576)
            .expect("first reservation");
        streams
            .reserve_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling reservation");
        streams
            .release_stream(&first.channel_id, 4)
            .expect("release first stream");

        authorize(&mut streams, &first, 12);
        streams
            .reserve_bytes(&first.channel_id, 12, 1_048_576)
            .expect("released bytes are available");
        streams
            .release_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling accounting unchanged");
    }

    #[test]
    fn pre_accept_payload_failure_is_scoped_to_only_that_stream() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        authorize_open(&mut streams, &first, 4).expect("first open");
        assert_eq!(
            streams
                .prepare_application_stream(&first.channel_id, 4)
                .err(),
            Some(StreamReject::ControlRejected)
        );

        authorize(&mut streams, &sibling, 8);
        streams
            .reserve_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling remains usable");
        streams
            .release_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling accounting remains exact");
    }

    #[test]
    fn revoking_one_channel_removes_only_its_stream_and_byte_state() {
        let first = channel(1);
        let sibling = channel(2);
        let mut streams = ChannelStreams::new(ReplayHistoryLimit::MAX);
        authorize(&mut streams, &first, 4);
        authorize(&mut streams, &sibling, 8);
        streams
            .reserve_bytes(&first.channel_id, 4, 99)
            .expect("first bytes");
        streams
            .reserve_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling bytes");

        streams.revoke_channel(&first.channel_id);
        assert_eq!(
            streams.reserve_bytes(&first.channel_id, 4, 1),
            Err(StreamReject::ControlRejected)
        );
        streams
            .release_bytes(&sibling.channel_id, 8, 17)
            .expect("sibling accounting unchanged");
        streams
            .reserve_bytes(&sibling.channel_id, 8, 1_048_576)
            .expect("sibling remains independently usable");
    }

    fn envelope(
        message_type: u64,
        request_id: [u8; 16],
        sequence: u64,
        body: Vec<u8>,
    ) -> CoreV02Envelope {
        let mut wire = Vec::new();
        map(&mut wire, 6);
        field_uint(&mut wire, 0, 2);
        field_uint(&mut wire, 1, message_type);
        field_bytes(&mut wire, 2, &request_id);
        field_bytes(&mut wire, 3, &SESSION_ID);
        field_uint(&mut wire, 4, sequence);
        uint(&mut wire, 5);
        wire.extend_from_slice(&body);
        decode_control_envelope(&wire, CoreV02Limits::default()).expect("valid stream control")
    }

    fn field_uint(target: &mut Vec<u8>, key: u64, value: u64) {
        uint(target, key);
        uint(target, value);
    }

    fn field_bytes(target: &mut Vec<u8>, key: u64, value: &[u8]) {
        uint(target, key);
        bytes(target, value);
    }

    fn field_text(target: &mut Vec<u8>, key: u64, value: &str) {
        uint(target, key);
        text(target, value);
    }

    fn uint(target: &mut Vec<u8>, value: u64) {
        argument(target, 0, value);
    }

    fn bytes(target: &mut Vec<u8>, value: &[u8]) {
        argument(target, 2, value.len() as u64);
        target.extend_from_slice(value);
    }

    fn text(target: &mut Vec<u8>, value: &str) {
        argument(target, 3, value.len() as u64);
        target.extend_from_slice(value.as_bytes());
    }

    fn map(target: &mut Vec<u8>, len: u64) {
        argument(target, 5, len);
    }

    fn argument(target: &mut Vec<u8>, major: u8, value: u64) {
        let initial = major << 5;
        match value {
            0..=23 => target.push(initial | value as u8),
            24..=0xff => target.extend_from_slice(&[initial | 24, value as u8]),
            0x100..=0xffff => {
                target.push(initial | 25);
                target.extend_from_slice(&(value as u16).to_be_bytes());
            }
            0x1_0000..=0xffff_ffff => {
                target.push(initial | 26);
                target.extend_from_slice(&(value as u32).to_be_bytes());
            }
            _ => {
                target.push(initial | 27);
                target.extend_from_slice(&value.to_be_bytes());
            }
        }
    }
}
