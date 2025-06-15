"""
Memory client utilities for OpenMemory.

This module provides functionality to initialize and manage the Mem0 memory client
with automatic configuration management and Docker environment support.

Docker Ollama Configuration:
When running inside a Docker container and using Ollama as the LLM or embedder provider,
the system automatically detects the Docker environment and adjusts localhost URLs
to properly reach the host machine where Ollama is running.

Supported Docker host resolution (in order of preference):
1. OLLAMA_HOST environment variable (if set)
2. host.docker.internal (Docker Desktop for Mac/Windows)
3. Docker bridge gateway IP (typically 172.17.0.1 on Linux)
4. Fallback to 172.17.0.1

Example configuration that will be automatically adjusted:
{
    "llm": {
        "provider": "ollama",
        "config": {
            "model": "llama3.1:latest",
            "ollama_base_url": "http://localhost:11434"  # Auto-adjusted in Docker
        }
    }
}
"""

import os
import json
import hashlib
import socket
import platform
import logging

from mem0 import Memory
from app.database import SessionLocal
from app.models import Config as ConfigModel


logger = logging.getLogger(__name__)

_memory_client = None
_config_hash = None


class LLMResponseInterceptor:
    """
    LLM响应拦截器，用于修复qwen-32b等模型返回空响应的问题
    """
    
    @staticmethod
    def fix_llm_response(response_text):
        """
        修复LLM响应中的常见问题
        
        Args:
            response_text: 原始LLM响应文本
            
        Returns:
            修复后的响应文本
        """
        if not response_text or not response_text.strip():
            # 空响应，返回空的facts结构
            logger.warning("LLM返回空响应，使用默认结构")
            return '{"facts": []}'
        
        # 移除可能的前缀/后缀
        response_text = response_text.strip()
        
        # 移除markdown代码块标记
        if response_text.startswith('```json'):
            response_text = response_text[7:]
        if response_text.startswith('```'):
            response_text = response_text[3:]
        if response_text.endswith('```'):
            response_text = response_text[:-3]
        
        response_text = response_text.strip()
        
        # 如果仍然为空
        if not response_text:
            logger.warning("清理后响应仍为空，使用默认结构")
            return '{"facts": []}'
        
        # 尝试修复常见的JSON格式问题
        try:
            # 尝试直接解析
            json.loads(response_text)
            return response_text
        except json.JSONDecodeError as e:
            logger.warning(f"JSON解析错误，尝试修复: {e}")
            
            # 如果不是以{开头，尝试添加facts结构
            if not response_text.startswith('{'):
                # 可能是直接返回的facts数组
                if response_text.startswith('['):
                    response_text = f'{{"facts": {response_text}}}'
                else:
                    # 其他情况，包装成单个fact
                    escaped_text = response_text.replace('"', '\\"')
                    response_text = f'{{"facts": ["{escaped_text}"]}}'
            
            # 尝试再次解析
            try:
                json.loads(response_text)
                logger.info("JSON修复成功")
                return response_text
            except:
                logger.error("JSON修复失败，使用默认结构")
                return '{"facts": []}'


