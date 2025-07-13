# LLM とベクトルデータベース結合インターフェース

## 1. RAG (Retrieval-Augmented Generation) パターン

### 基本的な RAG フロー

```python
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import openai

class RAGInterface:
    def __init__(self, qdrant_url: str, collection_name: str):
        self.qdrant = QdrantClient(url=qdrant_url)
        self.collection = collection_name

    async def query_with_context(self, query: str) -> str:
        # 1. クエリをベクトル化
        query_vector = await self.embed_text(query)

        # 2. Qdrantから関連文書を検索
        search_results = self.qdrant.search(
            collection_name=self.collection,
            query_vector=query_vector,
            limit=5
        )

        # 3. 検索結果をコンテキストとしてLLMに渡す
        context = "\n".join([hit.payload["text"] for hit in search_results])

        prompt = f"""
        以下のコンテキストを使用して質問に答えてください：

        コンテキスト:
        {context}

        質問: {query}
        """

        # 4. LLMで回答生成
        response = await self.llm_complete(prompt)
        return response
```

## 2. LangChain 統合

### LangChain + Qdrant の実装

```python
from langchain.vectorstores import Qdrant
from langchain.embeddings import OpenAIEmbeddings
from langchain.chains import RetrievalQA
from langchain.llms import OpenAI

class LangChainQdrantInterface:
    def __init__(self):
        # Qdrantベクトルストアの初期化
        self.embeddings = OpenAIEmbeddings()
        self.vectorstore = Qdrant(
            client=QdrantClient(url="http://localhost:6333"),
            collection_name="terminal_logs",
            embeddings=self.embeddings
        )

        # RAGチェーンの構築
        self.qa_chain = RetrievalQA.from_chain_type(
            llm=OpenAI(temperature=0),
            chain_type="stuff",
            retriever=self.vectorstore.as_retriever(
                search_kwargs={"k": 5}
            )
        )

    async def query(self, question: str) -> str:
        return await self.qa_chain.arun(question)
```

## 3. LlamaIndex 統合

### LlamaIndex + Qdrant の実装

```python
from llama_index import VectorStoreIndex, ServiceContext
from llama_index.vector_stores import QdrantVectorStore
from llama_index.storage.storage_context import StorageContext

class LlamaIndexQdrantInterface:
    def __init__(self):
        # Qdrantベクトルストア設定
        vector_store = QdrantVectorStore(
            client=QdrantClient(url="http://localhost:6333"),
            collection_name="documents"
        )

        # ストレージコンテキスト
        storage_context = StorageContext.from_defaults(
            vector_store=vector_store
        )

        # インデックス作成
        self.index = VectorStoreIndex.from_documents(
            documents=[],  # 事前にロード済みのドキュメント
            storage_context=storage_context
        )

        # クエリエンジン
        self.query_engine = self.index.as_query_engine()

    async def query(self, query: str) -> str:
        response = await self.query_engine.aquery(query)
        return str(response)
```

## 4. セマンティック検索インターフェース

### 高度な検索とフィルタリング

```python
from qdrant_client.models import Filter, FieldCondition, MatchValue
from typing import List, Dict, Any

class SemanticSearchInterface:
    def __init__(self, qdrant_client: QdrantClient):
        self.client = qdrant_client

    async def hybrid_search(
        self,
        query: str,
        metadata_filters: Dict[str, Any],
        limit: int = 10
    ) -> List[Dict]:
        """ベクトル検索とメタデータフィルタリングの組み合わせ"""

        # クエリベクトル生成
        query_vector = await self.embed_text(query)

        # フィルター構築
        filters = []
        for key, value in metadata_filters.items():
            filters.append(
                FieldCondition(
                    key=key,
                    match=MatchValue(value=value)
                )
            )

        # 検索実行
        results = self.client.search(
            collection_name="logs",
            query_vector=query_vector,
            query_filter=Filter(must=filters),
            limit=limit,
            with_payload=True,
            with_vectors=False
        )

        return [
            {
                "id": hit.id,
                "score": hit.score,
                "content": hit.payload.get("content"),
                "metadata": hit.payload.get("metadata", {})
            }
            for hit in results
        ]
```

## 5. ストリーミング RAG インターフェース

### リアルタイムストリーミング対応

```python
import asyncio
from typing import AsyncIterator

class StreamingRAGInterface:
    def __init__(self, qdrant_client: QdrantClient, llm_client):
        self.qdrant = qdrant_client
        self.llm = llm_client

    async def stream_query(
        self,
        query: str,
        collection: str
    ) -> AsyncIterator[str]:
        """ストリーミングレスポンスを生成"""

        # 1. 関連文書を検索
        context_docs = await self.retrieve_context(query, collection)

        # 2. プロンプト構築
        prompt = self.build_prompt(query, context_docs)

        # 3. ストリーミング生成
        async for chunk in self.llm.stream_complete(prompt):
            yield chunk

    async def retrieve_context(
        self,
        query: str,
        collection: str,
        top_k: int = 5
    ) -> List[str]:
        query_vector = await self.embed_text(query)

        results = self.qdrant.search(
            collection_name=collection,
            query_vector=query_vector,
            limit=top_k
        )

        return [hit.payload["text"] for hit in results]
```

## 6. エージェント統合インターフェース

### LLM エージェントとベクトル DB の統合

