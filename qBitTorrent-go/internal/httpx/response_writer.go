package httpx

import (
	"net/http"
)

// closeNotifierWriter wraps an http.ResponseWriter so that it satisfies the
// http.CloseNotifier interface. This is required by net/http/httputil.ReverseProxy
// when running behind httptest.ResponseRecorder, which does not implement
// CloseNotify. The returned channel never fires; it exists only to satisfy the
// interface so the proxy can proceed without panicking in tests.
type closeNotifierWriter struct {
	http.ResponseWriter
	notify chan bool
}

// NewCloseNotifierWriter returns a ResponseWriter that also implements
// http.CloseNotifier and http.Flusher.
func NewCloseNotifierWriter(w http.ResponseWriter) http.ResponseWriter {
	return &closeNotifierWriter{ResponseWriter: w, notify: make(chan bool)}
}

func (w *closeNotifierWriter) CloseNotify() <-chan bool {
	return w.notify
}

func (w *closeNotifierWriter) Flush() {
	if f, ok := w.ResponseWriter.(http.Flusher); ok {
		f.Flush()
	}
}
