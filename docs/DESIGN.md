# AetherTerm UI Design Principles

## UI Structure Overview

### Tab Bar (Terminal-focused)
**Purpose**: Terminal and related functionality only
**Location**: Top of terminal area
**Contents**:
- 💻 Terminal tabs (dynamic, user-created)
- 🤖 AI Agent tabs (dynamic, user-created) 
- ➕ Tab Creation Menu
- 📈 Log Monitor (fixed, terminal-related)

**IMPORTANT**: No duplicate functionality with Side Panel. S3 Browser and AI Costs should NOT appear here.

### Side Panel (All non-terminal functions)
**Purpose**: Centralized location for all application features
**Location**: Right side, collapsible
**Contents**:
- 🤖 Assistant (AI chat)
- 🖥️ Inventory (server management)
- 👮 Admin (system administration)
- 🎨 Theme (appearance settings)
- 🗂️ S3 Browser (file management)
- 💰 AI Costs (cost monitoring)
- 🔧 Debug (development only)

### Sidebar (Shortcuts when panel closed)
**Purpose**: Quick access shortcuts when Side Panel is hidden
**Location**: Right edge, narrow strip
**Contents**:
- ← Panel toggle button
- 🤖 Assistant shortcut
- 🖥️ Inventory shortcut
- 🗂️ S3 Browser shortcut
- 👮 Admin shortcut
- 🎨 Theme shortcut

## Design Rules

### 1. No Function Duplication
- Each feature should have exactly ONE primary access point
- Tab Bar = Terminal-related only
- Side Panel = All application features
- Sidebar = Shortcuts only (opens Side Panel)

### 2. Clear Separation of Concerns
- **Tab Bar**: Terminal sessions and monitoring
- **Side Panel**: Application features and tools
- **Sidebar**: Quick navigation when panel hidden

### 3. Consistent Access Patterns
- Terminal functions → Tab Bar
- Application functions → Side Panel
- Quick access → Sidebar shortcuts

## Historical Issues to Avoid

### Issue: Function Duplication
**Problem**: S3 Browser and AI Costs appeared in both Tab Bar and Side Panel
**Solution**: Keep these ONLY in Side Panel
**Prevention**: Always check if function already exists elsewhere before adding

### Issue: sidebarStore Complexity  
**Problem**: Separate overlay sidebar system conflicted with unified Side Panel
**Solution**: Single unified Side Panel system only
**Prevention**: Use App.vue activeTab state, not separate sidebar stores

### Issue: Confusing Terminology
**Problem**: "Sidebar" and "Side Panel" used interchangeably
**Solution**: 
- **Side Panel** = Main collapsible panel with tabs
- **Sidebar** = Narrow shortcut strip when panel hidden

## Implementation Guidelines

1. **Adding New Features**: Always add to Side Panel first
2. **Terminal Features**: May appear in Tab Bar if directly terminal-related
3. **Shortcuts**: Only add to Sidebar if frequently used
4. **Testing**: Verify no duplication exists before deployment

This design ensures clean separation, prevents confusion, and maintains scalability.