```python
class AgentVectorDBInterface:
    def __init__(self):
        self.qdrant = QdrantClient(url="http://localhost:6333")
        self.tools = self._setup_tools()

    def _setup_tools(self):
        """エージェント用ツールの設定"""
        return {
            "search_logs": self.search_terminal_logs,
            "search_errors": self.search_error_patterns,
            "find_similar_commands": self.find_similar_commands,
            "analyze_context": self.analyze_context
        }

    async def search_terminal_logs(
        self,
        query: str,
        time_range: Optional[Tuple[datetime, datetime]] = None
    ) -> List[Dict]:
        """ターミナルログの意味的検索"""
        filters = []
        if time_range:
            filters.append(
                FieldCondition(
                    key="timestamp",
                    range={"gte": time_range[0], "lte": time_range[1]}
                )
            )

        return await self.hybrid_search(
            query=query,
            collection="terminal_logs",
            filters=filters
        )

    async def find_similar_commands(
        self,
        command: str,
        threshold: float = 0.8
    ) -> List[Dict]:
        """類似コマンドの検索"""
        command_vector = await self.embed_text(command)

        results = self.qdrant.search(
            collection_name="command_history",
            query_vector=command_vector,
            score_threshold=threshold,
            limit=10
        )

        return [
            {
                "command": hit.payload["command"],
                "success_rate": hit.payload["success_rate"],
                "avg_execution_time": hit.payload["avg_execution_time"],
                "similarity": hit.score
            }
            for hit in results
        ]
```

## 7. マルチモーダル検索インターフェース

### テキストと画像の統合検索

```python
from PIL import Image
import numpy as np

class MultiModalSearchInterface:
    def __init__(self, qdrant_client: QdrantClient):
        self.qdrant = qdrant_client
        self.text_encoder = self._load_text_encoder()
        self.image_encoder = self._load_image_encoder()

    async def search_by_screenshot(
        self,
        image_path: str,
        text_query: Optional[str] = None
    ) -> List[Dict]:
        """スクリーンショットによる検索"""

        # 画像ベクトル生成
        image = Image.open(image_path)
        image_vector = self.image_encoder.encode(image)

        # テキストクエリがある場合は結合
        if text_query:
            text_vector = await self.embed_text(text_query)
            # ベクトルの重み付け結合
            combined_vector = 0.7 * image_vector + 0.3 * text_vector
        else:
            combined_vector = image_vector

        # 検索実行
        results = self.qdrant.search(
            collection_name="terminal_screenshots",
            query_vector=combined_vector.tolist(),
            limit=5
        )

        return results
```

## 8. 実装例: ターミナルログ分析システム

### ControlServer 側の実装

```python
class TerminalLogVectorSystem:
    def __init__(self):
        self.qdrant = QdrantClient(url="http://localhost:6333")
        self._setup_collections()

    def _setup_collections(self):
        """コレクションの初期化"""
        collections = {
            "terminal_logs": 1536,  # OpenAI embedding dimension
            "error_patterns": 1536,
            "command_history": 1536,
            "user_interactions": 1536
        }

        for name, dim in collections.items():
            try:
                self.qdrant.create_collection(
                    collection_name=name,
                    vectors_config=VectorParams(
                        size=dim,
                        distance=Distance.COSINE
                    )
                )
            except:
                pass  # Collection already exists

    async def index_terminal_output(
        self,
        session_id: str,
        output: str,
        metadata: Dict[str, Any]
    ):
        """ターミナル出力のインデックス化"""
        # チャンク分割
        chunks = self._chunk_text(output, chunk_size=500)

        points = []
        for i, chunk in enumerate(chunks):
            vector = await self.embed_text(chunk)

            point = PointStruct(
                id=f"{session_id}_{metadata['timestamp']}_{i}",
                vector=vector,
                payload={
                    "session_id": session_id,
                    "content": chunk,
                    "timestamp": metadata["timestamp"],
                    "user": metadata.get("user"),
                    "command": metadata.get("command"),
                    "chunk_index": i,
                    "total_chunks": len(chunks)
                }
            )
            points.append(point)

        # バッチアップロード
        self.qdrant.upsert(
            collection_name="terminal_logs",
            points=points
        )

    async def intelligent_error_search(
        self,
        error_description: str,
        session_context: Optional[str] = None
    ) -> Dict[str, Any]:
        """インテリジェントエラー検索"""
        # エラーの意味的検索
        error_vector = await self.embed_text(error_description)

        similar_errors = self.qdrant.search(
            collection_name="error_patterns",
            query_vector=error_vector,
            limit=5
        )

        # LLMによる分析
        analysis_prompt = f"""
        エラー: {error_description}

        類似エラーパターン:
        {[err.payload for err in similar_errors]}

        セッションコンテキスト: {session_context}

        このエラーの原因と解決策を分析してください。
        """

        solution = await self.llm_analyze(analysis_prompt)

        return {
            "similar_errors": similar_errors,
            "analysis": solution,
            "confidence": self._calculate_confidence(similar_errors)
        }
```

## まとめ

主要なインターフェースパターン：

1. **RAG（Retrieval-Augmented Generation）**

   - 最も一般的なパターン
   - コンテキスト検索 → LLM 生成

2. **フレームワーク統合**

   - LangChain
   - LlamaIndex
   - Haystack

3. **セマンティック検索**

   - ベクトル類似性検索
   - メタデータフィルタリング

4. **ストリーミング対応**

   - リアルタイム応答
   - 逐次的なコンテキスト取得

5. **エージェント統合**

   - ツールとしてのベクトル DB
   - 自律的な情報検索

6. **マルチモーダル検索**
   - テキスト + 画像
   - 複合ベクトル検索

ターミナルアプリケーションでは、ログ分析、エラーパターンマッチング、コマンド推薦などにこれらのインターフェースを活用できます。
