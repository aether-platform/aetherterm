# ワークスペース設計仕様

## 基本設計

### **グローバル共有ワークスペース**
- **1つのワークスペース**のみ存在
- **全てのユーザー**が同じワークスペースを共有
- **全てのブラウザ**が同じワークスペースを共有
- **全てのターミナルセッション**が共有される

### **ユーザー権限**
- **User**: 読み書き可能（タブ作成、ターミナル操作）
- **Viewer**: 読み取り専用（閲覧のみ）

## API設計

### **最小限のAPI**
- `workspace_connect`: ワークスペースに接続してデータを取得
- `tab_create`: タブを作成（サーバーが自動的にワークスペースを更新）
- `reconnect_session`: セッションを再接続してスクリーンバッファ復元

### **削除理由**
- `workspace_update`: グローバルワークスペースでは名前変更不要、レイアウトも自動管理

### **削除されたAPI**
- ❌ `workspace_create` - 単一ワークスペースなので不要
- ❌ `workspace_list` - 単一ワークスペースなので不要
- ❌ `workspace_get` - connectで一緒に取得するので不要

## データフロー

1. **ユーザー接続**
   ```
   Client → workspace_connect → Server
   Server → workspace_connected + workspace_data → Client
   ```

2. **タブ作成**
   ```
   Client → tab_create → Server
   Server → tab_created → All Clients (broadcast)
   ```

3. **セッション復元**
   ```
   Client → reconnect_session → Server
   Server → session_reconnected + history_data → Client
   ```

## 実装の単純化

### **グローバル状態**
- 1つのワークスペースインスタンス
- 全クライアントが同じデータを共有
- 変更時は全クライアントにブロードキャスト

### **権限制御**
- サーバー側で権限チェック
- Viewerは変更操作を拒否
- Userは全ての操作が可能