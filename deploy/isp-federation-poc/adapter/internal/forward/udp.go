package forward

import (
	"context"
	"errors"
	"net"
	"sync"
	"time"
)

type udpPeer struct {
	client   *net.UDPAddr
	upstream *net.UDPConn
	lastSeen time.Time
}

// ServeUDP keeps one connected loopback socket per exact initiating UDP peer.
// It owns listener and closes all sockets before returning.
func ServeUDP(ctx context.Context, listener *net.UDPConn, upstream *net.UDPAddr, maxPeers int, idleTimeout time.Duration) error {
	if listener == nil || upstream == nil || upstream.IP.String() != "127.0.0.1" || upstream.Port <= 0 || upstream.Port > 65535 || upstream.Zone != "" || maxPeers != 16 || idleTimeout <= 0 || idleTimeout > 20*time.Second {
		return errInvalidConfig
	}
	ctx, cancel := context.WithCancel(ctx)
	var mu sync.Mutex
	var workers sync.WaitGroup
	peers := make(map[string]*udpPeer)
	stop := context.AfterFunc(ctx, func() { _ = listener.Close() })
	defer func() {
		cancel()
		_ = listener.Close()
		stop()
		mu.Lock()
		for _, peer := range peers {
			_ = peer.upstream.Close()
		}
		mu.Unlock()
		workers.Wait()
	}()
	remove := func(key string, peer *udpPeer) {
		mu.Lock()
		if peers[key] == peer {
			delete(peers, key)
		}
		mu.Unlock()
		_ = peer.upstream.Close()
	}
	workers.Add(1)
	go func() {
		defer workers.Done()
		interval := idleTimeout / 2
		if interval < time.Millisecond {
			interval = time.Millisecond
		}
		ticker := time.NewTicker(interval)
		defer ticker.Stop()
		for {
			select {
			case <-ctx.Done():
				return
			case now := <-ticker.C:
				mu.Lock()
				for key, peer := range peers {
					if now.Sub(peer.lastSeen) >= idleTimeout {
						delete(peers, key)
						_ = peer.upstream.Close()
					}
				}
				mu.Unlock()
			}
		}
	}()
	buffer := make([]byte, 65535)
	for {
		n, client, err := listener.ReadFromUDP(buffer)
		if err != nil {
			if ctx.Err() != nil {
				return nil
			}
			return errors.New("adapter listener failed")
		}
		key := client.String()
		mu.Lock()
		peer := peers[key]
		if peer == nil {
			if len(peers) >= maxPeers {
				mu.Unlock()
				continue
			}
			socket, err := net.DialUDP("udp4", nil, upstream)
			if err != nil {
				mu.Unlock()
				continue
			}
			peer = &udpPeer{client: &net.UDPAddr{IP: append(net.IP(nil), client.IP...), Port: client.Port}, upstream: socket}
			peers[key] = peer
			workers.Add(1)
			go func(key string, peer *udpPeer) {
				defer workers.Done()
				defer remove(key, peer)
				response := make([]byte, 65535)
				for {
					n, err := peer.upstream.Read(response)
					if err != nil {
						return
					}
					mu.Lock()
					active := peers[key] == peer
					if active {
						peer.lastSeen = time.Now()
					}
					mu.Unlock()
					if !active {
						return
					}
					if _, err = listener.WriteToUDP(response[:n], peer.client); err != nil {
						return
					}
				}
			}(key, peer)
		}
		peer.lastSeen = time.Now()
		mu.Unlock()
		if _, err := peer.upstream.Write(buffer[:n]); err != nil {
			remove(key, peer)
		}
	}
}
