package api

import (
	"encoding/json"
	"net/http"
	"os"
	"sync"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/models"
	"github.com/rs/zerolog/log"
)

// defaultThemeState is the sensible fallback served whenever no valid theme
// is persisted on disk. Kept as the single source of truth for the default so
// load() can restore it after a corrupt/partial file.
var defaultThemeState = models.ThemeState{PaletteID: "default", Mode: "dark"}

var allowedModes = map[string]bool{
	"light": true,
	"dark":  true,
}

type ThemeStore struct {
	mu    sync.RWMutex
	file  string
	state models.ThemeState
}

func NewThemeStore(file string) *ThemeStore {
	store := &ThemeStore{
		file:  file,
		state: defaultThemeState,
	}
	store.load()
	return store
}

func (s *ThemeStore) load() {
	data, err := os.ReadFile(s.file)
	if err != nil {
		// No file yet (first run) — keep the constructor default.
		return
	}
	// Decode into a scratch value so a corrupt/partial file can never
	// half-overwrite the live state with zero-value garbage. On any error we
	// keep the sensible default rather than silently serving a broken theme.
	var loaded models.ThemeState
	if err := json.Unmarshal(data, &loaded); err != nil {
		log.Warn().Err(err).Str("file", s.file).Msg("theme: corrupt theme file, keeping default state")
		s.state = defaultThemeState
		return
	}
	s.state = loaded
}

func (s *ThemeStore) save() error {
	data, err := json.MarshalIndent(s.state, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile(s.file, data, 0644)
}

func (s *ThemeStore) Get() models.ThemeState {
	s.mu.RLock()
	defer s.mu.RUnlock()
	return s.state
}

func (s *ThemeStore) Put(paletteID, mode string) (models.ThemeState, error) {
	if !allowedModes[mode] {
		return models.ThemeState{}, &ValidationError{Message: "mode must be 'light' or 'dark'"}
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	s.state = models.ThemeState{PaletteID: paletteID, Mode: mode}
	s.save()
	return s.state, nil
}

type ValidationError struct {
	Message string
}

func (e *ValidationError) Error() string {
	return e.Message
}

func GetThemeHandler(store *ThemeStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		c.JSON(http.StatusOK, store.Get())
	}
}

func PutThemeHandler(store *ThemeStore) gin.HandlerFunc {
	return func(c *gin.Context) {
		var req models.ThemeUpdate
		if err := c.ShouldBindJSON(&req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
			return
		}
		state, err := store.Put(req.PaletteID, req.Mode)
		if err != nil {
			c.JSON(http.StatusUnprocessableEntity, gin.H{"error": err.Error()})
			return
		}
		c.JSON(http.StatusOK, state)
	}
}