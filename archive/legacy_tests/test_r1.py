#!/usr/bin/env python
import sys
import redis

print(f"✅ Python 版本: {sys.version}")
r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
print(f"✅ Redis 连接测试: {r.ping()}")
print("🎉 项目骨架测试通过！可以继续下一步了！")
