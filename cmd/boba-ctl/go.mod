module github.com/milos85vasic/qbittorrent/cmd/boba-ctl

go 1.25.0

require (
	digital.vasic.containers v0.0.0
	gopkg.in/yaml.v3 v3.0.1
)

require gopkg.in/check.v1 v1.0.0-20201130134442-10cb98267c6c // indirect

replace digital.vasic.containers => ../../submodules/containers
