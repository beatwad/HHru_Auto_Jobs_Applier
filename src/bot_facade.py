from typing import Dict, Any

from loguru import logger


class BotState:
    def __init__(self):
        logger.debug("Инициализируем класс BotState")
        self.reset()

    def reset(self):
        logger.debug("Сброс состояния класса BotState")
        self.parameters_set = False
        self.logged_in = False
        self.search_parameters_set = False
        self.resume_profile_set = False
        self.gpt_answerer_set = False
        

    def validate_state(self, required_keys):
        logger.debug(f"Проверяем флаги состояний BotState: {required_keys}")
        for key in required_keys:
            if not getattr(self, key):
                logger.error(f"Проверка флагов состояний провалена, флаг {key} не установлен")
                raise ValueError(f"Флаг {key.replace('_', ' ').capitalize()} должен быть установлен")
        logger.debug("Проверка состояний пройдена успешно")


class BotFacade:
    """Класс интерфейса с ботом"""
    def __init__(self, login_component: Any, apply_component: Any):
        logger.debug("Initializing BotFacade")
        self.login_component = login_component # Authenticator
        self.apply_component = apply_component # JobManager
        self.state = BotState()
        self.resume_profile = None
        self.resume = None
        self.email = None
        self.password = None
        self.parameters = None

    def set_parameters(self, parameters: Dict[str, Any]) -> None:
        """Проверяем, что все параметры установлены верно"""
        logger.debug("Установка параметров")
        self._validate_non_empty(parameters, "Parameters")
        self.parameters = parameters
        self.login_component.set_parameters(parameters)
        self.apply_component.set_parameters(parameters)
        self.state.parameters_set = True
        logger.debug("Все параметры установлены успешно")
    
    def start_login(self) -> None:
        """Входим на сайт"""
        logger.debug("Входим на сайт")
        self.state.validate_state(['resume_profile_set', 'gpt_answerer_set'])
        self.login_component.start()
        self.state.logged_in = True
        logger.debug("Процесс входа на сайт завершен успешно")

    def set_search_parameters(self) -> None:
        """Устанавливаем дополнительные параметры поиска в hh.ru"""
        self.apply_component.set_advanced_search_params()
        self.state.search_parameters_set = True
        logger.debug("Параметры поиска установлены успешно")
    
    def set_resume_profile_and_resume(self, resume_profile, resume) -> None:
        """Загружаем резюме и профиль резюме"""
        logger.debug("Загружаем резюме и его профиль")
        self._validate_non_empty(resume_profile, "Профиль резюме")
        self._validate_non_empty(resume, "Резюме")
        self.resume_profile = resume_profile
        self.resume = resume
        self.state.resume_profile_set = True
        logger.debug("Резюме и его профиль загружены успешно")

    def set_gpt_answerer(self, gpt_answerer_component) -> None:
        """Запускаем класс для работы с LLM и обработчик резюме"""
        logger.debug("Запускаем класс для работы с LLM и обработчик резюме")
        self._ensure_resume_set()
        gpt_answerer_component.set_resume_profile(self.resume_profile)
        gpt_answerer_component.set_resume(self.resume)
        self.apply_component.set_gpt_answerer(gpt_answerer_component)
        self.state.gpt_answerer_set = True
        logger.debug("Класс для работы с LLM и обработчик резюме успешно запущены")

    def start_apply(self) -> None:
        """Начинаем процесс отправки резюме"""
        self.state.validate_state(['logged_in', 'parameters_set', 'search_parameters_set'])
        logger.debug("Начинаем процесс отправки резюме")
        self.apply_component.start_applying()
        logger.debug("Процесс отправки резюме успешно завершен")

    def _validate_non_empty(self, value, name) -> None:
        """Проверяем, что поле с именем `name` не пустое"""
        logger.debug(f"Проверяем, что поле с именем {name} не пустое")
        if not value:
            logger.error(f"Проверка провалена: поле с именем {name} пустое")
            raise ValueError(f"{name} cannot be empty.")
        logger.debug(f"Проверка поле с именем {name} проведена успешно")

    def _ensure_resume_set(self) -> None:
        """Проверяем, что резюме и его профиль заданы"""
        logger.debug("Проверяем, что резюме и его профиль заданы")
        if not self.state.resume_profile_set:
            logger.error("Резюме и/или его профиль не заданы")
            raise ValueError("Необходимо задать резюме и его профиль для корректной работы.")
        logger.debug("Резюме и его профиль заданы")
