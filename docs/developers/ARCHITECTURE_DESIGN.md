# AetherTerm Architecture Design v2.1

## 1. System Overview

AetherTerm は3コンポーネントから構成されるモジュラーターミナルシステム。
AgentServer を Hub とし、全通信を集約する。

```
                     ControlServer (:8765)
                    ┌─────────────────────────┐
                    │ AI分析・制御判断           │
                    │ LLM Log Analyzer         │
                    │ 緊急停止・ブロック         │
                    │ セッションマッピング       │
                    └──┬──────────┬──────┬─────┘
                       │          │      │
                  ROUTER(:8766)   │   SUB(:8769)
                  PUB(:8767)      │      ↑ AgentServer PUB
                       │          │      │ log/event stream
                       │ ZMQ      │      │
                       │ 双方向    │      │
                       │          │      │
    Browser ◄──WS──► AgentServer (:57575) ◄──Hub──
                    ┌──────────────────────────┐
                    │ Web UI配信                 │
                    │ PTY管理                    │
                    │ ControlBridge             │
                    │  DEALER ↔ ROUTER (制御)   │
                    │  SUB    ← PUB    (緊急)   │
                    │  PUB    → SUB    (ログ)   │
                    └─────┬────────────────────┘
                          │ PTY I/O
                          │ (fork/exec)
                          │
                     AgentShell ────────────────┐
                    ┌──────────────────┐        │
                    │ PTYラッパー        │  ZMQ PUSH (:8768)
                    │ + LogSender       │  → ControlServer
                    └──────────────────┘  (fire-and-forget)
```

### 設計原則

1. **AgentServer = Hub**: 全通信の中継点。ブラウザ向け表示 + ControlServer連携
2. **AgentShell = PTY + LogSender**: PTY実行 + 軽量ZMQ PUSHでログ直送
3. **ControlServer = 頭脳**: AI分析・制御判断 + セッション/シェルマッピング
4. **プロトコル統一**: ブラウザ向け = WebSocket、バックエンド間 = ZMQ
5. **Socket.IO廃止**: Native WebSocket に統一
6. **直送パス**: AgentShell → ControlServer (ZMQ PUSH/PULL) でクロスカッティング分析
7. **PUB/SUBストリーム**: AgentServer → ControlServer (PUB/SUB) でリアルタイムログ/イベント配信

---

## 2. ZMQ 通信トポロジー

### ポートマッピング

| ポート | ソケット | バインド側 | 接続側 | 用途 |
|--------|----------|------------|--------|------|
| 8766 | ROUTER/DEALER | ControlServer | AgentServer | 双方向 制御/RPC |
| 8767 | PUB/SUB | ControlServer | AgentServer | ブロードキャスト (緊急停止等) |
| 8768 | PULL/PUSH | ControlServer | AgentShell | シェル出力直送 |
| 8769 | SUB/PUB | ControlServer | AgentServer | ログ/イベントストリーム |

### メッセージエンベロープ共通形式

全 ZMQ メッセージは msgpack でシリアライズされ、以下のエンベロープ構造を持つ:

```python
{
    "type": str,              # メッセージタイプ
    "agent_server_id": str,   # 送信元ID
    "timestamp": float,       # Unix epoch
    "payload": dict,          # メッセージ固有データ
}
```

### PUB/SUB トピック体系

AgentServer PUB → ControlServer SUB:
```
log:{session_id}:{pane_id}    # ターミナル出力ログ
session:report                 # セッション状態レポート
event:{event_type}             # 任意イベント (shell_attached等)
```

ControlServer PUB → AgentServer SUB:
```
broadcast:{command}            # 全AgentServer宛 (emergency, block, unblock)
agent:{agent_server_id}:{cmd}  # 特定AgentServer宛
```

---

## 3. コンポーネント詳細

### 3.1 AgentServer (Hub)

**責務**:
- ブラウザへのWeb UI配信（Vue 3 SPA）
- PTYプロセス管理（tmux セッション/ウィンドウ/ペイン）
- WebSocket経由のターミナルI/O中継
- ControlServer との ZMQ 通信 (ControlBridge)
- セッション状態管理

