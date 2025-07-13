# AetherTerm Session Management Design

## Overview
AetherTermは3つの異なるセッション復元メカニズムを持っています。これらは重複しており、統一する必要があります。

## Current Handler Analysis

### 1. `resume_workspace(sid, data)` - Line 492
**Purpose**: Workspace全体の復元（複数のタブとペインを含む）
**Client Usage**: `sessionManager.ts` - ページ初期化時に呼ばれる
**Flow**: 
- Workspaceの全タブを取得
- 各タブ内の全ペインを処理
- 各ペインに対して新しいターミナルセッションを作成
- **Role**: 階層レベル - Workspace → Tabs → Panes

### 2. `resume_terminal(sid, data)` - Line 681  
**Purpose**: 単一ターミナルセッションの復元
**Client Usage**: コメントで言及されているが実際の呼び出しは見つからない
**Flow**:
- 指定されたsessionIdで既存セッションを検索
- セッションが見つからない場合は新規作成
- **Role**: 個別ターミナルレベル

### 3. `reconnect_session(sid, data)` - Line 1813
**Purpose**: アクティブなセッションへの再接続
**Client Usage**: `aetherTerminalStore.ts` - ターミナル初期化時に呼ばれる
**Flow**:
- メモリ内のアクティブセッションを検索
- バッファが存在する場合は復元（修正済み）
- **Role**: セッション再接続レベル

## Investigation Results (2025-07-13)

### Handler Usage Analysis
調査の結果、3つのハンドラーは**異なる階層レベル**で使われており、完全な重複ではないことが判明：

1. **`resume_workspace`**: ページ初期化時にワークスペース全体を復元
2. **`resume_terminal`**: 実際には使われていない（デッドコード）
3. **`reconnect_session`**: 個別ターミナルの再接続時に使用

### Root Cause of Buffer Restoration Bug
- **Issue**: `reconnect_session`がアクティブセッションのみ対応していた
- **Fix**: バッファ保存データからも復元するよう修正済み
- **Result**: ページリロード後もスクリーンバッファが復元される

### Memoization Issues
- **Problem**: Socket.IOの`environ`オブジェクトがJSON化できずエラー
- **Fix**: `get_user_info_from_environ`から`@memoize`デコレーターを削除
- **Impact**: ターミナル作成が正常に動作するようになった

## Problems Identified

1. **Handler Redundancy**: `resume_terminal`は未使用（削除候補）
2. **Buffer Restoration Gap**: `reconnect_session`でバッファ復元が不完全だった（修正済み）
3. **Session Persistence**: メモリ内セッションとバッファ保存の連携不足（改善済み）
4. **Memoization Conflicts**: Socket.IOオブジェクトとmemoizationの非互換性（修正済み）

## Buffer Storage Analysis

### Server-side Buffer Storage
- `AsyncioTerminal.session_buffers`: セッションごとのバッファを保存
- Format: `{session_id: {"lines": [], "max_lines": 5000, "created_at": time, "last_updated": time}}`
- Storage: メモリ内（永続化なし）

### Client-side Buffer Storage  
- `screenBufferStore`: クライアント側のバッファ管理
- localStorage: セッション情報の永続化

## Proposed Solution

### 1. Unified Session Handler
単一の`restore_session`ハンドラーに統合：
```python
async def restore_session(sid, data):
    """Unified session restoration handler."""
    session_id = data.get("sessionId")
    
    # 1. Check for active session
    if session_id in AsyncioTerminal.sessions:
        # Reconnect to active session
        return await reconnect_active_session(sid, session_id)
    
    # 2. Check for buffered session 
    if session_id in AsyncioTerminal.session_buffers:
        # Restore from buffer
        return await restore_from_buffer(sid, session_id)
    
    # 3. Create new session
    return await create_new_session(sid, session_id)
```

### 2. Buffer Restoration Flow
```python
async def restore_from_buffer(sid, session_id):
    """Restore session from saved buffer."""
    buffer_data = AsyncioTerminal.session_buffers[session_id]
    
    # Send buffer content to client
    for line in buffer_data["lines"]:
        await sio_instance.emit("terminal_output", {
            "session": session_id,
            "data": line["content"]
        }, room=sid)
    
    # Mark session as ready
    await sio_instance.emit("terminal_ready", {
        "session": session_id, 
        "status": "restored"
    }, room=sid)
```

### 3. Session ID Standardization
- Client: `terminal_pane_{paneId}_{hash}`
- Server: Same format for consistency
- Remove `aether_pane_` prefix that causes confusion

## Implementation Priority

### Completed (2025-07-13)
1. ✅ **High**: Fix immediate buffer restoration in existing handlers
2. ✅ **High**: Remove memoization conflicts causing JSON serialization errors
3. ✅ **Medium**: Document handler usage and relationships

### Future Improvements
1. **Medium**: Remove unused `resume_terminal` handler (dead code cleanup)
2. **Low**: Add persistent storage for buffers (currently memory-only)
3. **Low**: Standardize session ID formats across client/server

## Screen Buffer Restoration Bug Fix

### Root Cause
The `reconnect_session` handler only works for active sessions in memory. After page reload, sessions don't exist in memory but buffers may still exist.

### Immediate Fix
Modify `reconnect_session` to check `session_buffers` even when session doesn't exist:

```python
# In reconnect_session handler, after line 1860:
# Check if we have buffer data for this session
buffer_data = AsyncioTerminal.get_session_buffer(session_id)
if buffer_data and buffer_data.get("lines"):
    log.info(f"Found buffer data for session {session_id}, sending {len(buffer_data['lines'])} lines")
    
    # Send buffer content
    for line in buffer_data["lines"]:
        await sio_instance.emit("terminal_output", {
            "session": session_id,
            "data": line["content"]
        }, room=sid)
    
    # Send ready signal
    await sio_instance.emit("terminal_ready", {
        "session": session_id,
        "status": "restored_from_buffer"
    }, room=sid)
    return

# If no buffer found, send session_not_found
```