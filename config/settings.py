"""配置管理模块 - 升级版本
核心功能：
1. 环境变量分层（开发/测试/生产）
2. 配置项合法性校验
3. 配置热更新（无需重启服务）
"""
import json
import os
import time
from typing import Dict, Any, Optional
from dotenv import load_dotenv, find_dotenv
from utils.logger import get_logger
from utils.exceptions import ConfigError
from utils.validator import validate_preferences

# 初始化日志
logger = get_logger("config.settings")

# ==================== 1. 环境变量分层加载 ====================
class EnvConfig:
    """环境配置加载类"""
    _instance: Optional["EnvConfig"] = None
    _env_data: Dict[str, Any] = {}
    _last_load_time: float = 0.0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_env()
        return cls._instance

    def load_env(self, force: bool = False):
        """加载环境配置（支持热更新）
        Args:
            force: 是否强制重新加载
        """
        # 热更新控制：5秒内不重复加载
        if not force and time.time() - self._last_load_time < 5:
            return
        
        try:
            # 1. 先加载默认.env文件，获取当前环境配置文件路径
            default_env = find_dotenv(".env", usecwd=True)
            if default_env:
                load_dotenv(default_env, override=True)
            
            # 2. 加载指定的环境配置文件（.env.dev/.env.test/.env.prod）
            env_file = os.getenv("ENV_FILE", ".env.dev")
            if os.path.exists(env_file):
                load_dotenv(env_file, override=True)
                logger.info(f"成功加载环境配置: {env_file}")
            else:
                logger.warning(f"环境配置文件不存在: {env_file}，使用默认配置")
            
            # 3. 解析环境配置
            self._env_data = {
                "env": os.getenv("ENV", "development"),
                "api_base_url": os.getenv("API_BASE_URL", "http://localhost:8000"),
                "log_level": os.getenv("LOG_LEVEL", "INFO"),
                "server_port": int(os.getenv("SERVER_PORT", 8080)),
                "reload": os.getenv("RELOAD", "True").lower() == "true",
                "config_hot_reload": os.getenv("CONFIG_HOT_RELOAD", "True").lower() == "true"
            }
            
            self._last_load_time = time.time()
            logger.debug(f"环境配置加载完成: {self._env_data}")
        
        except Exception as e:
            logger.error(f"加载环境配置失败: {e}", exc_info=True)
            # 使用兜底配置
            self._env_data = {
                "env": "development",
                "api_base_url": "http://localhost:8000",
                "log_level": "INFO",
                "server_port": 8080,
                "reload": True,
                "config_hot_reload": True
            }

    @property
    def data(self) -> Dict[str, Any]:
        """获取环境配置（自动热更新）"""
        if self._env_data.get("config_hot_reload"):
            self.load_env()
        return self._env_data.copy()

# 全局环境配置实例
env_config = EnvConfig()

# ==================== 2. 用户偏好配置（带校验+热更新） ====================
# 默认用户偏好配置
DEFAULT_PREFERENCES: Dict[str, Any] = {
    "enabled": False,
    "risk_level": "medium",
    "max_stop_loss_pct": 2.0,
    "trade_style": "swing",
    "position_size": "medium",
    "preferred_leverage": 1,
    "custom_note": ""
}

# 配置缓存（用于热更新）
_PREFS_CACHE: Dict[str, Any] = {}
_CACHE_EXPIRE_TIME = 5  # 缓存过期时间（秒）
_LAST_PREFS_LOAD = 0.0

def get_preferences(force_reload: bool = False) -> Dict[str, Any]:
    """读取用户偏好配置（支持热更新+合法性校验）
    Args:
        force_reload: 是否强制重新加载（忽略缓存）
    Returns:
        校验后的用户偏好配置
    Raises:
        ConfigError: 配置校验失败时抛出
    """
    global _PREFS_CACHE, _LAST_PREFS_LOAD
    
    # 1. 检查缓存（热更新控制）
    current_time = time.time()
    if not force_reload and current_time - _LAST_PREFS_LOAD < _CACHE_EXPIRE_TIME and _PREFS_CACHE:
        return _PREFS_CACHE.copy()
    
    # 2. 读取配置文件
    try:
        prefs = DEFAULT_PREFERENCES.copy()
        if os.path.exists("preferences.json"):
            with open("preferences.json", "r", encoding="utf-8") as f:
                file_prefs = json.load(f)
                prefs.update(file_prefs)
                logger.info("读取用户偏好配置文件成功")
        
        # 3. 配置合法性校验（核心升级）
        validate_preferences(prefs)
        
        # 4. 更新缓存
        _PREFS_CACHE = prefs.copy()
        _LAST_PREFS_LOAD = current_time
        
        return prefs.copy()
    
    except ConfigError as e:
        logger.error(f"用户配置校验失败: {e}")
        raise
    except Exception as e:
        logger.error(f"读取用户配置失败: {e}", exc_info=True)
        # 校验默认配置（兜底）
        validate_preferences(DEFAULT_PREFERENCES)
        return DEFAULT_PREFERENCES.copy()

def save_preferences(prefs: Dict[str, Any]) -> None:
    """保存用户偏好配置（保存前先校验）
    Args:
        prefs: 要保存的配置字典
    Raises:
        ConfigError: 配置不合法或保存失败
    """
    try:
        # 1. 先校验配置合法性
        validate_preferences(prefs)
        
        # 2. 合并默认配置（防止缺失关键字段）
        final_prefs = {**DEFAULT_PREFERENCES, **prefs}
        
        # 3. 保存到文件
        with open("preferences.json", "w", encoding="utf-8") as f:
            json.dump(final_prefs, f, ensure_ascii=False, indent=2)
        
        # 4. 清空缓存（触发热更新）
        global _PREFS_CACHE, _LAST_PREFS_LOAD
        _PREFS_CACHE = final_prefs.copy()
        _LAST_PREFS_LOAD = 0.0
        
        logger.info("用户偏好配置保存成功（已触发热更新）")
    
    except ConfigError as e:
        logger.error(f"保存配置失败: 配置不合法 - {e}")
        raise
    except Exception as e:
        logger.error(f"保存配置文件失败: {e}", exc_info=True)
        raise ConfigError(f"配置保存失败: {str(e)}")

def reload_config() -> Dict[str, Any]:
    """手动触发配置全量热更新
    Returns:
        最新的环境配置 + 用户偏好配置
    """
    # 1. 热更新环境配置
    env_config.load_env(force=True)
    
    # 2. 热更新用户偏好配置
    prefs = get_preferences(force_reload=True)
    
    logger.info("配置已手动触发热更新")
    return {
        "env_config": env_config.data,
        "user_preferences": prefs
    }
