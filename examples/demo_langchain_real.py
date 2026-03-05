#!/usr/bin/env python3
"""
実際のLangChainを使用したコマンドアナライザーデモ

LangChainのメモリ、チェーン、エージェント機能を活用して
高度なコマンド解析を実現します。
"""

import asyncio
import os
import re
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from langchain.memory import ConversationSummaryBufferMemory
    from langchain.schema import BaseMemory
    from langchain_openai import ChatOpenAI
    from langchain.chains import ConversationChain
    from langchain.prompts import PromptTemplate
    from langchain.callbacks import StdOutCallbackHandler
    from langchain.agents import AgentExecutor, create_react_agent
    from langchain.tools import Tool
    from langchain_core.messages import HumanMessage, AIMessage
except ImportError:
    print("LangChainがインストールされていません。以下のコマンドでインストールしてください：")
    print("pip install langchain langchain-openai")
    sys.exit(1)


class CommandAnalysisTool:
    """コマンド解析ツール"""
    
    def __init__(self):
        self.danger_patterns = {
            "root_delete": re.compile(r"rm\s+.*(-rf|-fr).*\s+/\s*($|\s)"),
            "format_disk": re.compile(r"(mkfs|format|fdisk)"),
            "dd_system": re.compile(r"dd.*of=/dev/(sda|hda|nvme0n1)"),
            "fork_bomb": re.compile(r":\(\)\{:\|:&\};:|:\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),
            "system_files": re.compile(r"(rm|dd|>).*(etc|bin|boot|sys)"),
        }
    
    def analyze(self, command: str) -> str:
        """コマンドを解析して結果を返す"""
        risk_level = self._assess_risk(command)
        issues = self._get_issues(command)
        
        result = f"コマンド: {command}\n"
        result += f"リスクレベル: {risk_level}\n"
        
        if issues:
            result += "問題点:\n"
            for issue in issues:
                result += f"- {issue}\n"
        
        if risk_level in ["DANGEROUS", "CRITICAL"]:
            result += "\n⚠️ このコマンドは危険です。実行前に十分注意してください。"
        
        return result
    
    def _assess_risk(self, command: str) -> str:
        """リスクレベルを評価"""
        if any(pattern.search(command) for pattern in [
            self.danger_patterns["fork_bomb"],
            self.danger_patterns["root_delete"],
            self.danger_patterns["dd_system"]
        ]):
            return "CRITICAL"
        
        if any(pattern.search(command) for pattern in [
            self.danger_patterns["format_disk"],
            self.danger_patterns["system_files"]
        ]):
            return "DANGEROUS"
        
        if command.startswith("sudo") or "rm -rf" in command:
            return "CAUTION"
        
        return "SAFE"
    
    def _get_issues(self, command: str) -> List[str]:
        """問題点を取得"""
        issues = []
        
        if self.danger_patterns["root_delete"].search(command):
            issues.append("ルートディレクトリの削除は非常に危険です")
        if self.danger_patterns["fork_bomb"].search(command):
            issues.append("フォーク爆弾を検出しました")
        if self.danger_patterns["dd_system"].search(command):
            issues.append("システムディスクへの直接書き込みは危険です")
        if self.danger_patterns["format_disk"].search(command):
            issues.append("ディスクのフォーマット操作を検出しました")
        if self.danger_patterns["system_files"].search(command):
            issues.append("システムファイルへの破壊的操作を検出しました")
        
        return issues


class LangChainCommandAnalyzer:
    """LangChainを使用したコマンドアナライザー"""
    
    def __init__(self, openai_api_key: Optional[str] = None):
        # OpenAI APIキーの設定
        if openai_api_key:
            os.environ["OPENAI_API_KEY"] = openai_api_key
        
        # LLMの初期化（GPT-3.5-turbo使用）
        self.llm = ChatOpenAI(
            temperature=0,
            model_name="gpt-3.5-turbo",
            callbacks=[StdOutCallbackHandler()]
        )
        
        # メモリの初期化（要約機能付き）
        self.memory = ConversationSummaryBufferMemory(
            llm=self.llm,
            max_token_limit=1000,
            return_messages=True
        )
        
        # コマンド解析ツール
        self.command_tool = CommandAnalysisTool()
        
        # プロンプトテンプレート
        self.prompt = PromptTemplate(
            input_variables=["history", "input"],
            template="""あなたはLinuxコマンドのセキュリティ専門家です。
ユーザーが入力したコマンドを解析し、安全性を評価してください。

過去の会話履歴:
{history}

ユーザーのコマンド: {input}

以下の観点で分析してください：
1. コマンドの目的と動作
2. 潜在的なリスクや危険性
3. より安全な代替案（もしあれば）
4. 過去のコマンドとの関連性

回答は日本語で、簡潔かつ分かりやすく説明してください。
"""
        )
        
        # 会話チェーンの作成
        self.chain = ConversationChain(
            llm=self.llm,
            memory=self.memory,
            prompt=self.prompt,
            verbose=True
        )
        
        # エージェントツールの定義
        self.tools = [
            Tool(
                name="command_analyzer",
                func=self.command_tool.analyze,
                description="Linuxコマンドのリスクレベルと問題点を解析する"
            )
        ]
    
    async def analyze_with_langchain(self, command: str) -> Dict[str, Any]:
        """LangChainを使用してコマンドを解析"""
        
        # 基本的な解析（ツール使用）
        basic_analysis = self.command_tool.analyze(command)
        
        # LangChainによる高度な解析
        try:
            # チェーンを使用して解析
            response = await asyncio.to_thread(
                self.chain.predict,
                input=f"{command}\n\n基本解析結果:\n{basic_analysis}"
            )
            
            # メモリから会話履歴を取得
            messages = self.memory.chat_memory.messages
            
            return {
                "command": command,
                "basic_analysis": basic_analysis,
                "ai_analysis": response,
                "conversation_length": len(messages),
                "memory_buffer": self.memory.moving_summary_buffer if hasattr(self.memory, 'moving_summary_buffer') else ""
            }
            
        except Exception as e:
            return {
                "command": command,
                "basic_analysis": basic_analysis,
                "error": str(e)
            }
    
    def get_memory_info(self) -> Dict[str, Any]:
        """メモリ情報を取得"""
        messages = self.memory.chat_memory.messages
        
        return {
            "total_messages": len(messages),
            "memory_type": type(self.memory).__name__,
            "has_summary": hasattr(self.memory, 'moving_summary_buffer'),
            "summary": self.memory.moving_summary_buffer if hasattr(self.memory, 'moving_summary_buffer') else None
        }


async def demo_langchain_analyzer():
    """LangChainアナライザーのデモ"""
    
    print("\n=== 実際のLangChainを使用したコマンドアナライザー ===\n")
    
    # APIキーの確認
    if not os.environ.get("OPENAI_API_KEY"):
        print("警告: OPENAI_API_KEYが設定されていません")
        print("実際のLLM機能を使用するには、環境変数OPENAI_API_KEYを設定してください")
        print("デモは基本的な解析機能のみで実行されます\n")
        
        # 基本機能のみのデモ
        tool = CommandAnalysisTool()
        test_commands = [
            "ls -la",
            "sudo apt update",
            "rm -rf /tmp/test",
            "rm -rf /",
            ":(){ :|:& };:"
        ]
        
        for cmd in test_commands:
            print(f"\nコマンド: {cmd}")
            result = tool.analyze(cmd)
            print(result)
            print("-" * 50)
        
        return
    
    # LangChainアナライザーの初期化
    analyzer = LangChainCommandAnalyzer()
    
    # テストコマンド
    test_commands = [
        "ls -la /home",
        "sudo systemctl restart nginx",
        "rm -rf /tmp/cache",
        "chmod 777 /etc/passwd",
        "rm -rf /"
    ]
    
    print("LangChainメモリとLLMを使用した解析を開始...\n")
    
    for i, cmd in enumerate(test_commands, 1):
        print(f"\n--- テスト {i}/{len(test_commands)} ---")
        
        result = await analyzer.analyze_with_langchain(cmd)
        
        if "error" in result:
            print(f"エラー: {result['error']}")
        else:
            print(f"\n基本解析:\n{result['basic_analysis']}")
            print(f"\nAI解析:\n{result['ai_analysis']}")
            print(f"\n会話履歴: {result['conversation_length']}メッセージ")
        
        await asyncio.sleep(1)  # レート制限を考慮
    
    # メモリ情報の表示
    memory_info = analyzer.get_memory_info()
    print(f"\n\n=== LangChainメモリ情報 ===")
    print(f"メモリタイプ: {memory_info['memory_type']}")
    print(f"総メッセージ数: {memory_info['total_messages']}")
    if memory_info['has_summary']:
        print(f"要約: {memory_info['summary']}")


async def main():
    """メイン関数"""
    try:
        await demo_langchain_analyzer()
    except KeyboardInterrupt:
        print("\n\nデモが中断されました")
    except Exception as e:
        print(f"\nエラー: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())