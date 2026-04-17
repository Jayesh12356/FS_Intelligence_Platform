"""Quick check: verify provider API after Cursor LLM upgrade."""
import httpx
import asyncio

async def main():
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get("http://localhost:8000/api/orchestration/providers")
        for p in r.json()["data"]:
            print(f"  {p['name']}: caps={p['capabilities']}, llm_sel={p['llm_selectable']}, healthy={p['healthy']}")

        print()
        # Also test selecting cursor as LLM provider
        r2 = await client.put("http://localhost:8000/api/orchestration/config", json={"llm_provider": "cursor"})
        cfg = r2.json()
        print(f"  Config update: llm_provider={cfg['data']['llm_provider']}")
        assert cfg["data"]["llm_provider"] == "cursor", "Failed to set cursor as LLM provider"

        # Reset back to api
        await client.put("http://localhost:8000/api/orchestration/config", json={"llm_provider": "api"})
        print("  Reset back to api: OK")

asyncio.run(main())
print("\nAll checks passed!")
