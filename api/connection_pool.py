#!/usr/bin/env python3
"""
Connection Pool Manager
限制并发websocket连接数
"""

import asyncio
import logging
from typing import Dict, Optional
from .terminal_api_client import TerminalAPIClient

logger = logging.getLogger(__name__)

class ConnectionPool:
    """连接池管理器 - 限制并发连接数"""
    
    def __init__(self, max_connections: int = 2):
        self.max_connections = max_connections
        self._active_connections: Dict[str, TerminalAPIClient] = {}
        self._semaphore = asyncio.Semaphore(max_connections)
        
    async def acquire_connection(self, connection_id: str, **kwargs) -> Optional[TerminalAPIClient]:
        """获取连接"""
        try:
            await self._semaphore.acquire()
            
            if connection_id in self._active_connections:
                return self._active_connections[connection_id]
                
            client = TerminalAPIClient(**kwargs)
            success = await client.initialize()
            
            if success:
                self._active_connections[connection_id] = client
                return client
            else:
                self._semaphore.release()
                return None
                
        except Exception as e:
            logger.error(f"Failed to acquire connection {connection_id}: {e}")
            self._semaphore.release()
            return None
    
    async def release_connection(self, connection_id: str):
        """释放连接"""
        if connection_id in self._active_connections:
            client = self._active_connections.pop(connection_id)
            try:
                await client.shutdown()
            except Exception as e:
                logger.error(f"Error shutting down connection {connection_id}: {e}")
            finally:
                self._semaphore.release()
    
    def get_active_count(self) -> int:
        """获取活跃连接数"""
        return len(self._active_connections)

# 全局连接池实例
_connection_pool = ConnectionPool(max_connections=2)

async def get_client(connection_id: str, **kwargs) -> Optional[TerminalAPIClient]:
    """获取客户端连接"""
    return await _connection_pool.acquire_connection(connection_id, **kwargs)

async def release_client(connection_id: str):
    """释放客户端连接"""
    await _connection_pool.release_connection(connection_id)

def get_pool_status() -> Dict[str, int]:
    """获取连接池状态"""
    return {
        "active_connections": _connection_pool.get_active_count(),
        "max_connections": _connection_pool.max_connections
    }
