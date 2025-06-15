import logging
from typing import List, Optional
from openai import OpenAI
from typing import List

from dotenv import load_dotenv
from openai import OpenAI
from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential
from app.utils.prompts import MEMORY_CATEGORIZATION_PROMPT

load_dotenv()

# 全局变量用于缓存客户端
_openai_client = None

# 使用配置管理器创建正确的OpenAI客户端
def get_configured_openai_client():
    """获取配置正确的OpenAI客户端"""
    global _openai_client
    
    # 如果已经创建过，直接返回
    if _openai_client is not None:
        return _openai_client
    
    from app.utils.config_manager import get_mem0_config
    from app.utils.memory import _parse_environment_variables, _ensure_config_priority
    
    # 获取统一配置
    mem0_config = get_mem0_config()
    llm_config = mem0_config.get('llm', {}).get('config', {})
    
    # 解析环境变量
    parsed_config = _parse_environment_variables({'llm': {'config': llm_config}})
    llm_config = parsed_config['llm']['config']
    
    # 确保配置优先级
    _ensure_config_priority({'llm': {'config': llm_config}})
    
    # 创建OpenAI客户端
    api_key = llm_config.get('api_key')
    base_url = llm_config.get('openai_base_url', 'https://api.openai.com/v1')
    
    _openai_client = OpenAI(api_key=api_key, base_url=base_url)
    return _openai_client

logger = logging.getLogger(__name__)


class MemoryCategories(BaseModel):
    categories: List[str]


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=15))
def get_categories_for_memory(memory: str) -> List[str]:
    """Get categories for a memory."""
    try:
        # 获取配置中的模型名称
        from app.utils.config_manager import get_mem0_config
        mem0_config = get_mem0_config()
        model_name = mem0_config.get('llm', {}).get('config', {}).get('model', 'gpt-4o-mini')
        
        # 获取配置好的客户端（延迟创建）
        openai_client = get_configured_openai_client()
        
        logger.info(f"🔍 开始分类记忆: {memory[:50]}... (模型: {model_name})")
        
        # 使用标准的OpenAI chat completions API替代responses.parse
        response = openai_client.chat.completions.create(
            model=model_name,
            messages=[
                {
                    "role": "system",
                    "content": MEMORY_CATEGORIZATION_PROMPT
                },
                {
                    "role": "user",
                    "content": memory
                }
            ],
            temperature=0.6,
            response_format={"type": "json_object"}
        )
        
        # 保持原有的解析逻辑，但适配标准OpenAI响应格式
        response_text = response.choices[0].message.content
        logger.info(f"🔍 模型返回的原始内容: {response}\n memory: {memory}")
        
        # 检查响应是否为空
        if not response_text or response_text.strip() == "":
            logger.error("❌ 模型返回内容为空")
            raise ValueError("Empty response from model")
        
        # 尝试解析JSON
        try:
            response_json = json.loads(response_text)
            logger.info(f"🔍 JSON解析成功: {response_json}")
        except json.JSONDecodeError as json_error:
            logger.error(f"❌ JSON解析失败: {json_error}")
            logger.error(f"❌ 原始响应内容: {repr(response_text)}")
            logger.error(f"❌ 响应长度: {len(response_text)}")
            logger.error(f"❌ 响应类型: {type(response_text)}")
            raise json_error
        
        # 检查响应结构
        if 'categories' not in response_json:
            logger.error(f"❌ 响应中缺少 'categories' 字段: {response_json}")
            raise KeyError("Missing 'categories' field in response")
        
        categories = response_json['categories']
        logger.info(f"🔍 提取的分类: {categories}")
        
        # 验证categories是列表
        if not isinstance(categories, list):
            logger.error(f"❌ categories 不是列表: {type(categories)} = {categories}")
            raise TypeError("categories should be a list")
        
        categories = [cat.strip().lower() for cat in categories if cat and cat.strip()]
        logger.info(f"✅ 最终分类结果: {categories}")
        
        # TODO: Validate categories later may be
        return categories
        
    except Exception as e:
        logger.error(f"❌ 分类失败，错误类型: {type(e).__name__}")
        logger.error(f"❌ 错误详情: {str(e)}")
        raise e
