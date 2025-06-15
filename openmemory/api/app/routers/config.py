import os
import json
from typing import Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Config as ConfigModel
from app.utils.memory import reset_memory_client

router = APIRouter(prefix="/api/v1/config", tags=["config"])

class LLMConfig(BaseModel):
    model: str = Field(..., description="LLM model name")
    temperature: float = Field(..., description="Temperature setting for the model")
    max_tokens: int = Field(..., description="Maximum tokens to generate")
    api_key: Optional[str] = Field(None, description="API key or 'env:API_KEY' to use environment variable")
    ollama_base_url: Optional[str] = Field(None, description="Base URL for Ollama server (e.g., http://host.docker.internal:11434)")
    openai_base_url: Optional[str] = Field(None, description="Base URL for OpenAI-compatible API (e.g., https://api.openai.com/v1)")

class LLMProvider(BaseModel):
    provider: str = Field(..., description="LLM provider name")
    config: LLMConfig

class EmbedderConfig(BaseModel):
    model: str = Field(..., description="Embedder model name")
    api_key: Optional[str] = Field(None, description="API key or 'env:API_KEY' to use environment variable")
    ollama_base_url: Optional[str] = Field(None, description="Base URL for Ollama server (e.g., http://host.docker.internal:11434)")
    openai_base_url: Optional[str] = Field(None, description="Base URL for OpenAI-compatible API (e.g., https://api.openai.com/v1)")

class EmbedderProvider(BaseModel):
    provider: str = Field(..., description="Embedder provider name")
    config: EmbedderConfig

class OpenMemoryConfig(BaseModel):
    custom_instructions: Optional[str] = Field(None, description="Custom instructions for memory management and fact extraction")

class GraphStoreConfig(BaseModel):
    url: str = Field(..., description="Neo4j database URL")
    username: str = Field(..., description="Neo4j username")
    password: str = Field(..., description="Neo4j password")

class GraphStoreProvider(BaseModel):
    provider: str = Field(..., description="Graph store provider name")
    config: GraphStoreConfig
    llm: Optional[LLMProvider] = Field(None, description="LLM configuration for graph store")

class VectorStoreConfig(BaseModel):
    collection_name: str = Field(..., description="Collection name")
    url: str = Field(..., description="Vector store URL")
    embedding_model_dims: int = Field(..., description="Embedding model dimensions")
    token: Optional[str] = Field(None, description="Access token or 'env:TOKEN' to use environment variable")

class VectorStoreProvider(BaseModel):
    provider: str = Field(..., description="Vector store provider name")
    config: VectorStoreConfig

class Mem0Config(BaseModel):
    llm: Optional[LLMProvider] = None
    embedder: Optional[EmbedderProvider] = None
    graph_store: Optional[GraphStoreProvider] = None
    vector_store: Optional[VectorStoreProvider] = None
    version: Optional[str] = None

class ConfigSchema(BaseModel):
    openmemory: Optional[OpenMemoryConfig] = None
    mem0: Mem0Config

def get_default_configuration():
    """
    获取默认配置。
    
    注意：此函数已弃用，建议使用 app.utils.config_manager.config_manager.get_built_in_default_config() 代替。
    保留此函数仅为向后兼容。
    """
    from app.utils.config_manager import config_manager
    return config_manager.get_built_in_default_config()

def get_frontend_default_configuration(include_advanced: bool = False):
    """Get the filtered default configuration for frontend display."""
    full_config = get_default_configuration()
    
    if include_advanced:
        # Return full configuration for advanced view
        return {
            "openmemory": full_config.get("openmemory", {}),
            "mem0": full_config.get("mem0", {})
        }
    else:
        # Return basic configuration for standard view
        return {
            "openmemory": full_config.get("openmemory", {}),
            "mem0": {
                "llm": full_config.get("mem0", {}).get("llm"),
                "embedder": full_config.get("mem0", {}).get("embedder")
            }
        }

def get_config_from_db(db: Session, key: str = "main"):
    """
    从数据库获取配置。
    
    注意：此函数已弃用，建议使用 app.utils.config_manager.config_manager.get_config_from_db() 代替。
    保留此函数仅为向后兼容。
    """
    from app.utils.config_manager import config_manager
    return config_manager.get_config_from_db(db, key)

def save_config_to_db(db: Session, config: Dict[str, Any], key: str = "main"):
    """
    保存配置到数据库。
    
    注意：此函数已弃用，建议使用 app.utils.config_manager.config_manager.save_config_to_db() 代替。
    保留此函数仅为向后兼容。
    """
    from app.utils.config_manager import config_manager
    return config_manager.save_config_to_db(db, config, key)

@router.get("/", response_model=ConfigSchema)
async def get_configuration(advanced: bool = True, db: Session = Depends(get_db)):
    """Get the current configuration."""
    config = get_config_from_db(db)
    
    if advanced:
        # Return full configuration for advanced view
        return {
            "openmemory": config.get("openmemory", {}),
            "mem0": config.get("mem0", {})
        }
    else:
        # Filter the configuration to only return fields that the frontend expects
        filtered_config = {
            "openmemory": config.get("openmemory", {}),
            "mem0": {
                "llm": config.get("mem0", {}).get("llm"),
                "embedder": config.get("mem0", {}).get("embedder")
            }
        }
        
        return filtered_config

