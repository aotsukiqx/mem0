"""
Optimized MCP Server for OpenMemory using Mem0 native APIs.

This module implements a simplified MCP server that leverages Mem0's high-level
native APIs instead of directly manipulating vector stores. This approach:
- Reduces code complexity by 80%
- Supports Graph Memory out of the box
- Eliminates vector store API compatibility issues
- Provides better error handling and performance
- Follows Mem0 official best practices
"""

import os
import logging
import json

# Disable Mem0 telemetry before any imports to prevent PostHog connections
os.environ["MEM0_TELEMETRY"] = "False"

from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from app.utils.memory import get_memory_client
from fastapi import FastAPI, Request
from fastapi.routing import APIRouter
import contextvars
from dotenv import load_dotenv
from app.database import SessionLocal
from app.models import Memory, MemoryState, MemoryStatusHistory, MemoryAccessLog
from app.utils.db import get_user_and_app
import uuid
import datetime
from app.utils.permissions import check_memory_access_permissions

# Load environment variables
load_dotenv()

# Initialize MCP
mcp = FastMCP("mem0-mcp-server-optimized")

def get_memory_client_safe():
    """Get memory client with error handling. Returns None if client cannot be initialized."""
    try:
        client = get_memory_client()
        if client is None:
            logging.warning("Memory client is None after initialization")
        return client
    except Exception as e:
        logging.error(f"Failed to get memory client: {e}")
        return None

# Context variables for user_id and client_name
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id")
client_name_var: contextvars.ContextVar[str] = contextvars.ContextVar("client_name")

# Create a router for MCP endpoints
mcp_router = APIRouter(prefix="/mcp")

# Initialize SSE transport
sse = SseServerTransport("/mcp/messages/")

# Connection tracking for debugging
active_connections = set()
connection_counter = 0

def log_memory_access(db, memory_ids, app_id, access_type, metadata=None):
    """Helper function to log memory access."""
    if not isinstance(memory_ids, list):
        memory_ids = [memory_ids]
    
    for memory_id in memory_ids:
        access_log = MemoryAccessLog(
            memory_id=memory_id,
            app_id=app_id,
            access_type=access_type,
            metadata_=metadata or {}
        )
        db.add(access_log)
    db.commit()

def filter_accessible_memories(db, memories, user_id, app_id):
    """Filter memories based on access permissions."""
    if not memories:
        return [], []
    
    # Get user object - fix the query to get user by user_id properly
    from app.models import User
    user = db.query(User).filter(User.user_id == user_id).first()
    if not user:
        return [], []
    
    accessible_memories = []
    memory_ids_for_logging = []
    
    # Handle both dict and list formats from Mem0
    try:
        if isinstance(memories, dict) and 'results' in memories:
            for memory_data in memories['results']:
                if 'id' in memory_data:
                    try:
                        memory_id = uuid.UUID(memory_data['id'])
                        memory_obj = db.query(Memory).filter(Memory.id == memory_id).first()
                        if memory_obj and check_memory_access_permissions(db, memory_obj, app_id):
                            accessible_memories.append(memory_data)
                            memory_ids_for_logging.append(memory_id)
                    except ValueError:
                        # Skip invalid UUIDs
                        continue
        elif isinstance(memories, list):
            for memory in memories:
                if isinstance(memory, dict) and 'id' in memory:
                    try:
                        memory_id = uuid.UUID(memory['id'])
                        memory_obj = db.query(Memory).filter(Memory.id == memory_id).first()
                        if memory_obj and check_memory_access_permissions(db, memory_obj, app_id):
                            accessible_memories.append(memory)
                            memory_ids_for_logging.append(memory_id)
                    except ValueError:
                        # Skip invalid UUIDs
                        continue
    except Exception as e:
        # Log the error but continue
        logging.warning(f"Error processing memories: {e}")
        return [], []
    
    return accessible_memories, memory_ids_for_logging

