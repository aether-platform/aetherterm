# Vue Advanced Chat Integration with Pinia State Management

This document explains how vue-advanced-chat has been integrated into the frontend application using Pinia for advanced state management and terminal control.

## Installation

The required packages have been installed via npm:

```bash
npm install vue-advanced-chat pinia
```

## Architecture

### 1. Pinia State Management

The application uses Pinia stores for centralized state management:

- **AetherTerminalServiceStore**: Manages terminal connections, command processing, and AI monitoring
- **ChatStore**: Manages chat rooms, messages, and user interactions

### 2. AetherTerminalServiceStore Features

```typescript
// Connection Management
connectionState: ConnectionState
setSocket(socket)
connect() / disconnect()
startReconnection()

// Terminal Control
pauseTerminal(reason)
resumeTerminal()
suppressOutput(suppress, reason)
analyzeCommand(command)
submitCommand(command)

// Command Review System
approveCommand(commandId)
rejectCommand(commandId, reason)
pendingCommands: TerminalCommand[]

// AI Monitoring
dangerousCommands: string[]
addDangerousCommand(command)
setAIMonitoring(enabled)
```

### 3. Component Structure

- **TerminalComponent.vue**: Advanced terminal with command blocking, output suppression, and connection status
- **ChatComponent.vue**: Chat interface integrated with terminal control
- **AdminControlPanel.vue**: Administrative interface for terminal control and command approval
- **App.vue**: Three-column layout with terminal, chat, and admin panel

### 4. Main Application Setup

In `src/main.ts`, Pinia and the stores are initialized:

```typescript
import { createPinia } from 'pinia';
import { useAetherTerminalServiceStore } from './stores/aetherTerminalServiceStore';

const pinia = createPinia();
app.use(pinia);

// Initialize stores with Socket.IO connection
const terminalStore = useAetherTerminalServiceStore();
terminalStore.setSocket(socket);
terminalStore.initializeSession(`session_${Date.now()}`);
```

## Features

### Advanced Terminal Control

- **Command Analysis**: AI-powered analysis of dangerous commands
- **Command Blocking**: Critical commands require admin approval
- **Output Suppression**: Administrators can suppress terminal output
- **Terminal Pause/Resume**: Full terminal control by administrators
- **Connection Management**: Automatic reconnection with status indicators
- **Real-time Status**: Live connection and terminal status monitoring

### AI-Powered Security

- **Dangerous Command Detection**: Configurable list of dangerous command patterns
- **Risk Level Assessment**: Commands categorized as low, medium, high, or critical
- **AI Suggestions**: Contextual suggestions for safer alternatives
- **Command Review Queue**: Pending commands await administrative approval

### Administrative Features

- **Admin Control Panel**: Comprehensive interface for terminal management
- **Command Approval System**: Review and approve/reject pending commands
- **User Management**: Control user permissions and access levels
- **System Monitoring**: Real-time system status and activity logs
- **Configurable Security**: Add/remove dangerous command patterns

### Chat Integration

- **Multi-room Support**: General chat, terminal control, and AI assistance rooms
- **Real-time Messaging**: Socket.IO powered instant messaging
- **User Status**: Online/offline status with role-based permissions
- **Command Integration**: Chat commands can trigger terminal actions
- **Message History**: Persistent message storage and retrieval

### Socket.IO Events

**Terminal Control Events:**
- `shell_output`: Terminal shell output
- `ctl_output`: Terminal control output
- `admin_pause_terminal`: Administrative pause command
- `admin_resume_terminal`: Administrative resume command
- `admin_suppress_output`: Output suppression control
- `command_review_required`: Command requires approval
- `command_approval`: Admin approval/rejection response

**Chat Events:**
- `chat_message`: Real-time chat messages
- `user_join`: User joins chat room
- `user_leave`: User leaves chat room
- `typing_start`/`typing_stop`: Typing indicators

**Connection Events:**
- `connect`: Socket connection established
- `disconnect`: Socket connection lost
- `reconnect`: Socket reconnection successful
- `connect_error`: Connection error occurred

## Usage

### Running the Application

1. Start the development server:
   ```bash
   cd frontend
   npm run dev
   ```

2. Open your browser to `http://localhost:5174/` (or the port shown in terminal)

3. You'll see the terminal on the left and chat on the right

### Customization

To customize the chat component:

1. **Modify chat data**: Edit the `rooms` and `messages` refs in `ChatComponent.vue`
2. **Change styling**: Update the CSS in `ChatComponent.vue` or `App.vue`
3. **Add features**: Extend the event handlers in `ChatComponent.vue`
4. **Backend integration**: Modify the Socket.IO event handlers to match your backend API

### Backend Requirements

To fully utilize the chat functionality, your backend should:

1. Handle `chat_message` Socket.IO events
2. Broadcast messages to all connected clients
3. Store message history (optional)
4. Manage user authentication and rooms (optional)

## File Structure

```
frontend/src/
├── services/
│   └── AetherTermService.ts  # Shared Socket.IO service (singleton)
├── components/
│   ├── ChatComponent.vue     # Chat component using AetherTermService
│   └── TerminalComponent.vue # Terminal component using AetherTermService
├── views/
│   └── ChatView.vue         # Standalone chat view (optional)
├── App.vue                  # Main app container (no Socket.IO logic)
└── main.ts                  # App initialization with service setup
```

## Next Steps

1. **Backend Integration**: Implement Socket.IO chat handlers in your backend
2. **User Authentication**: Add proper user management
3. **Multiple Rooms**: Implement room switching functionality
4. **File Sharing**: Enable file uploads in chat
5. **Notifications**: Add desktop notifications for new messages
6. **Mobile Responsive**: Improve mobile layout