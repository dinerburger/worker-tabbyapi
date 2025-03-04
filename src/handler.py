import asyncio
import aiohttp
import requests
from engine import TabbyAPIEngine, OpenAIRequest
from utils import process_response
import runpod
import json
import os

CONFIG_PATH = os.getenv("CONFIG_PATH", "/src/config.yml")
TABBY_MAIN = os.getenv("TABBY_MAIN", "/tabbyAPI/main.py")
TABBY_PYTHON_COMMAND = os.getenv("TABBY_PYTHON_COMMAND", "python3")

# Initialize the engine
engine = TabbyAPIEngine(CONFIG_PATH, TABBY_PYTHON_COMMAND, TABBY_MAIN)
engine.start_server()
engine.wait_for_server()

oai_req = OpenAIRequest()

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
    job_input = job["input"]
    print(f"JOB_INPUT: {json.dumps(job_input)}")
    
    if job_input.get("openai_route"):
        openai_route, openai_input = job_input.get("openai_route"), job_input.get("openai_input")
        openai_url = f"{engine.base_url}{openai_route}"
        headers = {"Content-Type": "application/json"}
        if openai_route.startswith("/v1/model"):
            response = requests.get(openai_url, headers=headers, json=openai_input)
            yield response.text

        elif openai_route == "/v1/chat/completions" or openai_route == "/v1/completions":
            response = requests.post(openai_url, headers=headers, json=openai_input)
        
            if openai_input.get("stream", False):
                # streamed response code
                for formated_chunk in process_response(response):
                    yield formated_chunk
            else:
                # non-streamed response code
                for chunk in response.iter_lines():
                    if chunk:
                        decoded_chunk = chunk.decode('utf-8')
                        yield decoded_chunk        
    else:
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