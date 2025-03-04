import subprocess
import time
import requests
import openai
import asyncio
import aiohttp
import os

class TabbyAPIEngine:
    def __init__(self, config_path="/src/config.yml", tabby_python_command="python3", tabby_main="/tabbyAPI/main.py"):
        self.config_path = config_path
        self.tabby_main = tabby_main
        self.tabby_python_command = tabby_python_command
        self.base_url = "http://127.0.0.1:5000"
        self.process = None
    
    def start_server(self):
        command = [
            self.tabby_python_command, self.tabby_main, "--config", self.config_path
        ]
        self.process = subprocess.Popen(command, stdout=None, stderr=None)

    def wait_for_server(self, timeout=900, interval=1):
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
            self, 
            stream=False, 
            **kwargs
    ):
        response = self.client.chat.completions.create(
            stream=stream,
            **kwargs
        )
        
        if stream:
            async for chunk in response:
                yield chunk.to_dict()
        else:
            yield response.to_dict()
    
    async def request_completions(
            self, 
            stream=False,
            **kwargs
    ):
        response = self.client.completions.create(
            stream=stream
            **kwargs
        )
        
        if stream:
            async for chunk in response:
                yield chunk.to_dict()
        else:
            yield response.to_dict()
    
    async def get_models(self):
        response = await self.client.models.list()
        return response
