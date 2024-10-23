# В этом файле задаются настройки приложения

"""
Уровень логирования
Возможные значения:
    - "DEBUG"
    - "INFO"
    - "WARNING"
    - "ERROR"
    - "CRITICAL"
"""
MINIMUM_LOG_LEVEL = "DEBUG"

# Минимальное время, затрачиваемое на один отклик на вакансию
MINIMUM_WAIT_TIME_SEC = 60

"""
Тип LLM
Возможные значения:
    - "openai"
    - "claude"
    - "ollama"
    - "gemini"
    - "huggingface"
"""
LLM_MODEL_TYPE = "openai" 

# Модель LLM
LLM_MODEL = "gpt-4o-mini"  

# Если True - подавать в каждую компанию не более чем одну вакансию
APPLY_ONCE_AT_COMPANY = True

# Список компаний, на вакансии которых не откликаемся
JOB_BLACKLIST = ["Apple", "Google", "Meta"]
