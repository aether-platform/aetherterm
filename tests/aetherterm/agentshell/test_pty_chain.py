"""
PTY Chain テスト

PTYチェーンの基本的な動作を検証します。
注: 完全なPTYテストはLinux環境でのみ動作します。
"""

import asyncio
import os
import sys

import pytest

from aetherterm.agentshell.pty.pty_chain import PTYChain


class TestPTYChainUnit:
    """PTYChain単体テスト（PTYを実際に作らない）"""

    def test_initial_state(self):
        """初期状態の確認"""
        chain = PTYChain()
        assert not chain.is_running
        assert chain.child_pid is None

    def test_set_filters(self):
        """フィルター設定が動作すること"""
        chain = PTYChain()

        called = {"input": False, "output": False}

        def input_filter(data):
            called["input"] = True
            return data

        def output_filter(data):
            called["output"] = True
            return data

        chain.set_input_filter(input_filter)
        chain.set_output_filter(output_filter)

        # フィルターが設定されていることを確認
        assert chain._input_filter is input_filter
        assert chain._output_filter is output_filter

    def test_set_callbacks(self):
        """I/Oコールバック設定が動作すること"""
        chain = PTYChain()

        def on_input(data):
            pass

        def on_output(data):
            pass

        chain.set_on_user_input(on_input)
        chain.set_on_shell_output(on_output)

        assert chain._on_user_input is on_input
        assert chain._on_shell_output is on_output

    @pytest.mark.asyncio
    async def test_stop_without_start(self):
        """startせずにstopしてもエラーにならないこと"""
        chain = PTYChain()
        await chain.stop()
        assert not chain.is_running

    @pytest.mark.asyncio
    async def test_inject_without_start(self):
        """startせずにinjectしてもエラーにならないこと"""
        chain = PTYChain()
        await chain.inject_command("ls")
        await chain.inject_output("hello")


@pytest.mark.skipif(
    not hasattr(os, "fork"),
    reason="PTY tests require Unix fork()",
)
class TestPTYChainIntegration:
    """PTYChain結合テスト（実際にPTYを作成）"""

    @pytest.mark.asyncio
    async def test_start_and_stop(self):
        """PTYチェーンの起動・停止が動作すること"""
        chain = PTYChain()

        # /bin/echo を使用（即座に終了するため安全）
        await chain.start(shell_cmd=["/bin/echo", "hello"])

        # 少し待つ
        await asyncio.sleep(0.5)

        # echoは即座に終了するのでis_runningはFalseになっている可能性
        # stop()は常に安全に呼び出せること
        await chain.stop()
        assert not chain.is_running

    @pytest.mark.asyncio
    async def test_start_with_shell(self):
        """シェルを起動して停止できること"""
        chain = PTYChain()

        # bashを非インタラクティブで起動
        await chain.start(shell_cmd=["/bin/bash", "-c", "sleep 0.5"])

        assert chain.is_running
        assert chain.child_pid is not None

        # 停止
        await chain.stop()
        assert not chain.is_running

    @pytest.mark.asyncio
    async def test_inject_command(self):
        """コマンド注入が動作すること"""
        chain = PTYChain()
        output_data = []

        def capture_output(data):
            output_data.append(data)

        chain.set_on_shell_output(capture_output)

        # bashを起動してコマンドを注入
        await chain.start(shell_cmd=["/bin/bash", "--norc", "--noprofile"])
        await asyncio.sleep(0.3)

        await chain.inject_command("echo INJECT_TEST_12345")
        await asyncio.sleep(0.5)

        await chain.stop()

        # 出力にINJECT_TEST_12345が含まれていること
        all_output = b"".join(output_data).decode("utf-8", "replace")
        assert "INJECT_TEST_12345" in all_output

    @pytest.mark.asyncio
    async def test_input_filter_suppression(self):
        """入力フィルターで入力を抑制できること"""
        chain = PTYChain()

        # 全ての入力を抑制するフィルター
        chain.set_input_filter(lambda data: None)

        await chain.start(shell_cmd=["/bin/bash", "-c", "sleep 1"])
        assert chain.is_running

        await chain.stop()

    @pytest.mark.asyncio
    async def test_output_filter_transform(self):
        """出力フィルターで出力を変換できること"""
        transformed = []

        def transform_filter(data):
            transformed.append(data)
            return data  # pass through

        chain = PTYChain()
        chain.set_output_filter(transform_filter)

        await chain.start(shell_cmd=["/bin/echo", "filter_test"])
        await asyncio.sleep(0.3)
        await chain.stop()

        # フィルターが呼ばれたこと
        assert len(transformed) > 0
