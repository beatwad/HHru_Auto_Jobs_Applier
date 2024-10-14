import os
import re
import sys
from pathlib import Path
import yaml
import click
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import WebDriverException
from lib_resume_builder_AIHawk import Resume,StyleManager,FacadeManager,ResumeGenerator
from src.utils import chrome_browser_options
from src.llm.llm_manager import GPTAnswerer
from src.aihawk_authenticator import AIHawkAuthenticator
from src.aihawk_bot_facade import AIHawkBotFacade
from src.job_manager import JobManager
from src.job_application_profile import JobApplicationProfile
from loguru import logger

# Suppress stderr
sys.stderr = open(os.devnull, 'w')

class ConfigError(Exception):
    pass

class ConfigValidator:
    @staticmethod
    def validate_email(email: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email) is not None
    
    
    @staticmethod
    def validate_phone(phone_number: str) -> bool:
        # Delete all parenthesis and '-' symbols from number
        cleaned_number = re.sub(r'[()\-]', '', phone_number)
        
        # Regular expression to match a valid phone number
        pattern = r"^\+?[1-9][0-9]{7,14}$"
        
        # Match the phone number with the pattern
        return re.match(pattern, cleaned_number) is not None

    
    @staticmethod
    def validate_yaml_file(yaml_path: Path) -> dict:
        try:
            with open(yaml_path, 'r') as stream:
                return yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            raise ConfigError(f"Error reading file {yaml_path}: {exc}")
        except FileNotFoundError:
            raise ConfigError(f"File not found: {yaml_path}")
    
    
    def validate_config(self, config_yaml_path: Path) -> dict:
        parameters = self.validate_yaml_file(config_yaml_path)
        required_keys = {
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
            'experience': dict,
            'job_type': dict,
            'work_schedule': dict,
            'side_job': dict,
            'other_params': dict,
            'llm_model_type': str,
            'llm_model': str
        }
        
        # Проверить что все ключи находятся в файле настроек, а их поля имеют ожидаемый тип
        for key, expected_type in required_keys.items():
            if key not in parameters:
                    raise ConfigError(f"Отсутствует или неверный тип ключа '{key}' в конфигурационном файле {config_yaml_path}")
            elif not isinstance(parameters[key], expected_type):
                raise ConfigError(f"Неверный тип ключа '{key}' в конфигурационном файле {config_yaml_path}. Ожидается {expected_type}.")

        # Проверить все поля и значения настройки "Искать только"
        search_only_list = ['vacancy_name', 'company_name', 'vacancy_description']
        for search in search_only_list:
            if not isinstance(parameters['search_only'].get(search), bool):
                raise ConfigError(f"Поле 'search_only -> {search}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Образование"
        education = ['not_needed', 'middle', 'higher']
        for edu in education:
            if not isinstance(parameters['education'].get(edu), bool):
                raise ConfigError(f"Поле 'education -> {edu}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")

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

        # Проверить все поля и значения настройки "Тип занятости"
        job_type = ['full_time', 'part_time', 'project', 'volunteer', 'probation', 'civil_law_contract']
        for j_t in job_type:
            if not isinstance(parameters['job_type'].get(j_t), bool):
                raise ConfigError(f"Поле 'job_type -> {j_t}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")

        # Проверить все поля и значения настройки "График работы"
        work_schedule = ['full_day', 'shift', 'flexible', 'remote', 'fly_in_fly_out']
        for w_s in work_schedule:
            if not isinstance(parameters['work_schedule'].get(w_s), bool):
                raise ConfigError(f"Поле 'work_schedule -> {w_s}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Подработка"
        side_job = ['one_time_task', 'part_time', 'from_4_hours_per_day', 'weekend', 'evenings']
        for s_j in side_job:
            if not isinstance(parameters['side_job'].get(s_j), bool):
                raise ConfigError(f"Поле 'side_job -> {s_j}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")
            
        # Проверить все поля и значения настройки "Другие параметры"
        other_params = ['with_address', 'accept_handicapped', 'not_from_agency', 'accept_kids', 'accredited_it', 'low_performance']
        for o_p in other_params:
            if not isinstance(parameters['other_params'].get(o_p), bool):
                raise ConfigError(f"Поле 'other_params -> {o_p}' должно иметь тип bool в конфигурационном файле {config_yaml_path}")

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
        
        return parameters

    @staticmethod
    def validate_secrets(secrets_yaml_path: Path) -> tuple:
        secrets = ConfigValidator.validate_yaml_file(secrets_yaml_path)
        mandatory_secrets = ['llm_api_key']

        for secret in mandatory_secrets:
            if secret not in secrets:
                raise ConfigError(f"Missing secret '{secret}' in file {secrets_yaml_path}")

        if not secrets['llm_api_key']:
            raise ConfigError(f"llm_api_key cannot be empty in secrets file {secrets_yaml_path}.")
        return secrets['llm_api_key']


class FileManager:
    @staticmethod
    def find_file(name_containing: str, with_extension: str, at_path: Path) -> Path:
        return next((file for file in at_path.iterdir() if name_containing.lower() in file.name.lower() and file.suffix.lower() == with_extension.lower()), None)

    @staticmethod
    def validate_data_folder(app_data_folder: Path) -> tuple:
        """Проверяет, что все необходимые файлы находятся в папке данных"""
        if not app_data_folder.exists() or not app_data_folder.is_dir():
            raise FileNotFoundError(f"Data folder not found: {app_data_folder}")

        required_files = ['secrets.yaml', 'config.yaml', 'plain_text_resume.yaml']
        missing_files = [file for file in required_files if not (app_data_folder / file).exists()]
        
        if missing_files:
            raise FileNotFoundError(f"В папке данных отсутствуют файлы: {', '.join(missing_files)}")

        output_folder = app_data_folder / 'output'
        output_folder.mkdir(exist_ok=True)
        return (app_data_folder / 'secrets.yaml', app_data_folder / 'config.yaml', app_data_folder / 'plain_text_resume.yaml', output_folder)

    @staticmethod
    def file_paths_to_dict(resume_file: Path | None, plain_text_resume_file: Path) -> dict:
        if not plain_text_resume_file.exists():
            raise FileNotFoundError(f"Plain text resume file not found: {plain_text_resume_file}")

        result = {'plainTextResume': plain_text_resume_file}

        if resume_file:
            if not resume_file.exists():
                raise FileNotFoundError(f"Resume file not found: {resume_file}")
            result['resume'] = resume_file

        return result


def init_driver() -> webdriver.Chrome:
    try:
        options = chrome_browser_options()
        service = ChromeService(ChromeDriverManager().install())
        return webdriver.Chrome(service=service, options=options)
    except Exception as e:
        raise RuntimeError(f"Failed to initialize browser: {str(e)}")

def create_and_run_bot(parameters, llm_api_key):
    try:
        # style_manager = StyleManager()
        # resume_generator = ResumeGenerator()
        # with open(parameters['uploads']['plainTextResume'], "r", encoding='utf-8') as file:
        #     plain_text_resume = file.read()
        # resume_object = Resume(plain_text_resume)
        # resume_generator_manager = FacadeManager(llm_api_key, style_manager, resume_generator, resume_object, Path("data_folder/output"))
        # os.system('cls' if os.name == 'nt' else 'clear')
        # resume_generator_manager.choose_style()
        # os.system('cls' if os.name == 'nt' else 'clear')
        
        # job_application_profile_object = JobApplicationProfile(plain_text_resume)
        
        driver = init_driver()
        login_component = AIHawkAuthenticator(driver)
        apply_component = JobManager(driver)
        gpt_answerer_component = GPTAnswerer(parameters, llm_api_key)
        bot = AIHawkBotFacade(login_component, apply_component)
        # bot.set_job_application_profile_and_resume(job_application_profile_object, resume_object)
        # bot.set_gpt_answerer_and_resume_generator(gpt_answerer_component, resume_generator_manager)
        # bot.set_parameters(parameters)
        bot.start_login()
        bot.start_apply()
    except WebDriverException as e:
        logger.error(f"WebDriver error occurred: {e}")
    except Exception as e:
        raise RuntimeError(f"Error running the bot: {str(e)}")


@click.command()
@click.option('--resume', type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path), help="Path to the resume PDF file")
def main(resume: Path = None):
    try:
        data_folder = Path("data_folder")
        secrets_file, config_file, plain_text_resume_file, output_folder = FileManager.validate_data_folder(data_folder)
        
        parameters = ConfigValidator.validate_config(config_file)
        llm_api_key = ConfigValidator.validate_secrets(secrets_file)
        
        # parameters['uploads'] = FileManager.file_paths_to_dict(resume, plain_text_resume_file)
        # parameters['outputFileDirectory'] = output_folder
        
        create_and_run_bot(parameters, llm_api_key)
    except ConfigError as ce:
        logger.error(f"Configuration error: {str(ce)}")
        logger.error(f"Refer to the configuration guide for troubleshooting: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration {str(ce)}")
    except FileNotFoundError as fnf:
        logger.error(f"File not found: {str(fnf)}")
        logger.error("Ensure all required files are present in the data folder.")
        logger.error("Refer to the file setup guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")
    except RuntimeError as re:

        logger.error(f"Runtime error: {str(re)}")

        logger.error("Refer to the configuration and troubleshooting guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        logger.error("Refer to the general troubleshooting guide: https://github.com/feder-cr/AIHawk_AIHawk_automatic_job_application/blob/main/readme.md#configuration")

if __name__ == "__main__":
    main()