**エントリポイント**: `src/aetherterm/agentserver/main.py`

**レイヤー構成**:
```
agentserver/
├── main.py                    # CLI エントリポイント (Click)
├── api/                       # プレゼンテーション層
│   ├── server.py              # ASGI App Factory (FastAPI)
│   ├── containers.py          # DI Container (dependency-injector)
│   └── routes.py              # HTTP ルート
├── core/                      # ビジネスロジック層
│   ├── control_bridge.py      # ZMQ Client (DEALER + SUB + PUB)
│   ├── messaging.py           # MessageRouter, TaskListManager
│   └── sessions/
│       ├── manager.py         # PTYSessionManager (Singleton)
│       ├── agent_manager.py   # AgentSessionManager
│       └── tmux/              # tmux セッション管理
│           ├── session_registry.py  # TmuxSessionRegistry
│           ├── models.py      # ドメインモデル
│           ├── ws_handler.py  # WebSocket ハンドラ
│           └── layout_engine.py
├── services/                  # アプリケーションサービス
│   └── ai_service.py          # AI サービス (Anthropic/Mock)
├── analysis/                  # 分析レイヤー
│   ├── log_analyzer.py
│   └── reporting/
├── web/                       # 静的アセット
│   ├── static/
│   └── templates/
└── common/                    # ユーティリティ
```

#### ControlBridge (control_bridge.py)

AgentServer 側の ZMQ クライアント。3つのソケットを管理:

```python
class ControlBridge:
    # ソケット構成
    DEALER → ControlServer ROUTER (:8766)  # 双方向制御
    SUB    ← ControlServer PUB    (:8767)  # ブロードキャスト受信
    PUB    → ControlServer SUB    (:8769)  # ログ/イベント配信

    # 公開API
    async start() -> bool
    async stop()
    on_control_command(callback)        # 制御コマンドコールバック登録
    async forward_log(session_id, pane_id, data)  # ログバッファリング
    async send_session_report(sessions) # セッション状態レポート (PUB)
    async send_heartbeat()              # ハートビート (DEALER)
    async publish_event(topic, type, payload)  # 任意イベント (PUB)
```

**特徴**:
- ログは 100ms バッチ間隔でバッファリング後に PUB 送信 (DEALER フォールバック)
- ハートビートは 15 秒間隔
- pyzmq 未インストール時は graceful degradation
- ZMQ の自動再接続 (`RECONNECT_IVL` + `RECONNECT_IVL_MAX`)

**環境変数**:
| 変数名 | デフォルト | 用途 |
|--------|-----------|------|
| `CONTROL_SERVER_ROUTER` | `tcp://localhost:8766` | DEALER 接続先 |
| `CONTROL_SERVER_PUB` | `tcp://localhost:8767` | SUB 接続先 |
| `CONTROL_SERVER_SUB` | `tcp://localhost:8769` | PUB 接続先 |

**通信インターフェース**:

| 方向 | プロトコル | 用途 |
|------|-----------|------|
| Browser → AgentServer | WebSocket `/ws/tmux/{session_id}` | ターミナルI/O、セッション制御 |
| Browser → AgentServer | HTTP REST `/api/*` | セッション一覧、管理API |
| AgentServer → ControlServer | ZMQ PUB (`:8769`) | ログ/イベントストリーム |
| AgentServer → ControlServer | ZMQ DEALER (`:8766`) | 状態報告、ハートビート、フォールバック |
| ControlServer → AgentServer | ZMQ ROUTER (`:8766`) | 制御指示（停止、ブロック等） |
| ControlServer → AgentServer | ZMQ PUB (`:8767`) | 緊急停止ブロードキャスト |
| AgentServer → AgentShell | PTY I/O | fork/exec による直接プロセス管理 |

### 3.2 ControlServer (AI分析・制御 + セッションマッピング)

**責務**:
- AgentServer から受信したログの AI 分析
- 脅威検知・パターンマッチング
- 制御指示の発行（セッション停止、入力ブロック等）
- 複数 AgentServer インスタンスの統括
- **PTYセッションとAgentShellの関係マッピング**
- **セッション/シェル単位でのコマンドルーティング**