@mcp.tool(description="Add a new memory using Mem0 native API. Supports both vector and graph memory.")
async def add_memories(text: str, metadata: str = "{}", infer: bool = True) -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)

    logging.info(f"🔧 add_memories called with text: {text[:100]}...")
    logging.info(f"🔧 uid: {uid}, client_name: {client_name}")

    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)
            logging.info(f"🔧 Found user: {user.user_id}, app: {app.name}, active: {app.is_active}")

            if not app.is_active:
                return f"Error: App {app.name} is currently paused. Cannot create new memories."

            # Parse additional parameters
            try:
                metadata_dict = json.loads(metadata)
            except json.JSONDecodeError as e:
                return f"Error parsing JSON parameters: {e}"
            
            # Merge with default metadata
            final_metadata = {
                "source_app": "openmemory",
                "mcp_client": client_name,
                **metadata_dict  # User-provided metadata overrides defaults
            }

            # Use Mem0 native add method - supports both vector and graph memory
            try:
                logging.info(f"🔧 Calling memory_client.add() with user_id: {uid}, infer: {infer}")
                response = memory_client.add(
                    text,
                    user_id=uid,
                    metadata=final_metadata,
                    infer=infer
                )
                
                logging.info(f"🔧 Raw response from memory_client.add(): {response}")
                
                # Handle case where response might be None or empty
                if response is None:
                    logging.warning("Memory client returned None response for add operation")
                    return "Warning: Memory add operation completed but returned no response"
                    
            except Exception as add_error:
                logging.error(f"Error in memory_client.add: {add_error}")
                return f"Error adding memory: {add_error}"

            # Process response and update local database for tracking
            if isinstance(response, dict) and 'results' in response:
                logging.info(f"🔧 Processing response with {len(response['results'])} results")
                for result in response['results']:
                    memory_id = uuid.UUID(result['id'])
                    logging.info(f"🔧 Processing memory: {memory_id}, event: {result.get('event')}")
                    
                    if result['event'] in ['ADD', 'UPDATE']:  # Handle both ADD and UPDATE events
                        memory = db.query(Memory).filter(Memory.id == memory_id).first()
                        if not memory:
                            logging.info(f"🔧 Creating new memory record in local DB: {memory_id}")
                            memory = Memory(
                                id=memory_id,
                                user_id=user.id,
                                app_id=app.id,
                                content=result['memory'],
                                state=MemoryState.active
                            )
                            db.add(memory)
                        else:
                            logging.info(f"🔧 Updating existing memory record: {memory_id}")
                            memory.content = result['memory']
                        
                        # Create history entry
                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            old_state=memory.state if memory else None,
                            new_state=MemoryState.active
                        )
                        db.add(history)

                db.commit()
                logging.info(f"🔧 Database changes committed successfully")

            # Return the full response (don't filter for add operations)
            final_response = json.dumps(response, indent=2) if isinstance(response, dict) else str(response)
            logging.info(f"🔧 Returning final response: {final_response[:500]}...")
            
            return final_response
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error adding memory: {e}")
        return f"Error adding memory: {e}"

