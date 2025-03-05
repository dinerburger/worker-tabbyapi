import subprocess
import time
from typing import List
import requests
import asyncio
import aiohttp
import os
import pathlib
import yaml
from loguru import logger
from common.networking import get_generator_error, handle_request_error
from common.tabby_config import config

from endpoints.OAI.types.chat_completion import ChatCompletionRequest
from endpoints.OAI.utils.chat_completion import (
  _create_response as _create_response_chat_completion,
  _create_stream_chunk, 
  _stream_collector as _stream_collector_chat_completion, 
  apply_chat_template
)

from endpoints.OAI.types.completion import CompletionRequest
from endpoints.OAI.utils.completion import (
  _create_response as _create_response_completion, 
  _stream_collector as _stream_collector_completion
)
from common import model

class TabbyAPIEngine:
    def __init__(self, config_path:str):
        config.load({"config": {"config": config_path}})
        model_path = pathlib.Path(config.model.model_dir)
        model_path = model_path / config.model.model_name
        asyncio.run(model.load_model(
            model_path.resolve(),
            **config.model.model_dump(exclude_none=True),
            draft_model=config.draft_model.model_dump(exclude_none=True),
        ))

        # Load loras after loading the model
        if config.lora.loras:
            lora_dir = pathlib.Path(config.lora.lora_dir)
            # TODO: remove model_dump()
            asyncio.run(model.container.load_loras(
                lora_dir.resolve(), **config.lora.model_dump()
            ))

        
        # If an initial embedding model name is specified, create a separate container
        # and load the model
        embedding_model_name = config.embeddings.embedding_model_name
        if embedding_model_name:
            embedding_model_path = pathlib.Path(config.embeddings.embedding_model_dir)
            embedding_model_path = embedding_model_path / embedding_model_name

            try:
                # TODO: remove model_dump()
                asyncio.run(model.load_embedding_model(
                    embedding_model_path, **config.embeddings.model_dump()
                ))
            except ImportError as ex:
                logger.error(ex.msg)

    async def generate_completion(
        self, data: CompletionRequest, req_id: str
    ):
        """Non-streaming generate for completions"""
        data = CompletionRequest(**data)
        gen_tasks: List[asyncio.Task] = []
        try:
            logger.info(f"Recieved completion request {req_id}")

            for _ in range(0, data.n):
                task_gen_params = data.model_copy(deep=True)

                gen_tasks.append(
                    asyncio.create_task(
                        model.container.generate(
                            data.prompt,
                            req_id,
                            **task_gen_params.model_dump(exclude={"prompt"}),
                        )
                    )
                )

            generations = await asyncio.gather(*gen_tasks)
            response = _create_response_completion(req_id, generations)
            logger.info(f"Finished completion request {req_id}")
            return response
        except Exception as exc:
            error_message = handle_request_error(
                f"Completion {req_id} aborted. Maybe the model was unloaded? "
                "Please check the server console."
            ).error.message

            # Server error if there's a generation exception
            raise Exception(error_message)

    async def stream_generate_completion(
        self, data: CompletionRequest, req_id: str
    ):
        """Streaming generation for completions."""
        data = CompletionRequest(**data)
        abort_event = asyncio.Event()
        gen_queue = asyncio.Queue()
        gen_tasks: List[asyncio.Task] = []

        try:
            logger.info(f"Received streaming completion request {req_id}")

            for n in range(0, data.n):
                task_gen_params = data.model_copy(deep=True)

                gen_task = asyncio.create_task(
                    _stream_collector_completion(
                        n,
                        gen_queue,
                        data.prompt,
                        req_id,
                        abort_event,
                        **task_gen_params.model_dump(exclude={"prompt"}),
                    )
                )

                gen_tasks.append(gen_task)

            # Consumer loop
            while True:
                generation = await gen_queue.get()

                # Stream collector will push an exception to the queue if it fails
                if isinstance(generation, Exception):
                    raise generation

                response = _create_response_completion(req_id, generation)
                yield response.model_dump_json()

                # Check if all tasks are completed
                if all(task.done() for task in gen_tasks) and gen_queue.empty():
                    yield "[DONE]"
                    logger.info(f"Finished streaming completion request {req_id}")
                    break
        except Exception:
            yield get_generator_error(
                f"Completion {req_id} aborted. Please check the server console."
            )

    async def generate_chat_completion(
        self,
        data: ChatCompletionRequest,
        req_id: str
    ):
        data = ChatCompletionRequest(**data)
        prompt, embeddings = await apply_chat_template(data)
        gen_tasks: List[asyncio.Task] = []

        try:
            for _ in range(0, data.n):
                gen_tasks.append(
                    asyncio.create_task(
                        model.container.generate(
                            prompt,
                            req_id,
                            embeddings=embeddings,
                            **data.model_dump(exclude={"prompt"}),
                        )
                    )
                )

            generations = await asyncio.gather(*gen_tasks)

            # Let's not waste our time if we arn't running a tool model
            if data.tool_call_start:
                generations = await self.generate_tool_calls(data, generations, req_id)

            response = _create_response_chat_completion(req_id, generations)

            logger.info(f"Finished chat completion request {req_id}")

            return response
        except Exception as exc:
            error_message = handle_request_error(
                f"Chat completion {req_id} aborted. "
                "Maybe the model was unloaded? "
                "Please check the server console."
            ).error.message

            # Server error if there's a generation exception
            raise Exception(error_message) from exc

    async def stream_generate_chat_completion(
        self,
        data: ChatCompletionRequest,
        req_id: str
    ):
        """Generator for the generation process."""
        data = ChatCompletionRequest(**data)
        prompt, embeddings = await apply_chat_template(data)
        abort_event = asyncio.Event()
        gen_queue = asyncio.Queue()
        gen_tasks: List[asyncio.Task] = []
        try:
            logger.info(f"Received chat completion streaming request {req_id}")

            for n in range(0, data.n):
                task_gen_params = data.model_copy(deep=True)

                gen_task = asyncio.create_task(
                    _stream_collector_chat_completion(
                        n,
                        gen_queue,
                        prompt,
                        req_id,
                        abort_event,
                        embeddings=embeddings,
                        **task_gen_params.model_dump(exclude={"prompt"}),
                    )
                )

                gen_tasks.append(gen_task)

            # We need to keep track of the text generated so we can resume the tool calls
            current_generation_text = ""

            # Consumer loop
            while True:
                generation = await gen_queue.get()
                # lets only append the text if we need it for tool calls later
                if data.tool_call_start and "text" in generation:
                    current_generation_text += generation["text"]

                # check if we are running a tool model, and that we are at stop
                if data.tool_call_start and "stop_str" in generation:
                    generations = await self.generate_tool_calls(
                        data,
                        [generation],
                        req_id,
                        current_generations=current_generation_text,
                    )
                    generation = generations[0]  # We only have one generation in this case

                # Stream collector will push an exception to the queue if it fails
                if isinstance(generation, Exception):
                    raise generation

                response = _create_stream_chunk(
                    req_id, generation
                )
                yield response.model_dump_json()

                # Check if all tasks are completed
                if all(task.done() for task in gen_tasks) and gen_queue.empty():
                    # Send a usage chunk
                    if data.stream_options and data.stream_options.include_usage:
                        usage_chunk = _create_stream_chunk(
                            req_id,
                            generation,
                            is_usage_chunk=True,
                        )
                        yield usage_chunk.model_dump_json()

                    logger.info(
                        f"Finished chat completion streaming request {req_id}"
                    )
                    yield "[DONE]"
                    break
        except Exception:
            yield get_generator_error(
                "Chat completion aborted. Please check the server console."
            )

    async def generate_tool_calls(
        self,
        data: ChatCompletionRequest,
        generations: List[str],
        req_id: str,
        current_generations: str = None,
    ):
        gen_tasks: List[asyncio.Task] = []
        tool_idx: List[int] = []

        # Copy to make sure the parent JSON schema doesn't get modified
        # FIXME: May not be necessary depending on how the codebase evolves
        tool_data = data.model_copy(deep=True)
        tool_data.json_schema = tool_data.tool_call_schema
        gen_params = tool_data.model_dump()

        for idx, gen in enumerate(generations):
            if gen["stop_str"] in tool_data.tool_call_start:
                if "text" in gen:
                    # non streaming, all generations will have the text they generated
                    pre_tool_prompt, mm_embeddings = await apply_chat_template(
                        data, gen["text"]
                    )
                elif current_generations is not None:
                    # streaming, we wont have text in the generation,
                    # we'll have to use the current_generations
                    pre_tool_prompt, mm_embeddings = await apply_chat_template(
                        data, current_generations
                    )

                gen_tasks.append(
                    asyncio.create_task(
                        model.container.generate(
                            pre_tool_prompt,
                            req_id,
                            embeddings=mm_embeddings,
                            **gen_params,
                        )
                    )
                )
                tool_idx.append(idx)

        tool_calls = await asyncio.gather(*gen_tasks)
        for outer_idx in range(0, len(tool_idx)):
            gen_idx = tool_idx[outer_idx]
            generations[gen_idx]["tool_calls"] = tool_calls[outer_idx]["text"]

        return generations