**エントリポイント**: `src/aetherterm/controlserver/main.py`

**モジュール構成**:
```
controlserver/
├── main.py                    # CLI エントリポイント
├── central_controller.py      # 中央制御ロジック + WebSocket管理API
├── zmq_controller.py          # ZMQ transport (ROUTER + PUB + SUB)
├── llm_analyzer.py            # LLM ベースログ分析 (litellm)
├── log_buffer.py              # 循環ログバッファ
├── log_pattern_compressor.py  # パターン圧縮
└── log_analysis_config.py     # 分析設定
```

#### ZMQController (zmq_controller.py)

ControlServer 側の ZMQ サーバー。3つのソケットをバインド + セッションマッピング:

```python
class ZMQController:
    # ソケット構成 (全てバインド)
    ROUTER (tcp://*:8766)  ← AgentServer DEALER
    PUB    (tcp://*:8767)  → AgentServer SUB
    SUB    (tcp://*:8769)  ← AgentServer PUB

    # セッションマッピング
    _sessions: Dict[session_id, PtySessionInfo]
    _shells: Dict[shell_id, ShellInfo]
    _agent_sessions: Dict[agent_server_id, Set[session_id]]  # 逆引き

    # コールバック
    on_log_received(callback)       # ログ受信コールバック
    on_session_report(callback)     # セッションレポートコールバック
    on_event(callback)              # 汎用イベントコールバック

    # コマンド送信
    async send_to_agent(agent_id, msg_type, payload)  # 特定AgentServerへ
    async send_to_session(session_id, msg_type, payload)  # セッション所属AgentServer経由
    async send_to_shell(shell_id, msg_type, payload)  # シェル宛 (AgentServer経由)
    async broadcast(topic, msg_type, payload)  # PUBブロードキャスト

    # 便利メソッド
    async send_emergency_stop(reason)
    async send_block_input(session_id, pane_id, reason)
    async send_unblock_input(session_id, pane_id, admin_user)

    # マッピング照会
    get_session(session_id) -> PtySessionInfo
    get_shell(shell_id) -> ShellInfo
    list_sessions() -> List[PtySessionInfo]
    list_shells() -> List[ShellInfo]
    get_sessions_for_agent(agent_id) -> List[PtySessionInfo]
    get_shells_for_session(session_id) -> List[ShellInfo]
```

**セッションマッピング データモデル**:

```python
@dataclass
class PtySessionInfo:
    session_id: str           # PTYセッションID
    agent_server_id: str      # 所属AgentServer
    pane_ids: List[str]       # ペインID一覧
    shell_ids: List[str]      # 紐付くAgentShell ID一覧
    created_at: float
    last_activity: float

@dataclass
class ShellInfo:
    shell_id: str             # AgentShell インスタンスID
    session_id: str           # 紐付くPTYセッション
    agent_server_id: str      # 所属AgentServer
    registered_at: float
    last_heartbeat: float
```

**マッピング更新フロー**:
```
1. AgentServer → session_report → ZMQController._update_session_mapping()
   → _sessions, _agent_sessions 更新
   → 不要セッション自動削除 (pruning)

2. AgentServer → shell_register → ZMQController._register_shell()
   → _shells 追加, session.shell_ids にリンク

3. AgentServer → shell_detach → ZMQController._unregister_shell()
   → _shells 削除, session.shell_ids からリンク解除
```

**環境変数**:
| 変数名 | デフォルト | 用途 |
|--------|-----------|------|
| `ZMQ_ROUTER_BIND` | `tcp://*:8766` | ROUTER バインドアドレス |
| `ZMQ_PUB_BIND` | `tcp://*:8767` | PUB バインドアドレス |
| `ZMQ_SUB_BIND` | `tcp://*:8769` | SUB バインドアドレス |

**制御コマンド**:

