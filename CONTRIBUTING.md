# 贡献指南

请在离线演示和测试客户端中验证修改。不要为测试自动消耗真实账号物品。

```powershell
python -m unittest discover -s tests -v
python scripts/smoke_gui.py
```

新增交易类型时，需要同步更新计划、输入限制、输出校验、进度统计和异常处理测试。不要自动重试已经发送的写请求。

提交问题时，请提供工具版本、Windows版本、客户端地区、复现步骤和经脱敏的错误信息。不要上传lockfile、进程完整命令行、连接令牌、完整个人库存或账号标识。