class ResilientMemoryClient:
    """
    A wrapper around Mem0 Memory client that handles JSON parsing errors gracefully.
    This wrapper catches JSON parsing errors and provides fallback responses.
    """
    
    def __init__(self, memory_client):
        self.memory_client = memory_client
        # 拦截原始客户端的LLM
        self._patch_llm_generate_response()
    
    def _patch_llm_generate_response(self):
        """给LLM的generate_response方法打补丁，增加响应修复功能"""
        if hasattr(self.memory_client, 'llm') and hasattr(self.memory_client.llm, 'generate_response'):
            original_generate_response = self.memory_client.llm.generate_response
            
            def patched_generate_response(*args, **kwargs):
                try:
                    response = original_generate_response(*args, **kwargs)
                    # 修复响应
                    fixed_response = LLMResponseInterceptor.fix_llm_response(response)
                    logger.debug(f"LLM响应修复: 原始长度={len(response or '')}, 修复后长度={len(fixed_response)}")
                    return fixed_response
                except Exception as e:
                    logger.error(f"LLM调用失败: {e}")
                    return '{"facts": []}'
            
            self.memory_client.llm.generate_response = patched_generate_response
            logger.info("✅ 已为LLM添加响应修复补丁")
    
    def add(self, text, **kwargs):
        """
        Add memory with error handling for JSON parsing issues.
        
        Args:
            text: Text to add to memory
            **kwargs: Additional arguments passed to the memory client
            
        Returns:
            Dict containing results or empty results on error
        """
        logger.debug(f"ResilientMemoryClient.add: {text}, {kwargs}")
        
        # Strategy 1: Direct call with original parameters
        try:
            logger.debug("Attempting direct call to memory client...")
            result = self.memory_client.add(text, **kwargs)
            
            # Validate result structure and fix if needed
            if isinstance(result, dict):
                # Ensure proper structure
                if "results" not in result:
                    result["results"] = []
                if "relations" not in result:
                    result["relations"] = {"added_entities": [], "deleted_entities": []}
                
                logger.debug(f"Direct call completed successfully with {len(result.get('results', []))} results")
                return result
            elif result is not None:
                logger.debug(f"Direct call returned non-dict result: {type(result)}")
                return result
            else:
                logger.warning("Memory client returned None - this indicates a problem")
                # Don't continue to fallback for None results, treat as an error
                raise Exception("Memory client returned None")
                    
        except Exception as e:
            error_msg = str(e)
            logger.warning(f"Direct call failed with error: {error_msg}")
            
            # Check if it's a JSON parsing error (typical mem0 LLM response issue)
            is_json_error = any(keyword in error_msg for keyword in [
                "Expecting value", "JSON", "line 1 column 1", "Unterminated string", 
                "Invalid control character", "json"
            ])
            
            if is_json_error:
                logger.error(f"🔍 JSON parsing error detected: {error_msg}")
                logger.info("🔄 Applying enhanced fallback strategies...")
            else:
                # For non-JSON errors, re-raise to preserve original error behavior
                logger.error(f"❌ Non-JSON error in memory add operation: {error_msg}")
                raise
        
        # Enhanced Fallback Strategies
        fallback_strategies = [
            # Strategy 2: Disable inference completely
            {
                "params": {"infer": False},
                "description": "without inference (direct storage)"
            },
            # Strategy 3: Try with minimal metadata
            {
                "params": {"metadata": {"source": "resilient_fallback"}},
                "description": "with minimal metadata"
            },
            # Strategy 4: Force fresh client with different parameters
            {
                "params": {"infer": True, "metadata": {**kwargs.get("metadata", {}), "retry_attempt": True}},
                "description": "with retry flag"
            },
            # Strategy 5: Simplify text and retry
            {
                "params": {"infer": True},
                "text_modifier": lambda t: t.strip()[:200] if len(t) > 200 else t.strip(),
                "description": "with simplified text"
            }
        ]
        
        for i, strategy in enumerate(fallback_strategies, 1):
            try:
                logger.info(f"Attempting fallback strategy {i}: {strategy['description']}")
                
                # Prepare parameters
                fallback_kwargs = {**kwargs}
                fallback_kwargs.update(strategy["params"])
                
                # Modify text if needed
                fallback_text = text
                if "text_modifier" in strategy:
                    fallback_text = strategy["text_modifier"](text)
                    logger.debug(f"Modified text length: {len(fallback_text)}")
                
                # Try the fallback
                fallback_result = self.memory_client.add(fallback_text, **fallback_kwargs)
                
                if fallback_result and isinstance(fallback_result, dict):
                    # Ensure proper structure
                    if "results" not in fallback_result:
                        fallback_result["results"] = []
                    if "relations" not in fallback_result:
                        fallback_result["relations"] = {"added_entities": [], "deleted_entities": []}
                    
                    logger.info(f"Fallback strategy {i} succeeded with {len(fallback_result.get('results', []))} results")
                    return fallback_result
                else:
                    logger.warning(f"Fallback strategy {i} returned invalid result: {type(fallback_result)}")
                    
            except Exception as fallback_error:
                logger.warning(f"Fallback strategy {i} failed: {fallback_error}")
                continue
        
        # If all strategies fail, try one final direct storage approach
        try:
            logger.info("All fallback strategies failed, attempting direct storage bypass")
            
            # Last resort: try to store with absolute minimal parameters
            final_result = self.memory_client.add(
                text,
                user_id=kwargs.get("user_id"),
                infer=False,
                metadata={"emergency_storage": True, "original_text": text[:100]}
            )
            
            if final_result:
                logger.warning("Emergency storage succeeded - recommend checking LLM configuration")
                return final_result
                
        except Exception as final_error:
            logger.error(f"Emergency storage also failed: {final_error}")
        
        # Ultimate fallback: return empty structure with diagnostic info
        logger.error("All memory storage strategies failed")
        logger.error("Diagnostic recommendations:")
        logger.error("1. Check LLM model availability and response format")
        logger.error("2. Verify embedder configuration")
        logger.error("3. Test with simpler text input")
        logger.error("4. Consider temporary infer=False mode")
        
        return {
            "results": [], 
            "relations": {"added_entities": [], "deleted_entities": []},
            "diagnostic": {
                "all_strategies_failed": True,
                "original_text_length": len(text),
                "kwargs_keys": list(kwargs.keys())
            }
        }
    
    def search(self, query, **kwargs):
        """Search memories with error handling."""
        try:
            return self.memory_client.search(query, **kwargs)
        except Exception as e:
            logger.error(f"Error in memory search: {e}")
            return {"results": [], "relations": {"added_entities": [], "deleted_entities": []}}
    
    def get_all(self, **kwargs):
        """Get all memories with error handling."""
        try:
            return self.memory_client.get_all(**kwargs)
        except Exception as e:
            logger.error(f"Error in get_all: {e}")
            return {"results": [], "relations": {"added_entities": [], "deleted_entities": []}}
    
    def delete_all(self, **kwargs):
        """Delete all memories with error handling."""
        try:
            return self.memory_client.delete_all(**kwargs)
        except Exception as e:
            logger.error(f"Error in delete_all: {e}")
            return {"message": f"Error during deletion: {e}"}
    
    def __getattr__(self, name):
        """Delegate other method calls to the wrapped client."""
        return getattr(self.memory_client, name)


