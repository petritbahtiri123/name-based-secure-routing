package authority

import (
	"errors"
	"testing"
)

func FuzzAuthorityLifecycle(f *testing.F) {
	f.Add([]byte{0, 1, 2, 3, 4, 5, 6, 7})
	f.Add([]byte{7, 6, 5, 4, 3, 2, 1, 0})
	f.Fuzz(func(t *testing.T, ops []byte) {
		if len(ops) > 256 {
			ops = ops[:256]
		}
		m := task11Manager(t)
		reservations := make([]Reservation, 8)
		for index, op := range ops {
			slot := int(op>>3) % len(reservations)
			key := testKey(byte(slot + 1))
			authority := testAuthority(key, testGrant(byte(slot+1)), 200)
			var err error
			switch op & 7 {
			case 0:
				reservations[slot], err = m.reserveVerified(authority)
			case 1:
				err = m.Release(reservations[slot])
			case 2:
				_, err = m.Consume(reservations[slot], owner(key.TSGeneration), GenerationSnapshot{generation: key.AuthorityGeneration}, 99)
			case 3:
				err = m.Quarantine(reservations[slot], RequestID{byte(index + 1)})
			case 4:
				err = m.InvalidateGrant(authority.GrantDigest())
			case 5:
				_, err = m.InvalidateOlderThan(7)
			case 6:
				_, err = m.CaptureGeneration()
			case 7:
				err = m.ValidateStillCurrent(GenerationSnapshot{generation: 7})
			}
			if err != nil && !task11TypedAuthorityError(err) {
				t.Fatalf("operation %d (opcode %d) returned undocumented error %T: %v", index, op&7, err, err)
			}
			if err := m.ValidateInvariants(); err != nil {
				t.Fatalf("operation %d invariants: %v", index, err)
			}
			usage := m.Usage()
			if usage.CacheEntries > 8 || usage.PendingCalls > 4 || usage.RequestRecords > 8 || usage.PendingWaiters > 8 {
				t.Fatalf("operation %d exceeded bounded state: %+v", index, usage)
			}
		}
	})
}

func task11TypedAuthorityError(err error) bool {
	var typed *AuthorityError
	return errors.As(err, &typed) && typed != nil
}
