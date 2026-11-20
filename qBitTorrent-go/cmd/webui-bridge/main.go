package main

import (
	"fmt"
	"os"

	"github.com/gin-gonic/gin"
	"github.com/milos85vasic/qBitTorrent-go/internal/bridge"
	"github.com/rs/zerolog/log"
)

func main() {
	cfg := bridge.DefaultConfig()

	if os.Getenv("GIN_MODE") == "debug" || os.Getenv("GIN_MODE") == "test" {
		gin.SetMode(gin.DebugMode)
	} else {
		gin.SetMode(gin.ReleaseMode)
	}

	r := bridge.NewRouter(cfg)

	addr := fmt.Sprintf(":%d", cfg.Port)
	log.Info().Str("addr", addr).Str("qbit", cfg.QBittorrentURL).Msg("webui-bridge listening")
	if err := r.Run(addr); err != nil {
		log.Fatal().Err(err).Msg("bridge server failed")
		os.Exit(1)
	}
}
