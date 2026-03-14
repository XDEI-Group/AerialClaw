"""
Base LLM client interface and implementations.
Provides unified API for different LLM backends.
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import logging
import json
import time

logger = logging.getLogger(__name__)


class BaseLLMClient(ABC):
    """Abstract base class for LLM clients"""
    
    def __init__(self, model: str, temperature: float = 0.7, max_tokens: int = 1024):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
    
    @abstractmethod
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """
        Generate completion for given prompt.
        
        Args:
            prompt: User prompt
            system_prompt: System context
            **kwargs: Additional parameters
        
        Returns:
            Generated text
        """
        pass
    
    @abstractmethod
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """
        Generate chat completion.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            **kwargs: Additional parameters
        
        Returns:
            Generated text
        """
        pass


class OllamaClient(BaseLLMClient):
    """Client for local Ollama LLM service"""
    
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434/v1",
        model: str = "qwen:3.5",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 30,
        retry_count: int = 3,
    ):
        super().__init__(model, temperature, max_tokens)
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.retry_count = retry_count
        self._verify_connection()
    
    def _verify_connection(self):
        """Verify Ollama service is running"""
        try:
            import requests
            url = self.base_url.replace('/v1', '') + '/api/tags'
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                logger.info(f"✓ Connected to Ollama at {self.base_url}")
            else:
                logger.warning(f"⚠ Ollama returned status {response.status_code}")
        except Exception as e:
            logger.error(f"✗ Cannot connect to Ollama: {e}")
            logger.error(f"  Make sure Ollama is running: ollama serve")
            logger.error(f"  Or set OLLAMA_HOST environment variable")
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion using Ollama"""
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages, **kwargs)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Chat completion via Ollama API"""
        
        try:
            import requests
            
            url = f"{self.base_url}/chat/completions"
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
                "stream": False,
            }
            
            logger.debug(f"Ollama request: {payload}")
            
            # Retry logic
            for attempt in range(self.retry_count):
                try:
                    response = requests.post(
                        url,
                        json=payload,
                        timeout=self.timeout,
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        text = result.get("choices", [{}])[0].get("message", {}).get("content", "")
                        logger.debug(f"Ollama response: {text[:100]}...")
                        return text
                    else:
                        logger.error(f"Ollama error {response.status_code}: {response.text}")
                        if attempt < self.retry_count - 1:
                            time.sleep(2 ** attempt)  # Exponential backoff
                        else:
                            raise Exception(f"Ollama API error: {response.status_code}")
                
                except requests.exceptions.Timeout:
                    logger.warning(f"Ollama timeout (attempt {attempt + 1}/{self.retry_count})")
                    if attempt < self.retry_count - 1:
                        time.sleep(2 ** attempt)
                    else:
                        raise Exception("Ollama API timeout")
                
                except Exception as e:
                    logger.warning(f"Ollama error (attempt {attempt + 1}/{self.retry_count}): {e}")
                    if attempt < self.retry_count - 1:
                        time.sleep(2 ** attempt)
                    else:
                        raise
        
        except Exception as e:
            logger.error(f"Failed to get Ollama completion: {e}")
            raise


class QwenClient(BaseLLMClient):
    """Client for Alibaba Qwen API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "qwen-plus",
        base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 30,
    ):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion using Qwen API"""
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages, **kwargs)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Chat completion via Qwen API"""
        
        try:
            import requests
            
            url = f"{self.base_url}/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                raise Exception(f"Qwen API error: {response.status_code} - {response.text}")
        
        except Exception as e:
            logger.error(f"Failed to get Qwen completion: {e}")
            raise


class OpenAIClient(BaseLLMClient):
    """Client for OpenAI API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-3.5-turbo",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout: int = 30,
    ):
        super().__init__(model, temperature, max_tokens)
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.timeout = timeout
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion using OpenAI API"""
        
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self.chat(messages, **kwargs)
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Chat completion via OpenAI API"""
        
        try:
            import requests
            
            url = f"{self.base_url}/chat/completions"
            
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": self.model,
                "messages": messages,
                "temperature": kwargs.get("temperature", self.temperature),
                "max_tokens": kwargs.get("max_tokens", self.max_tokens),
            }
            
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=self.timeout,
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get("choices", [{}])[0].get("message", {}).get("content", "")
            else:
                raise Exception(f"OpenAI API error: {response.status_code}")
        
        except Exception as e:
            logger.error(f"Failed to get OpenAI completion: {e}")
            raise


class AnthropicClient(BaseLLMClient):
    """Client for Anthropic Claude API"""
    
    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-sonnet-20240229",
        max_tokens: int = 1024,
    ):
        super().__init__(model, temperature=1.0, max_tokens=max_tokens)
        self.api_key = api_key
    
    def complete(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        **kwargs
    ) -> str:
        """Generate completion using Claude API"""
        
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=self.api_key)
            
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system_prompt or "",
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )
            
            return message.content[0].text
        
        except Exception as e:
            logger.error(f"Failed to get Claude completion: {e}")
            raise
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        **kwargs
    ) -> str:
        """Chat completion via Claude API"""
        
        try:
            from anthropic import Anthropic
            
            client = Anthropic(api_key=self.api_key)
            
            # Extract system message if present
            system = ""
            user_messages = messages
            
            if messages and messages[0].get("role") == "system":
                system = messages[0]["content"]
                user_messages = messages[1:]
            
            message = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=user_messages,
            )
            
            return message.content[0].text
        
        except Exception as e:
            logger.error(f"Failed to get Claude chat completion: {e}")
            raise
