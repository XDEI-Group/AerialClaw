"""
任务执行日志记录器
记录每次任务的完整轨迹、感知事件、指标和 LLM 反思
"""

import json
import logging
import time
from dataclasses import dataclass, asdict, field
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


@dataclass
class SkillExecutionRecord:
    """一次技能执行的记录"""
    skill_name: str
    start_time: float
    duration: float
    success: bool
    error_msg: Optional[str] = None
    input_params: Optional[Dict] = None
    output_result: Optional[Dict] = None


@dataclass
class PerceptionEventRecord:
    """感知事件记录"""
    event_type: str
    summary: str
    timestamp: float
    confidence: float = 1.0
    data: Optional[Dict] = None


@dataclass
class TaskExecutionLog:
    """一次完整任务执行的记录"""
    task_name: str
    task_id: str
    start_time: float
    end_time: Optional[float] = None
    success: Optional[bool] = None
    
    # 执行轨迹
    skill_trace: List[SkillExecutionRecord] = field(default_factory=list)
    
    # 感知事件
    perception_events: List[PerceptionEventRecord] = field(default_factory=list)
    
    # 指标
    total_duration: Optional[float] = None
    obstacles_encountered: int = 0
    replans: int = 0
    emergency_stops: int = 0
    
    # 自然语言反思（LLM 生成）
    reflection: Optional[str] = None
    lessons: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（JSON 序列化友好）"""
        return {
            'task_name': self.task_name,
            'task_id': self.task_id,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'success': self.success,
            'total_duration': self.total_duration,
            'skill_trace': [
                {
                    'skill_name': s.skill_name,
                    'duration': s.duration,
                    'success': s.success,
                    'error_msg': s.error_msg,
                }
                for s in self.skill_trace
            ],
            'perception_events': [
                {
                    'event_type': e.event_type,
                    'summary': e.summary,
                    'timestamp': e.timestamp,
                    'confidence': e.confidence,
                }
                for e in self.perception_events
            ],
            'obstacles_encountered': self.obstacles_encountered,
            'replans': self.replans,
            'emergency_stops': self.emergency_stops,
            'reflection': self.reflection,
            'lessons': self.lessons,
        }


class TaskLogger:
    """任务执行日志记录器"""
    
    def __init__(self, log_dir: str = "data/task_logs", llm_client=None):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.current_task: Optional[TaskExecutionLog] = None
        self.llm_client = llm_client
    
    def start_task(self, task_name: str) -> str:
        """
        开始记录一个任务
        
        Args:
            task_name: 任务名称
            
        Returns:
            task_id: 任务 ID
        """
        self.current_task = TaskExecutionLog(
            task_name=task_name,
            task_id=f"{task_name}_{int(time.time())}",
            start_time=time.time()
        )
        logger.info(f"📝 开始记录任务: {task_name} (ID: {self.current_task.task_id})")
        return self.current_task.task_id
    
    def record_skill(self, 
                     skill_name: str, 
                     duration: float, 
                     success: bool,
                     error_msg: str = None,
                     input_params: Dict = None,
                     output_result: Dict = None):
        """记录一次技能执行"""
        if not self.current_task:
            logger.warning("没有活跃的任务，跳过技能记录")
            return
        
        record = SkillExecutionRecord(
            skill_name=skill_name,
            start_time=time.time() - duration,
            duration=duration,
            success=success,
            error_msg=error_msg,
            input_params=input_params,
            output_result=output_result
        )
        self.current_task.skill_trace.append(record)
        
        status = "✓" if success else "✗"
        logger.debug(f"  {status} {skill_name} ({duration:.1f}s)")
    
    def record_perception_event(self,
                                event_type: str,
                                summary: str,
                                confidence: float = 1.0,
                                data: Dict = None):
        """记录一个感知事件"""
        if not self.current_task:
            logger.warning("没有活跃的任务，跳过事件记录")
            return
        
        event = PerceptionEventRecord(
            event_type=event_type,
            summary=summary,
            timestamp=time.time(),
            confidence=confidence,
            data=data
        )
        self.current_task.perception_events.append(event)
        logger.debug(f"  📡 {event_type}: {summary}")
    
    def record_replan(self):
        """记录一次重新规划"""
        if self.current_task:
            self.current_task.replans += 1
            logger.debug(f"  🔄 规划已更新 (总计: {self.current_task.replans})")
    
    def record_emergency_stop(self):
        """记录一次应急停止"""
        if self.current_task:
            self.current_task.emergency_stops += 1
            logger.warning(f"  🚨 应急停止 (总计: {self.current_task.emergency_stops})")
    
    def record_obstacle(self):
        """记录遇到一个障碍物"""
        if self.current_task:
            self.current_task.obstacles_encountered += 1
    
    def end_task(self, success: bool):
        """
        任务完成，保存日志 + 生成反思
        
        Args:
            success: 任务是否成功
        """
        if not self.current_task:
            logger.warning("没有活跃的任务")
            return
        
        self.current_task.end_time = time.time()
        self.current_task.success = success
        self.current_task.total_duration = self.current_task.end_time - self.current_task.start_time
        
        # 生成自然语言反思（可选）
        if self.llm_client:
            try:
                reflection, lessons = self._generate_reflection(self.current_task)
                self.current_task.reflection = reflection
                self.current_task.lessons = lessons
            except Exception as e:
                logger.warning(f"生成反思失败: {e}")
        
        # 保存到 JSON
        self._save_log(self.current_task)
        
        # 追加到 markdown 历史
        self._append_to_history(self.current_task)
        
        status = "✅" if success else "❌"
        logger.info(f"{status} 任务完成: {self.current_task.task_id} ({self.current_task.total_duration:.1f}s)")
        
        self.current_task = None
    
    def _generate_reflection(self, log: TaskExecutionLog) -> tuple[Optional[str], List[str]]:
        """用 LLM 生成反思"""
        if not self.llm_client:
            return None, []
        
        skill_names = " → ".join([s.skill_name for s in log.skill_trace])
        events_summary = "\n".join([
            f"  - {e.summary}" for e in log.perception_events
        ]) if log.perception_events else "  (无)"
        
        prompt = f"""分析这次无人机任务执行，生成简洁的自然语言反思（2-3 句话）：

