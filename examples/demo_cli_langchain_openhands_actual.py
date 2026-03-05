#!/usr/bin/env python3
"""
CLI → LangChain → OpenHands 実際の統合デモ（スタンドアロン版）

実際のOpenHandsサービスにHTTP/WebSocketで接続し、
コード生成タスクを委譲するデモです。
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import aiohttp

# ログ設定
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class OpenHandsClient:
    """OpenHandsサービスへの直接クライアント"""

    def __init__(self, endpoint: str = "http://localhost:3000"):
        self.endpoint = endpoint
        self.ws_endpoint = endpoint.replace("http://", "ws://").replace("https://", "wss://")
        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.connected = False

    async def connect(self) -> bool:
        """OpenHandsサービスに接続"""
        try:
            self.session = aiohttp.ClientSession()

            # ヘルスチェック
            async with self.session.get(f"{self.endpoint}/health") as resp:
                if resp.status == 200:
                    logger.info(f"OpenHandsサービスに接続しました: {self.endpoint}")
                    self.connected = True
                    return True

        except aiohttp.ClientConnectorError:
            logger.warning(f"OpenHandsサービスに接続できません: {self.endpoint}")
        except Exception as e:
            logger.error(f"接続エラー: {e}")

        self.connected = False
        return False

    async def submit_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """タスクをOpenHandsに送信"""
        if not self.connected:
            return {"success": False, "error": "Not connected to OpenHands service"}

        try:
            # タスクペイロード
            payload = {
                "task_id": str(uuid4()),
                "type": task_data.get("type", "code_generation"),
                "description": task_data.get("description", ""),
                "prompt": task_data.get("prompt", ""),
                "language": task_data.get("language", "python"),
                "context": task_data.get("context", {}),
                "timeout": task_data.get("timeout", 60),
            }

            # APIエンドポイントにPOST
            async with self.session.post(
                f"{self.endpoint}/api/tasks",
                json=payload,
                headers={"Content-Type": "application/json"},
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    return {"success": True, "task_id": result.get("task_id"), "result": result}
                error_text = await resp.text()
                return {"success": False, "error": f"HTTP {resp.status}: {error_text}"}

        except Exception as e:
            logger.error(f"タスク送信エラー: {e}")
            return {"success": False, "error": str(e)}

    async def get_task_result(self, task_id: str, timeout: int = 30) -> Dict[str, Any]:
        """タスク結果を取得（ポーリング）"""
        start_time = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start_time < timeout:
            try:
                async with self.session.get(f"{self.endpoint}/api/tasks/{task_id}") as resp:
                    if resp.status == 200:
                        data = await resp.json()

                        if data.get("status") == "completed":
                            return {
                                "success": True,
                                "code": data.get("result", {}).get("code", ""),
                                "output": data.get("result", {}),
                            }
                        if data.get("status") == "failed":
                            return {"success": False, "error": data.get("error", "Task failed")}

            except Exception as e:
                logger.error(f"結果取得エラー: {e}")

            await asyncio.sleep(1)

        return {"success": False, "error": "Timeout waiting for result"}

    async def disconnect(self):
        """切断"""
        if self.ws and not self.ws.closed:
            await self.ws.close()
        if self.session and not self.session.closed:
            await self.session.close()
        self.connected = False


class MockOpenHandsClient:
    """OpenHandsのモッククライアント（サービスが利用できない場合）"""

    def __init__(self):
        self.connected = True

    async def connect(self) -> bool:
        return True

    async def submit_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """モックタスク送信"""
        task_type = task_data.get("type", "code_generation")
        prompt = task_data.get("prompt", "")

        # タスクIDを生成
        task_id = str(uuid4())

        return {"success": True, "task_id": task_id, "result": {"status": "queued"}}

    async def get_task_result(self, task_id: str, timeout: int = 30) -> Dict[str, Any]:
        """モック結果を生成"""
        # 少し待機してリアルな感じを演出
        await asyncio.sleep(2)

        # モックコードを生成
        code_templates = {
            "calculator": '''class Calculator:
    """計算機クラス"""
    
    def __init__(self):
        self.result = 0
    
    def add(self, a: float, b: float) -> float:
        """加算"""
        self.result = a + b
        return self.result
    
    def subtract(self, a: float, b: float) -> float:
        """減算"""
        self.result = a - b
        return self.result
    
    def multiply(self, a: float, b: float) -> float:
        """乗算"""
        self.result = a * b
        return self.result
    
    def divide(self, a: float, b: float) -> float:
        """除算"""
        if b == 0:
            raise ValueError("Cannot divide by zero")
        self.result = a / b
        return self.result

# 使用例
if __name__ == "__main__":
    calc = Calculator()
    print(f"10 + 5 = {calc.add(10, 5)}")
    print(f"10 - 3 = {calc.subtract(10, 3)}")''',
            "fibonacci": '''def fibonacci(n: int) -> List[int]:
    """フィボナッチ数列を生成
    
    Args:
        n: 生成する数列の長さ
        
    Returns:
        フィボナッチ数列のリスト
    """
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    
    return fib[:n]

def fibonacci_generator(n: int):
    """フィボナッチ数列のジェネレータ版"""
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# 使用例
if __name__ == "__main__":
    print("最初の10個:", fibonacci(10))
    print("ジェネレータ版:", list(fibonacci_generator(10)))''',
            "default": '''# OpenHandsによって生成されたコード

def generated_function():
    """自動生成された関数"""
    # TODO: 実装を追加
    pass

if __name__ == "__main__":
    generated_function()''',
        }

        # タスクIDに基づいてテンプレートを選択（簡易的に）
        if "計算" in str(task_id):
            code = code_templates["calculator"]
        elif "フィボナッチ" in str(task_id):
            code = code_templates["fibonacci"]
        else:
            code = code_templates["default"]

        return {
            "success": True,
            "code": code,
            "output": {
                "code": code,
                "language": "python",
                "generated_at": datetime.now().isoformat(),
            },
        }

    async def disconnect(self):
        pass


class SimpleLangChainAnalyzer:
    """シンプルなLangChain風アナライザー"""

    def __init__(self):
        self.patterns = {
            "code_generation": [
                "作成",
                "作って",
                "実装",
                "書いて",
                "コード",
                "generate",
                "create",
                "implement",
            ],
            "explanation": ["説明", "教えて", "とは", "何", "explain", "what is"],
            "optimization": ["最適化", "改善", "高速化", "optimize", "improve"],
            "debug": ["デバッグ", "修正", "直して", "バグ", "debug", "fix"],
        }

    def analyze(self, user_input: str) -> Dict[str, Any]:
        """ユーザー入力を分析"""
        user_input_lower = user_input.lower()

        # タスクタイプを判定
        task_type = "unknown"
        confidence = 0.0

        for t_type, keywords in self.patterns.items():
            matches = sum(1 for kw in keywords if kw in user_input_lower)
            if matches > 0:
                score = matches / len(keywords)
                if score > confidence:
                    task_type = t_type
                    confidence = score

        # OpenHandsに委譲すべきか判定
        should_delegate = task_type in ["code_generation", "optimization", "debug"]

        # 応答を生成
        if should_delegate:
            response = f"{task_type}タスクとして認識しました。OpenHandsに委譲します。"
        else:
            response = self._generate_explanation(user_input, task_type)

        return {
            "task_type": task_type,
            "confidence": confidence,
            "should_delegate": should_delegate,
            "response": response,
        }

    def _generate_explanation(self, query: str, task_type: str) -> str:
        """説明を生成"""
        if task_type == "explanation":
            if "langchain" in query.lower():
                return "LangChainは、大規模言語モデル（LLM）を活用したアプリケーション開発フレームワークです。"
            if "openhands" in query.lower():
                return "OpenHandsは、AIによるコード生成とソフトウェア開発を支援するプラットフォームです。"
            return f"{query}についての説明は準備中です。"

        return "申し訳ありません。このリクエストは理解できませんでした。"


class CLILangChainOpenHandsSystem:
    """統合システム"""

    def __init__(self, openhands_endpoint: str = "http://localhost:3000", use_mock: bool = False):
        self.analyzer = SimpleLangChainAnalyzer()

        if use_mock:
            logger.info("モックモードで実行します")
            self.openhands = MockOpenHandsClient()
        else:
            self.openhands = OpenHandsClient(openhands_endpoint)

        self.history = []
        self.use_mock = use_mock

    async def initialize(self):
        """システムを初期化"""
        connected = await self.openhands.connect()

        if not connected and not self.use_mock:
            logger.warning("OpenHandsサービスに接続できません。モックモードに切り替えます。")
            self.openhands = MockOpenHandsClient()
            await self.openhands.connect()

        return True

    async def process_input(self, user_input: str) -> Dict[str, Any]:
        """ユーザー入力を処理"""
        # LangChain風の分析
        analysis = self.analyzer.analyze(user_input)

        result = {
            "user_input": user_input,
            "analysis": analysis,
            "delegated_to_openhands": False,
            "openhands_result": None,
            "timestamp": datetime.now().isoformat(),
        }

        # OpenHandsに委譲が必要な場合
        if analysis["should_delegate"]:
            logger.info("OpenHandsにタスクを委譲します")

            # タスクデータを構築
            task_data = {
                "type": analysis["task_type"],
                "description": user_input,
                "prompt": user_input,
                "language": "python",
                "context": {
                    "confidence": analysis["confidence"],
                    "history_length": len(self.history),
                },
            }

            # OpenHandsに送信
            submit_result = await self.openhands.submit_task(task_data)

            if submit_result["success"]:
                task_id = submit_result["task_id"]
                logger.info(f"タスクID: {task_id}")

                # 結果を待機
                task_result = await self.openhands.get_task_result(task_id)

                if task_result["success"]:
                    result["delegated_to_openhands"] = True
                    result["openhands_result"] = task_result
                else:
                    result["error"] = task_result.get("error", "Unknown error")
            else:
                result["error"] = submit_result.get("error", "Failed to submit task")

        # 履歴に追加
        self.history.append(result)

        return result

    async def shutdown(self):
        """シャットダウン"""
        await self.openhands.disconnect()


async def run_demo():
    """デモを実行"""
    print("\n" + "=" * 70)
    print("🚀 CLI → LangChain → OpenHands 実際の統合デモ")
    print("=" * 70)
    print("\n📌 OpenHandsサービスへの接続を試みます...")
    print("   接続できない場合はモックモードで実行されます\n")

    # システムの初期化（最初は実際のサービスに接続を試みる）
    system = CLILangChainOpenHandsSystem(use_mock=False)
    await system.initialize()

    # テストケース
    test_cases = [
        "Pythonで計算機クラスを作成してください",
        "LangChainについて説明してください",
        "フィボナッチ数列を生成する効率的な関数を実装してください",
        "for i in range(len(list)): print(list[i]) を最適化してください",
    ]

    for i, test_input in enumerate(test_cases, 1):
        print(f"\n{'=' * 70}")
        print(f"テストケース {i}/{len(test_cases)}")
        print(f"{'=' * 70}")
        print(f"📝 入力: {test_input}")

        # 処理実行
        print("\n🔄 処理中...")
        result = await system.process_input(test_input)

        # 結果表示
        print("\n📊 分析結果:")
        print(f"   タスクタイプ: {result['analysis']['task_type']}")
        print(f"   信頼度: {result['analysis']['confidence']:.2f}")
        print(f"   LangChain応答: {result['analysis']['response']}")

        if result["delegated_to_openhands"]:
            print("\n✅ OpenHandsへの委譲: 成功")

            if result["openhands_result"] and result["openhands_result"]["success"]:
                code = result["openhands_result"]["code"]
                print("\n💻 生成されたコード:")
                print("-" * 50)
                # 最初の15行を表示
                lines = code.split("\n")[:15]
                for line in lines:
                    print(f"   {line}")
                if len(code.split("\n")) > 15:
                    print("   ... (省略)")
                print("-" * 50)
        else:
            print("\n💬 LangChainが直接処理しました")

        # エラーがある場合
        if "error" in result:
            print(f"\n❌ エラー: {result['error']}")

        await asyncio.sleep(1)

    # 統計表示
    print(f"\n\n{'=' * 70}")
    print("📊 実行統計")
    print(f"{'=' * 70}")
    print(f"総タスク数: {len(system.history)}")
    delegated = sum(1 for r in system.history if r["delegated_to_openhands"])
    print(f"OpenHandsに委譲: {delegated}")
    print(f"LangChain直接処理: {len(system.history) - delegated}")

    await system.shutdown()
    print("\n✨ デモ完了！")


async def main():
    """メイン関数"""
    import argparse

    parser = argparse.ArgumentParser(description="CLI → LangChain → OpenHands 実際の統合デモ")
    parser.add_argument(
        "--endpoint", default="http://localhost:3000", help="OpenHandsサービスのエンドポイント"
    )
    parser.add_argument("--mock", action="store_true", help="モックモードで実行")
    args = parser.parse_args()

    if args.mock:
        # 明示的にモックモードを指定
        system = CLILangChainOpenHandsSystem(use_mock=True)
        await system.initialize()
        print("🎭 モックモードで実行中...")

    await run_demo()


if __name__ == "__main__":
    asyncio.run(main())
