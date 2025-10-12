#!/bin/bash
# 系统资源监控脚本
LOG_FILE="/home/ubuntu/huixin/aiops_v2/system_monitor.log"
echo "=== 监控开始时间: $(date) ===" >> $LOG_FILE

while true; do
    echo "--- $(date) ---" >> $LOG_FILE
    
    # CPU和内存使用情况
    echo "CPU和内存:" >> $LOG_FILE
    top -bn1 | head -5 >> $LOG_FILE
    
    # 内存详情
    echo "内存详情:" >> $LOG_FILE
    free -h >> $LOG_FILE
    
    # qproxy进程状态
    echo "qproxy进程:" >> $LOG_FILE
    ps aux | grep qproxy_pool | grep -v grep >> $LOG_FILE || echo "qproxy进程未找到" >> $LOG_FILE
    
    # 端口状态
    echo "端口8080状态:" >> $LOG_FILE
    ss -tlnp | grep :8080 >> $LOG_FILE || echo "端口8080未监听" >> $LOG_FILE
    
    echo "" >> $LOG_FILE
    sleep 5
done
