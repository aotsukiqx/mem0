#!/usr/bin/env python3
"""
统一配置管理模块

实现数据库优先的配置策略：
1. 优先从SQLite数据库读取配置
2. 如果数据库中没有配置，则从default_config.json读取并保存到数据库
3. 如果default_config.json不存在，则使用内置默认配置
4. 统一所有模块的配置获取逻辑
"""

import os
import json
import logging
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Config as ConfigModel

logger = logging.getLogger(__name__)

class ConfigManager:
    """统一配置管理器"""
    
    def __init__(self):
        self._config_cache = None
        self._cache_key = None
    
    def get_built_in_default_config(self) -> Dict[str, Any]:
        """获取内置默认配置"""
        return {
            "openmemory": {
                "custom_instructions": None
            },
            "mem0": {
                "llm": {
                    "provider": "openai",
                    "config": {
                        "model": "qwen-32b",
                        "openai_base_url": "https://1api.mynameqx.top:5003/v1",
                        "api_key": "env:OPENAI_API_KEY",
                        "temperature": 0.6,
                        "max_tokens": 32768
                    }
                },
                "graph_store": {
                    "provider": "neo4j",
                    "config": {
                        "url": "neo4j+s://n1.mynameqx.top:7687",
                        "username": "neo4j",
                        "password": "i2EYPRi5FQsGxLNviL6T"
                    },
                    "llm": {
                        "provider": "openai",
                        "config": {
                            "model": "qwen-plus-latest",
                            "openai_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                            "api_key": "env:ALIYUN_API_KEY",
                            "temperature": 0.6,
                            "max_tokens": 32768
                        }
                    }
                },
                "vector_store": {
                    "provider": "milvus",
                    "config": {
                        "collection_name": "cursor",
                        "url": "http://r86s.mynameqx.top:19530",
                        "embedding_model_dims": 5376,
                        "token": "env:MILVUS_TOKEN"
                    }
                },
                "embedder": {
                    "provider": "openai",
                    "config": {
                        "openai_base_url": "https://1api.mynameqx.top:5003/v1",
                        "model": "gemma3-27b",
                        "api_key": "env:OPENAI_API_KEY"
                    }
                },
                "version": "v1.1"
            }
        }
    
    def load_config_from_file(self, filename: str) -> Optional[Dict[str, Any]]:
        """从JSON文件加载配置"""
        try:
            if os.path.exists(filename):
                with open(filename, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                logger.info(f"✅ 从文件 {filename} 加载配置成功")
                return config
            else:
                logger.warning(f"⚠️  配置文件 {filename} 不存在")
                return None
        except Exception as e:
            logger.error(f"❌ 读取配置文件 {filename} 失败: {e}")
            return None
    
    def get_default_config(self) -> Dict[str, Any]:
        """获取默认配置（文件优先，内置后备）"""
        
        # 尝试从default_config.json读取
        file_config = self.load_config_from_file("default_config.json")
        if file_config:
            logger.info("📄 使用 default_config.json 中的配置")
            return file_config
        
        # 尝试从config.json读取（向后兼容）
        file_config = self.load_config_from_file("config.json")
        if file_config:
            logger.info("📄 使用 config.json 中的配置")
            return file_config
        
        # 使用内置默认配置
        logger.info("🔧 使用内置默认配置")
        return self.get_built_in_default_config()
    
    def ensure_config_completeness(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """确保配置完整性，补充缺失的配置项"""
        default_config = self.get_built_in_default_config()
        
        # 深度合并配置
        def deep_merge(base: Dict, override: Dict) -> Dict:
            result = base.copy()
            for key, value in override.items():
                if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = deep_merge(result[key], value)
                else:
                    result[key] = value
            return result
        
        complete_config = deep_merge(default_config, config)
        
        # 检查是否有配置项被补充
        if complete_config != config:
            logger.info("🔄 配置项已补充完整")
        
        return complete_config
    
    def get_config_from_db(self, db: Session, key: str = "main") -> Dict[str, Any]:
        """从数据库获取配置"""
        config_record = db.query(ConfigModel).filter(ConfigModel.key == key).first()
        
        if config_record:
            logger.info(f"✅ 从数据库加载配置 (key: {key})")
            # 确保配置完整性
            return self.ensure_config_completeness(config_record.value)
        
        # 数据库中没有配置，创建默认配置
        logger.info(f"🆕 数据库中无配置，创建默认配置 (key: {key})")
        default_config = self.get_default_config()
        
        # 保存到数据库
        self.save_config_to_db(db, default_config, key)
        
        return default_config
    
    def save_config_to_db(self, db: Session, config: Dict[str, Any], key: str = "main") -> Dict[str, Any]:
        """保存配置到数据库"""
        # 确保配置完整性
        complete_config = self.ensure_config_completeness(config)
        
        config_record = db.query(ConfigModel).filter(ConfigModel.key == key).first()
        
        if config_record:
            config_record.value = complete_config
            config_record.updated_at = None  # 触发自动更新时间戳
            logger.info(f"🔄 更新数据库配置 (key: {key})")
        else:
            config_record = ConfigModel(key=key, value=complete_config)
            db.add(config_record)
            logger.info(f"🆕 创建数据库配置 (key: {key})")
        
        db.commit()
        db.refresh(config_record)
        
        # 清除缓存
        self._config_cache = None
        self._cache_key = None
        
        return complete_config
    
    def get_config(self, key: str = "main", use_cache: bool = True) -> Dict[str, Any]:
        """获取配置（带缓存）"""
        
        # 检查缓存
        if use_cache and self._config_cache and self._cache_key == key:
            logger.debug(f"📋 使用缓存配置 (key: {key})")
            return self._config_cache
        
        # 从数据库加载
        db = SessionLocal()
        try:
            config = self.get_config_from_db(db, key)
            
            # 更新缓存
            if use_cache:
                self._config_cache = config
                self._cache_key = key
            
            return config
        finally:
            db.close()
    
    def get_mem0_config(self, key: str = "main") -> Dict[str, Any]:
        """获取Mem0专用配置"""
        full_config = self.get_config(key)
        return full_config.get("mem0", {})
    
    def get_openmemory_config(self, key: str = "main") -> Dict[str, Any]:
        """获取OpenMemory专用配置"""
        full_config = self.get_config(key)
        return full_config.get("openmemory", {})
    
    def clear_cache(self):
        """清除配置缓存"""
        self._config_cache = None
        self._cache_key = None
        logger.info("🧹 配置缓存已清除")
    
    def reset_to_default(self, key: str = "main") -> Dict[str, Any]:
        """重置配置为默认值"""
        default_config = self.get_default_config()
        
        db = SessionLocal()
        try:
            saved_config = self.save_config_to_db(db, default_config, key)
            logger.info(f"🔄 配置已重置为默认值 (key: {key})")
            return saved_config
        finally:
            db.close()


# 全局配置管理器实例
config_manager = ConfigManager()

# 便捷函数
def get_config(key: str = "main", use_cache: bool = True) -> Dict[str, Any]:
    """获取完整配置"""
    return config_manager.get_config(key, use_cache)

def get_mem0_config(key: str = "main") -> Dict[str, Any]:
    """获取Mem0配置"""
    return config_manager.get_mem0_config(key)

def get_openmemory_config(key: str = "main") -> Dict[str, Any]:
    """获取OpenMemory配置"""
    return config_manager.get_openmemory_config(key)

def save_config(config: Dict[str, Any], key: str = "main") -> Dict[str, Any]:
    """保存配置到数据库"""
    db = SessionLocal()
    try:
        return config_manager.save_config_to_db(db, config, key)
    finally:
        db.close()

def reset_config(key: str = "main") -> Dict[str, Any]:
    """重置配置为默认值"""
    return config_manager.reset_to_default(key)

def clear_config_cache():
    """清除配置缓存"""
    config_manager.clear_cache() 