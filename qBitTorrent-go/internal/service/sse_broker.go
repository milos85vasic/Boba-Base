package service

import (
	"fmt"
	"sync"

	"github.com/rs/zerolog/log"
)

type SSEBroker struct {
	clients map[chan string]bool
	mu      sync.RWMutex
}

func NewSSEBroker() *SSEBroker {
	return &SSEBroker{
		clients: make(map[chan string]bool),
	}
}

func (b *SSEBroker) Subscribe() (chan string, func()) {
	b.mu.Lock()
	defer b.mu.Unlock()
	ch := make(chan string, 10)
	b.clients[ch] = true
	// BOB-095 §11.4.85 / §11.4.253: unsubscribe MUST be idempotent — an HTTP
	// handler's request-context cancel + a peer disconnect can both fire the
	// callback, and a second `close(ch)` panics ("close of closed channel").
	// Gate on registry membership so the second call is a safe no-op.
	return ch, func() {
		b.mu.Lock()
		defer b.mu.Unlock()
		if _, ok := b.clients[ch]; !ok {
			return
		}
		delete(b.clients, ch)
		close(ch)
	}
}

func (b *SSEBroker) Publish(event string, data string) {
	b.mu.RLock()
	defer b.mu.RUnlock()
	msg := FormatSSEEvent(event, data)
	for ch := range b.clients {
		select {
		case ch <- msg:
		default:
			log.Warn().Msg("dropping SSE message for slow client")
		}
	}
}

func FormatSSEEvent(event string, data string) string {
	return fmt.Sprintf("event: %s\ndata: %s\n\n", event, data)
}