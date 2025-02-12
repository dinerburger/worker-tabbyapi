import subprocess
import time
import requests
import openai
import asyncio
import aiohttp
import os

class TabbyAPIEngine:
    def __init__(self, config_path="/src/config.yml"):
        self.config_path = config_path
        self.base_url = "http://127.0.0.1:5000"
        self.process = None
    
    def start_server(self):
        command = [
            "python3", "/tabbyAPI/main.py", "--config", self.config_path
        ]
        self.process = subprocess.Popen(command, stdout=None, stderr=None)

    def wait_for_server(self, timeout=900, interval=5):
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{self.base_url}/v1/models")
                if response.status_code == 200:
                    print("Server is ready!")
                    return True
            except requests.RequestException:
                pass
            time.sleep(interval)
        raise TimeoutError("Server failed to start within the timeout period.")

    def shutdown(self):
        if self.process:
            self.process.terminate()
            self.process.wait()
            print("Server shut down.")

class OpenAIRequest:
    def __init__(self, base_url="http://127.0.0.1:5000/v1", api_key="xx"):
        self.client = openai.Client(base_url=base_url, api_key=api_key)
    
    async def request_chat_completions(
            self, model="default", 
            messages=None, 
            max_tokens=100, 
            stream=False, 
            frequency_penalty=0.0, 
            n=1, 
            stop=None, 
            temperature=1.0, 
            top_p=1.0
    ):
        if messages is None:
            messages = [
                {"role": "system", "content": "You are a helpful AI assistant"},
                {"role": "user", "content": "List 3 countries and their capitals."},
            ]
        
        response = self.client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            stream=stream,frequency_penalty=frequency_penalty,
            n=n,
            stop=stop,
            temperature=temperature,
            top_p=top_p
        )
        
        if stream:
            async for chunk in response:
                yield chunk.to_dict()
        else:
            yield response.to_dict()
    
    async def request_completions(
            self, 
            model="default", 
            prompt="The capital of France is", 
            max_tokens=100, 
            stream=False, 
            frequency_penalty=0.0, 
            n=1, 
            stop=None, 
            temperature=1.0, 
            top_p=1.0
    ):
        response = self.client.completions.create(
            model=model,
            prompt=prompt,
            max_tokens=max_tokens,
            stream=stream,
            frequency_penalty=frequency_penalty,
            n=n,
            stop=stop,
            temperature=temperature,
            top_p=top_p
        )
        
        if stream:
            async for chunk in response:
                yield chunk.to_dict()
        else:
            yield response.to_dict()
    
    async def get_models(self):
        response = await self.client.models.list()
        return response