| コマンド | ソケット | ペイロード | 動作 |
|----------|---------|-----------|------|
| `kill_session` | ROUTER | `{session_id}` | 指定セッションの PTY を kill |
| `block_input` | PUB broadcast | `{session_id, pane_id, reason}` | 入力を一時停止 |
| `unblock_input` | PUB broadcast | `{session_id, pane_id, admin_user}` | 入力再開 |
| `emergency_stop` | PUB broadcast | `{reason}` | 全セッション即時停止 |
| `send_to_session` | ROUTER | `{session_id, ...}` | セッション所属のAgentServerへ転送 |
| `send_to_shell` | ROUTER | `{shell_id, target_shell_id, ...}` | AgentShell宛 (AgentServer経由) |

### 3.3 AgentShell (PTYラッパー + LogSender)

**責務**:
- PTY プロセスの実行
- ターミナル出力を ControlServer に直送 (ZMQ PUSH, fire-and-forget)
- AgentServer が fork/exec で起動

**モジュール構成**:
```
agentshell/
├── main.py                    # エントリポイント
├── config.py                  # 設定
├── log_sender.py              # ZMQ PUSH ログ送信 (→ ControlServer :8768)
├── controller/
│   └── terminal_controller.py # ターミナル制御 (LogSender統合済み)
├── pty/
│   ├── terminal_pty.py        # PTY 管理
│   ├── sync_terminal_pty.py   # 同期 PTY
│   └── pty_chain.py           # PTYチェーン（将来用）
└── pty_monitor/               # PTY監視 (AgentServer側に移行検討)
    ├── ai_analyzer.py
    └── input_blocker.py
```

**LogSender 仕様**:
- ZMQ PUSH ソケット (`SNDHWM=1000`, `LINGER=0`)
- 接続先: `CONTROL_SERVER_PULL` 環境変数 (デフォルト: `tcp://localhost:8768`)
- 100ms バッチ間隔でバッファリング・送信
- msgpack シリアライズ: `{type, session_id, timestamp, data}`
- pyzmq 未インストール or ControlServer停止時は無視 (graceful degradation)

**terminal_controller.py 統合**:
```python
# start_monitoring() で LogSender 起動
await self._log_sender.start()

# OUTPUT イベントでログ転送
if event.event_type == EventType.OUTPUT:
    await self._log_sender.send_output(event.data)

# stop_monitoring() で LogSender 停止
await self._log_sender.stop()
```

---

## 4. データフロー

### 4.1 ユーザー入力 → シェル実行

```
1. Browser: キー入力
2. → WebSocket binary frame [pane_id + input_data]
3. → TmuxWebSocketHandler.handle_binary()
4. → TmuxSessionRegistry.write_to_pane(pane_id, data)
5. → os.write(pane.master_fd, data)
6. → OS Shell が実行
```

### 4.2 シェル出力 → ブラウザ表示

```
1. OS Shell: stdout 出力
2. → PTY master_fd read (asyncio loop)
3. → TmuxSessionRegistry._pane_read_loop()
4. → 全クライアントの Queue に配信
5. → TmuxWebSocketHandler: binary frame 送信
6. → Browser: xterm.js に描画
```

### 4.3 シェル出力 → AI分析 (PUB/SUB パス)

```
1. OS Shell: stdout 出力
2. → PTY master_fd read (asyncio loop)
3. → AgentServer: ControlBridge.forward_log(session_id, pane_id, data)
4. → バッファリング (100ms バッチ)
5. → ZMQ PUB [topic: "log:{session_id}:{pane_id}"] → ControlServer SUB (:8769)
6. → ZMQController._handle_sub_msg() → log_received callback
7. → LogBufferManager → LogPatternCompressor → LLMLogAnalyzer
8. → 脅威検知時: ZMQController.broadcast("broadcast:block", "block_input", ...)
9. → AgentServer SUB → ControlBridge._dispatch() → callback
10. → Browser: { "type": "input_blocked", "reason": "..." }
```

### 4.4 シェル出力 → AI分析 (直送パス: AgentShell → ControlServer)

```
1. OS Shell: stdout 出力
2. → PTY master_fd read (asyncio loop)
3. → AgentShell: LogSender.send_output(data)  [バッファに追加]
4. → 100ms バッチ: LogSender.flush()
5. → ZMQ PUSH → ControlServer PULL (:8768)
6. → ZMQController → 既存の log_callbacks に統合
7. → LLMLogAnalyzer.analyze(data)
8. → 脅威検知時: ZMQController → AgentServer (ROUTER): block_input
9. → AgentServer → Browser: { "type": "input_blocked", "reason": "..." }
```

