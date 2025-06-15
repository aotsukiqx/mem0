#!/usr/bin/env python3
"""
测试ResilientMemoryClient修复效果的脚本

此脚本会测试各种情况下的内存添加操作，验证修复后的ResilientMemoryClient
能够正确处理JSON解析错误并提供合适的fallback策略。

使用方法：
1. 正常模式：python test_resilient_client_fix.py
2. 绕过resilient wrapper模式：BYPASS_RESILIENT_CLIENT=true python test_resilient_client_fix.py
"""

import os
import sys
import json
import logging
from typing import Dict, Any

# 添加当前目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.utils.memory import get_memory_client, reset_memory_client

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ResilientClientTester:
    """ResilientMemoryClient 修复效果测试器"""
    
    def __init__(self):
        self.test_cases = [
            {
                "name": "中文事实提取",
                "text": "助手名字是Jarvis",
                "expected_issue": "可能触发JSON解析错误"
            },
            {
                "name": "简单问候",
                "text": "Hi",
                "expected_issue": "简单文本可能导致空响应"
            },
            {
                "name": "复杂中文文本",
                "text": "我需要记住今天下午3点要开会，会议主题是项目进度讨论",
                "expected_issue": "复杂中文可能触发LLM处理问题"
            },
            {
                "name": "英文事实",
                "text": "My name is John and I like pizza",
                "expected_issue": "应该正常工作"
            },
            {
                "name": "特殊字符",
                "text": "测试特殊字符：@#$%^&*()_+-={}[]|\\:;\"'<>?,./ 🚀 🎉",
                "expected_issue": "特殊字符可能影响LLM解析"
            },
            {
                "name": "长文本",
                "text": "这是一个很长的文本，用来测试ResilientMemoryClient的处理能力。" * 10,
                "expected_issue": "长文本可能触发截断fallback策略"
            }
        ]
    
    def test_memory_add(self, text: str, test_name: str) -> Dict[str, Any]:
        """测试单个内存添加操作"""
        logger.info(f"🧪 测试: {test_name}")
        logger.info(f"📝 文本: {text[:50]}{'...' if len(text) > 50 else ''}")
        
        try:
            memory_client = get_memory_client()
            if not memory_client:
                return {
                    "status": "error",
                    "error": "无法获取memory client"
                }
            
            # 执行添加操作
            result = memory_client.add(
                text,
                user_id="test_user",
                metadata={
                    "test_case": test_name,
                    "source": "resilient_client_test"
                }
            )
            
            # 分析结果
            if result is None:
                return {
                    "status": "error",
                    "error": "返回了None"
                }
            
            if isinstance(result, dict):
                results_count = len(result.get("results", []))
                has_diagnostic = "diagnostic" in result
                
                if has_diagnostic and result["diagnostic"].get("all_strategies_failed"):
                    return {
                        "status": "all_failed",
                        "diagnostic": result["diagnostic"],
                        "results_count": results_count
                    }
                elif results_count > 0:
                    return {
                        "status": "success",
                        "results_count": results_count,
                        "relations": result.get("relations", {}),
                        "has_diagnostic": has_diagnostic
                    }
                else:
                    return {
                        "status": "empty_results",
                        "results_count": 0,
                        "has_diagnostic": has_diagnostic
                    }
            else:
                return {
                    "status": "unexpected_format",
                    "result_type": str(type(result)),
                    "result": str(result)[:200]
                }
                
        except Exception as e:
            return {
                "status": "exception",
                "error": str(e),
                "error_type": type(e).__name__
            }
    
    def run_all_tests(self):
        """运行所有测试用例"""
        print("=" * 80)
        print("🚀 ResilientMemoryClient 修复效果测试")
        print("=" * 80)
        
        # 检查是否启用了绕过模式
        bypass_mode = os.environ.get('BYPASS_RESILIENT_CLIENT', 'false').lower() == 'true'
        if bypass_mode:
            print("⚠️  绕过模式已启用 (BYPASS_RESILIENT_CLIENT=true)")
        else:
            print("✅ 使用 ResilientMemoryClient 包装器")
        
        print(f"📊 总共 {len(self.test_cases)} 个测试用例")
        print()
        
        results = {}
        
        for i, test_case in enumerate(self.test_cases, 1):
            print(f"[{i}/{len(self.test_cases)}] {'-' * 50}")
            
            result = self.test_memory_add(
                test_case["text"],
                test_case["name"]
            )
            
            results[test_case["name"]] = result
            
            # 打印结果
            status = result["status"]
            if status == "success":
                print(f"✅ 成功: 创建了 {result['results_count']} 个记忆")
            elif status == "empty_results":
                print(f"⚠️  空结果: 没有创建记忆")
            elif status == "all_failed":
                print(f"❌ 全部失败: 所有fallback策略都失败了")
                print(f"   诊断信息: {result.get('diagnostic', {})}")
            elif status == "error":
                print(f"❌ 错误: {result['error']}")
            elif status == "exception":
                print(f"💥 异常: {result['error']} ({result['error_type']})")
            else:
                print(f"❓ 未知状态: {status}")
            
            print()
        
        # 总结
        print("=" * 80)
        print("📈 测试总结")
        print("=" * 80)
        
        success_count = sum(1 for r in results.values() if r["status"] == "success")
        empty_count = sum(1 for r in results.values() if r["status"] == "empty_results")
        failed_count = sum(1 for r in results.values() if r["status"] == "all_failed")
        error_count = sum(1 for r in results.values() if r["status"] in ["error", "exception"])
        
        print(f"✅ 成功: {success_count}/{len(self.test_cases)}")
        print(f"⚠️  空结果: {empty_count}/{len(self.test_cases)}")
        print(f"❌ 全部失败: {failed_count}/{len(self.test_cases)}")
        print(f"💥 错误/异常: {error_count}/{len(self.test_cases)}")
        
        if success_count == len(self.test_cases):
            print("\n🎉 所有测试都成功了！ResilientMemoryClient 工作正常。")
        elif success_count + empty_count == len(self.test_cases):
            print("\n⚠️  没有失败，但有空结果。这可能是正常的LLM行为。")
        elif failed_count == 0:
            print("\n✅ 没有出现全部策略失败的情况，修复生效。")
        else:
            print("\n❌ 仍有问题需要进一步调查。")
        
        return results

def main():
    """主函数"""
    try:
        # 重置memory client确保使用最新配置
        reset_memory_client()
        
        # 运行测试
        tester = ResilientClientTester()
        results = tester.run_all_tests()
        
        # 保存结果
        results_file = "resilient_client_test_results.json"
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        
        print(f"\n📄 详细结果已保存到: {results_file}")
        
    except KeyboardInterrupt:
        print("\n\n⏹️  测试被用户中断")
    except Exception as e:
        print(f"\n💥 测试过程中发生错误: {e}")
        logger.exception("测试失败")

if __name__ == "__main__":
    main()