import asyncio
from backend.pipeline import PipelineManager

async def main():
    pm = PipelineManager()
    job_id = await pm.create_job("https://amzn.in/d/02x2P9Ee")
    print(f"Running job {job_id}")
    await pm.run_job(job_id)
    status = await pm.get_status(job_id)
    print("Final status:", status)

if __name__ == "__main__":
    asyncio.run(main())