> **注意**: 4.3 (AgentServer PUB/SUB経由) と 4.4 (AgentShell PUSH/PULL直送) は並行パス。
> AgentServer経由パスは構造化ログ (pane_id付き) + トピックフィルタリング対応。
> AgentShell直送パスは生の PTY 出力バイトを送信。
> ControlServer 側で両方を統合してクロスカッティング分析を実現。

### 4.5 ControlServer → セッション停止

```
1. ControlServer: AI分析で危険検知
2. → ZMQController.send_to_session(session_id, "kill_session", {})
3.    → session mapping 参照: session → agent_server_id
4. → ZMQ ROUTER → AgentServer DEALER: メッセージ受信
5. → ControlBridge._dispatch() → callback
6. → TmuxSessionRegistry.destroy_session(session_id)
7. → PTY プロセス kill
8. → WebSocket: { "type": "session_terminated", "reason": "..." }
9. → Browser: 通知表示
```

### 4.6 ControlServer → AgentShell へのコマンド送信

```
1. ControlServer: シェル操作の必要性を判断
2. → ZMQController.send_to_shell(shell_id, "command", payload)
3.    → shell mapping 参照: shell_id → agent_server_id
4.    → payload に target_shell_id を付与
5. → ZMQ ROUTER → AgentServer DEALER: メッセージ受信
6. → AgentServer: target_shell_id で AgentShell を特定
7. → PTY I/O 経由でコマンド実行
```

### 4.7 セッションマッピング更新

```
1. AgentServer 起動時:
   → ControlBridge.start() → agent_register (DEALER)
   → ZMQController: _agents[agent_id] = timestamp

2. セッション作成/変更時:
   → ControlBridge.send_session_report(sessions) (PUB topic: session:report)
   → ZMQController: _update_session_mapping()
   → _sessions, _agent_sessions 更新

3. AgentShell 起動時:
   → AgentServer 経由: shell_register (DEALER)
   → ZMQController: _register_shell()
   → _shells 追加, session.shell_ids リンク

4. AgentShell 終了時:
   → AgentServer 経由: shell_detach (DEALER)
   → ZMQController: _unregister_shell()
   → _shells 削除
```

---

## 5. フロントエンド構成

### ルーティング

| パス | ページ | 用途 |
|------|--------|------|
| `/` | ControlCenterPage | セッション管理ダッシュボード |
| `/tmux/:session?` | TmuxPage | メインターミナル (tmux) |
| `/term/session/:session?` | AetherTermPage | レガシーターミナル |
| `/term/control` | ControlCenterPage | セッション管理 |
| `/chat` | AIChatOpenWebUI | AI チャット |

### Pinia ストア

| ストア | 役割 |
|--------|------|
| `tmuxStore` | tmux セッション/ウィンドウ/ペイン状態 |
| `tmuxKeybindingStore` | Ctrl+B プレフィックスキー状態マシン |
| `tmuxCopyModeStore` | Vi スタイルコピーモード |
| `paneStore` | [レガシー] AetherTerm ペインレイアウト |
| `uiModeStore` | UIモード/プラットフォーム選択 |
| `chatStore` | チャットメッセージ/AIメッセージ |
| `aetherTerminalServiceStore` | [レガシー] PTY WebSocket接続 |

### コンポーネント構成 (tmux 系)

```
TmuxPage
└── TmuxContainer (キーバインド処理)
    ├── TmuxStatusBar (ステータスバー)
    ├── TmuxPaneLayout (再帰的レイアウト)
    │   ├── TmuxPane → TmuxTerminal (xterm.js)
    │   └── TmuxPaneDivider (ドラッグ可能)
    ├── TmuxPrefixIndicator (Ctrl+B表示)
    ├── TmuxPaneNumbers (ペイン番号オーバーレイ)
    ├── TmuxCopyMode (コピーモード)
    ├── TmuxCommandLine (: コマンド入力)
    ├── TmuxConfirmDialog
    ├── TmuxRenameDialog
    └── TmuxSessionSwitcher
```