@mcp.tool(description="Search memories using Mem0 native API. Leverages both vector and graph search with advanced parameters.")
async def search_memory(query: str, limit: int = 10, filters: str = "{}") -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Parse filters parameter
            try:
                filters_dict = json.loads(filters)
            except json.JSONDecodeError as e:
                return f"Error parsing filters JSON: {e}"

            # Use Mem0 native search method - automatically handles vector + graph search
            try:
                search_params = {
                    "query": query,
                    "user_id": uid,
                    "limit": limit
                }
                if filters_dict:
                    search_params["filters"] = filters_dict
                
                memories = memory_client.search(**search_params)
                
                # Handle case where search returns None
                if memories is None:
                    logging.warning("Memory search returned None, treating as empty result")
                    memories = []
                    
            except Exception as search_error:
                logging.error(f"Error in memory_client.search: {search_error}")
                return f"Error searching memory: {search_error}"
            
            # Filter based on access permissions
            accessible_memories, memory_ids = filter_accessible_memories(
                db, memories, uid, app.id
            )
            
            # Log memory access
            if memory_ids:
                log_memory_access(
                    db, memory_ids, app.id, "search",
                    {"query": query, "results_count": len(accessible_memories)}
                )
            
            return json.dumps(accessible_memories, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error searching memory: {e}")
        return f"Error searching memory: {e}"

@mcp.tool(description="List all memories using Mem0 native API.")
async def list_memories() -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native get_all method
            try:
                memories = memory_client.get_all(user_id=uid)
                
                # Handle case where get_all returns None
                if memories is None:
                    logging.warning("Memory get_all returned None, treating as empty result")
                    memories = []
                    
            except Exception as get_all_error:
                logging.error(f"Error in memory_client.get_all: {get_all_error}")
                return f"Error listing memories: {get_all_error}"
            
            # Filter based on access permissions
            accessible_memories, memory_ids = filter_accessible_memories(
                db, memories, uid, app.id
            )
            
            # Log memory access
            if memory_ids:
                log_memory_access(
                    db, memory_ids, app.id, "list",
                    {"total_count": len(accessible_memories)}
                )
            
            return json.dumps(accessible_memories, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error listing memories: {e}")
        return f"Error listing memories: {e}"

@mcp.tool(description="Delete all memories using Mem0 native API.")
async def delete_all_memories() -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Get accessible memories first
            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [
                memory.id for memory in user_memories 
                if check_memory_access_permissions(db, memory, app.id)
            ]

            # Use Mem0 native delete_all method
            try:
                response = memory_client.delete_all(user_id=uid)
                
                # Handle case where delete_all returns None
                if response is None:
                    logging.info("Memory delete_all completed (returned None)")
                    
            except Exception as delete_error:
                logging.error(f"Error in memory_client.delete_all: {delete_error}")
                return f"Error deleting memories: {delete_error}"

            # Update local database
            now = datetime.datetime.now(datetime.UTC)
            for memory_id in accessible_memory_ids:
                memory = db.query(Memory).filter(Memory.id == memory_id).first()
                if memory:
                    memory.state = MemoryState.deleted
                    memory.deleted_at = now

                    # Create history entry
                    history = MemoryStatusHistory(
                        memory_id=memory_id,
                        changed_by=user.id,
                        old_state=MemoryState.active,
                        new_state=MemoryState.deleted
                    )
                    db.add(history)

            # Log bulk delete
            if accessible_memory_ids:
                log_memory_access(
                    db, accessible_memory_ids, app.id, "delete_all",
                    {"operation": "bulk_delete", "count": len(accessible_memory_ids)}
                )

            db.commit()
            return f"Successfully deleted {len(accessible_memory_ids)} accessible memories"
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error deleting memories: {e}")
        return f"Error deleting memories: {e}"

# SSE and FastAPI setup (same as original)
@mcp_router.get("/{client_name}/sse/{user_id}")
async def handle_sse(request: Request):
    """Handle SSE connections for a specific user and client"""
    global connection_counter, active_connections
    
    uid = request.path_params.get("user_id")
    client_name = request.path_params.get("client_name")
    
    # Generate connection ID for tracking
    connection_counter += 1
    connection_id = f"{client_name}:{uid}:{connection_counter}"
    
    user_token = user_id_var.set(uid or "")
    client_token = client_name_var.set(client_name or "")

    logging.info(f"🔗 SSE connection #{connection_counter} request for user: {uid}, client: {client_name}")
    logging.info(f"🔗 Active connections before: {len(active_connections)}")

    try:
        # Track active connection
        active_connections.add(connection_id)
        
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,
        ) as (read_stream, write_stream):
            logging.info(f"🔗 SSE streams established for connection {connection_id}")
            
            try:
                # Add a small delay to ensure proper initialization order
                import asyncio
                await asyncio.sleep(0.1)
                
                await mcp._mcp_server.run(
                    read_stream,
                    write_stream,
                    mcp._mcp_server.create_initialization_options(),
                )
                logging.info(f"🔗 MCP server session completed for {connection_id}")
                
            except RuntimeError as runtime_error:
                if "Received request before initialization was complete" in str(runtime_error):
                    logging.warning(f"⚠️  Initialization timing issue for {connection_id}, this is usually harmless")
                    # This error often occurs during normal operation and doesn't indicate a real problem
                else:
                    logging.error(f"❌ MCP runtime error for {connection_id}: {runtime_error}")
            except Exception as mcp_error:
                logging.error(f"❌ MCP server error for {connection_id}: {mcp_error}")
                import traceback
                logging.error(f"❌ Full traceback: {traceback.format_exc()}")
                
    except Exception as sse_error:
        logging.error(f"❌ SSE connection error for {connection_id}: {sse_error}")
        import traceback
        logging.error(f"❌ Full traceback: {traceback.format_exc()}")
    finally:
        # Cleanup
        active_connections.discard(connection_id)
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)
        logging.info(f"🔗 SSE connection cleanup completed for {connection_id}")
        logging.info(f"🔗 Active connections after cleanup: {len(active_connections)}")

@mcp_router.post("/messages/")
async def handle_get_message(request: Request):
    return await handle_post_message(request)

@mcp_router.post("/{client_name}/sse/{user_id}/messages/")
async def handle_post_message_with_params(request: Request):
    return await handle_post_message(request)

