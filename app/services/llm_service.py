"""
Servicio LLM - Cliente CometAPI
Accede a 500+ modelos via un solo gateway OpenAI-compatible
"""
import os
import logging
from typing import Optional, Dict, Any, List
from openai import OpenAI, OpenAIError
from tenacity import retry, stop_after_attempt, wait_exponential
from flask import current_app

logger = logging.getLogger(__name__)


class LLMService:
    """Cliente unificado para CometAPI"""
    
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or current_app.config['COMETAPI_KEY']
        self.base_url = base_url or current_app.config['COMETAPI_BASE_URL']
        
        if not self.api_key:
            raise ValueError("COMETAPI_KEY no configurada")
        
        self.client = OpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        self.models = current_app.config['MODELS']
        
        logger.info(f"LLM Service initialized with CometAPI (base_url={self.base_url})")
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True
    )
    def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: str,
        temperature: float = 0.3,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Llama a un modelo via CometAPI
        
        Args:
            messages: Lista de mensajes [{"role": "system", "content": "..."}]
            model: ID del modelo (ej: "claude-opus-4-20250514", "claude-sonnet-4-20250514")
            temperature: 0.0-2.0
            max_tokens: Límite de tokens de salida
            response_format: {"type": "json_object"} para JSON mode
            
        Returns:
            Dict con la respuesta completa de la API
        """
        try:
            params = {
                "model": model,
                "messages": messages,
                "temperature": temperature,
            }
            
            if max_tokens:
                params["max_tokens"] = max_tokens
            
            if response_format:
                params["response_format"] = response_format
            
            # Parámetros adicionales
            params.update(kwargs)
            
            response = self.client.chat.completions.create(**params)
            
            # Log para métricas
            usage = response.usage
            logger.info(
                f"LLM call: model={model} "
                f"tokens_in={usage.prompt_tokens} "
                f"tokens_out={usage.completion_tokens} "
                f"total={usage.total_tokens}"
            )
            
            return response
            
        except OpenAIError as e:
            logger.error(f"CometAPI error: {e}")
            raise
    
    def research_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada para Research Agent (Claude Sonnet 4)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['research'],
            temperature=kwargs.get('temperature', 0.3),
            **kwargs
        )
    
    def classifier_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada para Classifier Agent (Claude Sonnet 4)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['classifier'],
            temperature=kwargs.get('temperature', 0.2),
            **kwargs
        )
    
    def writer_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada para Writer Agent (Claude Opus 4 JSON mode)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['writer'],
            temperature=kwargs.get('temperature', 0.4),
            response_format={"type": "json_object"},
            **kwargs
        )
    
    def evaluator_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada para Quality Evaluator (Claude Sonnet 4)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['evaluator'],
            temperature=kwargs.get('temperature', 0.1),
            response_format={"type": "json_object"},
            **kwargs
        )
    
    def chat_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada para Chat Agent conversacional (Claude Sonnet 4)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['chat'],
            temperature=kwargs.get('temperature', 0.5),
            max_tokens=kwargs.get('max_tokens', 1024),
            **kwargs
        )

    def fallback_call(self, messages: List[Dict], **kwargs) -> Dict:
        """Llamada con modelo fallback (Gemini 2.5 Flash)"""
        return self.chat_completion(
            messages=messages,
            model=self.models['fallback'],
            **kwargs
        )
    
    def get_available_models(self) -> Dict[str, str]:
        """Retorna los modelos configurados"""
        return self.models.copy()


def get_llm_service() -> LLMService:
    """Factory para obtener instancia del servicio"""
    return LLMService()


def log_llm_call(step: str, response, context: Optional[Dict] = None):
    """
    Loguea una llamada LLM con métricas detalladas
    
    Args:
        step: Nombre del paso (research, classifier, writer, etc.)
        response: Respuesta de OpenAI API
        context: Contexto adicional para logging
    """
    usage = response.usage
    
    log_data = {
        'step': step,
        'model': response.model,
        'tokens_in': usage.prompt_tokens,
        'tokens_out': usage.completion_tokens,
        'tokens_total': usage.total_tokens,
    }
    
    if context:
        log_data.update(context)
    
    logger.info(f"[{step}] " + " ".join(f"{k}={v}" for k, v in log_data.items()))
    
    return log_data
