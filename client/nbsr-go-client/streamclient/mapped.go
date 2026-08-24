package streamclient

import (
	"context"
	"io"

	"nbsr.local/client/nbsr-go-client/internal/corestate"
	"nbsr.local/client/nbsr-go-client/internal/resolution"
)

type MappedRouteOpener struct {
	channel         *OwnedChannel
	serviceIdentity string
	serviceDigest   corestate.ServiceDigest
}

func NewMappedRouteOpener(channel *OwnedChannel) (*MappedRouteOpener, error) {
	if channel == nil || channel.serviceIdentity == "" || channel.serviceDigest == (corestate.ServiceDigest{}) {
		return nil, resolution.ErrRouteBinding
	}
	return &MappedRouteOpener{channel: channel, serviceIdentity: channel.serviceIdentity, serviceDigest: channel.serviceDigest}, nil
}

func (opener *MappedRouteOpener) OpenVerifiedRoute(ctx context.Context, route resolution.RouteContext) (io.ReadWriteCloser, error) {
	if ctx == nil || route.MappingID == 0 || route.ServiceIdentity != opener.serviceIdentity || route.ServiceDigest != opener.serviceDigest ||
		route.Intent.ServiceIdentity != opener.serviceIdentity || route.Intent.Transport == "" || route.Intent.Port == 0 {
		return nil, resolution.ErrRouteBinding
	}
	return opener.channel.Open(ctx)
}

var _ resolution.SecureRouteOpener = (*MappedRouteOpener)(nil)