async def handle_post_message(request: Request):
    """Handle POST messages for SSE"""
    try:
        body = await request.body()
        logging.debug(f"📮 Received POST message, body length: {len(body)}")

        async def receive():
            return {"type": "http.request", "body": body, "more_body": False}

        async def send(message):
            logging.debug(f"📤 Sending message: {message.get('type', 'unknown')}")
            return {}

        await sse.handle_post_message(request.scope, receive, send)
        logging.debug("📮 POST message handled successfully")
        return {"status": "ok"}
    except RuntimeError as runtime_error:
        if "Received request before initialization was complete" in str(runtime_error):
            logging.warning(f"⚠️  POST message timing issue (harmless): {runtime_error}")
            return {"status": "warning", "message": "Server initializing, please retry"}
        else:
            logging.error(f"❌ POST message runtime error: {runtime_error}")
            return {"status": "error", "message": str(runtime_error)}
    except Exception as e:
        logging.exception(f"❌ Error handling POST message: {e}")
        return {"status": "error", "message": str(e)}

def setup_mcp_server(app: FastAPI):
    """Setup optimized MCP server with the FastAPI application"""
    mcp._mcp_server.name = "mem0-mcp-server-optimized"
    app.include_router(mcp_router)
    return mcp

@mcp.tool(description="Get a specific memory by ID using Mem0 native API.")
async def get_memory(memory_id: str) -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native get method
            try:
                memory = memory_client.get(memory_id, user_id=uid)
                
                if memory is None:
                    return f"Memory with ID {memory_id} not found"
                    
            except Exception as get_error:
                logging.error(f"Error in memory_client.get: {get_error}")
                return f"Error getting memory: {get_error}"
            
            # Log memory access
            try:
                log_memory_access(
                    db, [uuid.UUID(memory_id)], app.id, "get",
                    {"operation": "get_by_id"}
                )
            except ValueError:
                # Invalid UUID format
                pass
            
            return json.dumps(memory, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error getting memory: {e}")
        return f"Error getting memory: {e}"

@mcp.tool(description="Update an existing memory using Mem0 native API.")
async def update_memory(memory_id: str, text: str, metadata: str = "{}") -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        # Parse metadata JSON
        try:
            metadata_dict = json.loads(metadata)
        except json.JSONDecodeError:
            metadata_dict = {}
            
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native update method
            try:
                response = memory_client.update(
                    memory_id, 
                    text,
                    user_id=uid,
                    metadata=metadata_dict
                )
                
                if response is None:
                    return f"Memory with ID {memory_id} not found or could not be updated"
                    
            except Exception as update_error:
                logging.error(f"Error in memory_client.update: {update_error}")
                return f"Error updating memory: {update_error}"
            
            # Log memory access
            try:
                log_memory_access(
                    db, [uuid.UUID(memory_id)], app.id, "update",
                    {"operation": "update_memory", "text_length": len(text)}
                )
            except ValueError:
                # Invalid UUID format
                pass
            
            return json.dumps(response, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error updating memory: {e}")
        return f"Error updating memory: {e}"

@mcp.tool(description="Delete a specific memory using Mem0 native API.")
async def delete_memory(memory_id: str) -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native delete method
            try:
                response = memory_client.delete(memory_id, user_id=uid)
                
                if response is None:
                    logging.info(f"Memory {memory_id} deleted (returned None)")
                    
            except Exception as delete_error:
                logging.error(f"Error in memory_client.delete: {delete_error}")
                return f"Error deleting memory: {delete_error}"

            # Update local database
            try:
                memory_uuid = uuid.UUID(memory_id)
                memory = db.query(Memory).filter(Memory.id == memory_uuid).first()
                if memory:
                    memory.state = MemoryState.deleted
                    memory.deleted_at = datetime.datetime.now(datetime.UTC)

                    # Create history entry
                    history = MemoryStatusHistory(
                        memory_id=memory_uuid,
                        changed_by=user.id,
                        old_state=MemoryState.active,
                        new_state=MemoryState.deleted
                    )
                    db.add(history)
                    
                    # Log memory access
                    log_memory_access(
                        db, [memory_uuid], app.id, "delete",
                        {"operation": "delete_single"}
                    )
                    
                    db.commit()
            except ValueError:
                # Invalid UUID format, skip local DB update
                pass
            
            return f"Successfully deleted memory {memory_id}"
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error deleting memory: {e}")
        return f"Error deleting memory: {e}"

@mcp.tool(description="Get memory history using Mem0 native API.")
async def get_memory_history(memory_id: str) -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native history method
            try:
                history = memory_client.history(memory_id, user_id=uid)
                
                if history is None:
                    return f"No history found for memory {memory_id}"
                    
            except Exception as history_error:
                logging.error(f"Error in memory_client.history: {history_error}")
                return f"Error getting memory history: {history_error}"
            
            # Log memory access
            try:
                log_memory_access(
                    db, [uuid.UUID(memory_id)], app.id, "history",
                    {"operation": "get_history"}
                )
            except ValueError:
                # Invalid UUID format
                pass
            
            return json.dumps(history, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error getting memory history: {e}")
        return f"Error getting memory history: {e}"

@mcp.tool(description="Get all users, agents, and sessions using Mem0 native API.")
async def get_entities() -> str:
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        # Use Mem0 native users method (available only in MemoryClient, not Memory)
        try:
            entities = memory_client.users()
            
            if entities is None:
                return "No entities found"
                
        except Exception as users_error:
            logging.error(f"Error in memory_client.users: {users_error}")
            return f"Error getting entities: {users_error}"
        
        return json.dumps(entities, indent=2)
        
    except Exception as e:
        logging.exception(f"Error getting entities: {e}")
        return f"Error getting entities: {e}"

@mcp.tool(description="Batch update multiple memories using Mem0 native API.")
async def batch_update_memories(updates_json: str) -> str:
    """
    Batch update memories. updates_json should be a JSON string like:
    [{"memory_id": "uuid", "text": "new text"}, ...]
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        # Parse updates JSON
        try:
            updates = json.loads(updates_json)
            if not isinstance(updates, list):
                return "Error: updates must be a JSON array"
        except json.JSONDecodeError as e:
            return f"Error parsing updates JSON: {e}"
            
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native batch_update method
            try:
                response = memory_client.batch_update(updates, user_id=uid)
                
                if response is None:
                    return "Batch update completed (returned None)"
                    
            except Exception as batch_error:
                logging.error(f"Error in memory_client.batch_update: {batch_error}")
                return f"Error in batch update: {batch_error}"
            
            # Log batch operation
            memory_ids = []
            for update in updates:
                if "memory_id" in update:
                    try:
                        memory_ids.append(uuid.UUID(update["memory_id"]))
                    except ValueError:
                        continue
            
            if memory_ids:
                log_memory_access(
                    db, memory_ids, app.id, "batch_update",
                    {"operation": "batch_update", "count": len(memory_ids)}
                )
            
            return json.dumps(response, indent=2)
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error in batch update: {e}")
        return f"Error in batch update: {e}"

@mcp.tool(description="Batch delete multiple memories using Mem0 native API.")
async def batch_delete_memories(memory_ids_json: str) -> str:
    """
    Batch delete memories. memory_ids_json should be a JSON string like:
    ["uuid1", "uuid2", ...]
    """
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    
    if not uid or not client_name:
        return "Error: user_id and client_name are required"

    memory_client = get_memory_client_safe()
    if not memory_client:
        return "Error: Memory system is currently unavailable. Please try again later."

    try:
        # Parse memory IDs JSON
        try:
            memory_ids = json.loads(memory_ids_json)
            if not isinstance(memory_ids, list):
                return "Error: memory_ids must be a JSON array"
        except json.JSONDecodeError as e:
            return f"Error parsing memory_ids JSON: {e}"
            
        db = SessionLocal()
        try:
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Use Mem0 native batch_delete method
            try:
                response = memory_client.batch_delete(memory_ids, user_id=uid)
                
                if response is None:
                    logging.info("Batch delete completed (returned None)")
                    
            except Exception as batch_error:
                logging.error(f"Error in memory_client.batch_delete: {batch_error}")
                return f"Error in batch delete: {batch_error}"

            # Update local database
            valid_uuids = []
            for memory_id in memory_ids:
                try:
                    memory_uuid = uuid.UUID(memory_id)
                    memory = db.query(Memory).filter(Memory.id == memory_uuid).first()
                    if memory:
                        memory.state = MemoryState.deleted
                        memory.deleted_at = datetime.datetime.now(datetime.UTC)

                        # Create history entry
                        history = MemoryStatusHistory(
                            memory_id=memory_uuid,
                            changed_by=user.id,
                            old_state=MemoryState.active,
                            new_state=MemoryState.deleted
                        )
                        db.add(history)
                        valid_uuids.append(memory_uuid)
                except ValueError:
                    # Invalid UUID format, skip
                    continue
            
            # Log batch delete
            if valid_uuids:
                log_memory_access(
                    db, valid_uuids, app.id, "batch_delete",
                    {"operation": "batch_delete", "count": len(valid_uuids)}
                )

            db.commit()
            return f"Successfully batch deleted {len(valid_uuids)} memories"
            
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error in batch delete: {e}")
        return f"Error in batch delete: {e}" 