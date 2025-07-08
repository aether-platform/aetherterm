# セッション永続化要件書

## 概要
画面リロード時に、前回のセッションに自動的に再接続し、セッション内容を復元する機能。

## 機能要件

### 1. セッション情報の永続化
- **保存タイミング**: セッション作成時、変更時
- **保存先**: ブラウザのlocalStorage
- **保存内容**:
  - ワークスペースID
  - タブ情報（ID、タイトル、レイアウト）
  - ペイン情報（ID、セッションID、位置、サイズ）
  - 最終アクセス日時

### 2. スクリーンバッファの永続化
- **保存タイミング**: 出力受信時
- **保存先**: localStorage
- **保存内容**:
  - 最大5000行のターミナル出力
  - 各行のタイムスタンプ
  - 入力/出力/エラーのタイプ情報
- **キー形式**: `screen_buffer_${sessionId}`

### 3. ワークスペースの復元
- **復元タイミング**: アプリケーション起動時
- **復元プロセス**:
  1. localStorageからワークスペース情報を読み込み
  2. 最後にアクティブだったワークスペースを特定
  3. WebSocket接続を確立
  4. 保存されたセッションIDで再接続を試行
  5. スクリーンバッファを復元

### 4. セッション再接続
- **再接続フロー**:
  1. 既存セッションIDでサーバーに再接続要求
  2. サーバーがセッションの存在を確認
  3. 成功時: 既存セッションに接続
  4. 失敗時: 新規セッションを作成

## 技術仕様

### LocalStorageキー
```
aetherterm_workspaces        # ワークスペースIDリスト
aetherterm_current_workspace # 現在のワークスペースID
aetherterm_workspaces_${id}  # 各ワークスペースの詳細
screen_buffer_${sessionId}   # 各セッションのバッファ
```

### ワークスペース構造
```typescript
interface WorkspaceState {
  id: string
  name: string
  lastAccessed: Date
  tabs: TerminalTabWithPanes[]
  isActive: boolean
  layout: {
    type: 'tabs' | 'grid' | 'mosaic'
    configuration?: any
  }
}
```

### 実装ファイル
- `/stores/workspaceStore.ts` - ワークスペース永続化
- `/stores/screenBufferStore.ts` - スクリーンバッファ管理
- `/stores/aetherTerminalStore.ts` - セッション再接続ロジック
- `/components/terminal/AetherTerminalComponent.vue` - バッファ復元UI

## セキュリティ考慮事項
- localStorageに機密情報（パスワード、APIキー等）を保存しない
- セッションIDのみを保存し、認証情報は別途管理
- 古いセッションデータの自動削除機能

## パフォーマンス考慮事項
- スクリーンバッファは最大5000行に制限
- 大量データの書き込み時はdebounce処理
- 不要なセッションデータの定期的なクリーンアップ

## 今後の拡張案
1. セッション履歴の表示・管理UI
2. 複数デバイス間でのセッション同期
3. セッションのエクスポート/インポート機能
4. 自動保存間隔の設定