---

## 6. 通信プロトコル詳細

### 6.1 Browser ↔ AgentServer (WebSocket)

**エンドポイント**: `/ws/tmux/{session_id}`

**バイナリフレーム** (ターミナルI/O):
```
送受信共通: [1byte: pane_id_len][N bytes: pane_id][M bytes: pty_data]
```

**テキストフレーム** (制御メッセージ):
```json
// セッション管理
{ "type": "session_create", "name": "..." }
{ "type": "session_attach", "session_id": "..." }
{ "type": "session_detach" }

// ウィンドウ管理
{ "type": "window_create", "name": "..." }
{ "type": "window_close", "window_id": "..." }
{ "type": "window_select", "window_id": "..." }

// ペイン管理
{ "type": "pane_split", "direction": "v|h", "pane_id": "..." }
{ "type": "pane_close", "pane_id": "..." }
{ "type": "pane_focus", "pane_id": "..." }
{ "type": "pane_resize_pty", "pane_id": "...", "cols": 80, "rows": 24 }

// レイアウト
{ "type": "layout_resize", "pane_id": "...", "delta": 10 }
{ "type": "layout_preset", "preset": "even-horizontal" }
```

**サーバー → クライアント**:
```json
{ "type": "state_sync", "session": { ... } }
{ "type": "state_update", ... }
{ "type": "pane_exited", "pane_id": "...", "exit_code": 0 }
{ "type": "session_blocked", "reason": "..." }
{ "type": "input_blocked", "pane_id": "...", "reason": "..." }
```

### 6.2 AgentServer → ControlServer (ZMQ PUB → SUB, ポート 8769)

ログ/イベントのリアルタイムストリーム。トピックベースフィルタリング。

```
# トピック + msgpack ペイロード (2フレーム multipart)
# フレーム[0]: topic (UTF-8)
# フレーム[1]: msgpack エンベロープ

# ログ転送 (100ms バッチ, _flush_log_buffer)
topic: "log:{session_id}:{pane_id}"
{
    "type": "log_forward",
    "agent_server_id": "agentserver-hostname-12345",
    "timestamp": 1708905600.0,
    "payload": {
        "session_id": "...",
        "pane_id": "...",
        "data": b"..."  # 生バイト (バッチ済み)
    }
}

# セッション状態レポート
topic: "session:report"
{
    "type": "session_report",
    "payload": {
        "sessions": [
            {
                "session_id": "...",
                "pane_ids": ["pane-0", "pane-1"],
                "shell_ids": ["shell-abc"]
            }
        ]
    }
}

# 任意イベント
topic: "event:shell_attached"
{
    "type": "shell_attached",
    "payload": { "shell_id": "...", "session_id": "..." }
}
```

### 6.3 AgentServer ↔ ControlServer (ZMQ DEALER ↔ ROUTER, ポート 8766)

双方向の制御/RPC チャネル。

**AgentServer → ControlServer**:
```json
// 登録
{ "type": "agent_register", "payload": { "hostname": "..." } }

// ハートビート
{ "type": "heartbeat", "payload": { "uptime": 12345.6 } }

// シェル登録/解除
{ "type": "shell_register", "payload": { "shell_id": "...", "session_id": "..." } }
{ "type": "shell_detach", "payload": { "shell_id": "..." } }

// ログ転送 (PUB フォールバック時)
{ "type": "log_forward", "payload": { "session_id": "...", "data": "..." } }
```

**ControlServer → AgentServer**:
```json
// 登録確認
{ "type": "registration_confirmed", "payload": { "agent_server_id": "..." } }

// セッション制御
{ "type": "kill_session", "payload": { "session_id": "..." } }
{ "type": "block_input", "payload": { "session_id": "...", "pane_id": "...", "reason": "..." } }
{ "type": "unblock_input", "payload": { "session_id": "...", "pane_id": "..." } }

// シェル宛コマンド (AgentServer がルーティング)
{ "type": "shell_command", "payload": { "target_shell_id": "...", "command": "..." } }
```

### 6.4 ControlServer PUB → AgentServer SUB (ポート 8767)