def _get_config_hash(config_dict):
    """Generate a hash of the config to detect changes."""
    config_str = json.dumps(config_dict, sort_keys=True)
    return hashlib.md5(config_str.encode()).hexdigest()


def _get_docker_host_url():
    """
    Determine the appropriate host URL to reach host machine from inside Docker container.
    Returns the best available option for reaching the host from inside a container.
    """
    # Check for custom environment variable first
    custom_host = os.environ.get('OLLAMA_HOST')
    if custom_host:
        print(f"Using custom Ollama host from OLLAMA_HOST: {custom_host}")
        return custom_host.replace('http://', '').replace('https://', '').split(':')[0]
    
    # Check if we're running inside Docker
    if not os.path.exists('/.dockerenv'):
        # Not in Docker, return localhost as-is
        return "localhost"
    
    print("Detected Docker environment, adjusting host URL for Ollama...")
    
    # Try different host resolution strategies
    host_candidates = []
    
    # 1. host.docker.internal (works on Docker Desktop for Mac/Windows)
    try:
        socket.gethostbyname('host.docker.internal')
        host_candidates.append('host.docker.internal')
        print("Found host.docker.internal")
    except socket.gaierror:
        pass
    
    # 2. Docker bridge gateway (typically 172.17.0.1 on Linux)
    try:
        with open('/proc/net/route', 'r') as f:
            for line in f:
                fields = line.strip().split()
                if fields[1] == '00000000':  # Default route
                    gateway_hex = fields[2]
                    gateway_ip = socket.inet_ntoa(bytes.fromhex(gateway_hex)[::-1])
                    host_candidates.append(gateway_ip)
                    print(f"Found Docker gateway: {gateway_ip}")
                    break
    except (FileNotFoundError, IndexError, ValueError):
        pass
    
    # 3. Fallback to common Docker bridge IP
    if not host_candidates:
        host_candidates.append('172.17.0.1')
        print("Using fallback Docker bridge IP: 172.17.0.1")
    
    # Return the first available candidate
    return host_candidates[0]


