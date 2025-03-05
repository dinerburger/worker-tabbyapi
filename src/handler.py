
import sys
import os

# ok this is wack, I know but hear me out.
# we need to add tabby to the python resolver path, but also we want to cleanly support
# local development, so in the Dockerfile we export TABBY_PATH to where it should be 
# I'm working fast here give me a break
tabbypath = os.getenv(
    "TABBY_PATH",
    os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "builder", "tabbyAPI")))
sys.path.append(tabbypath)

import asyncio
import aiohttp
import requests
from engine import TabbyAPIEngine
import runpod
import json

# Initialize the engine
CONFIG_PATH = os.getenv("CONFIG_PATH", "/src/config.yml")
engine = TabbyAPIEngine(CONFIG_PATH)
def get_max_concurrency(default=50):
    """
    Returns the maximum concurrency value.
    By default, it uses 50 unless the 'MAX_CONCURRENCY' environment variable is set.

    Args:
        default (int): The default concurrency value if the environment variable is not set.

    Returns:
        int: The maximum concurrency value.
    """
    return int(os.getenv('MAX_CONCURRENCY', default))


async def async_handler(job):
    """Handle the requests asynchronously."""
    job_id = job["id"]
    job_input = job["input"]
    print(f"JOB_INPUT: {json.dumps(job_input)}")
    
    if job_input.get("openai_route"):
        openai_route, openai_input = job_input.get("openai_route"), job_input.get("openai_input")
        headers = {"Content-Type": "application/json"}
        if openai_route == "/v1/chat/completions":
            stream = openai_input.get("stream", False)
            if stream:
                async for chunk in engine.stream_generate_chat_completion(openai_input, job_id):
                    yield chunk
            else:
                result = await engine.generate_chat_completion(openai_input, job_id)
                yield result
        elif openai_route == "/v1/completions":
            stream = openai_input.get("stream", False)
            if stream:
                async for chunk in engine.stream_generate_completion(openai_input, job_id):
                    yield chunk
            else:
                result = await engine.generate_completion(openai_input, job_id)
                yield result
        else:
            raise Exception("Not implemented")
    else:
        raise Exception("Not implemented")
        generate_url = f"{engine.base_url}/generate"
        headers = {"Content-Type": "application/json"}
        # Directly pass `job_input` to `json`. Can we tell users the possible fields of `job_input`?
        response = requests.post(generate_url, json=job_input, headers=headers)
        if response.status_code == 200:
            yield response.json()
        else:
            yield {"error": f"Generate request failed with status code {response.status_code}", "details": response.text}

runpod.serverless.start({
    "handler": async_handler, 
    "concurrency_modifier": get_max_concurrency, 
    "return_aggregate_stream": True})