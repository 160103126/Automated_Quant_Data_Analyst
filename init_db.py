import asyncio
import os

from mcp import ClientSession
from mcp.client.sse import sse_client


MCP_GATEWAY_URL = os.getenv("MCP_GATEWAY_URL", "http://localhost:8000").rstrip("/")


async def write_query(session: ClientSession, query: str) -> None:
    result = await session.call_tool("write_query", {"query": query})
    if getattr(result, "isError", False):
        text = "\n".join(getattr(item, "text", "") for item in result.content)
        raise RuntimeError(text)


async def main() -> None:
    async with sse_client(f"{MCP_GATEWAY_URL}/servers/sqlite/sse") as streams:
        async with ClientSession(*streams) as session:
            await session.initialize()

            await write_query(
                session,
                """
                CREATE TABLE IF NOT EXISTS daily_prices (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    close_price REAL,
                    volume INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(ticker, date)
                )
                """,
            )

            await write_query(
                session,
                """
                CREATE TABLE IF NOT EXISTS technical_indicators (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    sma_50 REAL,
                    sma_200 REAL,
                    rsi REAL,
                    volatility_20d_annualized REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(ticker, date)
                )
                """,
            )

            await write_query(
                session,
                """
                CREATE TABLE IF NOT EXISTS market_sentiment (
                    ticker TEXT NOT NULL,
                    date TEXT NOT NULL,
                    news_summary TEXT,
                    sentiment_score REAL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(ticker, date)
                )
                """,
            )

    print("Database tables initialized successfully.")


if __name__ == "__main__":
    asyncio.run(main())
