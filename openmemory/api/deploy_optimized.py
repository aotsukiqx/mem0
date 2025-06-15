#!/usr/bin/env python3
"""
部署脚本：在原有MCP服务器和优化版本之间切换

使用方法:
python deploy_optimized.py --mode optimized  # 切换到优化版本
python deploy_optimized.py --mode original   # 切换回原版本
python deploy_optimized.py --status         # 查看当前状态
"""

import argparse
import shutil
import os
import sys
from pathlib import Path

def backup_file(file_path, backup_suffix=".backup"):
    """备份文件"""
    if os.path.exists(file_path):
        backup_path = f"{file_path}{backup_suffix}"
        shutil.copy2(file_path, backup_path)
        print(f"✅ 已备份: {file_path} -> {backup_path}")
        return True
    return False

def restore_file(file_path, backup_suffix=".backup"):
    """恢复文件"""
    backup_path = f"{file_path}{backup_suffix}"
    if os.path.exists(backup_path):
        shutil.copy2(backup_path, file_path)
        print(f"✅ 已恢复: {backup_path} -> {file_path}")
        return True
    return False

def switch_to_optimized():
    """切换到优化版本"""
    print("🚀 切换到优化版本的MCP服务器...")
    
    # 备份原版本
    if not backup_file("app/mcp_server.py"):
        print("❌ 无法备份原版本 mcp_server.py")
        return False
    
    if not backup_file("main.py"):
        print("❌ 无法备份原版本 main.py")
        return False
    
    # 检查优化版本是否存在
    if not os.path.exists("app/mcp_server_optimized.py"):
        print("❌ 优化版本文件不存在: app/mcp_server_optimized.py")
        return False
    
    # 替换导入语句
    try:
        with open("main.py", "r", encoding="utf-8") as f:
            content = f.read()
        
        # 修改导入语句
        content = content.replace(
            "from app.mcp_server import setup_mcp_server",
            "from app.mcp_server_optimized import setup_mcp_server"
        )
        
        with open("main.py", "w", encoding="utf-8") as f:
            f.write(content)
        
        print("✅ 已更新 main.py 导入语句")
        
        # 创建状态文件
        with open(".mcp_mode", "w") as f:
            f.write("optimized")
        
        print("✅ 成功切换到优化版本!")
        print("📝 下一步:")
        print("   1. 重启服务: docker-compose restart openmemory-mcp")
        print("   2. 检查日志: docker-compose logs -f openmemory-mcp")
        
        return True
        
    except Exception as e:
        print(f"❌ 切换失败: {e}")
        return False

def switch_to_original():
    """切换回原版本"""
    print("🔄 切换回原版本的MCP服务器...")
    
    # 恢复原版本
    if not restore_file("main.py"):
        print("❌ 无法恢复原版本 main.py")
        return False
    
    # 创建状态文件
    with open(".mcp_mode", "w") as f:
        f.write("original")
    
    print("✅ 成功切换回原版本!")
    print("📝 下一步:")
    print("   1. 重启服务: docker-compose restart openmemory-mcp")
    print("   2. 检查日志: docker-compose logs -f openmemory-mcp")
    
    return True

def show_status():
    """显示当前状态"""
    mode_file = ".mcp_mode"
    if os.path.exists(mode_file):
        with open(mode_file, "r") as f:
            mode = f.read().strip()
        print(f"📊 当前模式: {mode}")
    else:
        print("📊 当前模式: 未知 (可能是原版本)")
    
    # 检查文件存在性
    files_status = {
        "app/mcp_server.py": "✅" if os.path.exists("app/mcp_server.py") else "❌",
        "app/mcp_server.py.backup": "✅" if os.path.exists("app/mcp_server.py.backup") else "❌",
        "app/mcp_server_optimized.py": "✅" if os.path.exists("app/mcp_server_optimized.py") else "❌",
        "main.py.backup": "✅" if os.path.exists("main.py.backup") else "❌"
    }
    
    print("\n📁 文件状态:")
    for file_path, status in files_status.items():
        print(f"   {status} {file_path}")

def verify_graph_config():
    """验证Graph Memory配置"""
    print("\n🔍 验证Graph Memory配置...")
    
    try:
        from app.utils.memory import get_default_memory_config
        config = get_default_memory_config()
        
        if "graph_store" in config:
            graph_config = config["graph_store"]
            print(f"✅ Graph Store 配置: {graph_config['provider']}")
            print(f"   URL: {graph_config['config']['url']}")
            print(f"   用户名: {graph_config['config']['username']}")
        else:
            print("❌ 未找到 graph_store 配置")
            
        return True
    except Exception as e:
        print(f"❌ 配置验证失败: {e}")
        return False

def main():
    parser = argparse.ArgumentParser(description="OpenMemory MCP服务器部署切换工具")
    parser.add_argument("--mode", choices=["optimized", "original"], 
                      help="切换模式: optimized=优化版本, original=原版本")
    parser.add_argument("--status", action="store_true", help="显示当前状态")
    parser.add_argument("--verify", action="store_true", help="验证Graph Memory配置")
    
    args = parser.parse_args()
    
    if args.status:
        show_status()
        return
    
    if args.verify:
        verify_graph_config()
        return
    
    if not args.mode:
        parser.print_help()
        return
    
    # 切换到API目录
    if not os.path.exists("app"):
        print("❌ 请在 openmemory/api 目录下运行此脚本")
        sys.exit(1)
    
    if args.mode == "optimized":
        success = switch_to_optimized()
    elif args.mode == "original":
        success = switch_to_original()
    
    if success:
        print(f"\n🎉 切换成功! 当前模式: {args.mode}")
        if args.mode == "optimized":
            verify_graph_config()
    else:
        print(f"\n❌ 切换失败!")
        sys.exit(1)

if __name__ == "__main__":
    main() 