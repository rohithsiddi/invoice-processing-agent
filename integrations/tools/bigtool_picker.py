"""
BigtoolPicker - Unified Dynamic Tool Selection System

Supports two selection modes:
1. LLM-based selection (for OCR) - Uses OpenAI for intelligent tool choice
2. YAML-based selection (for other tools) - Uses priority-based selection from tools.yaml
"""
import os
import yaml
from typing import Dict, List, Optional, Any
from pathlib import Path
from openai import OpenAI
from core.config.config import config
from core.utils.logging_config import get_logger

logger = get_logger(__name__)


class BigtoolPicker:
    """
    Unified dynamic tool selector supporting both LLM-based and YAML-based selection.
    
    - LLM-based: Uses OpenAI for intelligent OCR tool selection
    - YAML-based: Uses priority-based selection for other tools
    """
    
    # Agent personality prompt template for LLM selection
    AGENT_PROMPT = """You are Langie – the Invoice Processing LangGraph Agent.

You think in structured stages.
Each node is a well-defined processing phase.
You always carry forward state variables between nodes.
You know when to execute deterministic steps and when to choose dynamically.
You orchestrate MCP clients to call COMMON or ATLAS abilities as required.
You use Bigtool whenever a tool must be selected from a pool.
You log every decision, every tool choice, and every state update.
You always produce clean structured output.

Your current task: Select the best tool from the available pool based on the given context.
"""
    
    def __init__(self, tools_config_path: Optional[str] = None):
        """
        Initialize BigtoolPicker with tools configuration and OpenAI client
        
        Args:
            tools_config_path: Path to tools.yaml, defaults to config/tools.yaml
        """
        # Load YAML configuration for non-OCR tools
        if tools_config_path is None:
            # Point to core/config/tools.yaml
            project_root = Path(__file__).parent.parent.parent
            tools_config_path = project_root / 'core' / 'config' / 'tools.yaml'
        
        with open(tools_config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.tool_pools = self.config.get('tool_pools', {})
        self.selection_strategy = self.config.get('selection_strategy', {})
        self.fallback_enabled = self.selection_strategy.get('fallback', True)
        self.retry_count = self.selection_strategy.get('retry_count', 2)
        
        # Initialize OpenAI client for LLM-based OCR selection
        self.api_key = os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            logger.warning("OPENAI_API_KEY not found, LLM OCR selection will fall back to rules")
            self.llm_client = None
        else:
            self.llm_client = OpenAI(api_key=self.api_key)
            logger.info("LLM Bigtool Picker initialized with OpenAI")
    
    def select(
        self, 
        capability: str, 
        context: Optional[Dict[str, Any]] = None,
        pool_hint: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Select the best tool for a given capability
        
        Args:
            capability: The capability needed (e.g., 'ocr', 'erp_connector')
            context: Optional context for selection (e.g., {'use_case': 'high_accuracy'})
            pool_hint: Optional list of preferred tool names
            
        Returns:
            Dictionary with selected tool information:
            {
                'name': 'tool_name',
                'config': {...},
                'priority': 1,
                'use_cases': [...]
            }
            
        Raises:
            ValueError: If capability not found or no tools available
        """
        if capability not in self.tool_pools:
            raise ValueError(f"Capability '{capability}' not found in tool pools")
        
        available_tools = self.tool_pools[capability]
        
        if not available_tools:
            raise ValueError(f"No tools available for capability '{capability}'")
        
        # Filter by pool_hint if provided
        if pool_hint:
            filtered_tools = [
                tool for tool in available_tools 
                if tool['name'] in pool_hint
            ]
            if filtered_tools:
                available_tools = filtered_tools
        
        # Filter by context use_case if provided
        if context and 'use_case' in context:
            use_case = context['use_case']
            matching_tools = [
                tool for tool in available_tools
                if use_case in tool.get('use_cases', [])
            ]
            if matching_tools:
                available_tools = matching_tools
        
        # Sort by priority (lower number = higher priority)
        available_tools.sort(key=lambda x: x.get('priority', 999))
        
        # Select the highest priority tool
        selected_tool = available_tools[0]
        
        # Resolve environment variables in config
        resolved_config = self._resolve_config(selected_tool.get('config', {}))
        
        return {
            'name': selected_tool['name'],
            'config': resolved_config,
            'priority': selected_tool.get('priority', 999),
            'use_cases': selected_tool.get('use_cases', [])
        }
    
    def _resolve_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Resolve environment variable references in config
        
        Args:
            config: Configuration dictionary with potential env var references
            
        Returns:
            Configuration with resolved values
        """
        resolved = {}
        for key, value in config.items():
            if isinstance(value, str) and key.endswith('_env'):
                # This is an env var reference
                env_var_name = value
                actual_key = key.replace('_env', '')
                resolved[actual_key] = os.getenv(env_var_name, '')
            else:
                resolved[key] = value
        return resolved
    
    def get_fallback(self, capability: str, exclude: List[str]) -> Optional[Dict[str, Any]]:
        """
        Get a fallback tool for a capability, excluding specified tools
        
        Args:
            capability: The capability needed
            exclude: List of tool names to exclude
            
        Returns:
            Fallback tool info or None if no fallback available
        """
        if not self.fallback_enabled:
            return None
        
        if capability not in self.tool_pools:
            return None
        
        available_tools = [
            tool for tool in self.tool_pools[capability]
            if tool['name'] not in exclude
        ]
        
        if not available_tools:
            return None
        
        # Sort by priority
        available_tools.sort(key=lambda x: x.get('priority', 999))
        
        selected_tool = available_tools[0]
        resolved_config = self._resolve_config(selected_tool.get('config', {}))
        
        return {
            'name': selected_tool['name'],
            'config': resolved_config,
            'priority': selected_tool.get('priority', 999),
            'use_cases': selected_tool.get('use_cases', [])
        }
    
    def list_capabilities(self) -> List[str]:
        """List all available capabilities"""
        return list(self.tool_pools.keys())
    
    def list_tools(self, capability: str) -> List[str]:
        """List all tools for a given capability"""
        if capability not in self.tool_pools:
            return []
        return [tool['name'] for tool in self.tool_pools[capability]]
    
    # ========== LLM-Based OCR Selection Methods ==========
    
    def select_ocr_tool(self, context: Dict[str, Any]) -> str:
        """
        Select the best OCR tool using LLM reasoning
        
        Args:
            context: Context about the invoice/image
        
        Returns:
            Selected tool name: 'tesseract' or 'easyocr'
        """
        tools = {
            "tesseract": {
                "description": "Fast, lightweight OCR. Best for high-quality printed text.",
                "strengths": ["Speed", "Printed text", "English", "Low resource"],
                "weaknesses": ["Handwriting", "Low quality", "Multi-language"]
            },
            "easyocr": {
                "description": "Deep learning OCR. Better for handwriting and low quality.",
                "strengths": ["Handwriting", "Low quality", "Multi-language"],
                "weaknesses": ["Slower", "Higher resource usage"]
            }
        }
        
        if not self.llm_client:
            return self._rule_based_ocr_selection(context, tools)
        
        prompt = f"""Given: File Type: {context.get('file_type')}, Quality: {context.get('quality_hint')}, Handwriting: {context.get('has_handwriting')}

Tools:
1. Tesseract: {tools['tesseract']['description']}
2. EasyOCR: {tools['easyocr']['description']}

Select ONLY: "tesseract" or "easyocr" (prefer tesseract for standard invoices)"""
        
        try:
            logger.info("=" * 60)
            logger.info("LLM BIGTOOL PICKER - OCR Tool Selection")
            logger.info("=" * 60)
            logger.info(f"Context: {context}")
            
            response = self.llm_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self.AGENT_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=50
            )
            
            selected_tool = response.choices[0].message.content.strip().lower()
            if selected_tool not in ['tesseract', 'easyocr']:
                selected_tool = 'tesseract'
            
            logger.info(f"LLM Selected: {selected_tool}")
            logger.info("=" * 60)
            return selected_tool
            
        except Exception as e:
            logger.error(f"LLM selection failed: {e}")
            return self._rule_based_ocr_selection(context, tools)
    
    def _rule_based_ocr_selection(self, context: Dict[str, Any], tools: Dict) -> str:
        """Fallback rule-based OCR selection"""
        if context.get('has_handwriting'):
            return 'easyocr'
        if context.get('quality_hint', '').lower() == 'low':
            return 'easyocr'
        if context.get('language', 'en') != 'en':
            return 'easyocr'
        return 'tesseract'
    
    def get_tool_info(self, tool_name: str, capability: str = 'ocr') -> Dict[str, Any]:
        """Get detailed information about a selected tool"""
        if capability == 'ocr':
            if tool_name == 'tesseract':
                return {
                    'name': 'Tesseract OCR',
                    'version': '5.x',
                    'type': 'local',
                    'capabilities': ['printed_text', 'english', 'fast'],
                    'config': {'psm': 6, 'oem': 3}
                }
            elif tool_name == 'easyocr':
                return {
                    'name': 'EasyOCR',
                    'version': 'latest',
                    'type': 'deep_learning',
                    'capabilities': ['handwriting', 'multi_language', 'low_quality'],
                    'config': {'gpu': False, 'languages': ['en']}
                }
        return {'name': tool_name, 'type': 'unknown'}


# Create singleton instance
bigtool_picker = BigtoolPicker()


if __name__ == "__main__":
    # Test BigtoolPicker
    print("BigtoolPicker Test")
    print("=" * 60)
    
    picker = BigtoolPicker()
    
    print("\nAvailable capabilities:")
    for cap in picker.list_capabilities():
        tools = picker.list_tools(cap)
        print(f"  {cap}: {tools}")
    
    print("\n" + "=" * 60)
    print("Tool Selection Examples:")
    print("=" * 60)
    
    # Test OCR selection
    print("\n1. Select OCR tool (default):")
    ocr_tool = picker.select('ocr')
    print(f"   Selected: {ocr_tool['name']} (priority: {ocr_tool['priority']})")
    
    # Test OCR with context
    print("\n2. Select OCR tool (high accuracy):")
    ocr_tool = picker.select('ocr', context={'use_case': 'high_accuracy'})
    print(f"   Selected: {ocr_tool['name']} (priority: {ocr_tool['priority']})")
    
    # Test ERP selection
    print("\n3. Select ERP connector (default):")
    erp_tool = picker.select('erp_connector')
    print(f"   Selected: {erp_tool['name']} (priority: {erp_tool['priority']})")
    
    # Test with pool hint
    print("\n4. Select ERP connector (pool hint: ['sap_sandbox']):")
    erp_tool = picker.select('erp_connector', pool_hint=['sap_sandbox'])
    print(f"   Selected: {erp_tool['name']} (priority: {erp_tool['priority']})")
    
    # Test fallback
    print("\n5. Get fallback OCR (exclude google_vision):")
    fallback = picker.get_fallback('ocr', exclude=['google_vision'])
    if fallback:
        print(f"   Fallback: {fallback['name']} (priority: {fallback['priority']})")
    
    print("\n" + "=" * 60)
