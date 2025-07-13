# AetherTerm TODO Tracking

This document tracks TODO items found in the codebase that represent future work items.

## Backend TODOs

### Memory System
- [ ] **hierarchical_memory.py:402** - 全体統計を取得するメソッドが必要
- [ ] **hierarchical_memory.py:438** - 平均関連度スコア、最もアクセスされたエントリ、最古/最新エントリの計算
- [ ] **hierarchical_memory.py:471** - SQLから古い会話IDを取得し、それらの埋め込みをVector Storeから削除するロジックが必要
- [ ] **conversation_memory.py:264** - 全体統計を取得するメソッドをSQLStorageAdapterに追加する必要がある
- [ ] **session_memory.py:265** - 全体統計を取得するロジックを実装

### API/Routes
- [ ] **session_routes.py:39** - Implement proper session listing when terminal sessions are implemented
- [ ] **spec_routes.py:51** - ベクトルストレージに保存して検索可能にする
- [ ] **spec_routes.py:79** - ベクトル検索で関連仕様を取得
- [ ] **spec_routes.py:115** - ストレージから仕様一覧を取得

### WebSocket/Handlers
- [ ] **socket_handlers.py:873** - Implement auto-blocking feature
- [ ] **socket_handlers.py:1103** - VectorStorageAdapterへの保存実装
- [ ] **socket_handlers.py:1153** - ベクトル検索で関連仕様を取得
- [ ] **terminal_handler.py:125** - Implement delayed closure

### Server
- [ ] **server.py:536** - Add unblock handlers when implemented

### Short-term Memory
- [ ] **short_term_memory.py:3** - Implement proper short-term memory functionality

## Frontend TODOs

None found - frontend code is clean of TODO comments.

## Notes

These TODOs represent legitimate future work items and should be tracked in the project's issue tracking system rather than as inline comments. They are preserved here for reference.