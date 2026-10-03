// Package config reads the API's settings from the environment (.env.example lists them).
package config

import (
	"errors"
	"os"
)

type Config struct {
	Addr         string // listen address, default :8080
	DatabaseURL  string
	RedisURL     string
	ArtifactsDir string // shared volume the worker writes overlay tiles to
}

func FromEnv() (Config, error) {
	c := Config{
		Addr:         getenv("API_ADDR", ":8080"),
		DatabaseURL:  os.Getenv("DATABASE_URL"),
		RedisURL:     os.Getenv("REDIS_URL"),
		ArtifactsDir: getenv("ARTIFACTS_DIR", "/artifacts"),
	}
	if c.DatabaseURL == "" || c.RedisURL == "" {
		return c, errors.New("DATABASE_URL and REDIS_URL must be set")
	}
	return c, nil
}

func getenv(k, def string) string {
	if v := os.Getenv(k); v != "" {
		return v
	}
	return def
}
