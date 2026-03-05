"""ZMQ Agent-to-Agent Communication PoC

親プロセス(AgentServer相当)がZMQ ROUTERとして動作し、
子プロセス(AgentShell相当)をtmux paneで起動してDEALERで接続。
Agent間でDM/ブロードキャスト/タスク委任のメッセージングを行う。
"""
