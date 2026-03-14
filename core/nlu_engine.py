"""
LLM-based Natural Language Understanding (NLU) engine.
Uses large language models to understand user intentions and generate task plans.
"""

import json
import logging
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

try:
    from config.config_manager import ConfigManager, LLMClientFactory
except ImportError:
    ConfigManager = None
    LLMClientFactory = None
from llm.base_client import BaseLLMClient

logger = logging.getLogger(__name__)


class Intent(Enum):
    RESCUE = "rescue"
    PATROL = "patrol"
    TRANSPORT = "transport"
    SURVEY = "survey"
    UNKNOWN = "unknown"


@dataclass
class ParsedMission:
    """Result of NLU parsing"""
    intent: Intent
    robots_involved: list[str]
    sub_tasks: Dict[str, list[str]]
    area: Optional[str] = None
    constraints: Dict[str, Any] = None
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_questions: Optional[list[str]] = None


class LLMBasedNLUEngine:
    """
    Natural Language Understanding using Large Language Models.
    Supports Ollama (local) and various API-based LLMs.
    """
    
    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """
        Initialize NLU engine with configuration.
        
        Args:
            config_path: Path to configuration YAML file
        """
        self.config = ConfigManager(config_path)
        self.factory = LLMClientFactory(self.config)
        self.llm = self.factory.create_client()
        
        logger.info(f"NLU Engine initialized with backend: {self.config.get_active_llm_backend()}")
        logger.info(f"Model: {self.llm.model}")
    
    def parse(self, user_input: str) -> ParsedMission:
        """
        Parse natural language user input into structured mission.
        
        Args:
            user_input: Natural language mission description
        
        Returns:
            ParsedMission with extracted information
        """
        logger.info(f"Parsing mission: {user_input}")
        
        # System prompt from config
        system_prompt = self.config.get_nlu_system_prompt()
        
        # Build the prompt for LLM
        analysis_prompt = f"""用户输入: "{user_input}"

请分析用户的意图，返回 JSON 格式（仅 JSON，无其他文本）：
{{
    "intent": "rescue|patrol|transport|survey|unknown",
    "robots": ["drone_1", "car_1"] 中的硬件列表,
    "tasks": {{
        "drone_1": ["任务1", "任务2"],
        "car_1": ["任务1"]
    }},
    "coordination": "sequential|parallel|unknown",
    "area": "用户提到的区域或 null",
    "constraints": {{"key": "value"}},
    "confidence": 0.0-1.0,
    "needs_clarification": true|false,
    "clarification_questions": ["问题1", "问题2"] 或 null
}}"""
        
        try:
            # Call LLM for analysis
            response = self.llm.complete(
                analysis_prompt,
                system_prompt=system_prompt,
            )
            
            logger.debug(f"LLM response: {response}")
            
            # Parse JSON response
            result = self._extract_json(response)
            
            # Convert to ParsedMission
            parsed = ParsedMission(
                intent=Intent[result.get("intent", "UNKNOWN").upper()],
                robots_involved=result.get("robots", ["drone_1"]),
                sub_tasks=result.get("tasks", {}),
                area=result.get("area"),
                constraints=result.get("constraints", {}),
                confidence=result.get("confidence", 0.0),
                needs_clarification=result.get("needs_clarification", False),
                clarification_questions=result.get("clarification_questions"),
            )
            
            logger.info(f"Parsed: intent={parsed.intent.value}, robots={parsed.robots_involved}, confidence={parsed.confidence}")
            
            return parsed
        
        except Exception as e:
            logger.error(f"NLU parsing failed: {e}")
            return ParsedMission(
                intent=Intent.UNKNOWN,
                robots_involved=["drone_1"],
                sub_tasks={},
                confidence=0.0,
                needs_clarification=True,
                clarification_questions=["无法理解您的需求，能重新描述吗？"],
            )
    
    def clarify(self, parsed: ParsedMission, user_response: str) -> ParsedMission:
        """
        Process user response to clarification questions.
        
        Args:
            parsed: Initial parsed mission
            user_response: User's clarification response
        
        Returns:
            Updated ParsedMission with clarifications applied
        """
        logger.info(f"Processing clarification: {user_response}")
        
        system_prompt = self.config.get_nlu_system_prompt()
        
        clarify_prompt = f"""用户最初的需求: "{parsed}"
用户的补充说明: "{user_response}"

请整合这两条信息，返回完整的任务定义 JSON（仅 JSON）：
{{
    "intent": "...",
    "robots": [...],
    "tasks": {{...}},
    "coordination": "...",
    "area": "...",
    "constraints": {{...}},
    "confidence": 0.0-1.0,
    "needs_clarification": false
}}"""
        
        try:
            response = self.llm.complete(
                clarify_prompt,
                system_prompt=system_prompt,
            )
            
            result = self._extract_json(response)
            
            return ParsedMission(
                intent=Intent[result.get("intent", "UNKNOWN").upper()],
                robots_involved=result.get("robots", ["drone_1"]),
                sub_tasks=result.get("tasks", {}),
                area=result.get("area"),
                constraints=result.get("constraints", {}),
                confidence=result.get("confidence", 0.0),
                needs_clarification=result.get("needs_clarification", False),
            )
        
        except Exception as e:
            logger.error(f"Clarification failed: {e}")
            return parsed
    
    def _extract_json(self, text: str) -> Dict:
        """
        Extract and parse JSON from LLM response.
        Handles cases where LLM adds extra text around JSON.
        """
        # Try to find JSON object in the response
        import json as json_lib
        
        # First try parsing the whole response
        try:
            return json_lib.loads(text)
        except:
            pass
        
        # Try to find JSON in the text
        start = text.find('{')
        end = text.rfind('}') + 1
        
        if start >= 0 and end > start:
            try:
                json_str = text[start:end]
                return json_lib.loads(json_str)
            except:
                pass
        
        # Fallback: return default structure
        logger.warning("Could not extract valid JSON from LLM response")
        return {
            "intent": "unknown",
            "robots": ["drone_1"],
            "tasks": {},
            "confidence": 0.0,
            "needs_clarification": True,
        }


# Backward compatibility: also provide SimpleNLUEngine alias
class SimpleNLUEngine(LLMBasedNLUEngine):
    """Alias for LLMBasedNLUEngine for backward compatibility"""
    pass
