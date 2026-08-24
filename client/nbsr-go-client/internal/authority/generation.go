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

func (m *Manager) ValidateGeneration(generation AuthorityGeneration) error {
	return m.ValidateStillCurrent(GenerationSnapshot{generation: generation})
}

func (m *Manager) ValidateSessionBinding(generation AuthorityGeneration, sourceOperator, profile string) error {
	if m == nil || sourceOperator == "" || profile == "" {
		return ErrInvalidAuthority
	}
	now := m.clock.NowUnix()
	m.mu.Lock()
	events, err := m.requireFreshLocked(now)
	if err == nil && (generation == 0 || generation != m.generation) {
		err = ErrStaleGeneration
	}
	if err == nil && (m.checkpoint.sourceOperator() != sourceOperator || m.checkpoint.profile() != profile) {
		err = ErrBindingMismatch
	}
	m.mu.Unlock()
	m.notify(events)
	return err
}

func (m *Manager) AdmissionMaterialForGeneration(reservation Reservation, generation AuthorityGeneration, serviceIdentity string, serviceDigest ServiceDigest, proof ProofKeyThumbprint, grant RouteGrantDigest, now uint64) ([]byte, error) {
	if m == nil || serviceIdentity == "" || serviceDigest == (ServiceDigest{}) || proof == (ProofKeyThumbprint{}) || grant == (RouteGrantDigest{}) {
		return nil, ErrInvalidAuthority
	}
	m.mu.Lock()
	events, err := m.validateReservedLocked(reservation, GenerationSnapshot{generation: generation}, now)
	var material []byte
	if err == nil {
		entry := m.reserved[reservation.id]
		if entry == nil || entry.authority.seal.serviceIdentity != serviceIdentity || entry.authority.Key().ServiceDigest != serviceDigest || entry.authority.Key().ProofThumbprint != proof || entry.authority.GrantDigest() != grant {
			err = ErrBindingMismatch
		} else {
			material = append([]byte(nil), entry.authority.seal.exactRouteGrant...)
		}
	}
	m.mu.Unlock()
	m.notify(events)
	return material, err
}

func (m *Manager) ConsumeForGeneration(reservation Reservation, owner AdmissionOwner, generation AuthorityGeneration, now uint64) (AuthorityHandle, error) {
	return m.Consume(reservation, owner, GenerationSnapshot{generation: generation}, now)
}
