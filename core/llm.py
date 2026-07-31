import json
import requests
import ollama

class LLMResponse:
    def __init__(self, content="", tool_calls=None):
        self.content = content or ""
        self.tool_calls = tool_calls or []

class LLMClient:
    def __init__(self, config):
        self.config = config.get("llm", {})
        self.backend = self.config.get("backend", "ollama")
        self.model = self.config.get("model", "gemma3:2b")
        self.temperature = self.config.get("temperature", 0.1)
        self.max_tokens = self.config.get("max_tokens", 4096)
        
        self.ollama_host = self.config.get("ollama_host", "http://localhost:11434")
        self.llamacpp_host = self.config.get("llamacpp_host", "http://localhost:8080")

        # Set host environment variable for ollama library
        import os
        os.environ["OLLAMA_HOST"] = self.ollama_host

    def check_availability(self):
        """Verify if the configured backend and model are available."""
        if self.backend == "ollama":
            try:
                # Check connection and models. ollama>=0.4 returns a typed
                # ListResponse (model objects with a .model attribute); older
                # versions return a plain dict — support both.
                listing = ollama.list()
                raw_models = listing.get('models', []) if isinstance(listing, dict) else getattr(listing, 'models', [])
                available_models = []
                for m in raw_models:
                    if isinstance(m, dict):
                        available_models.append(m.get('name') or m.get('model'))
                    else:
                        available_models.append(getattr(m, 'model', None) or getattr(m, 'name', None))
                available_models = [m for m in available_models if m]
                # Ollama models might have tags like :latest, check both exact match and prefix
                if self.model in available_models or any(m.startswith(self.model + ":") for m in available_models):
                    return True, f"Ollama model '{self.model}' is available."
                
                # Check if it contains the tag already
                base_model_names = [m.split(":")[0] for m in available_models]
                if self.model.split(":")[0] in base_model_names:
                    # Let's find the exact match tag
                    exact = [m for m in available_models if m.split(":")[0] == self.model.split(":")[0]][0]
                    self.model = exact
                    return True, f"Ollama model '{self.model}' is available."

                return False, f"Ollama is running, but model '{self.model}' was not found. Available: {', '.join(available_models)}"
            except Exception as e:
                return False, f"Could not connect to Ollama at {self.ollama_host}. Error: {e}"
        elif self.backend == "llamacpp":
            try:
                # Test connection to llama.cpp health endpoint or models endpoint
                url = f"{self.llamacpp_host}/health"
                r = requests.get(url, timeout=5)
                if r.status_code == 200:
                    return True, "llama.cpp server is available."
                return False, f"llama.cpp health check returned status {r.status_code}."
            except Exception as e:
                return False, f"Could not connect to llama.cpp at {self.llamacpp_host}. Error: {e}"
        else:
            return False, f"Unknown LLM backend: {self.backend}"

    def chat(self, messages, tools=None):
        """Send chat messages and optional tools to the LLM backend."""
        if self.backend == "ollama":
            return self._chat_ollama(messages, tools)
        elif self.backend == "llamacpp":
            return self._chat_llamacpp(messages, tools)
        else:
            raise ValueError(f"Unsupported backend: {self.backend}")

    def _chat_ollama(self, messages, tools=None):
        formatted_tools = []
        if tools:
            # Convert our tools dictionary list to Ollama-expected tool list
            for tool in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                })

        # Remove any helper keys from messages (like 'tool_call_id' which Ollama doesn't use)
        clean_messages = []
        for msg in messages:
            clean_msg = {"role": msg["role"], "content": msg.get("content") or ""}
            if msg.get("images"):
                # Vision-capable models (e.g. gemma3) accept base64-encoded
                # image data attached to a message via this key.
                clean_msg["images"] = msg["images"]
            if "tool_calls" in msg:
                # Format assistant tool calls back for Ollama context
                ollama_tool_calls = []
                for tc in msg["tool_calls"]:
                    ollama_tool_calls.append({
                        "function": {
                            "name": tc["name"],
                            "arguments": tc["arguments"]
                        }
                    })
                clean_msg["tool_calls"] = ollama_tool_calls
            if msg["role"] == "tool":
                clean_msg["name"] = msg.get("name")
            clean_messages.append(clean_msg)

        options = {
            "temperature": self.temperature,
            "num_predict": self.max_tokens
        }

        try:
            # Call Ollama. Thinking-mode models (e.g. qwen3.5) put their
            # reasoning in message.thinking and can return an EMPTY
            # message.content on plain text calls, so explicitly disable
            # thinking; retry without the flag for models/servers that
            # reject the parameter.
            kwargs = dict(
                model=self.model,
                messages=clean_messages,
                tools=formatted_tools if formatted_tools else None,
                options=options
            )
            try:
                response = ollama.chat(think=False, **kwargs)
            except Exception:
                response = ollama.chat(**kwargs)
            
            msg = response.get("message", {})
            content = msg.get("content", "")
            
            tool_calls = []
            if msg.get("tool_calls"):
                for tc in msg["tool_calls"]:
                    func = tc.get("function", {})
                    tool_calls.append({
                        "name": func.get("name"),
                        "arguments": func.get("arguments") or {},
                        "id": None  # Ollama function calls don't strictly require IDs in the client loop
                    })
            
            return LLMResponse(content=content, tool_calls=tool_calls)
        except Exception as e:
            raise RuntimeError(f"Ollama chat call failed: {e}")

    def _chat_llamacpp(self, messages, tools=None):
        # Translate to OpenAI chat completion format
        url = f"{self.llamacpp_host}/v1/chat/completions"
        
        formatted_tools = []
        if tools:
            for tool in tools:
                formatted_tools.append({
                    "type": "function",
                    "function": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "parameters": tool["parameters"]
                    }
                })

        # Re-map messages for standard OpenAI format (must include tool_call_id matching)
        openai_messages = []
        for msg in messages:
            clean_msg = {"role": msg["role"], "content": msg.get("content")}
            if "tool_calls" in msg:
                openai_tool_calls = []
                for tc in msg["tool_calls"]:
                    openai_tool_calls.append({
                        "id": tc.get("id") or f"call_{tc['name']}",
                        "type": "function",
                        "function": {
                            "name": tc["name"],
                            "arguments": json.dumps(tc["arguments"])
                        }
                    })
                clean_msg["tool_calls"] = openai_tool_calls
            if msg["role"] == "tool":
                clean_msg["tool_call_id"] = msg.get("tool_call_id") or f"call_{msg.get('name')}"
            openai_messages.append(clean_msg)

        payload = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }
        if formatted_tools:
            payload["tools"] = formatted_tools

        try:
            r = requests.post(url, json=payload, timeout=120)
            r.raise_for_status()
            res_json = r.json()
            
            choice = res_json.get("choices", [{}])[0]
            choice_msg = choice.get("message", {})
            content = choice_msg.get("content", "")
            
            tool_calls = []
            if choice_msg.get("tool_calls"):
                for tc in choice_msg["tool_calls"]:
                    func = tc.get("function", {})
                    args_str = func.get("arguments", "{}")
                    try:
                        args = json.loads(args_str) if isinstance(args_str, str) else args_str
                    except Exception:
                        args = {}
                    
                    tool_calls.append({
                        "name": func.get("name"),
                        "arguments": args,
                        "id": tc.get("id")
                    })
                    
            return LLMResponse(content=content, tool_calls=tool_calls)
        except Exception as e:
            raise RuntimeError(f"llama.cpp chat call failed: {e}")
