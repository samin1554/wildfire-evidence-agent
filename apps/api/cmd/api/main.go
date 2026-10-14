// Command api serves contracts/openapi.yaml.
package main

import (
	"context"
	"errors"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/samin1554/inland-resilience/apps/api/internal/config"
	"github.com/samin1554/inland-resilience/apps/api/internal/httpapi"
	"github.com/samin1554/inland-resilience/apps/api/internal/queue"
	"github.com/samin1554/inland-resilience/apps/api/internal/store"
)

func main() {
	if len(os.Args) > 1 && os.Args[1] == "-healthcheck" { // for the container healthcheck (no curl in distroless)
		c := http.Client{Timeout: 2 * time.Second}
		res, err := c.Get("http://127.0.0.1:8080/health")
		if err != nil || res.StatusCode != http.StatusOK {
			os.Exit(1)
		}
		os.Exit(0)
	}
	slog.SetDefault(slog.New(slog.NewJSONHandler(os.Stdout, nil)))
	cfg, err := config.FromEnv()
	if err != nil {
		slog.Error("config", "err", err)
		os.Exit(1)
	}
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()

	st, err := store.New(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("postgres", "err", err)
		os.Exit(1)
	}
	q, err := queue.New(cfg.RedisURL)
	if err != nil {
		slog.Error("redis", "err", err)
		os.Exit(1)
	}
	go q.Run(ctx)

	srv := &http.Server{
		Addr:              cfg.Addr,
		Handler:           (&httpapi.Server{Store: st, Queue: q, ArtifactsDir: cfg.ArtifactsDir}).Routes(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		_ = srv.Shutdown(shutdown)
	}()
	slog.Info("api listening", "addr", cfg.Addr)
	if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		slog.Error("server", "err", err)
		os.Exit(1)
	}
}
