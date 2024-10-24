from typing import List, Dict, Tuple, Any

import os
import re
import json
import random
import time
import traceback
from pathlib import Path

from inputimeout import inputimeout, TimeoutOccurred

from selenium import webdriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.app_config import MINIMUM_WAIT_TIME_SEC, APPLY_ONCE_AT_COMPANY
from loguru import logger


class JobManager:
    """Класс для поиска и рассылки откликов работодателям"""
    def __init__(self, driver: webdriver.Chrome):
        logger.debug("Инициализация JobManager")
        self.driver = driver
        self.gpt_answerer = None
        self.wait = WebDriverWait(driver, 4, poll_frequency=1)
        self.page_num = 1
        self.current_position = 0
        logger.debug("JobManager успешно инициализирован")

    def set_parameters(self, parameters: Dict[str, Any]):
        """Установка параметрок поиска"""
        logger.debug("Установка параметров JobManager")
        # загрузка обязательных параметров
        self.job_title = parameters['job_title']
        self.login = parameters['login']
        self.keywords = parameters.get("keywords", [])
        self.experience = parameters['experience']
        self.sort_by = parameters['sort_by']
        self.output_period = parameters['output_period']
        self.output_size = parameters['output_size']
        # загрузка необязательных параметров
        self.search_only = parameters.get('search_only', {})
        self.words_to_exclude = parameters.get('words_to_exclude', [])
        self.specialization = parameters.get('specialization', "")
        self.industry = parameters.get('industry', "")
        self.regions = parameters.get('regions', [])
        self.districts = parameters.get('districts', [])
        self.subway = parameters.get('subway', [])
        self.income = parameters.get('income', 0)
        self.education = parameters.get('education', {})
        self.job_type = parameters.get('job_type', {})
        self.work_schedule = parameters.get('work_schedule', {})
        self.side_job = parameters.get('side_job', {})
        self.other_params = parameters.get('other_params', {})
        # загрузить черный список компаний
        self.job_blacklist = parameters.get('job_blacklist', [])
        self.job_blacklist = [self._sanitize_text(j_b) for j_b in self.job_blacklist]
        # загрузить компании, в которые уже были отправлены заявки
        self.companies = self._load_companies_from_json()
        self.seen_answers = self._load_questions_from_json()
        logger.debug("Параметры успешно установлены")
    
    def set_advanced_search_params(self) -> None:
        """Задать дополнительные параметры поиска в hh.ru"""
        self._enter_advanced_search_menu()
        keywords_element = ("xpath", "//*[@data-qa='vacancysearch__keywords-input']")
        self.wait.until(EC.visibility_of_element_located(keywords_element))
        self.current_position = 0
        
        self._set_key_words()
        self._set_search_only()
        self._set_words_to_exclude()
        self._set_specialization()
        self._set_industry()
        self._set_region()
        self._set_district()
        self._set_subway()
        self._set_income()
        self._set_education()
        self._set_experience()
        self._set_job_type()
        self._set_work_schedule()
        self._set_side_job()
        self._set_other_params()
        self._set_sort_by()
        self._set_output_period()
        self._set_output_size()
        try:
            _ = inputimeout(
                prompt="""Пожалуйста,проверьте настройки, убедитесь, что все верно или исправьте неверные по вашему мнению настройки. 
                По завершению нажмите Enter. У вас есть 2 минуты.""",
                timeout=120)
        except TimeoutOccurred:
            pass
        self._start_search()

        
    def set_gpt_answerer(self, gpt_answerer: Any):
        """
        Задать LLM для ответов на вопросы и написания
        сопроводительных писем
        """
        self.gpt_answerer = gpt_answerer
    
    def start_applying(self) -> None:
        """Разослать отклики всем работодателям на всех страницах"""
        while True:
            try:
                # идем по всем страницам пока они не закончатся
                if self.page_num > 1:
                    text = f"number-pages-{self.page_num}"
                    try:
                        next_page = self.driver.find_element("xpath", f"//*[starts-with(@data-qa, '{text}')]")
                        self.current_position = self._scroll_slow(next_page, self.current_position)
                        next_page.click()
                    except NoSuchElementException:
                        break
                self._send_repsonses()
                self.page_num += 1
                # делать случайную паузу на каждой странице
                self._sleep((20, 40))
                logger.debug(f"Переходим на страницу {self.page_num}")
            except Exception:
                tb_str = traceback.format_exc()
                logger.error(f"Неизвестная ошибка: {tb_str}")
                continue
    
    def apply_job(self, job: Dict[str, str]) -> None:
        """Откликнусться на вакансию"""
        self.gpt_answerer.set_job(job)
        # найти кнопку отклика
        respnose_buttons = self.driver.find_elements("xpath", f"//*[@data-qa='vacancy-response-link-top']")
        if len(respnose_buttons) == 0:
            logger.debug(f"Не нашли кнопку отклика, видимо вы уже откликались на вакансию {job["company_name"]}")
        else:
            respnose_buttons[0].click()
            self._find_and_handle_questions()
            self._write_and_send_cover_letter()
        self._pause()

    def _scroll_slow(self, element: WebElement, current_position: int, time_to_scroll_sec: float = 2) -> int:
        """Медленно скроллить страницу, пока не дойдем до элемента"""
        # Get the element's position on the page
        element_position = element.location['y']

        # определить размер шага, необходимый для того, чтобы
        # доскроллить до элемента за время time_to_scroll_sec
        sleep_time = 0.01
        distance = abs(current_position - element_position)
        step_num = time_to_scroll_sec // sleep_time + 1
        step = distance // step_num + 1
        
        # медленно скроллим до нужного нам элемента
        if current_position < element_position:
            while current_position < element_position - 30:
                current_position += step
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(sleep_time)
        else:
            while current_position > element_position + 30:
                current_position -= step
                self.driver.execute_script(f"window.scrollTo(0, {current_position});")
                time.sleep(sleep_time) 
        
        time.sleep(0.5)
        return current_position
    
    def _send_repsonses(self) -> None:
        """Разослать отклики всем работодателям на странице"""
        self.current_position = 0
        minimum_page_time = time.time() + MINIMUM_WAIT_TIME_SEC
        employers = self.driver.find_elements("xpath", "//*[starts-with(@data-qa, 'serp-item__title-text')]")
        for employer in employers:
            # зайти на страницу к работодателю
            self.current_position = self._scroll_slow(employer, self.current_position)
            employer.click()
            self._pause()
            window_handles = self.driver.window_handles
            self.driver.switch_to.window(window_handles[-1])
            # собрать описание вакансии
            job = self._scrape_employer_page()
            company_name = job["company_name"]
            company_name = self._sanitize_text(company_name)
            company_job_title = job["title"]
            company_job_title = self._sanitize_text(company_job_title)
            logger.debug(f"Найдена вакансия {company_job_title}")
            # если вакансия еще не встречалась и компания не в черном списке 
            # - начать процесс отклика на вакансию
            if not self._is_blacklisted(company_name) and \
                not self._is_already_applied_to_job_or_company(company_name, company_job_title):
                # добавить информацию об отклике для последующей записи в JSON файл
                my_company = self.companies[self.login][self.job_title]
                if company_name in my_company:
                    my_company[company_name].append(company_job_title)
                else:
                    my_company[company_name] = [company_job_title]
                # откликнуться на вакансию
                self.apply_job(job)
                # записать информацию об отклике в JSON файл
                self._save_company_to_json()
            # вернуться обратно на страницу поиска
            self.driver.close()
            self._pause()
            self.driver.switch_to.window(window_handles[0])
        # если страница была обработана быстрее, чем за минимальное время - 
        # подождать, пока это время не закончится       
        time_left = int(minimum_page_time - time.time())
        if time_left > 0:
            self._sleep((time_left, time_left + 5))
                
    def _scrape_employer_page(self) -> Dict[str, str]:
        """
        Собрать всю информацию о работодателе со страницы
        для дальнейшей передачи в LLM
        """
        job = {}

        description_keys = [
            "title", "salary", "experience", "job_type", "company_name", 
            "company_address", "company_address", "description",
            "description", "skills"
            ]
        data_qas = [
            "vacancy-title", "vacancy-salary-compensation-type-net", "vacancy-experience",
            "vacancy-view-employment-mode", "vacancy-company-name",
            "vacancy-view-raw-address", "vacancy-view-location", "vacancy-branded", 
            "vacancy-description", "skills-element"
            ]
        self.wait.until(EC.visibility_of_element_located(("xpath", "//*[@data-qa='vacancy-title']")))
        for key, data_qa in zip(description_keys, data_qas):
            if key == "skills":
                skill_list = self.driver.find_elements("xpath", f"//*[@data-qa='{data_qa}']")
                skill_list = [skill.text for skill in skill_list]
                job["skills"] = ', '.join(skill_list)
                continue
            if key in ["company_address", "description"] and job.get(key) is not None:
                continue
            try:
                job[key] = self.driver.find_element("xpath", f"//*[@data-qa='{data_qa}']").text
            except NoSuchElementException:
                job[key] = None
        
        return job

    @staticmethod
    def _define_answers_output_file(filename: str) -> Path:
        try:
            output_file = os.path.join(
                Path("data_folder/output"), filename)
            logger.debug(f"Определено расположение лог-файла: {output_file}")
        except Exception as e:
            logger.error(f"Ошибка в определении расположения лог-файла: {str(e)}")
            raise
        return output_file
    
    def _save_company_to_json(self) -> None:
        """Сохранить уже просмотренные компании и их вакансии в файл"""
        output_file = self._define_answers_output_file("companies.json")
        logger.debug(f"Сохраняем данные о вакансии в JSON")
        try:
            try:
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        if not isinstance(data, dict):
                            raise ValueError("JSON file format is incorrect. Expected a list of questions.")
                    except json.JSONDecodeError:
                        logger.error("JSON decoding failed")
            except FileNotFoundError:
                logger.warning("JSON file not found, creating new file")
            with open(output_file, 'w') as f:
                json.dump(self.companies, f, indent=4)
            logger.debug("Данные о компании и ее вакансии успешно сохранены в JSON")
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error saving questions data to JSON file: {tb_str}")
            raise Exception(f"Error saving questions data to JSON file: \nTraceback:\n{tb_str}")
        
    def _load_companies_from_json(self) -> List[dict]:
        """Загрузить файл c уже просмотренными компаниями и их вакансиями"""
        output_file = self._define_answers_output_file("companies.json")
        logger.debug(f"Loading companies from JSON file: {output_file}")
        try:
            with open(output_file, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, dict):
                        raise ValueError("JSON file format is incorrect. Expected a list of questions.")
                except json.JSONDecodeError:
                    logger.error("JSON decoding failed")
                    data = {self.login: {self.job_title: {}}}
            logger.debug("Данные о компаниях и ее вакансиях успешно загружены из JSON")
            if self.login not in data:
                data[self.login] = {}
            if self.job_title not in data[self.login]:
                data[self.login][self.job_title] = {}
            return data
        except FileNotFoundError:
            data = {self.login: {self.job_title: {}}}
            logger.warning("JSON file not found, returning empty dict")
            return data
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error loading questions data from JSON file: {tb_str}")
            raise Exception(f"Error loading questions data from JSON file: \nTraceback:\n{tb_str}")
    
    def _save_questions_to_json(self, question_data: dict) -> None:
        """Сохранить вопрос в файл"""
        output_file = self._define_answers_output_file("answers.json")
        question_data['question'] = self._sanitize_text(question_data['question'])
        logger.debug(f"Saving question data to JSON: {question_data}")
        try:
            try:
                with open(output_file, 'r') as f:
                    try:
                        data = json.load(f)
                        if not isinstance(data, list):
                            raise ValueError("JSON file format is incorrect. Expected a list of questions.")
                    except json.JSONDecodeError:
                        logger.error("JSON decoding failed")
                        data = []
            except FileNotFoundError:
                logger.warning("JSON file not found, creating new file")
                data = []
            data.append(question_data)
            with open(output_file, 'w') as f:
                json.dump(data, f, indent=4)
            logger.debug("Question data saved successfully to JSON")
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error saving questions data to JSON file: {tb_str}")
            raise Exception(f"Error saving questions data to JSON file: \nTraceback:\n{tb_str}")
        
    def _load_questions_from_json(self) -> List[dict]:
        """Загрузить файл с уже готовыми ответами на вопросы"""
        output_file = self._define_answers_output_file("answers.json")
        logger.debug(f"Loading questions from JSON file: {output_file}")
        try:
            with open(output_file, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError("JSON file format is incorrect. Expected a list of questions.")
                except json.JSONDecodeError:
                    logger.error("JSON decoding failed")
                    data = []
            logger.debug("Questions loaded successfully from JSON")
            return data
        except FileNotFoundError:
            logger.warning("JSON file not found, returning empty list")
            return []
        except Exception:
            tb_str = traceback.format_exc()
            logger.error(f"Error loading questions data from JSON file: {tb_str}")
            raise Exception(f"Error loading questions data from JSON file: \nTraceback:\n{tb_str}")
        
    def _find_and_handle_questions(self) -> None:
        """Если на странице есть вопросы - использовать LLM для ответа на них"""
        question_element = ("xpath", "//*[@data-qa='task-body']")
        try:
            self.wait.until(EC.visibility_of_element_located(question_element))
        except TimeoutException:
            return
        questions = self.driver.find_elements(*question_element)
        if questions:
            logger.debug("Нашли вопрос(ы).")
            for question in questions:
                self._find_and_handle_textbox_question(question)
        else:
            logger.debug("Вопросы не найдены.")

    def _write_and_send_cover_letter(self) -> None:
        """Написать и отправить работодателю сопроводительное письмо"""
        cover_letter_text = self.gpt_answerer.write_cover_letter()
        cover_letter_field = self.driver.find_elements("xpath", "//*[@data-qa='vacancy-response-popup-form-letter-input']")
        # если удалось найти форму для ввода сопроводительного письма - отправить его туда 
        if cover_letter_field:
            cover_letter_field = cover_letter_field[0]
            position = self._scroll_slow(cover_letter_field, 0)
            self._enter_text(cover_letter_field, cover_letter_text)
            # нажать на кнопку отклика
            response_button = self.driver.find_element("xpath", "//*[@data-qa='vacancy-response-submit-popup']")
            self._scroll_slow(response_button, position)
            response_button.click()
        else:
            # если удалось найти кнопки добавления сопроводительного письма - нажать и отправить его 
            cover_letter_buttons = self.driver.find_elements("xpath", f"//*[@data-qa='vacancy-response-letter-toggle']")
            if cover_letter_buttons:
                # нажать на кнопку добавления сопроводительного письма
                cover_letter_button = cover_letter_buttons[0]
                self._scroll_slow(cover_letter_buttons[0], 0)
                cover_letter_button.click()
                # записать в поле текст сопроводительного письма
                cover_letter_field = self.driver.find_element("xpath", f"//*[@data-qa='vacancy-response-letter-informer']")
                cover_letter_text_field = cover_letter_field.find_element("tag name", 'textarea')
                self._enter_text(cover_letter_text_field, cover_letter_text)
            else:
                # иначе зайти в чат с работодателем и отправить сопроводительное из него
                chat_button = self.driver.find_element("xpath", f"//*[@data-qa='vacancy-response-link-view-topic']")
                self._scroll_slow(chat_button, 0)
                chat_button.click()
                iframes = self.driver.find_elements("tag name", "iframe")
                # найти окошко чата
                for frame in iframes:
                    if frame.get_attribute('class') == "chatik-integration-iframe chatik-integration-iframe_loaded":
                        self.driver.switch_to.frame(frame)
                        self.driver.find_element("xpath", f"//*[@data-qa='chatik-chat-message-applicant-action-text']").click()
                        # послать в чат сопроводительное письмо
                        text_field = self.driver.find_element("xpath", f"//*[@data-qa='chatik-new-message-text']")
                        self._enter_text(text_field, cover_letter_text)
                        self._pause()
                        text_field.send_keys(Keys.ENTER)
                        break
                self.driver.switch_to.default_content()
                
    def _find_and_handle_textbox_question(self, question: WebElement) -> bool:
        text_question_fields = question.find_elements("tag name", 'textarea')
        if text_question_fields:
            question_text = question.text.lower().strip()
            logger.debug(f"Нашли текстовый вопрос: {question_text}")
            text_field = text_question_fields[0]

            # Look for existing answer if it's not a cover letter field
            existing_answer = None
            for answer in self.seen_answers:
                if self._sanitize_text(answer['question']) == self._sanitize_text(question_text):
                    existing_answer = answer['answer']
                    logger.debug(f"Найден готовый ответ: {existing_answer}")
                    break

            if existing_answer:
                answer = existing_answer
                logger.debug(f"Используем готовый ответ: {answer}")
            else:
                answer = self.gpt_answerer.answer_question_textual_wide_range(question_text)
                logger.debug(f"Сгенерирован ответ: {answer}")

            # Save non-cover letter answers
            self._save_questions_to_json({'question': question_text, 'answer': answer})
            logger.debug("Тестовый вопрос сохранен в JSON.")

            time.sleep(1)
            self._enter_text(text_field, answer)
            logger.debug("Ответ введен в textbox")
            return True

        logger.debug("No text fields found in the section.")
        return False
    
    def _is_blacklisted(self, company: str) -> bool:
        """Проверить, откликались ли мы уже на эту вакансию"""
        if company in self.job_blacklist:
            logger.debug("Компания в черном списке, пропускаем")
            return True
        return False
    
    def _is_already_applied_to_job_or_company(self, company: str, job: str) -> bool:
        """Проверить, откликались ли мы уже на эту вакансию"""
        my_companies = self.companies[self.login][self.job_title]
        if company in my_companies:
            if APPLY_ONCE_AT_COMPANY:
                logger.debug("Компания уже встречалась и задана настройка не подаваться "
                             "повторно в ту же компанию, пропускаем")
                return True
            if job in my_companies[company]:
                logger.debug("Вакансия уже встречалась, пропускаем")
                return True
        return False
    
    def _enter_text(self, element: WebElement, text: str) -> None:
        logger.debug(f"Entering text: {text}")
        element.clear()
        element.send_keys(text)
    
    @staticmethod
    def _pause(low: int = 1, high: int = 2) -> None:
        """
        Выдержать случайную паузу в диапазоне от 
        low секунд до high секунд. 
        Используется для имитации пользовательского поведения.
        """
        pause = round(random.uniform(low, high), 1)
        time.sleep(pause)

    @staticmethod
    def _sleep(sleep_interval: Tuple[int, int]) -> None:
        """Аналог _pause, но ожидание можно прервать"""
        low, high = sleep_interval
        sleep_time = random.randint(low, high)
        try:
            user_input = inputimeout(
                prompt=f"Делаем паузу на {round(sleep_time / 60, 2)} минут(ы). Нажмите Enter, чтобы прекратить ожидание.",
                timeout=sleep_time).strip().lower()
        except TimeoutOccurred:
            user_input = ''  # No input after timeout
        if user_input != '':
            logger.debug("Прекращаем ожидание.")
        else:
            logger.debug(f"Ожидание продлилось {sleep_time} секунд.")
    
    def _find_by_text_and_click(self, text: str) -> None:
        """Функция для поиска элемента по тексту и клика по нему"""
        element = self.driver.find_element("xpath", f'//*[text()="{text}"]')
        self.current_position = self._scroll_slow(element, self.current_position)
        element.click()

    def _find_by_data_qa_and_click(self, text: str) -> None:
        """Функция для поиска элемента по тексту и клика по нему"""
        element = self.driver.find_element("xpath", f"//*[@data-qa='{text}']")
        self.current_position = self._scroll_slow(element, self.current_position)
        element.click()
    
    def _enter_advanced_search_menu(self) -> None:
        """Зайти на страницу с резюме, выбрать нужное и перейти через него к поиску вакансий"""
        self.driver.get("https://hh.ru/applicant/resumes")
        resume_title_element = ("xpath", "//*[starts-with(@data-qa, 'resume-title-link')]")
        resume_recommendation_element = ("xpath", "//*[starts-with(@data-qa, 'resume-recommendations__button')]")
        self.wait.until(EC.visibility_of_element_located(resume_title_element))
        resume_titles = self.driver.find_elements(*resume_title_element)
        # найти среди резюме подходящее с таким же названием, что указано в настройках
        for i, resume_title in enumerate(resume_titles):
            if resume_title.text == self.job_title:
                resume_num = i
                break
        else:
            logger.error(f"Не смогли найти среди ваших резюме нужное с именем {self.job_title}")
            raise
        resume_recommendations = self.driver.find_elements(*resume_recommendation_element)
        resume_recommendation = resume_recommendations[resume_num]
        # Получить наименование
        self._scroll_slow(resume_recommendation, 0)
        resume_recommendation.click()
        # перейти к расширенному поиску
        for _ in range(10):
            # дождаться пока кнопка станет кликабельной
            try:
                wait = WebDriverWait(self.driver, 2, poll_frequency=1)
                advanced_search_element = ("xpath", "//*[@data-qa='advanced-search']")
                element = wait.until(EC.element_to_be_clickable(advanced_search_element))
            except (TimeoutException, StaleElementReferenceException):
                pass
            else:
                element.click()
    
    def _set_key_words(self) -> None:
        """Задать ключевые слова"""
        if self.keywords:
            keywords_field = self.driver.find_element("xpath", "//*[@data-qa='vacancysearch__keywords-input']")
            self._enter_text(keywords_field, ', '.join(self.keywords))
            self._pause()
            keywords_field.send_keys(Keys.TAB)

    def _set_search_only(self) -> None:
        """Искать только"""
        search_only_dict = {
            "vacancy_name": "в названии вакансии", 
            "company_name": "в названии компании", 
            "vacancy_description": "в описании вакансии" 
            }
        for s_o in self.search_only:
            if self.search_only[s_o] is True:
                self._find_by_text_and_click(search_only_dict[s_o])

    def _set_words_to_exclude(self) -> None:
        """Исключить слова"""    
        if not self.words_to_exclude:
            return
        words_to_exclude_element = self.driver.find_element("xpath", "//*[@data-qa='vacancysearch__keywords-excluded-input']")
        self.current_position = self._scroll_slow(words_to_exclude_element, self.current_position)
        self._enter_text(words_to_exclude_element, ', '.join(self.words_to_exclude))

    def _set_specialization(self) -> None:   
        """Задать специализацию"""
        if not self.specialization:
            return
        # Выбрать меню 'Указать специализации'
        self._find_by_data_qa_and_click("resumesearch__profroles-switcher")
        specialization_item =("xpath", "//*[@data-qa='bloko-tree-selector-popup-search']")
        # Ввести специализацию в поисковую строку
        self.wait.until(EC.visibility_of_element_located(specialization_item))
        specialization_element = self.driver.find_element("xpath", "//*[@data-qa='bloko-tree-selector-popup-search']")
        self._enter_text(specialization_element, self.specialization)
        self._pause()
        # Попытаться найти специализацию с таким же названием, что и название специализации в переменной
        specialization_list = self.driver.find_elements("xpath", f'//*[text()="{self.specialization}"]')
        # Иначе выбрать первую специализацию в чекбоксе (если есть, иначе закрыть)
        if len(specialization_list) == 0:
            specialization_list = self.driver.find_elements("xpath", "//*[starts-with(@data-qa, 'bloko-tree-selector-item-text bloko-tree-selector-item-text')]")
        if len(specialization_list) > 0:
            specialization_list[0].click()
            self.driver.find_element("xpath", "//*[@data-qa='bloko-tree-selector-popup-submit']").click()
        else:
            self.driver.find_element("xpath", "//*[@data-qa='bloko-modal-close']").click()

    def _set_industry(self) -> None:   
        """Задать oтрасль компании"""
        if not self.industry:
            return
        # Выбрать меню 'Указать отрасль компании'
        self._find_by_data_qa_and_click("industry-addFromList")
        industry_item = ("xpath", "//*[@data-qa='bloko-tree-selector-popup-search']")
        # Ввести отрасль в поисковую строку
        self.wait.until(EC.visibility_of_element_located(industry_item))
        industry_element = self.driver.find_element(*industry_item)
        self._enter_text(industry_element, self.industry)
        self._pause()
        # Попытаться найти отрасль с таким же названием, что и название отрасли в переменной
        industry_list = self.driver.find_elements("xpath", f'//*[text()="{self.industry}"]')
        # Иначе выбрать первую отрасль в чекбоксе (если есть, иначе закрыть)
        if len(industry_list) == 0:
            industry_list = self.driver.find_elements("xpath", "//*[starts-with(@data-qa, 'bloko-tree-selector-item-text bloko-tree-selector-item-text')]")
        if len(industry_list) > 0:
            industry_list[0].click()
            self.driver.find_element("xpath", "//*[@data-qa='bloko-tree-selector-popup-submit']").click() 
        else:
            self.driver.find_element("xpath", "//*[@data-qa='bloko-modal-close']").click() 

    def _set_region(self) -> None:   
        """Задать регион"""
        region_element = self.driver.find_element("xpath",f"//*[@data-qa='advanced-search-region-add']")
        for region in self.regions:
            self._enter_text(region_element, region)
            self._pause()
            region_element.send_keys(Keys.TAB)
            self._pause()

    def _set_district(self) -> None:   
        """Задать район (если есть на странице)"""
        try:
            district_element = self.driver.find_element("xpath", "//*[@data-qa='searchform__district-input']")
        except NoSuchElementException:
            pass
        else:
            for district in self.districts:
                self._enter_text(district_element, district)
                self._pause()
                district_element.send_keys(Keys.TAB)
                self._pause()
                
    def _set_subway(self) -> None:   
        """Задать метро (если есть на странице)"""
        try:
            subway_element = self.driver.find_element("xpath", "//*[@data-qa='searchform__subway-input']")
        except NoSuchElementException:
            pass
        else:
            for station in self.subway:
                self._enter_text(subway_element, station)
                self._pause()
                subway_element.send_keys(Keys.TAB)
                self._pause()

    def _set_income(self) -> None:   
        """Задать уровень дохода"""
        if self.income > 0:
            income_element = self.driver.find_element("xpath", "//*[@data-qa='advanced-search-salary']")
            self._enter_text(income_element, self.income)

    def _set_education(self) -> None:   
        """Задать образование"""    
        education_dict = {
            "not_needed": "advanced-search__education-item-label_not_required_or_not_specified",
            "middle": "advanced-search__education-item-label_special_secondary",
            "higher": "advanced-search__education-item-label_higher",
        }
        for edu in self.education:
            self._find_by_data_qa_and_click(education_dict[edu])

    def _set_experience(self) -> None:       
        """Задать требуемый опыт работы"""
        experience_dict = {
            "doesnt_matter": "advanced-search__experience-item-label_doesNotMatter",
            "no_experience": "advanced-search__experience-item-label_noExperience",
            "between_1_and_3": "advanced-search__experience-item-label_between1And3",
            "between_3_and_6": "advanced-search__experience-item-label_between3And6",
            "more_than_6": "advanced-search__experience-item-label_moreThan6",
            }
        for exp in self.experience:
            if self.experience[exp] is True:
                self._find_by_data_qa_and_click(experience_dict[exp])
                break

    def _set_job_type(self) -> None:       
        """Задать тип занятости"""  
        job_type_dict = {
            "full_time": "advanced-search__employment-item-label_full",
            "part_time": "advanced-search__employment-item-label_part",
            "project": "advanced-search__employment-item-label_project",
            "volunteering": "advanced-search__employment-item-label_volunteer",
            "internship": "advanced-search__employment-item-label_probation",
            "civil_law_contract": "advanced-search__accept_temporary-item_true",
        }
        for j_t in self.job_type:
            if self.job_type[j_t] is not True:
                continue
            if j_t == "civil_law_contract":
                checkboxes = self.driver.find_elements("class name", "bloko-checkbox__text")
                element = [c for c in checkboxes if "ГПХ" in c.text]
                if len(element) > 0:
                    self.current_position = self._scroll_slow(element[0], self.current_position)
                    element[0].click()
                else:
                    logger.error("Не смогли найти на странице элемент 'Оформление по ГПХ или по совместительству'")
            else:
                self._find_by_data_qa_and_click(job_type_dict[j_t])

    def _set_work_schedule(self) -> None:
        """Задать график работы"""     
        work_schedule_dict = {
            "full_day": "advanced-search__schedule-item-label_fullDay",
            "shift": "advanced-search__schedule-item-label_shift",
            "flexible": "advanced-search__schedule-item-label_flexible",
            "remote": "advanced-search__schedule-item-label_remote",
            "fly_in_fly_out": "advanced-search__schedule-item-label_flyInFlyOut",

        }
        for w_s in self.work_schedule:
            if self.work_schedule[w_s] is True:
                self._find_by_data_qa_and_click(work_schedule_dict[w_s])

    def _set_side_job(self) -> None:
        """Подработка"""
        side_job_dict = {
            "project": "advanced-search__part_time-item-label_employment_project",
            "part": "advanced-search__part_time-item-label_employment_part" ,
            "from_4_hours_per_day": "advanced-search__part_time-item-label_from_four_to_six_hours_in_a_day",
            "weekend": "advanced-search__part_time-item-label_only_saturday_and_sunday",
            "evenings": "advanced-search__part_time-item-label_start_after_sixteen",
        }
        for s_j in self.side_job:
            if self.side_job[s_j] is True:
                self._find_by_data_qa_and_click(side_job_dict[s_j])

    def _set_other_params(self) -> None:
        """Задать другие параметры"""
        other_params_dict = {
            "with_address": "advanced-search__label-item-label_with_address", 
            "accept_handicapped": "advanced-search__label-item-label_accept_handicapped",
            "not_from_agency": "advanced-search__label-item-label_not_from_agency",
            "accept_kids": "advanced-search__label-item-label_accept_kids",
            "accredited_it": "advanced-search__label-item-label_accredited_it",
            "low_performance": "advanced-search__label-item-label_low_performance",
            }
        for o_p in self.other_params:
            if self.other_params[o_p] is True:
                self._find_by_data_qa_and_click(other_params_dict[o_p])

    def _set_sort_by(self) -> None:
        """Сортировка"""
        sort_by_dict = {
            "relevance": "advanced-search__order_by-item-label_relevance",
            "publication_time": "advanced-search__order_by-item-label_publication_time",
            "salary_desc": "advanced-search__order_by-item-label_salary_desc",
            "salary_asc": "advanced-search__order_by-item-label_salary_asc",
            }
        for s_b in self.sort_by:
            if self.sort_by[s_b] is True:
                self._find_by_data_qa_and_click(sort_by_dict[s_b])
                break

    def _set_output_period(self) -> None:    
        """Выводить за"""
        output_period_dict = {
            "all_time": "advanced-search__search_period-item-label_0",
            "month": "advanced-search__search_period-item-label_30",
            "week": "advanced-search__search_period-item-label_7",
            "three_days": "advanced-search__search_period-item-label_3",
            "one_day": "advanced-search__search_period-item-label_1",
            }
        for o_p in self.output_period:
            if self.output_period[o_p] is True:
                self._find_by_data_qa_and_click(output_period_dict[o_p])
                break
        
    def _set_output_size(self) -> None:    
        """Показывать на странице"""
        output_size_dict = {
            "show_20": "advanced-search__items_on_page-item-label_20",
            "show_50": "advanced-search__items_on_page-item-label_50",
            "show_100": "advanced-search__items_on_page-item-label_100",
            }
        for o_s in self.output_size:
            if self.output_size[o_s] is True:
                self._find_by_data_qa_and_click(output_size_dict[o_s])
                break

    def _start_search(self) -> None:
        """Начать поиск"""
        search_button = self.driver.find_element("xpath", "//*[@data-qa='advanced-search-submit-button']")
        search_button.click()

    def _sanitize_text(self, text: str) -> str:
        """Очистить текст вопроса/ответа"""
        sanitized_text = text.lower().strip().replace('"', '').replace('\\', '')
        sanitized_text = re.sub(r'[\x00-\x1F\x7F]', '', sanitized_text).replace('\n', ' ').replace('\r', '').rstrip(',')
        logger.debug(f"Sanitized text: {sanitized_text}")
        return sanitized_text