def _fix_ollama_urls(config_section):
    """
    Fix Ollama URLs for Docker environment.
    Replaces localhost URLs with appropriate Docker host URLs.
    Sets default ollama_base_url if not provided.
    """
    if not config_section or "config" not in config_section:
        return config_section
    
    ollama_config = config_section["config"]
    
    # Set default ollama_base_url if not provided
    if "ollama_base_url" not in ollama_config:
        ollama_config["ollama_base_url"] = "http://host.docker.internal:11434"
    else:
        # Check for ollama_base_url and fix if it's localhost
        url = ollama_config["ollama_base_url"]
        if "localhost" in url or "127.0.0.1" in url:
            docker_host = _get_docker_host_url()
            if docker_host != "localhost":
                new_url = url.replace("localhost", docker_host).replace("127.0.0.1", docker_host)
                ollama_config["ollama_base_url"] = new_url
                print(f"Adjusted Ollama URL from {url} to {new_url}")
    
    return config_section


def reset_memory_client():
    """Reset the global memory client to force reinitialization with new config."""
    global _memory_client, _config_hash
    _memory_client = None
    _config_hash = None
    
    # 清除配置缓存以确保使用最新配置
    try:
        from app.utils.config_manager import clear_config_cache
        clear_config_cache()
    except ImportError:
        # 如果config_manager还没有被导入，忽略错误
        pass


def get_default_memory_config():
    """
    获取默认memory客户端配置。
    
    注意：此函数已弃用，建议使用 app.utils.config_manager.get_mem0_config() 代替。
    保留此函数仅为向后兼容。
    """
    from app.utils.config_manager import get_mem0_config
    return get_mem0_config()


def _parse_environment_variables(config_dict):
    """
    Parse environment variables in config values.
    Converts 'env:VARIABLE_NAME' to actual environment variable values.
    """
    if isinstance(config_dict, dict):
        parsed_config = {}
        for key, value in config_dict.items():
            if isinstance(value, str) and value.startswith("env:"):
                env_var = value.split(":", 1)[1]
                env_value = os.environ.get(env_var)
                if env_value:
                    parsed_config[key] = env_value
                    print(f"Loaded {env_var} from environment for {key}")
                else:
                    print(f"Warning: Environment variable {env_var} not found, keeping original value")
                    parsed_config[key] = value
            elif isinstance(value, dict):
                parsed_config[key] = _parse_environment_variables(value)
            else:
                parsed_config[key] = value
        return parsed_config
    return config_dict


def _ensure_config_priority(config_dict):
    """
    确保配置文件中的设置优先于环境变量。
    
    这是一个关键函数，用于解决环境变量覆盖配置文件设置的问题。
    当配置文件中明确设置了openai_base_url时，临时清除可能冲突的环境变量。
    """
    print("🔧 检查并处理环境变量冲突...")
    
    # 检查是否在配置中设置了自定义base_url
    llm_config = config_dict.get('llm', {}).get('config', {})
    embedder_config = config_dict.get('embedder', {}).get('config', {})
    graph_llm_config = config_dict.get('graph_store', {}).get('llm', {}).get('config', {})
    
    custom_base_urls = []
    if llm_config.get('openai_base_url'):
        custom_base_urls.append(('LLM', llm_config['openai_base_url']))
    if embedder_config.get('openai_base_url'):
        custom_base_urls.append(('Embedder', embedder_config['openai_base_url']))
    if graph_llm_config.get('openai_base_url'):
        custom_base_urls.append(('Graph LLM', graph_llm_config['openai_base_url']))
    
    if custom_base_urls:
        print("✅ 发现配置文件中的自定义Base URL:")
        for component, url in custom_base_urls:
            print(f"   {component}: {url}")
        
        # 检查可能冲突的环境变量
        conflicting_vars = ['OPENAI_API_BASE', 'OPENAI_BASE_URL']
        found_conflicts = {}
        
        for var in conflicting_vars:
            value = os.environ.get(var)
            if value:
                found_conflicts[var] = value
                print(f"⚠️  发现冲突环境变量: {var}={value}")
        
        if found_conflicts:
            print("🛠️  临时清除冲突的环境变量以确保配置文件优先...")
            
            # 临时保存原始值
            original_values = {}
            for var in found_conflicts:
                original_values[var] = os.environ.get(var)
                del os.environ[var]
                print(f"   已临时清除: {var}")
            
            # 在全局存储原始值，以便后续恢复（如果需要）
            config_dict['_original_env_vars'] = original_values
            
            print("✅ 环境变量冲突已解决，配置文件设置现在将优先生效")
        else:
            print("✅ 未发现环境变量冲突")
    else:
        print("ℹ️  配置文件中未设置自定义Base URL，将使用默认行为")
    
    return config_dict


