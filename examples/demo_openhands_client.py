#!/usr/bin/env python3
"""
OpenHandsクライアントを使用したデモ

実際のOpenHandsクライアントライブラリを使用して
コード生成を行うデモです。
"""

import asyncio
import os
from typing import Any, Dict, Optional

try:
    # OpenHandsクライアントをインポート
    from openhands import OpenHands
    from openhands.types import CodeGenerationRequest, CodeGenerationResponse

    OPENHANDS_AVAILABLE = True
except ImportError:
    print("警告: OpenHandsクライアントがインストールされていません")
    print("インストール: pip install openhands")
    OPENHANDS_AVAILABLE = False


class OpenHandsCodeGenerator:
    """OpenHandsを使用したコード生成"""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.environ.get("OPENHANDS_API_KEY")
        self.client = None

        if OPENHANDS_AVAILABLE and self.api_key:
            try:
                self.client = OpenHands(api_key=self.api_key)
                print("✅ OpenHandsクライアントを初期化しました")
            except Exception as e:
                print(f"❌ OpenHands初期化エラー: {e}")

    async def generate_code(self, prompt: str, language: str = "python") -> Dict[str, Any]:
        """コードを生成"""
        if not self.client:
            return self._mock_generate(prompt, language)

        try:
            # OpenHandsにリクエスト
            request = CodeGenerationRequest(
                prompt=prompt, language=language, max_tokens=2000, temperature=0.7
            )

            response: CodeGenerationResponse = await self.client.generate_code(request)

            return {
                "success": True,
                "code": response.code,
                "language": response.language,
                "explanation": response.explanation,
            }

        except Exception as e:
            print(f"エラー: {e}")
            return {"success": False, "error": str(e)}

    def _mock_generate(self, prompt: str, language: str) -> Dict[str, Any]:
        """モック生成（OpenHandsが利用できない場合）"""
        prompt_lower = prompt.lower()

        if "計算機" in prompt or "calculator" in prompt_lower:
            code = '''class Calculator:
    """シンプルな計算機クラス"""
    
    def __init__(self):
        self.memory = 0
    
    def add(self, a: float, b: float) -> float:
        """加算"""
        return a + b
    
    def subtract(self, a: float, b: float) -> float:
        """減算"""
        return a - b
    
    def multiply(self, a: float, b: float) -> float:
        """乗算"""
        return a * b
    
    def divide(self, a: float, b: float) -> float:
        """除算"""
        if b == 0:
            raise ValueError("ゼロで除算することはできません")
        return a / b
    
    def store_memory(self, value: float):
        """メモリに保存"""
        self.memory = value
    
    def recall_memory(self) -> float:
        """メモリから呼び出し"""
        return self.memory
    
    def clear_memory(self):
        """メモリをクリア"""
        self.memory = 0


# 使用例
if __name__ == "__main__":
    calc = Calculator()
    
    # 基本的な計算
    print(f"10 + 5 = {calc.add(10, 5)}")
    print(f"20 - 8 = {calc.subtract(20, 8)}")
    print(f"7 * 6 = {calc.multiply(7, 6)}")
    print(f"15 / 3 = {calc.divide(15, 3)}")

    # メモリ機能
    calc.store_memory(42)
    print(f"メモリに保存: 42")
    print(f"メモリから呼び出し: {calc.recall_memory()}")'''

        elif "フィボナッチ" in prompt or "fibonacci" in prompt_lower:
            code = '''from typing import List, Iterator


def fibonacci_list(n: int) -> List[int]:
    """フィボナッチ数列をリストで返す
    
    Args:
        n: 生成する数列の長さ
        
    Returns:
        フィボナッチ数列のリスト
    """
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]
    
    fib = [0, 1]
    for i in range(2, n):
        fib.append(fib[i-1] + fib[i-2])
    
    return fib


def fibonacci_generator(n: int) -> Iterator[int]:
    """フィボナッチ数列のジェネレータ
    
    メモリ効率的な実装
    
    Args:
        n: 生成する数列の長さ
        
    Yields:
        フィボナッチ数
    """
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b


def fibonacci_recursive(n: int) -> int:
    """n番目のフィボナッチ数を再帰的に計算
    
    Args:
        n: 何番目のフィボナッチ数か（0から開始）
        
    Returns:
        n番目のフィボナッチ数
    """
    if n <= 1:
        return n
    return fibonacci_recursive(n-1) + fibonacci_recursive(n-2)


def fibonacci_memoized(n: int, memo: Dict[int, int] = None) -> int:
    """メモ化を使用した効率的な再帰実装
    
    Args:
        n: 何番目のフィボナッチ数か
        memo: メモ化用の辞書
        
    Returns:
        n番目のフィボナッチ数
    """
    if memo is None:
        memo = {}
    
    if n in memo:
        return memo[n]
    
    if n <= 1:
        return n
    
    memo[n] = fibonacci_memoized(n-1, memo) + fibonacci_memoized(n-2, memo)
    return memo[n]


# 使用例
if __name__ == "__main__":
    n = 10
    
    # リスト版
    print(f"最初の{n}個のフィボナッチ数（リスト）:")
    print(fibonacci_list(n))
    
    # ジェネレータ版
    print(f"\n最初の{n}個のフィボナッチ数（ジェネレータ）:")
    for num in fibonacci_generator(n):
        print(num, end=" ")
    print()
    
    # 特定の番号
    print(f"\n{n}番目のフィボナッチ数: {fibonacci_memoized(n)}")'''

        else:
            code = f'''# {prompt}

def generated_function():
    """OpenHandsによって生成された関数"""
    # TODO: 実装を追加
    pass

if __name__ == "__main__":
    generated_function()'''

        return {
            "success": True,
            "code": code,
            "language": language,
            "explanation": "モックモードで生成されたコードです",
        }


