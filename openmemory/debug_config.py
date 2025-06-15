#!/usr/bin/env python3
"""
配置诊断脚本 - 深度分析OpenMemory配置传递问题
"""

import os
import sys
import json

# 设置路径以便导入模块
sys.path.append('/usr/src/openmemory')
sys.path.append('.')

def check_environment_variables():
    """检查相关环境变量"""
    print("=" * 80)
    print("🔍 环境变量检查")
    print("=" * 80)
    
    openai_vars = [
        'OPENAI_API_KEY',
        'OPENAI_API_BASE', 
        'OPENAI_BASE_URL',
        'OPENROUTER_API_KEY',
        'OPENROUTER_API_BASE',
        'MEM0_API_KEY'
    ]
    
    for var in openai_vars:
        value = os.environ.get(var)
        if value:
            if 'KEY' in var or 'TOKEN' in var:
                masked_value = f"{'*' * 8}...{value[-4:]}" if len(value) > 4 else f"{'*' * len(value)}"
                print(f"✅ {var}: {masked_value}")
            else:
                print(f"✅ {var}: {value}")
        else:
            print(f"❌ {var}: 未设置")
    print()

def test_config_manager():
    """测试配置管理器"""
    print("=" * 80)
    print("🔧 配置管理器测试")
    print("=" * 80)
    
    try:
        from app.utils.config_manager import get_mem0_config, get_config
        
        # 获取完整配置
        full_config = get_config()
        mem0_config = get_mem0_config()
        
        def mask_config(config):
            """递归遮掩敏感信息"""
            if isinstance(config, dict):
                masked = {}
                for key, value in config.items():
                    if key.lower() in ['api_key', 'password', 'token']:
                        if isinstance(value, str) and value:
                            if value.startswith('env:'):
                                masked[key] = value  # 显示env:标记
                            else:
                                masked[key] = f"{'*' * 8}...{value[-4:]}" if len(value) > 4 else f"{'*' * len(value)}"
                        else:
                            masked[key] = value
                    else:
                        masked[key] = mask_config(value) if isinstance(value, dict) else value
                return masked
            return config
        
        masked_full = mask_config(full_config)
        masked_mem0 = mask_config(mem0_config)
        
        print("📋 完整配置:")
        print(json.dumps(masked_full, indent=2, ensure_ascii=False))
        print()
        
        print("🧠 Mem0配置:")
        print(json.dumps(masked_mem0, indent=2, ensure_ascii=False))
        print()
        
        # 重点检查LLM配置
        llm_config = mem0_config.get('llm', {}).get('config', {})
        embedder_config = mem0_config.get('embedder', {}).get('config', {})
        
        print("🔍 重点配置检查:")
        print(f"   LLM OpenAI Base URL: {llm_config.get('openai_base_url', '未设置')}")
        print(f"   LLM API Key: {llm_config.get('api_key', '未设置')}")
        print(f"   Embedder OpenAI Base URL: {embedder_config.get('openai_base_url', '未设置')}")
        print(f"   Embedder API Key: {embedder_config.get('api_key', '未设置')}")
        print()
        
        return mem0_config
        
    except Exception as e:
        print(f"❌ 配置管理器测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_memory_client_creation():
    """测试内存客户端创建过程"""
    print("=" * 80)
    print("🤖 内存客户端创建测试")
    print("=" * 80)
    
    try:
        from app.utils.memory import get_memory_client
        
        print("正在创建内存客户端...")
        client = get_memory_client()
        
        if client:
            print("✅ 内存客户端创建成功!")
            
            # 检查客户端内部配置
            if hasattr(client, 'memory_client'):
                raw_client = client.memory_client
            else:
                raw_client = client
                
            print(f"   客户端类型: {type(raw_client).__name__}")
            
            # 检查LLM配置
            if hasattr(raw_client, 'llm'):
                llm = raw_client.llm
                print(f"   LLM类型: {type(llm).__name__}")
                
                if hasattr(llm, 'client'):
                    openai_client = llm.client
                    print(f"   OpenAI客户端类型: {type(openai_client).__name__}")
                    if hasattr(openai_client, 'base_url'):
                        print(f"   ✅ 实际Base URL: {openai_client.base_url}")
                    else:
                        print("   ❌ 无法获取base_url")
                        
                if hasattr(llm, 'config'):
                    llm_config = llm.config
                    print(f"   LLM配置模型: {getattr(llm_config, 'model', '未知')}")
                    print(f"   LLM配置Base URL: {getattr(llm_config, 'openai_base_url', '未设置')}")
            
            # 检查Embedder配置
            if hasattr(raw_client, 'embedding_model'):
                embedder = raw_client.embedding_model
                print(f"   Embedder类型: {type(embedder).__name__}")
                
                if hasattr(embedder, 'client'):
                    embedder_client = embedder.client
                    print(f"   Embedder客户端类型: {type(embedder_client).__name__}")
                    if hasattr(embedder_client, 'base_url'):
                        print(f"   ✅ Embedder实际Base URL: {embedder_client.base_url}")
                    else:
                        print("   ❌ 无法获取embedder base_url")
        else:
            print("❌ 内存客户端创建失败!")
            
        return client
        
    except Exception as e:
        print(f"❌ 内存客户端创建测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_mem0_direct():
    """直接测试Mem0配置"""
    print("=" * 80)
    print("🎯 直接Mem0测试")
    print("=" * 80)
    
    try:
        from mem0 import Memory
        
        # 使用配置管理器的配置
        from app.utils.config_manager import get_mem0_config
        config = get_mem0_config()
        
        print("使用配置创建Mem0客户端...")
        print(f"配置LLM Provider: {config.get('llm', {}).get('provider')}")
        print(f"配置LLM Base URL: {config.get('llm', {}).get('config', {}).get('openai_base_url')}")
        
        # 解析环境变量
        from app.utils.memory import _parse_environment_variables
        parsed_config = _parse_environment_variables(config)
        
        print("解析环境变量后:")
        print(f"解析后LLM API Key: {parsed_config.get('llm', {}).get('config', {}).get('api_key', '')[:10] if parsed_config.get('llm', {}).get('config', {}).get('api_key') else '未设置'}...")
        
        memory_client = Memory.from_config(config_dict=parsed_config)
        
        print("✅ Mem0客户端创建成功!")
        
        # 检查实际使用的base_url
        if hasattr(memory_client, 'llm') and hasattr(memory_client.llm, 'client'):
            actual_base_url = getattr(memory_client.llm.client, 'base_url', '未知')
            print(f"🎯 关键发现 - 实际使用的Base URL: {actual_base_url}")
            
            if 'api.openai.com' in str(actual_base_url):
                print("❌ 警告: 仍在使用OpenAI官方地址!")
            else:
                print("✅ 使用了自定义Base URL")
                
        return memory_client
        
    except Exception as e:
        print(f"❌ 直接Mem0测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    print("🚀 OpenMemory配置诊断脚本")
    print("此脚本将深度分析配置传递过程，找出为什么仍在访问OpenAI官方API")
    print()
    
    # 1. 检查环境变量
    check_environment_variables()
    
    # 2. 测试配置管理器
    config = test_config_manager()
    
    # 3. 测试内存客户端创建
    memory_client = test_memory_client_creation()
    
    # 4. 直接测试Mem0
    direct_client = test_mem0_direct()
    
    print("=" * 80)
    print("📊 诊断总结")
    print("=" * 80)
    
    if config:
        print("✅ 配置管理器正常")
    else:
        print("❌ 配置管理器异常")
        
    if memory_client:
        print("✅ 内存客户端创建正常")
    else:
        print("❌ 内存客户端创建异常")
        
    if direct_client:
        print("✅ 直接Mem0客户端创建正常")
    else:
        print("❌ 直接Mem0客户端创建异常")
        
    print()
    print("🔍 如果仍然访问OpenAI官方API，可能的原因:")
    print("1. 环境变量OPENAI_API_BASE或OPENAI_BASE_URL被设置且覆盖了配置")
    print("2. 某个地方直接使用OpenAI客户端而没有传递配置")
    print("3. 配置解析过程中出现问题")
    print("4. 多个不同的客户端实例使用了不同的配置")

if __name__ == "__main__":
    main() 