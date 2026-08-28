// Package streamowner is the independent Go peer's local ownership model for
// the frozen Stream Credit wire profile. It deliberately imports neither the
// production Go client nor any Rust implementation.
package streamowner

import (
	"context"
	"errors"
	"io"
	"sync"
	"time"

	"nbsr.local/interop/nbsr-go-peer/internal/streamcredit"
)

const ProfileID = streamcredit.ProfileID
const creditsPerEpoch = 48

var (
	ErrInvalid            = errors.New("invalid stream ownership configuration")
	ErrClosed             = errors.New("stream owner closed")
	ErrCreditRejected     = errors.New("stream credit rejected")
	ErrGenerationCapacity = errors.New("transport generation capacity reached")
)

type Wire interface {
	io.Reader
	io.Writer
	io.Closer
}

type OpenFunc func(context.Context) (Wire, uint64, error)
type RefillFunc func(context.Context, uint64) error

type ApplicationStreamState uint8

const (
	ApplicationStreamAccepted ApplicationStreamState = iota + 1
	ApplicationStreamClosed
)

type ApplicationStream struct {
	mu    sync.Mutex
	wire  Wire
	id    uint64
	state ApplicationStreamState
}

func (stream *ApplicationStream) Read(value []byte) (int, error)  { return stream.wire.Read(value) }
func (stream *ApplicationStream) Write(value []byte) (int, error) { return stream.wire.Write(value) }
func (stream *ApplicationStream) FinishWrite() error              { return stream.wire.Close() }
func (stream *ApplicationStream) StreamID() uint64                { return stream.id }
func (stream *ApplicationStream) State() ApplicationStreamState {
	stream.mu.Lock()
	defer stream.mu.Unlock()
	return stream.state
}
func (stream *ApplicationStream) Close() error {
	stream.mu.Lock()
	if stream.state == ApplicationStreamClosed {
		stream.mu.Unlock()
		return nil
	}
	stream.state = ApplicationStreamClosed
	stream.mu.Unlock()
	return stream.wire.Close()
}

type OwnedChannelConfig struct {
	Now, ExpiresAt, TSGeneration, ChannelGeneration, AuthorityGeneration     uint64
	ChannelID                                                                [16]byte
	DeviceID, PolicyDigest, ServiceDigest, RouteGrantDigest, ProofThumbprint [32]byte
	SourceOperator, Gateway, ServiceIdentity, Profile, Transport             string
	Open                                                                     OpenFunc
	Refill                                                                   RefillFunc
}

type OwnedChannel struct {
	mu                sync.Mutex
	channel           [16]byte
	channelGeneration uint64
	profile           string
	open              OpenFunc
	refill            RefillFunc
	epoch             uint64
	slot              uint8
	closed            bool
}

func NewOwnedChannel(_ context.Context, config OwnedChannelConfig) (*OwnedChannel, error) {
	if config.Open == nil || config.ChannelID == ([16]byte{}) || config.ChannelGeneration == 0 || config.Profile != ProfileID {
		return nil, ErrInvalid
	}
	if config.ExpiresAt != 0 && config.Now >= config.ExpiresAt {
		return nil, ErrInvalid
	}
	return &OwnedChannel{channel: config.ChannelID, channelGeneration: config.ChannelGeneration, profile: config.Profile, open: config.Open, refill: config.Refill, epoch: 1}, nil
}

func (owner *OwnedChannel) Open(ctx context.Context) (*ApplicationStream, error) {
	owner.mu.Lock()
	if owner.closed {
		owner.mu.Unlock()
		return nil, ErrClosed
	}
	if owner.slot == creditsPerEpoch {
		if owner.refill == nil {
			owner.mu.Unlock()
			return nil, ErrCreditRejected
		}
		nextEpoch := owner.epoch + 1
		if err := owner.refill(ctx, nextEpoch); err != nil {
			owner.mu.Unlock()
			return nil, err
		}
		owner.epoch = nextEpoch
		owner.slot = 0
	}
	epoch, slot := owner.epoch, owner.slot
	owner.slot++
	channel, generation, profile, open := owner.channel, owner.channelGeneration, owner.profile, owner.open
	owner.mu.Unlock()
	return admit(ctx, profile, open, channel, generation, epoch, slot)
}

func (owner *OwnedChannel) Close() error {
	owner.mu.Lock()
	owner.closed = true
	owner.mu.Unlock()
	return nil
}

type Stream struct{ *ApplicationStream }

func Admit(ctx context.Context, profile string, open OpenFunc, channel [16]byte, channelGeneration, epoch uint64, slot uint8) (*Stream, error) {
	stream, err := admit(ctx, profile, open, channel, channelGeneration, epoch, slot)
	if err != nil {
		return nil, err
	}
	return &Stream{ApplicationStream: stream}, nil
}

func admit(ctx context.Context, profile string, open OpenFunc, channel [16]byte, channelGeneration, epoch uint64, slot uint8) (*ApplicationStream, error) {
	if ctx == nil || open == nil || profile != ProfileID || channel == ([16]byte{}) || channelGeneration == 0 || epoch == 0 || slot >= creditsPerEpoch {
		return nil, ErrInvalid
	}
	wire, streamID, err := open(ctx)
	if err != nil {
		return nil, err
	}
	fail := func(cause error) (*ApplicationStream, error) {
		_ = wire.Close()
		return nil, cause
	}
	preface, err := streamcredit.EncodePreface(channel, channelGeneration, epoch, uint64(slot), streamID)
	if err != nil {
		return fail(err)
	}
	if _, err = wire.Write(preface); err != nil {
		return fail(err)
	}
	decision := []byte{0xff}
	if _, err = io.ReadFull(wire, decision); err != nil {
		return fail(err)
	}
	if decision[0] != 0 {
		return fail(ErrCreditRejected)
	}
	return &ApplicationStream{wire: wire, id: streamID, state: ApplicationStreamAccepted}, nil
}

