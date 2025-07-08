/**
 * Pane Factory
 * 
 * Factory for creating panes without circular dependencies
 */

import type { TerminalPane } from './workspaceTypes'

export class PaneFactory {
  static createPane(
    type: 'terminal' | 'ai-chat' | 'log-viewer',
    title: string,
    sessionId?: string
  ): TerminalPane {
    return {
      id: `pane_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      type,
      sessionId,
      title,
      isActive: true
    }
  }

  static createTerminalPane(title: string, sessionId?: string): TerminalPane {
    return this.createPane('terminal', title, sessionId)
  }

  static createAiChatPane(title: string = 'AI Chat'): TerminalPane {
    return this.createPane('ai-chat', title)
  }

  static createLogViewerPane(title: string = 'Logs'): TerminalPane {
    return this.createPane('log-viewer', title)
  }
}