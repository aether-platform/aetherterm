# アーキテクチャ変更 (2025年1月)

## 概要

ターミナルアプリケーションのアーキテクチャを、クライアントサイド状態管理からサーバーサイド状態管理に移行しました。

## 主な変更点

### 1. localStorage依存の削除

**Before:**
- ワークスペース、タブ、ペインの状態をlocalStorageに保存
- サーバーとの同期は「オプション」
- 再接続時にlocalStorageから復元を試み、その後サーバーと同期

**After:**
- すべての状態をサーバーで管理
- localStorageは一切使用しない
- 再接続時はサーバーから直接状態を取得

### 2. ワークスペース管理の変更

**Before:**
```typescript
// クライアント側でタブを作成
const tab = createTabWithPane(tabId, 'Terminal', 'terminal', 'pure')
currentWorkspace.tabs.push(tab)
// その後サーバーに保存
await saveWorkspaceToServer(currentWorkspace)
```

**After:**
```typescript
// サーバー側でタブを作成
const tab = await createTabOnServer(workspace.id, 'Terminal 1', 'terminal', 'pure')
// サーバーから返されたタブをローカル状態に反映
workspace.tabs.push(tab)
```

### 3. Socket.IOイベントの再設計

#### 削除されたイベント
- `save_workspace` / `workspace_saved`
- `load_workspace` / `workspace_loaded`
- `list_workspaces` / `workspaces_listed`
- `shell_output`, `ctl_output` (→ `terminal_output`に統合)

#### 新しいイベント構造

**ワークスペース管理:**
```
Client → Server:
- workspace_create    → workspace_created
- workspace_get      → workspace_data
- workspace_list     → workspace_list_data
- workspace_delete   → workspace_deleted

- tab_create         → tab_created
- tab_delete         → tab_deleted
- pane_create        → pane_created
- pane_delete        → pane_deleted
```

### 4. セッション管理の改善

**Before:**
- クライアントが独自にセッションIDを生成（`aether_pane_${paneId}`）
- 再接続時にセッションIDの不一致が発生

**After:**
- サーバーがすべてのセッションIDを管理
- タブ/ペイン作成時にサーバーがセッションを作成
- 再接続時も同じセッションIDを使用

## アーキテクチャ図

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Vue.js)                     │
│                                                          │
│  ┌──────────────┐    ┌──────────────┐                  │
│  │WorkspaceStore│    │TerminalStore │                  │
│  │ (No localStorage) │    │              │                  │
│  └──────┬───────┘    └──────┬───────┘                  │
│         │                    │                           │
│         └────────┬───────────┘                           │
│                  │                                       │
│                  ▼                                       │
│         ┌────────────────┐                              │
│         │  Socket.IO     │                              │
│         │  Connection    │                              │
│         └────────────────┘                              │
└─────────────────────┬───────────────────────────────────┘
                      │
                      │ WebSocket
                      ▼
┌─────────────────────────────────────────────────────────┐
│                    Backend (Python)                      │
│                                                          │
│  ┌─────────────────────────┐    ┌─────────────────┐    │
│  │WorkspaceManagementService│    │AsyncioTerminal  │    │
│  │ - Workspace creation     │    │ - PTY management│    │
│  │ - Tab/Pane management    │    │ - Session state │    │
│  │ - Session tracking       │    └─────────────────┘    │
│  └─────────────────────────┘                            │
│                                                          │
│         All state lives here (Single Source of Truth)   │
└─────────────────────────────────────────────────────────┘
```

## 利点

1. **単一の真実の源（Single Source of Truth）**
   - サーバーがすべての状態を管理
   - クライアント間の不整合がない

2. **簡素化されたクライアント**
   - 表示ロジックのみに集中
   - 複雑な同期ロジックが不要

3. **改善されたセッション管理**
   - 再接続時の挙動が予測可能
   - セッションの永続性が向上

4. **スケーラビリティ**
   - 複数のクライアントが同じワークスペースを共有可能
   - 将来的なコラボレーション機能の基盤

## 移行時の注意点

1. **既存のlocalStorageデータ**
   - 移行スクリプトは提供しない（クリーンスタート推奨）
   - ユーザーは新しいワークスペースを作成する必要がある

2. **パフォーマンス**
   - すべての操作がネットワーク経由になる
   - 適切なローディング状態の表示が重要

3. **エラーハンドリング**
   - ネットワーク断絶時の挙動を明確に
   - 再接続時の自動復旧を実装

## 今後の拡張

1. **データベース永続化**
   - 現在はメモリ内保存
   - PostgreSQLやRedisへの永続化を検討

2. **リアルタイムコラボレーション**
   - 複数ユーザーが同じワークスペースを共有
   - カーソル位置の同期など

3. **ワークスペーステンプレート**
   - 事前定義されたタブ/ペイン構成
   - プロジェクトタイプ別のテンプレート