緊急ブロードキャスト。

```
# トピック + msgpack ペイロード (2フレーム multipart)
topic: "broadcast:emergency"
{ "type": "emergency_stop", "payload": { "reason": "..." } }

topic: "broadcast:block"
{ "type": "block_input", "payload": { "session_id": "...", "reason": "..." } }

topic: "broadcast:unblock"
{ "type": "unblock_input", "payload": { "session_id": "...", "admin_user": "..." } }

# 特定AgentServer宛
topic: "agent:{agent_server_id}:config"
{ "type": "config_update", "payload": { "key": "...", "value": "..." } }
```

### 6.5 AgentShell → ControlServer (ZMQ PUSH/PULL, ポート 8768)

AgentShell は ControlServer の PULL ソケット (:8768) に直接ターミナル出力を送信。
Fire-and-forget: 応答なし、ControlServer停止時は送信をスキップ。

**メッセージフォーマット** (msgpack):
```python
{
    "type": "shell_output",       # 固定
    "session_id": str,            # AgentShell セッションID
    "timestamp": float,           # Unix epoch
    "data": bytes,                # 生のターミナル出力 (バッチ済み)
}
```

---

## 7. 削除対象ファイル

### 確定削除 (Phase 1 完了)

| ファイル | 理由 | 状態 |
|----------|------|------|
| `common/zmq/` (全体) | ZMQ Broker パターン廃止 | **削除済** |
| `agentshell/zmq_agent_connector.py` | Shell にネットワーク通信不要 | **削除済** |
| `agentshell/main_zmq.py` | ZMQ エントリポイント不要 | **削除済** |
| `agentshell/service/server_connector.py` | Hub方式で Shell→Server 接続不要 | **削除済** |
| `agentshell/service/agent_coordinator.py` | Hub方式で不要 | **削除済** |
| `agentshell/service/agent_orchestrator.py` | Hub方式で不要 | **削除済** |
| `agentserver/api/socket_handlers.py` | Socket.IO 廃止 (WebSocket に統一) | **削除済** |

### 移行後に削除

| ファイル | 移行先 |
|----------|--------|
| `agentshell/service/ai_service.py` | ControlServer の LLM Analyzer |
| `agentshell/service/shell_agent.py` | ControlServer 側に統合 |
| `agentshell/service/telemetry_service.py` | AgentServer の ControlBridge 経由 |
| `frontend/src/services/AetherTermService.ts` | tmux WebSocket に統一 |
| `frontend/src/stores/aetherTerminalServiceStore.ts` | tmuxStore に統合 |
| `frontend/src/stores/paneStore.ts` | tmuxStore に統合 |

---

## 8. 新規作成ファイル

| ファイル | 役割 | 状態 |
|----------|------|------|
| `agentserver/core/control_bridge.py` | ZMQ Client (DEALER + SUB + PUB) | **実装済** |
| `controlserver/zmq_controller.py` | ZMQ Server (ROUTER + PUB + SUB) + セッションマッピング | **実装済** |
| `agentshell/log_sender.py` | ZMQ PUSH ログ送信 (AgentShell → ControlServer) | **実装済** |

---

## 9. 依存関係

### Python (pyproject.toml)

**保持**:
- `fastapi`, `uvicorn` — Web フレームワーク
- `websockets` — WebSocket プロトコル
- `pyzmq>=25.0.0` — ZMQ 通信
- `msgpack>=1.0.0` — ZMQ メッセージシリアライズ
- `litellm>=1.0.0` — ControlServer LLM 連携
- `jinja2`, `libsass` — テンプレート/テーマ
- `click` — CLI
- `dependency-injector` — DI

**削除候補**:
- `python-socketio` — WebSocket に統一後は不要

### Node.js (frontend/package.json)

**保持**:
- `vue@3.5`, `vue-router@4`, `pinia@3` — フレームワーク
- `@xterm/xterm@5.5` — ターミナルエミュレーション
- `deep-chat@2.4` — AI チャット

**削除候補**:
- `socket.io-client` — WebSocket に統一後は不要

---

## 10. Docker Compose 構成

