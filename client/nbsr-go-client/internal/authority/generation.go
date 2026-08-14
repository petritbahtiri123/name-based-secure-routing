package authority

// CaptureGeneration takes a local, freshness-checked barrier snapshot. It
// performs no provider or verifier work.
func (m *Manager) CaptureGeneration() (GenerationSnapshot, error) {
	if m == nil {
		return GenerationSnapshot{}, ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	m.mu.Lock()
	events, err := m.requireFreshLocked(now)
	snapshot := GenerationSnapshot{generation: m.generation}
	m.mu.Unlock()
	m.notify(events)
	if err != nil {
		return GenerationSnapshot{}, err
	}
	return snapshot, nil
}

// ValidateStillCurrent is the final local barrier before work that relies on
// authority. A newer checkpoint invalidates every earlier snapshot.
func (m *Manager) ValidateStillCurrent(snapshot GenerationSnapshot) error {
	if m == nil {
		return ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	m.mu.Lock()
	events, err := m.requireFreshLocked(now)
	if err == nil && (snapshot.generation == 0 || snapshot.generation != m.generation) {
		err = ErrStaleGeneration
	}
	m.mu.Unlock()
	m.notify(events)
	return err
}
