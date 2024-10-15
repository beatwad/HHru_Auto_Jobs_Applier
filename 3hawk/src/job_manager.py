from typing import List

import json
import os
import random
import time
from itertools import product
from pathlib import Path

from inputimeout import inputimeout, TimeoutOccurred
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

import src.utils as utils
from app_config import MINIMUM_WAIT_TIME
# from src.job import Job
# from src.aihawk_easy_applier import AIHawkEasyApplier
from loguru import logger


class JobManager:
    def __init__(self, driver):
        logger.debug("Инициализация JobManager")
        self.driver = driver
        self.wait = WebDriverWait(driver, 15, poll_frequency=1)
        # self.set_old_answers = set()
        # self.easy_applier_component = None
        logger.debug("JobManager успешно инициализирован")

    def set_parameters(self, parameters):
        logger.debug("Установка параметров JobManager")
        self.keywords = parameters['keywords']
        self.search_only = parameters['search_only']
        self.words_to_exclude = parameters['words_to_exclude']
        self.specialization = parameters['specialization']
        self.industry = parameters['industry']
        self.regions = parameters['regions']
        self.districts = parameters['districts']
        self.subway = parameters['subway']
        self.income = parameters['income']
        self.education = parameters['education']
        self.experience = parameters['experience']
        self.job_type = parameters['job_type']
        self.work_schedule = parameters['work_schedule']
        self.side_job = parameters['side_job']
        self.other_params = parameters['other_params']
        self.sort_by = parameters['sort_by']
        self.output_period = parameters['output_period']
        self.output_size = parameters['output_size']

        self.job_blacklist = parameters.get('title_blacklist', [])
        self.seen_jobs = []
        logger.debug("Параметры успешно установлены")

    @staticmethod
    def _pause(low: int = 1, high: int = 2) -> None:
        """
        Выдержать случайную паузу в диапазоне от 
        low секунд до high секунд
        """
        pause = round(random.uniform(low, high), 1)
        time.sleep(pause)

    def _select_suggestion(self) -> None:
        """
        Функция для поиска и выбора первой подсказки в списке подсказок, 
        появляющихся во время поиска
        """
        suggest_item = ("class name", "suggest__item")
        self.wait.until(EC.element_to_be_clickable(suggest_item))
        suggestion_list = self.driver.find_elements(*suggest_item)
        if len(suggestion_list) > 0:
            suggestion_list[0].click()

    def _find_by_text_and_click(self, text: str) -> None:
        """Функция для поиска элемента по тексту и клика по нему"""
        element = self.driver.find_element("xpath", f'//*[text()="{text}"]')
        self.driver.execute_script("arguments[0].scrollIntoView();", element)
        element.click()

    def _find_by_data_qa_and_click(self, text: str) -> None:
        """Функция для поиска элемента по тексту и клика по нему"""
        element = self.driver.find_element("css selector", f'[data-qa="{text}"]')
        self.driver.execute_script("arguments[0].scrollIntoView();", element)
        element.click()

    def _select_checkbox(self, options: List[str], type="data_qa") -> None:
        """Функция для выбора всех нужных опций в checkbox"""
        for option in options:
            if type == "data_qa":
                self._find_by_data_qa_and_click(option)
            else:
                self._find_by_text_and_click(option)
    
    def set_advance_search_params(self) -> None:
        """Задать дополнительные параметры поиска в hh.ru"""
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

    def _set_key_words(self) -> None:
        """Задать ключевые слова"""
        keywords_element = self.driver.find_element("css selector", '[data-qa="vacancysearch__keywords-input"]')
        keywords_element.send_keys(self.keywords)
        self._select_suggestion()

    def _set_search_only(self) -> None:
        """Искать только"""
        search_only_dict = {
            "vacancy_name": "в названии вакансии", 
            "company_name": "в названии компании", 
            "vacancy_description": "в описании вакансии" 
            }
        for s_o in self.search_only:
            self._find_by_text_and_click(search_only_dict[s_o])

    def _set_words_to_exclude(self) -> None:
        """Исключить слова"""    
        words_to_exclude_element = self.driver.find_element("css selector", '[data-qa="vacancysearch__keywords-excluded-input"]')
        words_to_exclude_element.send_keys(self.words_to_exclude)

    def _set_specialization(self) -> None:   
        """Задать специализацию"""
        # Выбрать меню 'Указать специализации'
        self._find_by_data_qa_and_click("resumesearch__profroles-switcher")
        specialization_item = ("css selector", '[data-qa="bloko-tree-selector-popup-search"]')
        # Ввести специализацию в поисковую строку
        self.wait.until(EC.visibility_of_element_located(specialization_item))
        specialization_element = self.driver.find_element("css selector", '[data-qa="bloko-tree-selector-popup-search"]')
        specialization_element.send_keys(self.specialization)
        self._pause()
        # Попытаться найти специализацию с таким же названием, что и название специализации в переменной
        specialization_list = self.driver.find_elements("xpath", f'//*[text()="{self.specialization}"]')
        # Иначе выбрать первую специализацию в чекбоксе (если есть, иначе закрыть)
        if len(specialization_list) == 0:
            specialization_list = self.driver.find_elements("css selector", '[data-qa^="bloko-tree-selector-item-text bloko-tree-selector-item-text"]')
        if len(specialization_list) > 0:
            self.driver.execute_script("arguments[0].scrollIntoView();", specialization_list[0])
            specialization_list[0].click()
            self.driver.find_element("css selector", '[data-qa="bloko-tree-selector-popup-submit"]').click()
        else:
            self.driver.find_element("css selector", '[data-qa="bloko-modal-close"]').click()

    def _set_industry(self) -> None:   
        """Задать oтрасль компании"""
        # Выбрать меню 'Указать отрасль компании'
        self._find_by_data_qa_and_click("industry-addFromList")
        industry_item = ("css selector", '[data-qa="bloko-tree-selector-popup-search"]')
        # Ввести отрасль в поисковую строку
        self.wait.until(EC.visibility_of_element_located(industry_item))
        industry_element = self.driver.find_element(*industry_item)
        industry_element.clear()
        industry_element.send_keys(self.industry)
        self._pause()
        # Попытаться найти отрасль с таким же названием, что и название отрасли в переменной
        industry_list = self.driver.find_elements("xpath", f'//*[text()="{self.industry}"]')
        # Иначе выбрать первую отрасль в чекбоксе (если есть, иначе закрыть)
        if len(industry_list) == 0:
            industry_list = self.driver.find_elements("css selector", '[data-qa^="bloko-tree-selector-item-text bloko-tree-selector-item-text"]')
        if len(industry_list) > 0:
            self.driver.execute_script("arguments[0].scrollIntoView();", industry_list[0])
            industry_list[0].click()
            self.driver.find_element("css selector", '[data-qa="bloko-tree-selector-popup-submit"]').click()
        else:
            self.driver.find_element("css selector", '[data-qa="bloko-modal-close"]').click()

    def _set_region(self) -> None:   
        """Задать регион"""
        region_element = self.driver.find_element("css selector", '[data-qa="advanced-search-region-add"]')
        for region in self.regions:
            region_element.send_keys(region)
            self._pause()
            self._select_suggestion()

    def _set_district(self) -> None:   
        """Задать район (если есть на странице)"""
        try:
            district_element = self.driver.find_element("css selector", '[data-qa="searchform__district-input"]')
        except NoSuchElementException:
            pass
        else:
            for district in self.districts:
                district_element.send_keys(district)
                self._pause()
                self._select_suggestion()
                
    def _set_subway(self) -> None:   
        """Задать метро (если есть на странице)"""
        try:
            subway_element = self.driver.find_element("css selector", '[data-qa="searchform__subway-input"]')
        except NoSuchElementException:
            pass
        else:
            for station in self.subway:
                subway_element.clear()
                subway_element.send_keys(station)
                self._pause()
                self._select_suggestion()

    def _set_income(self) -> None:   
        """Задать уровень дохода"""
        income_element = self.driver.find_element("css selector", '[data-qa="advanced-search-salary"]')
        income_element.clear()
        income_element.send_keys(self.income)

    def _set_education(self) -> None:   
        """Задать образование"""    
        education = ["higher"]
        education_dict = {
            "not_needed": "advanced-search__education-item-label_not_required_or_not_specified",
            "middle": "advanced-search__education-item-label_special_secondary",
            "higher": "advanced-search__education-item-label_higher",
        }
        for edu in education:
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
        self._find_by_data_qa_and_click(experience_dict[self.experience])

    def _set_job_type(self) -> None:       
        """Задать тип занятости"""  
        job_type = ["full_time"]
        job_type_dict = {
            "full_time": "advanced-search__employment-item-label_full",
            "part_time": "advanced-search__employment-item-label_part",
            "project": "advanced-search__employment-item-label_project",
            "volunteering": "advanced-search__employment-item-label_volunteer",
            "internship": "advanced-search__employment-item-label_probation",
            "civil_law_contract": "Оформление по ГПХ или по совместительству",
        }
        for j_t in job_type:
            if j_t == "civil_law_contract":
                self._find_by_text_and_click(job_type_dict[j_t])
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
            self._find_by_data_qa_and_click(other_params_dict[o_p])

    def _set_sort_by(self) -> None:
        """Сортировка"""
        sort_by_dict = {
            "relevance": "advanced-search__order_by-item-label_relevance",
            "publication_time": "advanced-search__order_by-item-label_publication_time",
            "salary_desc": "advanced-search__order_by-item-label_salary_desc",
            "salary_asc": "advanced-search__order_by-item-label_salary_asc",
            }
        self._find_by_data_qa_and_click(sort_by_dict[self.sort_by])

    def _set_output_period(self) -> None:    
        """Выводить за"""
        output_period_dict = {
            "all_time": "advanced-search__search_period-item-label_0",
            "month": "advanced-search__search_period-item-label_30",
            "week": "advanced-search__search_period-item-label_7",
            "three_days": "advanced-search__search_period-item-label_3",
            "one_day": "advanced-search__search_period-item-label_1",
            }
        self._find_by_data_qa_and_click(output_period_dict[self.output_period])
        
    def _set_output_size(self) -> None:    
        """Показывать на странице"""
        output_size_dict = {
            "show_20": "advanced-search__items_on_page-item-label_20",
            "show_50": "advanced-search__items_on_page-item-label_50",
            "show_100": "advanced-search__items_on_page-item-label_100",
            }
        self._find_by_data_qa_and_click(output_size_dict[self.output_size])
            
    def set_gpt_answerer(self, gpt_answerer):
        pass

    def set_resume_generator_manager(self, resume_generator_manager):
        pass

    def start_applying(self):
        pass

    def get_jobs_from_page(self):
        pass

    def apply_jobs(self):
        pass

    def write_to_file(self, job, file_name):
        pass

    def get_base_search_url(self, parameters):
        pass

    def next_job_page(self, position, location, job_page):
        pass

    def extract_job_information_from_tile(self, job_tile):
        pass


    def is_blacklisted(self, job_title, company, link):
        pass


    def is_already_applied_to_job(self, job_title, company, link):
        pass

    def is_already_applied_to_company(self, company):
        pass
