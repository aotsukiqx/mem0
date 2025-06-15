from mem0 import Memory
import os
import uuid
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

# 加载 .env 文件
env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
print(f"env_path: {env_path}")
load_dotenv(dotenv_path=env_path)

config = {
    "version": "v1.1",
    "llm": {
        "provider": "openai",
        "config": {
            "model": "gemma3-27b",
            "openai_base_url": os.getenv("VECTOR_API_BASE","https://1api.mynameqx.top:5003/v1"),
            "api_key": os.getenv("api-key"),
            "temperature": 0.2,
            "max_tokens": 32768,
        }
    },
    "graph_store": {
        "provider": "neo4j",
        "config": {
            "url": "neo4j://rock5srv.mynameqx.top:7687",
            "username": "neo4j",
            "password": "i2EYPRi5FQsGxLNviL6T"
        },
        "llm" : {
            "provider": "openai",
            "config": {
                "model": "gemma3-27b",
                "openai_base_url": os.getenv("VECTOR_API_BASE","https://1api.mynameqx.top:5003/v1"),
                "api_key": os.getenv("api-key"),
                "temperature": 0,
                "max_tokens": 32768,
            }
        }
    },
    "vector_store": {
        "provider": os.getenv("VECTOR_STORE_TYPE"),
        "config": {
                "collection_name": "cursor",
                "url": "http://n1.mynameqx.top:19530",
                "embedding_model_dims": 5376,
                "token": "env:MILVUS_TOKEN"
            }
    },
    "embedder": {
        "provider": "openai",
        "config": {
            "openai_base_url": os.getenv("VECTOR_API_BASE","http://studioh.mynameqx.top:9997/v1"),
            "model": os.getenv("VECTOR_MODEL","gte-Qwen2"),
            "api_key": os.getenv("VECTOR_API_KEY","test")
        }
    }
}
kb=json.dumps([
  [
    "如何处理用户未指定位置的天气预报请求?",
    "首先请求用户提供具体位置,然后使用AskInternet搜索该位置的天气预报,并提供包含天气详情和参考的结构化响应."
  ],
  [
    "天气预报应包含哪些关键信息?",
    "天气预报应包含天气状况,温度范围,风速和风向,湿度,降水量和空气质量指数(AQI)等关键信息."
  ],
  [
    "如何确保天气预报信息的准确性?",
    "使用来自多个全球气象机构的数据来生成预报,确保信息的准确性."
  ]
])
testmemory = Memory.from_config(config)
# print(f"clean memory:{testmemory.delete_all('testmem0')}")
res=testmemory.add(kb, user_id="testmem0")
print(f"add memory:{res}")
res = testmemory.search("你叫什么",user_id="testmem0")
# res = testmemory.get_all(user_id="testmem0")
print(f"type: {type(res)}")
print(res)
