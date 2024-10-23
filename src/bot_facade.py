from loguru import logger


class BotState:
    def __init__(self):
        logger.debug("Initializing AIHawkBotState")
        self.reset()

    def reset(self):
        logger.debug("Resetting AIHawkBotState")
        self.parameters_set = False
        self.logged_in = False
        self.search_parameters_set = False
        self.resume_profile_set = False
        self.gpt_answerer_set = False
        

    def validate_state(self, required_keys):
        logger.debug(f"Validating BotState with required keys: {required_keys}")
        for key in required_keys:
            if not getattr(self, key):
                logger.error(f"State validation failed: {key} is not set")
                raise ValueError(f"{key.replace('_', ' ').capitalize()} must be set before proceeding.")
        logger.debug("State validation passed")


class BotFacade:
    def __init__(self, login_component, apply_component):
        logger.debug("Initializing BotFacade")
        self.login_component = login_component # Authenticator
        self.apply_component = apply_component # JobManager
        self.state = BotState()
        self.resume_profile = None
        self.resume = None
        self.email = None
        self.password = None
        self.parameters = None

    def set_parameters(self, parameters):
        """Проверяем, что все параметры установлены верно"""
        logger.debug("Установка параметров")
        self._validate_non_empty(parameters, "Parameters")
        self.parameters = parameters
        self.login_component.set_parameters(parameters)
        self.apply_component.set_parameters(parameters)
        self.state.parameters_set = True
        logger.debug("Все параметры установлены успешно")
    
    def start_login(self):
        """Входим на сайт"""
        logger.debug("Starting login process")
        self.state.validate_state(['resume_profile_set', 'gpt_answerer_set'])
        self.login_component.start()
        self.state.logged_in = True
        logger.debug("Процесс входа на сайт завершен успешно")

    def set_search_parameters(self):
        """Устанавливаем дополнительные параметры поиска в hh.ru"""
        self.apply_component.set_advanced_search_params()
        self.state.validate_state(['search_parameters_set'])
        self.state.search_parameters_set = True
        logger.debug("Параметры поиска установлены успешно")
    
    def set_resume_profile_and_resume(self, resume_profile, resume):
        """Загружаем резюме и профиль резюме"""
        logger.debug("Загружаем резюме и его профиль")
        self._validate_non_empty(resume_profile, "Профиль резюме")
        self._validate_non_empty(resume, "Резюме")
        self.resume_profile = resume_profile
        self.resume = resume
        self.state.resume_profile_set = True
        logger.debug("Резюме и его профиль загружены успешно")

    def set_gpt_answerer(self, gpt_answerer_component):
        logger.debug("Setting GPT answerer and resume generator")
        self._ensure_job_profile_and_resume_set()
        gpt_answerer_component.set_resume_profile(self.resume_profile)
        gpt_answerer_component.set_resume(self.resume)
        self.apply_component.set_gpt_answerer(gpt_answerer_component)
        self.state.gpt_answerer_set = True
        logger.debug("GPT answerer and resume generator set successfully")

    def start_apply(self):
        self.state.validate_state(['logged_in', 'parameters_set'])
        logger.debug("Apply process started successfully")
        self.apply_component.start_applying()
        logger.debug("Apply process finished successfully")

    def _validate_non_empty(self, value, name):
        logger.debug(f"Validating that {name} is not empty")
        if not value:
            logger.error(f"Validation failed: {name} is empty")
            raise ValueError(f"{name} cannot be empty.")
        logger.debug(f"Validation passed for {name}")

    def _ensure_job_profile_and_resume_set(self):
        logger.debug("Ensuring job profile and resume are set")
        if not self.state.resume_profile_set:
            logger.error("Job application profile and resume are not set")
            raise ValueError("Job application profile and resume must be set before proceeding.")
        logger.debug("Job profile and resume are set")