type GenerationSession interface {
	Close() error
	Identity() string
	Open(context.Context) (Wire, uint64, error)
	Refill(context.Context, [16]byte, uint64) error
}

type GenerationConfig struct {
	Generation, ChannelGeneration uint64
	ChannelID                     [16]byte
	ProofThumbprint               [32]byte
	Factory                       func(context.Context) (GenerationSession, error)
}

type RotationTrigger uint8

const RotationExplicit RotationTrigger = 1

type RotationClientConfig struct {
	Now, ExpiresAt, AuthorityGeneration                          uint64
	DeviceID, PolicyDigest, ServiceDigest, RouteGrantDigest      [32]byte
	SourceOperator, Gateway, ServiceIdentity, Profile, Transport string
	DrainTimeout                                                 time.Duration
	Generations                                                  []GenerationConfig
}

type generationState uint8

const (
	generationCurrent generationState = iota + 1
	generationDraining
)

type generation struct {
	config  GenerationConfig
	session GenerationSession
	state   generationState
	epoch   uint64
	slot    uint8
}

type GenerationSnapshot struct {
	Generation uint64
	State      generationState
}
type RotationResult struct{ Previous, Current GenerationSnapshot }
type Usage struct{ Sessions, PendingRotations, PendingChannels int }
type DrainingRejections struct{ ServiceChannel, Credit, Refill, ApplicationStream bool }

type RotationClient struct {
	mu      sync.Mutex
	configs map[uint64]GenerationConfig
	live    map[uint64]*generation
	current uint64
}

func NewRotationClient(ctx context.Context, config RotationClientConfig) (*RotationClient, error) {
	if ctx == nil || len(config.Generations) < 2 {
		return nil, ErrInvalid
	}
	client := &RotationClient{configs: make(map[uint64]GenerationConfig), live: make(map[uint64]*generation)}
	for _, item := range config.Generations {
		if item.Generation == 0 || item.ChannelGeneration == 0 || item.ChannelID == ([16]byte{}) || item.Factory == nil || client.configs[item.Generation].Generation != 0 {
			return nil, ErrInvalid
		}
		client.configs[item.Generation] = item
	}
	first := config.Generations[0]
	session, err := first.Factory(ctx)
	if err != nil || session == nil {
		return nil, err
	}
	client.live[first.Generation] = &generation{config: first, session: session, state: generationCurrent, epoch: 1}
	client.current = first.Generation
	return client, nil
}

func (client *RotationClient) Open(ctx context.Context, id uint64) (*ApplicationStream, error) {
	client.mu.Lock()
	generation := client.live[id]
	if generation == nil || generation.state != generationCurrent {
		client.mu.Unlock()
		return nil, ErrClosed
	}
	if generation.slot == creditsPerEpoch {
		nextEpoch := generation.epoch + 1
		if err := generation.session.Refill(ctx, generation.config.ChannelID, nextEpoch); err != nil {
			client.mu.Unlock()
			return nil, err
		}
		generation.epoch = nextEpoch
		generation.slot = 0
	}
	epoch, slot, config, session := generation.epoch, generation.slot, generation.config, generation.session
	generation.slot++
	client.mu.Unlock()
	return admit(ctx, ProfileID, session.Open, config.ChannelID, config.ChannelGeneration, epoch, slot)
}

func (client *RotationClient) Rotate(ctx context.Context, id uint64, trigger RotationTrigger) (RotationResult, error) {
	client.mu.Lock()
	defer client.mu.Unlock()
	if trigger != RotationExplicit || client.configs[id].Generation == 0 || client.live[id] != nil {
		return RotationResult{}, ErrInvalid
	}
	if len(client.live) >= 2 {
		return RotationResult{}, ErrGenerationCapacity
	}
	config := client.configs[id]
	session, err := config.Factory(ctx)
	if err != nil || session == nil {
		return RotationResult{}, err
	}
	previous := client.live[client.current]
	previous.state = generationDraining
	client.live[id] = &generation{config: config, session: session, state: generationCurrent, epoch: 1}
	oldID := client.current
	client.current = id
	return RotationResult{Previous: GenerationSnapshot{Generation: oldID, State: previous.state}, Current: GenerationSnapshot{Generation: id, State: generationCurrent}}, nil
}

func (client *RotationClient) ProbeDraining(_ context.Context, id uint64) DrainingRejections {
	client.mu.Lock()
	defer client.mu.Unlock()
	value := client.live[id]
	rejected := value != nil && value.state == generationDraining
	return DrainingRejections{ServiceChannel: rejected, Credit: rejected, Refill: rejected, ApplicationStream: rejected}
}

func (client *RotationClient) CloseGeneration(id uint64) error {
	client.mu.Lock()
	value := client.live[id]
	if value == nil {
		client.mu.Unlock()
		return ErrClosed
	}
	delete(client.live, id)
	client.mu.Unlock()
	return value.session.Close()
}

func (client *RotationClient) Current() (GenerationSnapshot, error) {
	client.mu.Lock()
	defer client.mu.Unlock()
	value := client.live[client.current]
	if value == nil {
		return GenerationSnapshot{}, ErrClosed
	}
	return GenerationSnapshot{Generation: client.current, State: value.state}, nil
}

func (client *RotationClient) TransportIdentity(id uint64) string {
	client.mu.Lock()
	defer client.mu.Unlock()
	if client.live[id] == nil {
		return ""
	}
	return client.live[id].session.Identity()
}

func (client *RotationClient) Usage() Usage {
	client.mu.Lock()
	defer client.mu.Unlock()
	return Usage{Sessions: len(client.live)}
}
