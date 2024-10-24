import os
import sys
from pathlib import Path
import yaml
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from src.utils import chrome_browser_options
from src.llm.llm_manager import GPTAnswerer
from src.authenticator import Authenticator
from src.bot_facade import BotFacade
from src.job_manager import JobManager
from loguru import logger

# TODO: check the whole pipeline 
# TODO: translate all comments and debug statements to Russian
# TODO: write README
# TODO: change License
# TODO: write tests

log_file = "log/app_log.log"
logger.add(log_file)

# Не выводить stderr
sys.stderr = open(os.devnull, 'w')

class ConfigError(Exception):
    pass

class ConfigValidator:
    """Класс для проверки правильности настроек конфигурации"""
    @staticmethod
    def load_yaml_file(yaml_path: Path) -> dict:
        """Загрузить настройки из YAML файла конфигурации"""
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")
    
    
    def validate_config(self, config_yaml_path: Path) -> dict:
        """Проверить правильность настроек из файлов конфигурации"""
        parameters = self.load_yaml_file(config_yaml_path)
        # обязательные настройки
        required_keys = {
            'job_title': str,
            'login': str,
            'experience': dict,
            'sort_by': dict,
            'output_period': dict,
            'output_size': dict,
        }

        # Проверить что все обязательные настройки находятся в файле настроек, а их поля имеют ожидаемый тип
        for key, expected_type in required_keys.items():
            if key not in parameters:
                    raise ConfigError(f"Отсутствует или неверный тип ключа '{key}' в конфигурационном файле {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                raise ConfigError(f"Неверный тип ключа '{key}' в конфигурационном файле {config_yaml_path}. Ожидается {expected_type}.")
        
        # Проверить все поля и значения настройки "Опыт"
        experience = ['doesnt_matter', 'no_experience', 'between_1_and_3', 'between_3_and_6', '6_and_more']
        exp_value_counter = 0
        for exp in experience:
            exp_value = parameters['experience'].get(exp)
            exp_value_counter += exp_value
            if not isinstance(exp_value, bool):
                raise ConfigError(f"Поле 'experience -> {exp}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
        if exp_value_counter > 1:
            raise ConfigError(f"Среди значение 'experience' только одно может иметь значение true в конфигурационном файле {config_yaml_path}")
        
        # Проверить все поля и значения настройки "Сортировка"
        sort_by = ['relevance', 'publication_time', 'salary_desc', 'salary_asc']
        sort_value_counter = 0
        for s_b in sort_by:
            sort_value = parameters['sort_by'].get(s_b)
            sort_value_counter += sort_value
            if not isinstance(sort_value, bool):
                raise ConfigError(f"Поле 'sort_by -> {s_b}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
        if sort_value_counter > 1:
            raise ConfigError(f"Среди значение 'sort_by' только одно может иметь значение true в конфигурационном файле {config_yaml_path}")
        
        # Проверить все поля и значения настройки "Выводить"
        output_period = ['all_time', 'month', 'week', 'three_days', 'one_day']
        output_value_counter = 0
        for o_p in output_period:
            output_period_value = parameters['output_period'].get(o_p)
            output_value_counter += output_period_value
            if not isinstance(output_period_value, bool):
                raise ConfigError(f"Поле 'output_value -> {o_p}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
        if output_value_counter > 1:
            raise ConfigError(f"Среди значение 'output_period' только одно может иметь значение true в конфигурационном файле {config_yaml_path}")

        # Проверить все поля и значения настройки "Показывать на странице"
        output_size = ['show_20', 'show_50', 'show_100']
        output_size_value_counter = 0
        for o_s in output_size:
            output_size_value = parameters['output_size'].get(o_s)
            output_size_value_counter += output_size_value
            if not isinstance(output_size_value, bool):
                raise ConfigError(f"Поле 'output_size -> {o_s}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
        if output_size_value_counter > 1:
            raise ConfigError(f"Среди значение 'output_size' только одно может иметь значение true в конфигурационном файле {config_yaml_path}")

        # необязательные настройки
        optional_keys = {
            'keywords' : list,
            'search_only': dict,
            'words_to_exclude' : list,
            'specialization': str,
            'industry': str,
            'regions' : list,
            'districts' : list,
            'subway' : list,
            'income': int,
            'education': dict,
            'job_type': dict,
            'work_schedule': dict,
            'side_job': dict,
            'other_params': dict,
            'job_blacklist': list,
        }

        # Проверить что все обязательные настройки находятся в файле настроек, а их поля имеют ожидаемый тип
        for key, expected_type in optional_keys.items():
            if key in parameters and not isinstance(parameters[key], expected_type):
                raise ConfigError(f"Неверный тип ключа '{key}' в конфигурационном файле {config_yaml_path}. Ожидается {expected_type}.")
        
        # Проверить все поля и значения настройки "Искать только"
        search_only_list = ['vacancy_name', 'company_name', 'vacancy_description']
        for search in search_only_list:
            if 'search_only' in parameters and not isinstance(parameters['search_only'].get(search), bool):
                raise ConfigError(f"Поле 'search_only -> {search}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Образование"
        education = ['not_needed', 'middle', 'higher']
        for edu in education:
            if 'education' in parameters and not isinstance(parameters['education'].get(edu), bool):
                raise ConfigError(f"Поле 'education -> {edu}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")

        # Проверить все поля и значения настройки "Тип занятости"
        job_type = ['full_time', 'part_time', 'project', 'volunteer', 'probation', 'civil_law_contract']
        for j_t in job_type:
            if 'job_type' in parameters and not isinstance(parameters['job_type'].get(j_t), bool):
                raise ConfigError(f"Поле 'job_type -> {j_t}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")

        # Проверить все поля и значения настройки "График работы"
        work_schedule = ['full_day', 'shift', 'flexible', 'remote', 'fly_in_fly_out']
        for w_s in work_schedule:
            if 'work_schedule' in parameters and not isinstance(parameters['work_schedule'].get(w_s), bool):
                raise ConfigError(f"Поле 'work_schedule -> {w_s}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Подработка"
        side_job = ['project', 'part', 'from_4_hours_per_day', 'weekend', 'evenings']
        for s_j in side_job:
            if 'side_job' in parameters and not isinstance(parameters['side_job'].get(s_j), bool):
                raise ConfigError(f"Поле 'side_job -> {s_j}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Другие параметры"
        other_params = ['with_address', 'accept_handicapped', 'not_from_agency', 'accept_kids', 'accredited_it', 'low_performance']
        for o_p in other_params:
            if 'other_params' in parameters and not isinstance(parameters['other_params'].get(o_p), bool):
                raise ConfigError(f"Поле 'other_params -> {o_p}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
        
        logger.debug("Проверка параметров завершена успешно.")
        
        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> tuple:
        """Проверить наличие секретных ключей для LLM API"""
        secrets = ConfigValidator.load_yaml_file(secrets_yaml_path)
        mandatory_secrets = ['llm_api_key']

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"Отсутствует ключ '{secret}' в файле {secrets_yaml_path}")

        if not secrets['llm_api_key']:
            raise ConfigError(f"Значение llm_api_key не может быть пустым в файле {secrets_yaml_path}.")
        return secrets['llm_api_key']


class FileManager:
    """"Класс для поиска и проверки содержимого файла в папке данных"""
    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        """Проверить наличие всех необходимых файлов настроек"""
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Папка данных не найдена: {app_data_folder}")

        required_files = ['secrets.yaml', 'config.yaml', 'plain_text_resume.yaml', 'resume.txt']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"Отсутствуют файлы в папке данных: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', app_data_folder / 'resume.txt')
    
    @staticmethod
    def file_paths_to_dict(resume_file: Path, plain_text_resume_file: Path) -> dict:
        """Добавить в параметры файлы резюме"""
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Схема резюме не найдена: {plain_text_resume_file}")
        
        if not resume_file.exists():
                raise FileNotFoundError(f"Файл резюме не найден: {resume_file}")

        result = {'plainTextResume': plain_text_resume_file, 'resume': resume_file}

        return result


def init_driver() -> webdriver.Chrome:
    """Инициализировать Selenium driver"""
    try:
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")


def create_and_run_bot(parameters, llm_api_key):
    """Запустить бот"""
    try:
        with open(parameters['uploads']['plainTextResume'], 'r') as stream:
            resume_profile =  yaml.safe_load(stream)
        with open(parameters['uploads']['resume'], "r", encoding='utf-8') as file:
            resume = file.read()
        
        driver = init_driver()
        login_component = Authenticator(driver)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        apply_component = JobManager(driver)
        bot = BotFacade(login_component, apply_component)
        bot.set_resume_profile_and_resume(resume_profile, resume)
        bot.set_gpt_answerer(gpt_answerer_component)
        bot.set_parameters(parameters)
        bot.start_login()
        bot.set_search_parameters()
        bot.start_apply()
    except WebDriverException as e:
        logger.error(f"WebDriver ошибка: {e}")
    except Exception as e:
        raise RuntimeError(f"Ошибка в процессе работы бота: {str(e)}")

def main():
    try:
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, resume = FileManager.validate_data_folder(data_folder)
        
        config_validator = ConfigValidator()
        parameters = config_validator.validate_config(config_file)
        llm_api_key = config_validator.validate_secrets(secrets_file)
        
        parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        
        create_and_run_bot(parameters, llm_api_key)
    except ConfigError as ce:
        logger.error(f"Ошибка конфигурации: {str(ce)}")
        # logger.error(f"Refer to the configuration guide for troubleshooting: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration {str(ce)}")
    except FileNotFoundError as fnf:
        logger.error(f"Файл не найден: {str(fnf)}")
        logger.error("Убедитесь, что все необходимые файлы находятся в папке data_folder")
        # logger.error("Refer to the file setup guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")
    except RuntimeError:
        tb_str = traceback.format_exc()
        logger.error(f"Runtime error: {tb_str}")
        # logger.error("Refer to the configuration and troubleshooting guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")
    except Exception:
        tb_str = traceback.format_exc()
        logger.error(f"Неизвестная ошибка: {tb_str}")
        # logger.error("Refer to the general troubleshooting guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")

if __name__ == "__main__":
    main()