【任务】{log.task_name}
【结果】{'成功 ✓' if log.success else '失败 ✗'}
【耗时】{log.total_duration:.1f} 秒
【技能流程】{skill_names}
【感知事件】
{events_summary}
【关键指标】
  - 重新规划: {log.replans} 次
  - 应急停止: {log.emergency_stops} 次
  - 遇到障碍: {log.obstacles_encountered} 个

反思："""
        
        try:
            reflection = self.llm_client.complete(prompt, max_tokens=150)
            reflection = reflection.strip()
        except Exception as e:
            logger.warning(f"LLM 反思失败: {e}")
            reflection = None
        
        # 提取经验教训
        lessons = []
        if log.skill_trace:
            longest_skill = max(log.skill_trace, key=lambda x: x.duration)
            lessons.append(f"{longest_skill.skill_name} 耗时最长 ({longest_skill.duration:.1f}s)，可优化")
        
        if log.replans > 0:
            lessons.append(f"任务中重新规划 {log.replans} 次，建议预规划优化")
        
        if log.obstacles_encountered > 0:
            lessons.append(f"遇到 {log.obstacles_encountered} 个障碍物，激光雷达距离阈值可调整")
        
        return reflection, lessons
    
    def _save_log(self, log: TaskExecutionLog):
        """保存任务日志到 JSON 文件"""
        log_file = self.log_dir / f"{log.task_id}.json"
        
        log_dict = log.to_dict()
        
        with open(log_file, 'w', encoding='utf-8') as f:
            json.dump(log_dict, f, indent=2, ensure_ascii=False)
        
        logger.info(f"📊 日志保存: {log_file}")
    
    def _append_to_history(self, log: TaskExecutionLog):
        """追加到任务历史 markdown"""
        history_file = self.log_dir / "task_history.md"
        
        # 确保文件存在
        if not history_file.exists():
            with open(history_file, 'w', encoding='utf-8') as f:
                f.write("# 任务执行历史\n\n")
        
        # 创建 markdown 条目
        skill_chain = " → ".join([s.skill_name for s in log.skill_trace])
        if not skill_chain:
            skill_chain = "(无)"
        
        status = "✅ 成功" if log.success else "❌ 失败"
        timestamp = datetime.fromtimestamp(log.start_time).strftime("%Y-%m-%d %H:%M:%S")
        
        entry = f"""## [{timestamp}] {log.task_name}

**ID**: {log.task_id}  
**状态**: {status}  
**耗时**: {log.total_duration:.1f}s  
**技能链**: {skill_chain}  

**指标**:
- 重新规划: {log.replans} 次
- 应急停止: {log.emergency_stops} 次
- 遇到障碍: {log.obstacles_encountered} 个

"""
        
        if log.perception_events:
            entry += "**感知事件**:\n"
            for event in log.perception_events:
                entry += f"- {event.event_type}: {event.summary} (置信度: {event.confidence:.1%})\n"
            entry += "\n"
        
        if log.reflection:
            entry += f"**反思**: {log.reflection}\n\n"
        
        if log.lessons:
            entry += "**经验教训**:\n"
            for lesson in log.lessons:
                entry += f"- {lesson}\n"
            entry += "\n"
        
        entry += "---\n\n"
        
        with open(history_file, 'a', encoding='utf-8') as f:
            f.write(entry)
    
    def get_all_logs(self) -> List[TaskExecutionLog]:
        """获取所有任务日志"""
        logs = []
        for log_file in sorted(self.log_dir.glob("*.json")):
            try:
                with open(log_file, 'r', encoding='utf-8') as f:
                    log_dict = json.load(f)
                    logs.append(log_dict)
            except Exception as e:
                logger.warning(f"读取日志失败 {log_file}: {e}")
        return logs
    
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        logs = self.get_all_logs()
        
        if not logs:
            return {
                "total_tasks": 0,
                "success_tasks": 0,
                "success_rate": 0.0,
                "total_duration": 0.0,
                "avg_duration": 0.0,
                "total_replans": 0,
                "total_obstacles": 0,
            }
        
        total = len(logs)
        success = sum(1 for log in logs if log['success'])
        total_duration = sum(log['total_duration'] for log in logs if log['total_duration'])
        total_replans = sum(log['replans'] for log in logs)
        total_obstacles = sum(log['obstacles_encountered'] for log in logs)
        
        return {
            "total_tasks": total,
            "success_tasks": success,
            "success_rate": success / total if total > 0 else 0.0,
            "total_duration": total_duration,
            "avg_duration": total_duration / total if total > 0 else 0.0,
            "total_replans": total_replans,
            "total_obstacles": total_obstacles,
        }
