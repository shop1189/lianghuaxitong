# 关键主文件防护与追责 SOP

目标：防止 `main.py`、`live_trading.py` 等核心文件被误删/篡改后无感运行，做到可阻断、可告警、可追溯。

## 一、已落地组件

- 巡检器：`scripts/critical_files_guard.py`
  - `--init-baseline` 生成基线（存在性 + size + sha256）
  - `--check --strict` 严格检查（异常返回非 0）
- 定时守护：`scripts/run_critical_files_guard.sh`
- cron 安装器：`scripts/install_critical_guard_cron.sh`
- 启动前阻断：`scripts/start_main_guarded.sh`

## 二、一次性初始化（必须执行）

```bash
cd /root/longxia_system
/usr/bin/python3 scripts/critical_files_guard.py --init-baseline
bash scripts/install_critical_guard_cron.sh
```

检查输出：

- 基线文件：`logs/critical_files_baseline.json`
- 状态文件：`logs/critical_files_guard_status.json`
- 巡检日志：`logs/critical_files_guard.log`

## 三、日常运行建议

- 启动服务时优先使用：
  - `bash /root/longxia_system/scripts/start_main_guarded.sh`
- 守护 cron 默认：
  - 每 5 分钟检查一次
  - 开机后执行一次

## 四、告警判定标准

`logs/critical_files_guard_status.json` 中出现以下任一项即判定高危：

- `"ok": false`
- `"missing_files"` 非空
- `"changed_files"` 非空

## 五、事故应急流程

1. 先止损（避免继续漂移）  
   - 暂停高频自动任务（如回测矩阵 cron）。
2. 取证  
   - 备份 `logs/critical_files_guard_status.json`、`logs/critical_files_guard.log`、`/var/log/syslog*`。
3. 恢复  
   - `git restore --source=HEAD -- <关键文件>`。
4. 校验  
   - `python3 scripts/critical_files_guard.py --check --strict` 必须通过。
5. 再启动  
   - 用 `scripts/start_main_guarded.sh` 启动。

## 六、注意事项

- 当你**主动升级核心文件**后，需要更新基线：

```bash
python3 /root/longxia_system/scripts/critical_files_guard.py --init-baseline
```

- 基线应只在“你确认当前版本正确且可运行”时更新。

