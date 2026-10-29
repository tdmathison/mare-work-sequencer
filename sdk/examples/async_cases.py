"""Read authorized cases asynchronously; never writes data."""
import asyncio
from mws_sdk import AsyncMWSClient

async def main():
    async with AsyncMWSClient() as client:
        async for case in client.cases.iter_all(params={'limit':100}):
            print(case.number,case.name)

if __name__=='__main__':asyncio.run(main())