def get_memory_client(custom_instructions: str = None):
    """
    Get or initialize the Mem0 client.

    Args:
        custom_instructions: Optional instructions for the memory project.

    Returns:
        Initialized Mem0 client instance or None if initialization fails.

    Raises:
        Exception: If required API keys are not set or critical configuration is missing.
    """
    global _memory_client, _config_hash

    try:
        # 使用统一的配置管理器获取配置
        from app.utils.config_manager import get_mem0_config, get_openmemory_config
        
        # 获取Mem0配置
        config = get_mem0_config()
        
        # 获取OpenMemory配置中的自定义指令
        openmemory_config = get_openmemory_config()
        db_custom_instructions = openmemory_config.get("custom_instructions")
        
        # 应用Docker Ollama URL修复
        if config.get("llm", {}).get("provider") == "ollama":
            config["llm"] = _fix_ollama_urls(config["llm"])
        
        if config.get("embedder", {}).get("provider") == "ollama":
            config["embedder"] = _fix_ollama_urls(config["embedder"])
        
        if config.get("graph_store", {}).get("llm", {}).get("provider") == "ollama":
            config["graph_store"]["llm"] = _fix_ollama_urls(config["graph_store"]["llm"])

        # Use custom_instructions parameter first, then fall back to database value
        instructions_to_use = custom_instructions or db_custom_instructions
        if instructions_to_use:
            config["custom_fact_extraction_prompt"] = instructions_to_use
        
        # Add robust JSON handling instruction to prevent parsing errors
#         if "custom_fact_extraction_prompt" not in config:
#             config["custom_fact_extraction_prompt"] = """You are a Personal Information Organizer specialized in extracting facts from conversations.

# CRITICAL REQUIREMENTS:
# 1. ALWAYS return valid JSON format with 'facts' key
# 2. NEVER return empty responses or malformed JSON
# 3. If no meaningful facts found, return {"facts": []}
# 4. If facts found, return {"facts": ["fact1", "fact2", ...]}

# Examples:
# Input: Hi
# Output: {"facts": []}

# Input: My name is John
# Output: {"facts": ["Name is John"]}

# Input: I like pizza and coffee
# Output: {"facts": ["Likes pizza", "Likes coffee"]}

# Guidelines:
# - Extract personal preferences, names, relationships, plans, and other relevant information
# - Record facts in the same language as the input
# - Break down complex statements into individual facts
# - Always ensure the response is valid JSON