async def demo_with_langchain_integration():
    """LangChain統合のデモ"""
    print("\n" + "=" * 70)
    print("🚀 LangChain → OpenHandsクライアント デモ")
    print("=" * 70 + "\n")

    # OpenHandsクライアントを初期化
    generator = OpenHandsCodeGenerator()

    # テストケース
    test_cases = [
        {
            "prompt": "Pythonで計算機クラスを作成してください。加減乗除とメモリ機能を含めてください。",
            "task_type": "code_generation",
        },
        {
            "prompt": "効率的なフィボナッチ数列生成関数を実装してください。",
            "task_type": "code_generation",
        },
        {"prompt": "二分探索アルゴリズムを実装してください。", "task_type": "code_generation"},
    ]

    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'=' * 70}")
        print(f"テストケース {i}/{len(test_cases)}")
        print(f"{'=' * 70}")
        print(f"📝 プロンプト: {test_case['prompt']}")
        print(f"📋 タスクタイプ: {test_case['task_type']}")

        # LangChain風の判定（簡易版）
        print("\n🧠 LangChain分析:")
        print("   → コード生成タスクと判定")
        print("   → OpenHandsクライアントに委譲")

        # OpenHandsでコード生成
        print("\n🔄 OpenHandsクライアントで生成中...")
        result = await generator.generate_code(test_case["prompt"])

        if result["success"]:
            print("\n✅ コード生成成功！")
            print("\n💻 生成されたコード:")
            print("-" * 50)
            # 最初の30行を表示
            lines = result["code"].split("\n")[:30]
            for line in lines:
                print(f"   {line}")
            if len(result["code"].split("\n")) > 30:
                print("   ... (省略)")
            print("-" * 50)

            if "explanation" in result:
                print(f"\n📝 説明: {result['explanation']}")
        else:
            print(f"\n❌ エラー: {result.get('error', '不明なエラー')}")

        await asyncio.sleep(1)

    print("\n\n✨ デモ完了！")


async def main():
    """メイン関数"""
    print("\n⚠️  注意事項:")
    print("• OpenHandsクライアントが利用できない場合はモックモードで実行されます")
    print("• 実際のOpenHands APIを使用するには:")
    print("  1. pip install openhands")
    print("  2. export OPENHANDS_API_KEY=your-api-key")

    await demo_with_langchain_integration()


if __name__ == "__main__":
    asyncio.run(main())
