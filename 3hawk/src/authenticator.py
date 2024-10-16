import random
import time

from selenium.common.exceptions import NoSuchElementException, TimeoutException, NoAlertPresentException, TimeoutException, UnexpectedAlertPresentException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from loguru import logger


class Authenticator:

    def __init__(self, driver=None):
        self.driver = driver
        self.login = None
        logger.debug(f"Аутентификатор проинициализирован драйвером: {driver}")

    def set_parameters(self, parameters) -> None:
        logger.debug("Установка параметров Authenticator")
        self.login = parameters['login']
    
    def start(self) -> bool:
        logger.info("Запускаем Chrome для захода на сайт.")
        if self.is_logged_in():
            logger.info("Пользователь уже вошел на сайт, пропускаем процесс входа.")
            return True
        else:
            logger.info("Пользователь не вошел на сайт. Запускаем процесс входа.")
            return self.handle_login()

    
    def handle_login(self) -> bool:
        """Вход на сайт"""
        logger.info("Заходим на сайт...")
        self.driver.get("https://hh.ru")
        
        # Найти кнопку входа
        try:
            return self.enter_credentials()
        except NoSuchElementException as e:
            logger.error(f"Не можем зайти на сайт - элемент не найден: {e}")
            return False


    def enter_credentials(self) -> bool:
        """Ввод данных пользователя"""
        try:
            logger.debug("Ввод данных пользователя...")
            
            check_interval = 20  # Interval to log the current URL

            self.driver.find_element("css selector", '[data-qa="login"]').click()
            
            login_field = ("name", 'login')
            WebDriverWait(self.driver, 3).until(
                        EC.presence_of_element_located(login_field)
                    )
            self.driver.find_element(*login_field).send_keys(self.login)
            self.driver.find_element("css selector", '[data-qa="account-signup-submit"]').click()
            
            while True:
                vacansies = self.driver.find_elements("css selector", '[data-qa="mainmenu_vacancyResponses"]')
                if len(vacansies) == 0:
                    time.sleep(check_interval)
                    print("Пожалуйста, войдите в аккаунт hh.ru")  # TODO: do we need a print?
                    continue
                else:
                    logger.debug("Вход произведен успешно, переходим на страницу пользователя.")
                    break

        except TimeoutException:
            logger.error("Форма для входа не найдена. Отменяем вход.")
            return False
        
        return True


    def handle_security_check(self) -> None:
        try:
            logger.debug("Handling security check...")
            WebDriverWait(self.driver, 10).until(
                EC.url_contains('https://www.linkedin.com/checkpoint/challengesV2/')
            )
            logger.warning("Security checkpoint detected. Please complete the challenge.")
            WebDriverWait(self.driver, 300).until(
                EC.url_contains('https://www.linkedin.com/feed/')
            )
            logger.info("Security check completed")
        except TimeoutException:
            logger.error("Security check not completed. Please try again later.")


    def is_logged_in(self) -> bool:
        """Проверка того, что пользователь вошел на сайт"""
        try:
            self.driver.get('https://www.hh.ru')
            logger.debug("Проверка того, что пользователь вошел на сайт...")
            
            
            logo = ("class name", 'supernova-logo-wrapper')
            WebDriverWait(self.driver, 3).until(
                EC.presence_of_element_located(logo)
            )

            # Check for the presence of the "Start a post" button
            resume_element = ("css selector", '[data-qa="mainmenu_myResumes"]')
            resumes = self.driver.find_elements(*resume_element)
            if len(resumes) > 0:
                logger.debug(f"Нашли меню 'Мои резюме', пользователь вошел на сайт.")
                return True

            
            profile_element = ("css selector", '[data-qa="mainmenu_applicantProfile"]')
            profiles = self.driver.find_elements(*profile_element)
            if len(profiles) > 0:
                logger.debug(f"Нашли меню профиля, пользователь вошел на сайт.")
                return True

            logger.info("Не нашли меню резюме или профиля, пользователь не вошел на сайт.")
            return False

        except TimeoutException:
            logger.error("Превышен лимит ожидания. Сайт  или нет подключения к интернету.")
            return False