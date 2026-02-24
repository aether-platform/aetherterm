// AetherTerm - Docker Buildx Bake configuration
// Clean, modular architecture for multi-platform builds.

variable "REGISTRY" {
  default = "ghcr.io/aether-platform"
}

variable "VERSION" {
  default = "latest"
}

variable "BASE_IMAGE_TAG" {
  default = "3.12-slim"
}

// Global groups
group "default" {
  targets = ["aetherterm", "aetherterm-agent"]
}

group "release" {
  targets = ["aetherterm", "aetherterm-agent"]
}

// Shared settings mixin
target "common" {
  context    = "."
  dockerfile = "Dockerfile"
  platforms  = ["linux/amd64", "linux/arm64"]
  args = {
    PYTHON_VERSION = "3.12"
  }
  cache-from = [
    "type=gha,scope=aetherterm",
    "type=local,src=.buildx-cache"
  ]
  cache-to = [
    "type=gha,mode=max,scope=aetherterm",
    "type=local,dest=.buildx-cache,mode=max"
  ]
}

target "aetherterm" {
  inherits = ["common"]
  tags = [
    "${REGISTRY}/aetherterm:${VERSION}",
    "${REGISTRY}/aetherterm:latest",
  ]
}

target "aetherterm-agent" {
  inherits = ["common"]
  tags = [
    "${REGISTRY}/aetherterm:${VERSION}-agent",
    "${REGISTRY}/aetherterm:latest-agent",
  ]
}