@router.put("/", response_model=ConfigSchema)
async def update_configuration(config: ConfigSchema, db: Session = Depends(get_db)):
    """Update the configuration."""
    current_config = get_config_from_db(db)
    
    # Convert to dict for processing
    updated_config = current_config.copy()
    
    # Update openmemory settings if provided
    if config.openmemory is not None:
        if "openmemory" not in updated_config:
            updated_config["openmemory"] = {}
        updated_config["openmemory"].update(config.openmemory.dict(exclude_none=True))
    
    # Update mem0 settings - merge with existing mem0 config to preserve other fields
    if "mem0" not in updated_config:
        updated_config["mem0"] = {}
    
    mem0_update = config.mem0.dict(exclude_none=True)
    if "llm" in mem0_update:
        updated_config["mem0"]["llm"] = mem0_update["llm"]
    if "embedder" in mem0_update:
        updated_config["mem0"]["embedder"] = mem0_update["embedder"]
    if "graph_store" in mem0_update:
        updated_config["mem0"]["graph_store"] = mem0_update["graph_store"]
    if "vector_store" in mem0_update:
        updated_config["mem0"]["vector_store"] = mem0_update["vector_store"]
    if "version" in mem0_update:
        updated_config["mem0"]["version"] = mem0_update["version"]
    
    # Save the configuration to database
    save_config_to_db(db, updated_config)
    reset_memory_client()
    
    # Return full configuration for frontend (so JSON editor shows complete config)
    return {
        "openmemory": updated_config.get("openmemory", {}),
        "mem0": updated_config.get("mem0", {})
    }

@router.post("/reset", response_model=ConfigSchema)
async def reset_configuration(db: Session = Depends(get_db)):
    """Reset the configuration to default values."""
    try:
        # Get the default configuration with proper provider setups
        default_config = get_default_configuration()
        
        # Save it as the current configuration in the database
        save_config_to_db(db, default_config)
        reset_memory_client()
        
        # Return full configuration for frontend (so JSON editor shows complete config)
        return get_frontend_default_configuration(include_advanced=True)
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to reset configuration: {str(e)}"
        )

@router.get("/mem0/llm", response_model=LLMProvider)
async def get_llm_configuration(db: Session = Depends(get_db)):
    """Get only the LLM configuration."""
    config = get_config_from_db(db)
    llm_config = config.get("mem0", {}).get("llm", {})
    return llm_config

@router.put("/mem0/llm", response_model=LLMProvider)
async def update_llm_configuration(llm_config: LLMProvider, db: Session = Depends(get_db)):
    """Update only the LLM configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the LLM configuration
    current_config["mem0"]["llm"] = llm_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["llm"]

@router.get("/mem0/embedder", response_model=EmbedderProvider)
async def get_embedder_configuration(db: Session = Depends(get_db)):
    """Get only the Embedder configuration."""
    config = get_config_from_db(db)
    embedder_config = config.get("mem0", {}).get("embedder", {})
    return embedder_config

@router.put("/mem0/embedder", response_model=EmbedderProvider)
async def update_embedder_configuration(embedder_config: EmbedderProvider, db: Session = Depends(get_db)):
    """Update only the Embedder configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Embedder configuration
    current_config["mem0"]["embedder"] = embedder_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["embedder"]

@router.get("/openmemory", response_model=OpenMemoryConfig)
async def get_openmemory_configuration(db: Session = Depends(get_db)):
    """Get only the OpenMemory configuration."""
    config = get_config_from_db(db)
    openmemory_config = config.get("openmemory", {})
    return openmemory_config

@router.put("/openmemory", response_model=OpenMemoryConfig)
async def update_openmemory_configuration(openmemory_config: OpenMemoryConfig, db: Session = Depends(get_db)):
    """Update only the OpenMemory configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure openmemory key exists
    if "openmemory" not in current_config:
        current_config["openmemory"] = {}
    
    # Update the OpenMemory configuration
    current_config["openmemory"].update(openmemory_config.dict(exclude_none=True))
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["openmemory"]

@router.get("/mem0/graph_store", response_model=GraphStoreProvider)
async def get_graph_store_configuration(db: Session = Depends(get_db)):
    """Get only the Graph Store configuration."""
    config = get_config_from_db(db)
    graph_store_config = config.get("mem0", {}).get("graph_store", {})
    return graph_store_config

@router.put("/mem0/graph_store", response_model=GraphStoreProvider)
async def update_graph_store_configuration(graph_store_config: GraphStoreProvider, db: Session = Depends(get_db)):
    """Update only the Graph Store configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Graph Store configuration
    current_config["mem0"]["graph_store"] = graph_store_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["graph_store"]

@router.get("/mem0/vector_store", response_model=VectorStoreProvider)
async def get_vector_store_configuration(db: Session = Depends(get_db)):
    """Get only the Vector Store configuration."""
    config = get_config_from_db(db)
    vector_store_config = config.get("mem0", {}).get("vector_store", {})
    return vector_store_config

@router.put("/mem0/vector_store", response_model=VectorStoreProvider)
async def update_vector_store_configuration(vector_store_config: VectorStoreProvider, db: Session = Depends(get_db)):
    """Update only the Vector Store configuration."""
    current_config = get_config_from_db(db)
    
    # Ensure mem0 key exists
    if "mem0" not in current_config:
        current_config["mem0"] = {}
    
    # Update the Vector Store configuration
    current_config["mem0"]["vector_store"] = vector_store_config.dict(exclude_none=True)
    
    # Save the configuration to database
    save_config_to_db(db, current_config)
    reset_memory_client()
    return current_config["mem0"]["vector_store"] 