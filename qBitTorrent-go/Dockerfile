# BOB-153: this builder MUST satisfy the `go` directive in go.mod (go 1.26.2).
# That directive is not an author's preference — it is forced by the dependency
# graph: kin-openapi v0.136.0 declares `go 1.26` in its own go.mod, and gin,
# modernc.org/sqlite and x/net declare `go 1.25.0`. Go refuses to build a module
# whose dependency needs a newer toolchain, so lowering the directive is not an
# option here — it would mean downgrading dependencies.
#
# The patch level is pinned deliberately: an unpinned `golang:1.26-alpine` floats,
# so it cannot be shown from this file alone to satisfy a 1.26.2 floor, and the
# build stops being reproducible (§11.4.246).
#
# scripts/pre_build/check_cm_go_toolchain_matches_builder.sh enforces the tie.
# If you raise go.mod, raise this line in the same commit.
FROM golang:1.26.2-alpine AS builder
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /qbittorrent-proxy ./cmd/qbittorrent-proxy
RUN CGO_ENABLED=0 GOOS=linux go build -o /webui-bridge ./cmd/webui-bridge

FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
WORKDIR /app
COPY --from=builder /qbittorrent-proxy .
COPY --from=builder /webui-bridge .
COPY .env.example .env
EXPOSE 7187 7188
CMD ["/app/qbittorrent-proxy"]