# AetherTerm Frontend

Vue 3 + TypeScript frontend for the AetherTerm terminal platform.

## Development

```bash
# Install dependencies
pnpm install

# Development server (hot-reload)
pnpm dev

# Production build
pnpm build

# Type checking
pnpm type-check
```

## Architecture

- **Framework**: Vue 3 + TypeScript + Vuetify
- **State Management**: Pinia stores
- **Build Tool**: Vite
- **Communication**: Socket.IO client

## Key Components

- `TerminalComponent.vue` - Main terminal interface
- `TabBarContainer.vue` - Tab management
- `MainContentView.vue` - Layout orchestration
- Store modules for state management

## IDE Setup

[VSCode](https://code.visualstudio.com/) + [Volar](https://marketplace.visualstudio.com/items?itemName=Vue.volar)

---
See main [README](../README.md) for full documentation.