```yaml
services:
  aetherterm:
    # AgentServer (Hub)
    image: ghcr.io/aether-platform/aetherterm:latest
    command: aetherterm-agentserver --host=0.0.0.0 --port=57575
    ports:
      - "57575:57575"
    environment:
      - CONTROL_SERVER_ROUTER=tcp://controlserver:8766
      - CONTROL_SERVER_PUB=tcp://controlserver:8767
      - CONTROL_SERVER_SUB=tcp://controlserver:8769

  controlserver:
    # ControlServer (AI分析 + セッションマッピング)
    image: ghcr.io/aether-platform/aetherterm:latest
    command: aetherterm-controlserver --port=8765
    ports:
      - "8765:8765"    # 管理API (WebSocket)
      - "8766:8766"    # ZMQ ROUTER (← AgentServer DEALER)
      - "8767:8767"    # ZMQ PUB (→ AgentServer SUB)
      - "8768:8768"    # ZMQ PULL (← AgentShell PUSH)
      - "8769:8769"    # ZMQ SUB (← AgentServer PUB)
    environment:
      - LLM_PROVIDER=anthropic
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}

  open-webui:
    image: ghcr.io/open-webui/open-webui:latest
    environment:
      - OLLAMA_BASE_URL=http://host.docker.internal:11434
```

---

## 11. マイルストーン

### Phase 1: クリーンアップ & 基盤整備 ✅
- [x] 削除対象ファイルの除去 (7ファイル git rm)
- [x] 壊れたインポートの修正 (13ファイル)
- [x] `aetherterm-broker` エントリポイント削除
- [ ] DI Container 統一
- [ ] Socket.IO 依存の除去

### Phase 2: ZMQ モジュール新規作成 ✅
- [x] `agentserver/core/control_bridge.py` 新規作成 (DEALER + SUB + PUB)
- [x] `controlserver/zmq_controller.py` 新規作成 (ROUTER + PUB + SUB + セッションマッピング)
- [x] `agentshell/log_sender.py` 新規作成 (ZMQ PUSH → ControlServer)

### Phase 3: 統合 ✅
- [x] ControlBridge → AgentServer 起動/停止に統合 (`api/server.py`)
- [x] ZMQController → ControlServer 起動/停止に統合 (`central_controller.py`)
- [x] LogSender → AgentShell PTY出力パスに統合 (`terminal_controller.py`)
- [x] PUB/SUB ログストリーム (AgentServer → ControlServer)
- [x] セッションマッピング (PTYセッション + AgentShell 関係追跡)

### Phase 4: 制御フロー実装 ✅
- [x] ControlServer → AgentServer: セッション停止 (send_to_session)
- [x] ControlServer → AgentServer: 入力ブロック/解除 (broadcast)
- [x] ControlServer PUB → AgentServer SUB: 緊急停止
- [x] ControlServer → AgentShell: コマンド送信 (send_to_shell → ControlCommandHandler._route_shell_command)
- [x] ブラウザ通知のWebSocket連携 (ControlCommandHandler._notify_clients)
- [x] _read_loop レースコンディション修正 (_start_read_loop 導入)
- [x] AgentServer 制御 REST API (`/api/control/*`)
- [x] ControlServer 管理 REST API (`/api/sessions/*`, `/api/emergency-stop`)

### Phase 5: AI分析パイプライン ✅
- [x] ログ PUB/SUB ストリーム → LLMLogAnalyzer 自動分析トリガー
- [x] 分析結果に基づく制御指示の自動発行 (high → 警告通知, critical → 自動ブロック)
- [x] AgentShell PUSH/PULL 直送パスと PUB/SUB パスの統合分析
- [x] ZMQController PULL ソケット (:8768) 追加
- [x] 生PTYバイト → 構造化ログエントリ変換
- [x] ZMQ経由の自動ブロック指示発行

### Phase 6: フロントエンド統一 ✅
- [x] Socket.IO クライアント除去
- [x] レガシー AetherTerm → tmux モード移行
- [x] paneStore → tmuxStore 統合
- [x] AetherTermService.ts, TerminalComponent.vue, AetherTermPage.vue 削除
- [x] レガシールート `/term/session` 削除
