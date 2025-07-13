# AetherTerm アーキテクチャ原則

> このドキュメントは、AetherTermプロジェクトにおける設計原則と実装ガイドラインを定義します。
> すべての開発者は、これらの原則に従って実装を行ってください。

## 目次

1. [基本原則](#基本原則)
2. [実装ガイドライン](#実装ガイドライン)
3. [アンチパターン](#アンチパターン)
4. [ベストプラクティス](#ベストプラクティス)
5. [トラブルシューティング](#トラブルシューティング)

## 基本原則

### 1. サーバー中心のアーキテクチャ

#### 原則
- **サーバーが唯一の真実の源（Single Source of Truth）**
- クライアントは表示層のみを担当
- すべての状態管理はサーバー側で行う

#### 実装ガイドライン

##### ❌ やってはいけないこと
```typescript
// BAD: クライアント側で状態を作成してからサーバーに送信
const tab = {
  id: `tab-${Date.now()}`,
  title: 'Terminal 1',
  panes: []
}
workspace.tabs.push(tab)
await saveToServer(workspace)  // 後からサーバーに同期
```

##### ✅ 正しい実装
```typescript
// GOOD: サーバーに作成を依頼し、結果を受け取る
const tab = await createTabOnServer(workspaceId, 'Terminal 1')
if (tab) {
  workspace.tabs.push(tab)  // サーバーが作成したものを表示
}
```

### 2. localStorage/sessionStorageの使用禁止

#### 原則
- ブラウザのローカルストレージは一切使用しない
- セッション情報もサーバー側で管理

#### 理由
1. **一貫性の問題**: 複数タブ/ウィンドウ間での状態の不整合
2. **セキュリティ**: 機密情報がブラウザに残る可能性
3. **スケーラビリティ**: 複数デバイス間での同期が困難
4. **デバッグの困難さ**: 状態が分散していると問題の特定が困難

#### 例外
- ユーザー設定（テーマ、フォントサイズなど）は保存可能
- ただし、これらも可能な限りサーバー側で管理することを推奨

#### 実装チェックリスト
- [ ] `localStorage.setItem()` を使用していない
- [ ] `localStorage.getItem()` を使用していない
- [ ] `sessionStorage` を使用していない
- [ ] IndexedDB を使用していない（キャッシュ目的を除く）

### 3. セッションID管理

#### 原則
- セッションIDは必ずサーバーが生成する
- クライアントは与えられたセッションIDを使用するのみ

#### 実装例
```typescript
// BAD: クライアントがセッションIDを生成
const sessionId = `session_${paneId}_${Date.now()}`

// GOOD: サーバーから受け取ったセッションIDを使用
const { sessionId } = await server.createTerminalSession()
```

### 4. イベント駆動アーキテクチャ

#### 原則
- クライアント→サーバー: 要求（Request）
- サーバー→クライアント: 応答（Response）または通知（Notification）

#### 命名規則
```
要求: <entity>_<action>
応答: <entity>_<action>_response または <entity>_<result>

例:
- workspace_create → workspace_created
- tab_create → tab_created
- session_connect → session_connected
```

#### Socket.IOイベント設計パターン

```typescript
// クライアント側
const requestWithTimeout = <T>(event: string, data: any, timeout = 5000): Promise<T> => {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      socket.off(`${event}_response`)
      socket.off('error')
      reject(new Error(`${event} timeout`))
    }, timeout)
    
    socket.once(`${event}_response`, (response: T) => {
      clearTimeout(timer)
      resolve(response)
    })
    
    socket.once('error', (error: any) => {
      clearTimeout(timer)
      reject(error)
    })
    
    socket.emit(event, data)
  })
}
```

### 5. エラーハンドリング

#### 原則
- すべてのサーバー操作は失敗する可能性があると想定
- ネットワーク断絶を考慮した設計

#### 実装例
```typescript
try {
  const workspace = await createWorkspaceOnServer(name)
  if (!workspace) {
    // フォールバック処理
    showError('Failed to create workspace')
    return
  }
  // 成功時の処理
} catch (error) {
  // ネットワークエラーなどの処理
  handleNetworkError(error)
}
```

### 6. 再接続とリカバリー

#### 原則
- 接続が切れても、再接続時に状態を復元できる設計
- サーバー側でセッション情報を保持

#### 実装
1. **Workspace Token**: ブラウザセッション間で共有される識別子
2. **Session Mapping**: Token → Workspace → Tab → Pane → Terminal Session
3. **自動再接続**: WebSocket切断時の自動再接続機能

### 7. データフローの方向性

```
User Action
    ↓
Frontend Component
    ↓
Store (Pinia)
    ↓
Socket.IO Event
    ↓
Backend Handler
    ↓
Service Layer
    ↓
Domain Entity
    ↓
Response Event
    ↓
Store Update
    ↓
UI Update
```

### 8. 状態の永続化

#### 原則
- 短期的な状態: メモリ内（Redis推奨）
- 長期的な状態: データベース（PostgreSQL推奨）

#### 実装段階
1. **Phase 1**: メモリ内保存（現在）
2. **Phase 2**: Redis導入（セッション情報）
3. **Phase 3**: PostgreSQL導入（ワークスペース構成）

## アンチパターン

### 1. ローカルファースト思考
```typescript
// ❌ AVOID
const data = localStorage.getItem('workspace') || await fetchFromServer()

// ❌ AVOID: キャッシュを信頼しすぎる
if (cache.has(id)) {
  return cache.get(id)  // 古いデータの可能性
}

// ✅ CORRECT: 常にサーバーから最新を取得
const data = await fetchFromServer()
if (data) {
  cache.set(id, data)  // 表示用のキャッシュのみ
}
```

### 2. クライアント側ID生成
```typescript
// ❌ AVOID
const id = uuid() // クライアントでID生成
```

### 3. 楽観的更新（Optimistic Updates）
```typescript
// ❌ AVOID (ターミナルアプリでは不適切)
state.tabs.push(newTab)  // 先に更新
await server.createTab(newTab)  // 後でサーバーに送信
```

### 4. 状態の重複
```typescript
// ❌ AVOID
// 同じ情報を複数の場所で管理
localStorage.setItem('session', sessionId)
store.session = sessionId
server.session = sessionId
```

## ベストプラクティス

### 1. 明示的なローディング状態
```typescript
const isCreatingTab = ref(false)
const createTabError = ref<string | null>(null)

const createTab = async () => {
  isCreatingTab.value = true
  createTabError.value = null
  
  try {
    const tab = await server.createTab()
    if (!tab) {
      throw new Error('Failed to create tab')
    }
    return tab
  } catch (error) {
    createTabError.value = error.message
    // ユーザーに表示
    showNotification({
      type: 'error',
      message: `Failed to create tab: ${error.message}`
    })
    return null
  } finally {
    isCreatingTab.value = false
  }
}
```

### 2. 適切なタイムアウト設定
```typescript
const OPERATION_TIMEOUT = 5000  // 5秒

const withTimeout = (promise, timeout = OPERATION_TIMEOUT) => {
  return Promise.race([
    promise,
    new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Timeout')), timeout)
    )
  ])
}
```

### 3. 段階的な機能低下（Graceful Degradation）
```typescript
// 接続がない場合でも、基本的なUI操作は可能にする
if (!isConnected) {
  showOfflineMessage()
  disableServerDependentFeatures()
} else {
  enableAllFeatures()
}
```

## トラブルシューティング

### よくある問題と解決策

#### 1. 「セッションが見つからない」エラー
**原因**: クライアントが古いセッションIDを使用している
```typescript
// 解決策: サーバーから新しいセッションを要求
if (error.code === 'SESSION_NOT_FOUND') {
  const newSession = await createNewSession()
  updateLocalSession(newSession)
}
```

#### 2. 状態の不整合
**原因**: 複数のタブが異なる状態を持っている
```typescript
// 解決策: BroadcastChannelを使用した同期
const channel = new BroadcastChannel('workspace_sync')
channel.onmessage = (event) => {
  if (event.data.type === 'refresh') {
    loadWorkspaceFromServer()
  }
}
```

#### 3. パフォーマンスの問題
**原因**: 頻繁なサーバーリクエスト
```typescript
// 解決策: デバウンスとバッチ処理
const pendingUpdates = new Map()
const flushUpdates = debounce(async () => {
  const updates = Array.from(pendingUpdates.values())
  await server.batchUpdate(updates)
  pendingUpdates.clear()
}, 300)
```

## コードレビューチェックリスト

新しい機能を実装する際は、以下の項目を確認してください：

- [ ] localStorage/sessionStorageを使用していない
- [ ] セッションIDはサーバーから取得している
- [ ] すべてのサーバー操作にエラーハンドリングがある
- [ ] ローディング状態が適切に管理されている
- [ ] タイムアウト処理が実装されている
- [ ] ネットワーク断絶時の処理が考慮されている
- [ ] イベント名が命名規則に従っている
- [ ] 状態の重複がない（Single Source of Truth）

## まとめ

これらの原則に従うことで：
1. **予測可能な動作**: 状態が一箇所で管理される
2. **デバッグの容易さ**: 問題の原因を特定しやすい
3. **拡張性**: 新機能の追加が容易
4. **信頼性**: ネットワーク問題に強い設計

常に「サーバーが主、クライアントは従」の関係を意識して実装すること。

---

*最終更新: 2025年1月*
*バージョン: 1.0*