# Remember: ALWAYS return valid JSON with 'facts' key, even for simple greetings!"""

        # ALWAYS parse environment variables in the final config
        # This ensures that even default config values like "env:OPENAI_API_KEY" get parsed
        print("Parsing environment variables in final config...")
        config = _parse_environment_variables(config)
        
        # 🔧 NEW: 确保配置文件优先级 - 解决环境变量覆盖问题
        config = _ensure_config_priority(config)
        
        # Debug: Print the final configuration being used
        print("=" * 60)
        print("🔧 Final Memory Client Configuration:")
        print("=" * 60)
        
        # Print config sections with sensitive data masked
        def mask_sensitive_data(config_dict, path=""):
            """Recursively mask sensitive configuration data for logging."""
            if isinstance(config_dict, dict):
                masked = {}
                for key, value in config_dict.items():
                    current_path = f"{path}.{key}" if path else key
                    if key.lower() in ['api_key', 'password', 'token']:
                        if isinstance(value, str) and value:
                            masked[key] = f"{'*' * 8}...{value[-4:]}" if len(value) > 4 else f"{'*' * len(value)}"
                        else:
                            masked[key] = value
                    else:
                        masked[key] = mask_sensitive_data(value, current_path)
                return masked
            return config_dict
        
        masked_config = mask_sensitive_data(config)
        
        print(f"LLM Config: {json.dumps(masked_config.get('llm', {}), indent=2)}")
        print(f"Vector Store Config: {json.dumps(masked_config.get('vector_store', {}), indent=2)}")
        print(f"Graph Store Config: {json.dumps(masked_config.get('graph_store', {}), indent=2)}")
        print(f"Embedder Config: {json.dumps(masked_config.get('embedder', {}), indent=2)}")
        print(f"Version: {config.get('version', 'not set')}")
        
        if 'custom_fact_extraction_prompt' in config:
            prompt_preview = config['custom_fact_extraction_prompt'][:100] + "..." if len(config['custom_fact_extraction_prompt']) > 100 else config['custom_fact_extraction_prompt']
            print(f"Custom Fact Extraction Prompt: {prompt_preview}")
        else:
            print("Custom Fact Extraction Prompt: Not set")
        
        print("=" * 60)

        # Check if config has changed by comparing hashes
        current_config_hash = _get_config_hash(config)
        
        # Only reinitialize if config changed or client doesn't exist
        if _memory_client is None or _config_hash != current_config_hash:
            print(f"Initializing memory client with config hash: {current_config_hash}")
            try:
                raw_client = Memory.from_config(config_dict=config)
                
                # Check if we should bypass the resilient wrapper
                bypass_resilient = os.environ.get('BYPASS_RESILIENT_CLIENT', 'false').lower() == 'true'
                
                if bypass_resilient:
                    print("⚠️  Using raw mem0 client without resilient wrapper (BYPASS_RESILIENT_CLIENT=true)")
                    _memory_client = raw_client
                else:
                    # Wrap the client with our resilient wrapper
                    _memory_client = ResilientMemoryClient(raw_client)
                    print("Memory client initialized successfully with resilient wrapper")
                
                _config_hash = current_config_hash
                
                # Print key client information
                print(f"✅ Memory Client Details:")
                print(f"   - LLM Provider: {getattr(raw_client.llm, '__class__', 'Unknown').__name__}")
                print(f"   - Vector Store: {getattr(raw_client.vector_store, '__class__', 'Unknown').__name__}")
                print(f"   - Embedder: {getattr(raw_client.embedding_model, '__class__', 'Unknown').__name__}")
                
                # Check if graph store is enabled
                graph_enabled = hasattr(raw_client, 'graph') and raw_client.graph is not None
                print(f"   - Graph Store: {'Enabled' if graph_enabled else 'Disabled'}")
                if graph_enabled:
                    print(f"   - Graph Store Type: {getattr(raw_client.graph, '__class__', 'Unknown').__name__}")
                
                # Also check the enable_graph flag for additional info
                enable_graph_flag = getattr(raw_client, 'enable_graph', False)
                print(f"   - Enable Graph Flag: {enable_graph_flag}")
                
                # Print version info
                version = config.get('version', 'unknown')
                print(f"   - Version: {version}")
                print(f"   - Resilient Wrapper: {'Disabled' if bypass_resilient else 'Enabled'}")
                
                print("=" * 60)
            except Exception as init_error:
                print(f"Warning: Failed to initialize memory client: {init_error}")
                print("Server will continue running with limited memory functionality")
                _memory_client = None
                _config_hash = None
                return None
        
        return _memory_client
        
    except Exception as e:
        print(f"Warning: Exception occurred while initializing memory client: {e}")
        print("Server will continue running with limited memory functionality")
        return None


def get_default_user_id():
    return "default_user"
